#!/usr/bin/env python3
"""Grid 2×11 de Information Gain por turno dos 11 seekers canonicals.

Linhas: FO (cima) / PO (baixo). Colunas: 1 por seeker canonical, na ordem
fixada abaixo. Dentro de cada painel: 1 linha por variante (CoT / No-CoT)
com banda de erro padrão (SE = sqrt(var)/sqrt(n)).

Só considera o triple s_<seeker>__o_<oracle>__p_<pruner> com oracle ==
--oracle (default Qwen3-8B) e experimentos do domínio --domain (default geo).

Se o aggregated_ig_over_time.jsonl de um experimento não existir, gera na
hora via aggregate_metrics_by_city + aggregate_ig_over_time (reuso, CPU).

Uso:
    python3 scripts/analysis/plot_canonical_ig_grid.py \
        --outputs-root outputs --out outputs/plots/canonical_ig_grid.png
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))                       # imports irmãos
sys.path.insert(0, str(_SCRIPT_DIR.parent.parent))         # project root

from aggregate_metrics_by_city import (  # noqa: E402
    aggregate_metrics_by_city,
    find_outputs_base_dir,
)
from aggregate_ig_over_time import aggregate_ig_over_time  # noqa: E402
from plot_aggregated_ig import load_aggregated_data        # noqa: E402

# (slug do dir, nome curto pro título) — ordem = ordem das colunas.
CANONICAL: list[tuple[str, str]] = [
    ("Llama-3.1-8B-Instruct", "Llama-3.1-8B-Instruct"),
    ("Nemotron-Cascade-8B", "Nemotron-Cascade-8B"),
    ("Qwen3-0.6B", "Qwen3-0.6B"),
    ("Qwen3-30B-A3B-Instruct-2507", "Qwen3-30B-Instruct"),
    ("Qwen3-30B-A3B-Thinking-2507", "Qwen3-30B-Thinking"),
    ("Qwen3-4B-Instruct-2507", "Qwen3-4B-Instruct"),
    ("Qwen3-4B-Thinking-2507", "Qwen3-4B-Thinking"),
    ("Qwen3-8B", "Qwen3-8B"),
    ("google-gemma-4-31B-it", "gemma-4-31B-it"),
    ("google-gemma-4-E4B-it", "gemma-4-E4B-it"),
    ("paprika_Meta-Llama-3.1-8B-Instruct", "paprika-Llama-3.1-8B"),
]

COLOR_COT = "#1f77b4"
COLOR_NO_COT = "#aec7e8"


def _classify(exp_name: str) -> tuple[str, bool] | None:
    """(obs, is_cot) só pro config CANÔNICO.

    Casa apenas o sufixo exato — exclui variantes não-canônicas
    (_with_prior, _with_kickoff, _ont, …) e o modo _io_, que não devem
    aparecer nesse gráfico (senão viram linhas duplicadas no painel).
    """
    e = exp_name.lower()
    if e.endswith("_fo_no_cot"):
        return "FO", False
    if e.endswith("_fo_cot"):
        return "FO", True
    if e.endswith("_po_no_cot"):
        return "PO", False
    if e.endswith("_po_cot"):
        return "PO", True
    return None


def _ensure_aggregated(exp_dir: Path, force: bool) -> Path | None:
    """Garante exp_dir/aggregated_ig_over_time.jsonl. Retorna o path ou None."""
    agg = exp_dir / "aggregated_ig_over_time.jsonl"
    if agg.exists() and not force:
        return agg
    runs_csv = exp_dir / "runs.csv"
    if not runs_csv.exists():
        return None
    city_dir = exp_dir / "city_metrics_by_turn"
    try:
        base = find_outputs_base_dir(runs_csv)
        aggregate_metrics_by_city(runs_csv, city_dir, base)
        aggregate_ig_over_time(city_dir, agg)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️  agregação falhou em {exp_dir.name}: {e}")
        return None
    return agg if agg.exists() else None


def _collect(outputs_root: Path, oracle: str, domain: str, force: bool):
    """seeker_slug -> 'FO'/'PO' -> list[(is_cot, data)]."""
    models_root = outputs_root / "models"
    out: dict[str, dict[str, list[tuple[bool, list[dict[str, Any]]]]]] = {
        slug: {"FO": [], "PO": []} for slug, _ in CANONICAL
    }
    for slug, _ in CANONICAL:
        triple = models_root / f"s_{slug}__o_{oracle}__p_{oracle}"
        if not triple.is_dir():
            print(f"… sem triple: {triple.name}")
            continue
        for exp_dir in sorted(p for p in triple.iterdir() if p.is_dir()):
            if not exp_dir.name.lower().startswith(domain.lower()):
                continue
            kind = _classify(exp_dir.name)
            if kind is None:
                continue
            obs, is_cot = kind
            agg = _ensure_aggregated(exp_dir, force)
            if agg is None:
                continue
            data = load_aggregated_data(agg)
            if data:
                out[slug][obs].append((is_cot, data))
    return out


def _plot_panel(ax, lines, title, ylabel):
    if not lines:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, fontsize=12)
        ax.set_title(title, fontsize=12, fontweight="bold")
        return
    for is_cot, data in sorted(lines, key=lambda t: not t[0]):  # CoT primeiro
        turns = [d["turn_index"] for d in data]
        mean = [d["mean_info_gain"] for d in data]
        var = [d["variance_info_gain"] for d in data]
        n = [d.get("num_cities", d.get("num_runs", 0)) for d in data]
        se = [math.sqrt(v) / math.sqrt(c) if c > 0 and v > 0 else 0.0
              for v, c in zip(var, n)]
        color = COLOR_COT if is_cot else COLOR_NO_COT
        ax.plot(turns, mean, color=color, linewidth=2, marker="o",
                markersize=3, alpha=0.85,
                label="CoT" if is_cot else "No CoT")
        ax.fill_between(turns,
                        [m - s for m, s in zip(mean, se)],
                        [m + s for m, s in zip(mean, se)],
                        color=color, alpha=0.2, linewidth=0)
    ax.set_xlabel("Turn", fontsize=11, fontweight="bold")
    if ylabel:
        ax.set_ylabel("Average Information Gain", fontsize=12, fontweight="bold")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.tick_params(axis="both", which="major", labelsize=9)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outputs-root", type=Path, default=Path("outputs"))
    ap.add_argument("--out", type=Path,
                    default=Path("outputs/plots/canonical_ig_grid.png"))
    ap.add_argument("--oracle", default="Qwen3-8B")
    ap.add_argument("--domain", default="geo")
    ap.add_argument("--force", action="store_true",
                    help="Re-agrega mesmo se aggregated_ig_over_time.jsonl existir.")
    args = ap.parse_args()

    collected = _collect(args.outputs_root, args.oracle, args.domain, args.force)

    ncol = len(CANONICAL)
    fig, axes = plt.subplots(2, ncol, figsize=(3.0 * ncol, 8.0), squeeze=False)
    for col, (slug, disp) in enumerate(CANONICAL):
        _plot_panel(axes[0][col], collected[slug]["FO"], disp, ylabel=(col == 0))
        _plot_panel(axes[1][col], collected[slug]["PO"], disp, ylabel=(col == 0))

    fig.text(0.008, 0.74, "Fully Observable\n(FO)", rotation=90, fontsize=14,
             fontweight="bold", ha="center", va="center")
    fig.text(0.008, 0.30, "Partially Observable\n(PO)", rotation=90, fontsize=14,
             fontweight="bold", ha="center", va="center")

    handles = [
        plt.Line2D([0], [0], color=COLOR_COT, lw=2, marker="o", markersize=5),
        plt.Line2D([0], [0], color=COLOR_NO_COT, lw=2, marker="o", markersize=5),
    ]
    fig.legend(handles, ["CoT", "No CoT"], loc="lower center",
               ncol=2, fontsize=12, frameon=True)

    plt.tight_layout(rect=[0.02, 0.06, 1, 0.99])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150, bbox_inches="tight")
    print(f"✅ salvo: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
