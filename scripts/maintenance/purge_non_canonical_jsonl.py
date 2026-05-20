#!/usr/bin/env python3
"""Purga linhas de JSONLs cujo triple s_<seeker>__o_<oracle>__p_<pruner>
fica fora da whitelist canônica (seeker ∈ --seekers, oracle == --oracle).

Funciona pros JSONLs agregados de classify (chave `turns_path`) e de
traces (chave `seeker_path`). A chave é auto-detectada se não passar
`--field`.

Por default é DRY-RUN: imprime contagens (mantidos/removidos por motivo)
e não altera nada. Passe `--apply` pra gravar: salva backup em
`<arquivo>.bak`, escreve `<arquivo>.tmp` e renomeia atomicamente.

Uso:
    python3 scripts/maintenance/purge_non_canonical_jsonl.py \\
        --jsonl outputs/question_classifications_gemma.jsonl
    # … inspecionar o relatório, então:
    python3 scripts/maintenance/purge_non_canonical_jsonl.py \\
        --jsonl outputs/question_classifications_gemma.jsonl --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path


CANONICAL_SEEKERS = [
    "Llama-3.1-8B-Instruct",
    "Nemotron-Cascade-8B",
    "Qwen3-0.6B",
    "Qwen3-30B-A3B-Instruct-2507",
    "Qwen3-30B-A3B-Thinking-2507",
    "Qwen3-4B-Instruct-2507",
    "Qwen3-4B-Thinking-2507",
    "Qwen3-8B",
    "google/gemma-4-31B-it",
    "google/gemma-4-E4B-it",
    "paprika_Meta-Llama-3.1-8B-Instruct",
]


def _slug(name: str) -> str:
    return name.replace("/", "-")


def _triple_parts(dir_name: str):
    if not dir_name.startswith("s_"):
        return None
    rest = dir_name[2:]
    if "__o_" not in rest or "__p_" not in rest:
        return None
    seeker, rest2 = rest.split("__o_", 1)
    oracle, pruner = rest2.split("__p_", 1)
    return seeker, oracle, pruner


def _triple_from_path(p: str) -> tuple[str, str, str] | None:
    """Extrai (seeker, oracle, pruner) de um path tipo
    outputs/models/<triple>/<exp>/conversations/<target>_runNN/<file>.
    """
    parts = Path(p).parts
    try:
        i = parts.index("models")
    except ValueError:
        return None
    if i + 1 >= len(parts):
        return None
    return _triple_parts(parts[i + 1])


def _detect_field(first_rec: dict) -> str:
    for k in ("turns_path", "seeker_path", "conversation_path"):
        if k in first_rec and isinstance(first_rec[k], str):
            return k
    raise SystemExit(
        f"Não consegui detectar a chave do path no JSONL "
        f"(esperado turns_path/seeker_path/conversation_path). "
        f"Chaves vistas: {sorted(first_rec.keys())[:10]}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, required=True)
    ap.add_argument("--field", default=None,
                    help="Chave que contém o path (turns_path/seeker_path). "
                         "Auto-detecta se omitido.")
    ap.add_argument("--seekers", default=",".join(CANONICAL_SEEKERS),
                    help="Whitelist de seekers (vírgula). '/' é slugificado p/ '-' "
                         "pra casar com o dir.")
    ap.add_argument("--oracle", default="Qwen3-8B",
                    help="Oracle exigido (segmento exato).")
    ap.add_argument("--apply", action="store_true",
                    help="Aplica de fato (cria .bak e sobrescreve). "
                         "Sem isso é dry-run.")
    args = ap.parse_args()

    seekers_set = {_slug(s.strip()) for s in args.seekers.split(",") if s.strip()}
    oracle = _slug(args.oracle.strip())

    if not args.jsonl.exists():
        raise SystemExit(f"Arquivo não existe: {args.jsonl}")

    # Detecta chave do path na 1ª linha parseável
    field = args.field
    if field is None:
        with args.jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                field = _detect_field(rec)
                break
        if field is None:
            raise SystemExit("JSONL vazio ou sem linhas parseáveis.")
    print(f"📋 chave do path: {field}")
    print(f"🎯 seekers ({len(seekers_set)}): {sorted(seekers_set)}")
    print(f"🎯 oracle: {oracle}")
    print()

    kept_lines: list[str] = []
    counts: Counter[str] = Counter()
    reason_examples: dict[str, str] = {}

    with args.jsonl.open(encoding="utf-8") as fh:
        for raw in fh:
            s = raw.rstrip("\n")
            if not s.strip():
                continue
            counts["raw_lines"] += 1
            try:
                rec = json.loads(s)
            except Exception:  # noqa: BLE001
                counts["parse_fail"] += 1
                reason_examples.setdefault("parse_fail", s[:120])
                continue
            path = rec.get(field)
            if not isinstance(path, str) or not path:
                counts["missing_path"] += 1
                continue
            triple = _triple_from_path(path)
            if triple is None:
                counts["unparsable_triple"] += 1
                reason_examples.setdefault("unparsable_triple", path)
                continue
            seeker, ora, _ = triple
            if seeker not in seekers_set:
                counts["wrong_seeker"] += 1
                reason_examples.setdefault(f"wrong_seeker:{seeker}", path)
                continue
            if ora != oracle:
                counts["wrong_oracle"] += 1
                reason_examples.setdefault(f"wrong_oracle:{ora}", path)
                continue
            counts["kept"] += 1
            kept_lines.append(s)

    print(f"linhas brutas:     {counts['raw_lines']}")
    print(f"  parse_fail:        {counts['parse_fail']}")
    print(f"  missing_path:      {counts['missing_path']}")
    print(f"  unparsable_triple: {counts['unparsable_triple']}")
    print(f"  wrong_seeker:      {counts['wrong_seeker']}")
    print(f"  wrong_oracle:      {counts['wrong_oracle']}")
    print(f"  KEPT:              {counts['kept']}")
    drop = (counts['raw_lines'] - counts['kept'])
    print(f"  → removidas:        {drop}")
    if reason_examples:
        print("\nExemplos por motivo:")
        for k, v in sorted(reason_examples.items())[:20]:
            print(f"  [{k}] {v}")

    if not args.apply:
        print(f"\n🔎 DRY-RUN (nada foi escrito). Use --apply pra aplicar.")
        return 0

    if counts["kept"] == counts["raw_lines"]:
        print("\n✅ Nada a remover; arquivo já está limpo.")
        return 0

    bak = args.jsonl.with_suffix(args.jsonl.suffix + ".bak")
    tmp = args.jsonl.with_suffix(args.jsonl.suffix + ".tmp")
    if bak.exists():
        print(f"⚠️  backup já existia, sobrescrevendo: {bak.name}")
    shutil.copy2(args.jsonl, bak)
    with tmp.open("w", encoding="utf-8") as fh:
        for s in kept_lines:
            fh.write(s + "\n")
    tmp.replace(args.jsonl)
    print(f"\n✅ aplicado.")
    print(f"   backup:    {bak}")
    print(f"   arquivo:   {args.jsonl}  ({counts['kept']} linhas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
