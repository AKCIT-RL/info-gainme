#!/usr/bin/env python3
"""Apaga conversas PO sem kickoff (e remove linhas correspondentes em runs.csv)
pra que o BenchmarkRunner reexecute via resume.

Critério: conversa PO cujo `seeker.json:history[1].role == "assistant"` (sem o
"Start the game" do kickoff). Apenas experimentos cujos triples+exp constam em
configs/full/**/*.yaml (canonicals) são considerados — Olmo e afins ficam de fora.

Uso:
    python3 scripts/maintenance/delete_no_kickoff_po_runs.py            # dry-run
    python3 scripts/maintenance/delete_no_kickoff_po_runs.py --apply    # executa
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = PROJECT_ROOT / "outputs" / "models"
CONFIGS_FULL = PROJECT_ROOT / "configs" / "full"


def conv_name_from_row(target_id: str, run_index: str | int) -> str:
    """target_id usa ':' e run_index é int; conv dir troca ':' por '-' e zera-pad em 2 dígitos."""
    return f"{target_id.replace(':', '-')}_run{int(run_index):02d}"


def canonical_pairs() -> set[tuple[str, str]]:
    """(triple, experiment_name) pairs presentes em configs/full/."""
    pairs = set()
    for yml in CONFIGS_FULL.rglob("*.yaml"):
        cfg = yaml.safe_load(yml.read_text())
        m = cfg["models"]
        triple = (
            f"s_{m['seeker']['model'].replace('/', '-')}__"
            f"o_{m['oracle']['model'].replace('/', '-')}__"
            f"p_{m['pruner']['model'].replace('/', '-')}"
        )
        exp = cfg["experiment"]["name"]
        pairs.add((triple, exp))
    return pairs


def is_no_kickoff(seeker_json: Path) -> bool | None:
    """True se a conv NÃO tem kickoff (history[1].role == 'assistant').
    None se não der pra ler."""
    try:
        d = json.loads(seeker_json.read_text())
        hist = d.get("history") or []
        if len(hist) < 2:
            return None
        return hist[1].get("role") == "assistant"
    except Exception:
        return None


def collect_targets() -> dict[tuple[str, str], list[str]]:
    """{(triple, exp) -> [conv_name, ...]} das conversas PO sem kickoff em canonicals."""
    canon = canonical_pairs()
    work = []  # (triple, exp, conv_name, seeker_json_path)
    for triple_dir in OUTPUTS.iterdir():
        if not triple_dir.is_dir():
            continue
        for exp_dir in triple_dir.iterdir():
            if not exp_dir.is_dir():
                continue
            if (triple_dir.name, exp_dir.name) not in canon:
                continue
            if "_po_" not in exp_dir.name:
                continue
            convs_root = exp_dir / "conversations"
            if not convs_root.exists():
                continue
            for conv_dir in convs_root.iterdir():
                seeker = conv_dir / "seeker.json"
                if conv_dir.is_dir() and seeker.exists():
                    work.append((triple_dir.name, exp_dir.name, conv_dir.name, seeker))

    targets: dict[tuple[str, str], list[str]] = {}
    with ThreadPoolExecutor(max_workers=32) as ex:
        futs = {ex.submit(is_no_kickoff, w[3]): w for w in work}
        for f in as_completed(futs):
            triple, exp, conv, _ = futs[f]
            if f.result() is True:
                targets.setdefault((triple, exp), []).append(conv)
    return targets


def runs_csv_drop_rows(csv_path: Path, conv_names: set[str], apply: bool) -> tuple[int, int]:
    """Remove de runs.csv as linhas cuja conv derivada (target_id+run_index) está em conv_names.
    Retorna (linhas_antes, linhas_depois)."""
    if not csv_path.exists():
        return (0, 0)
    rows = list(csv.DictReader(csv_path.open()))
    fieldnames = list(rows[0].keys()) if rows else []
    keep = [
        r for r in rows
        if conv_name_from_row(r.get("target_id", ""), r.get("run_index", "-1")) not in conv_names
    ]
    if apply and len(keep) != len(rows):
        backup = csv_path.with_suffix(".csv.bak_no_kickoff")
        try:
            if backup.exists():
                backup.unlink()
            shutil.copy2(csv_path, backup)
        except PermissionError:
            # Backup é só audit-trail — se outro usuário travou o .bak, segue sem ele.
            print(f"  (warn) backup skipped: {backup} (permission denied)")
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(keep)
    return (len(rows), len(keep))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="executa de verdade (default: dry-run)")
    args = ap.parse_args()

    print(f"Project root: {PROJECT_ROOT}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN (nada será apagado)'}\n")

    targets = collect_targets()
    if not targets:
        print("Nada a apagar.")
        return

    total_convs = sum(len(v) for v in targets.values())
    print(f"Experimentos PO canônicos afetados: {len(targets)}")
    print(f"Conversas sem kickoff a apagar:     {total_convs}\n")

    for (triple, exp), convs in sorted(targets.items()):
        exp_dir = OUTPUTS / triple / exp
        csv_path = exp_dir / "runs.csv"
        before, after = runs_csv_drop_rows(csv_path, set(convs), args.apply)
        print(f"  [{len(convs):>4} convs] {triple}/{exp}")
        print(f"           runs.csv: {before} -> {after} linhas")
        if args.apply:
            for c in convs:
                shutil.rmtree(exp_dir / "conversations" / c, ignore_errors=True)

    print("\nPronto." if args.apply else "\nDry-run — re-rodar com --apply pra executar.")


if __name__ == "__main__":
    main()
