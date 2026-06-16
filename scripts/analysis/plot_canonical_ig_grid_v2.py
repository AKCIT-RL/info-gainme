#!/usr/bin/env python3
"""Canonical per-turn IG trajectories — overlay CoT vs No-CoT in one figure.

Improvements over plot_canonical_ig_grid.py:
- Reads turns.jsonl directly via runs.csv (no cached aggregation), so we can
  filter run_index ∈ {1, 2} as requested.
- Overlays CoT and No-CoT (or Instruct vs. Thinking) in the same panel with
  strong, distinct colors and per-turn SE bands.
- One column per logical seeker / pair; non-CoT-only models still get a panel.
- SE band = s / sqrt(N_cities) where s is the std across per-city means at
  that turn (city = target_id). Per-city mean is itself the mean over the
  ≤2 runs of that city.

Usage:
    python scripts/analysis/plot_canonical_ig_grid_v2.py \\
        --outputs-root outputs --domain geo \\
        --out outputs/plots/canonical_ig_grid_v2.png
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# -------------------- Column layout (logical seeker = one panel) --------------------
# Each column: (display name, list of (seeker_slug, variant_kind, label_for_legend))
# variant_kind ∈ {"cot", "no_cot"} — used to assign color in the panel.
# For Qwen3-30B / Qwen3-4B, Thinking is the CoT variant and Instruct is no-CoT.
COLUMNS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Llama-3.1-8B",            [("Llama-3.1-8B-Instruct",          "no_cot", "Instruct")]),
    ("paprika-Llama-3.1-8B",    [("paprika_Meta-Llama-3.1-8B-Instruct", "no_cot", "paprika")]),
    ("Qwen3-4B",                [("Qwen3-4B-Instruct-2507",         "no_cot", "Instruct"),
                                 ("Qwen3-4B-Thinking-2507",         "cot",    "Thinking")]),
    ("Qwen3-8B",                [("Qwen3-8B",                       "no_cot", "no-CoT"),
                                 ("Qwen3-8B",                       "cot",    "CoT")]),
    ("Qwen3-30B-A3B",           [("Qwen3-30B-A3B-Instruct-2507",    "no_cot", "Instruct"),
                                 ("Qwen3-30B-A3B-Thinking-2507",    "cot",    "Thinking")]),
    ("Nemotron-Cascade-8B",     [("Nemotron-Cascade-8B",            "no_cot", "no-CoT"),
                                 ("Nemotron-Cascade-8B",            "cot",    "CoT")]),
    ("Gemma-4-E4B",             [("google-gemma-4-E4B-it",          "no_cot", "no-CoT"),
                                 ("google-gemma-4-E4B-it",          "cot",    "CoT")]),
    ("Gemma-4-31B",             [("google-gemma-4-31B-it",          "no_cot", "no-CoT"),
                                 ("google-gemma-4-31B-it",          "cot",    "CoT")]),
]

OBS_ROWS = ["FO", "IO", "PO"]
OBS_LABEL = {
    "FO": "Fully Observable\n(FO)",
    "IO": "Initially Observable\n(IO)",
    "PO": "Partially Observable\n(PO)",
}

# Distinct strong colors — same hue family, but enough contrast on white.
COLOR = {
    "cot":    "#1f77b4",   # strong blue
    "no_cot": "#d62728",   # strong red/dark orange
}

OBS_SUFFIX = {
    "FO": "_fo",
    "IO": "_io",
    "PO": "_po",
}


_BASE_SUFFIXES = {
    "_fo_no_cot": ("FO", "no_cot"),
    "_fo_cot":    ("FO", "cot"),
    "_io_no_cot": ("IO", "no_cot"),
    "_io_cot":    ("IO", "cot"),
    "_po_no_cot": ("PO", "no_cot"),
    "_po_cot":    ("PO", "cot"),
}

_EXTRA_SUFFIX = "_with_kickoff"  # preferred over base if present and non-empty
_EXCLUDE_SUBSTR = ("_with_prior", "_ont")  # never use these (different ablation)


def _classify_exp(name: str) -> tuple[str, str, bool] | None:
    """Return (obs, variant, is_kickoff) for a canonical experiment, else None.

    Canonical = ends in one of the BASE_SUFFIXES, optionally followed by
    _with_kickoff. Excludes _with_prior and _ont (different ablations).
    """
    n = name.lower()
    if any(s in n for s in _EXCLUDE_SUBSTR):
        return None
    # Strip _with_kickoff if present
    base = n
    is_kickoff = False
    if base.endswith(_EXTRA_SUFFIX):
        base = base[: -len(_EXTRA_SUFFIX)]
        is_kickoff = True
    for suf, (obs, variant) in _BASE_SUFFIXES.items():
        if base.endswith(suf):
            return obs, variant, is_kickoff
    return None


def _iter_canonical_experiments(
    outputs_root: Path,
    seeker_slug: str,
    oracle: str,
    domain: str,
) -> Iterable[tuple[Path, str, str]]:
    """Yield (exp_dir, obs, variant) for the canonical configs of this seeker+domain.

    Precedence: if both `<exp>` and `<exp>_with_kickoff` exist, prefer the
    `_with_kickoff` version (replacement run). This matches the table pipeline.
    """
    triple = outputs_root / "models" / f"s_{seeker_slug}__o_{oracle}__p_{oracle}"
    if not triple.is_dir():
        return

    # Bucket experiments by (obs, variant). For each bucket, pick kickoff if available.
    buckets: dict[tuple[str, str], list[tuple[Path, bool]]] = {}
    for exp_dir in sorted(triple.iterdir()):
        if not exp_dir.is_dir():
            continue
        if not exp_dir.name.lower().startswith(domain.lower()):
            continue
        kind = _classify_exp(exp_dir.name)
        if kind is None:
            continue
        obs, variant, is_kickoff = kind
        # Skip empty experiments (only header in runs.csv)
        runs_csv = exp_dir / "runs.csv"
        if not runs_csv.exists():
            continue
        try:
            with runs_csv.open() as f:
                row_count = sum(1 for _ in f) - 1  # exclude header
        except Exception:
            row_count = 0
        if row_count <= 0:
            continue
        buckets.setdefault((obs, variant), []).append((exp_dir, is_kickoff))

    for (obs, variant), candidates in buckets.items():
        # Prefer _with_kickoff if any candidate has it
        kickoff_cands = [c for c in candidates if c[1]]
        chosen = kickoff_cands[0] if kickoff_cands else candidates[0]
        yield chosen[0], obs, variant


def _aggregate_from_city_metrics(exp_dir: Path) -> list[dict]:
    """Fallback: read city_metrics_by_turn/*.jsonl when turns.jsonl are unavailable.

    Each file has lines: {turn_index, mean_info_gain, variance_info_gain, num_runs}.
    Returns list of dicts {turn_index, mean, sem, n_cities}.
    """
    metrics_dir = exp_dir / "city_metrics_by_turn"
    if not metrics_dir.is_dir():
        return []

    turn_to_city_means: dict[int, list[float]] = defaultdict(list)
    for jsonl_path in sorted(metrics_dir.glob("*.jsonl")):
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ti = rec.get("turn_index")
                ig = rec.get("mean_info_gain")
                if ti is None or ig is None:
                    continue
                turn_to_city_means[ti].append(float(ig))

    out = []
    for ti in sorted(turn_to_city_means.keys()):
        vals = turn_to_city_means[ti]
        n = len(vals)
        if n == 0:
            continue
        m = float(np.mean(vals))
        s = float(np.std(vals, ddof=1)) if n > 1 else 0.0
        sem = s / math.sqrt(n) if n > 1 else 0.0
        out.append({"turn_index": ti, "mean": m, "sem": sem, "n_cities": n})
    return out


def _aggregate_one_exp(
    exp_dir: Path,
    outputs_root: Path,
    runs_filter: set[int],
) -> list[dict]:
    """Read turns.jsonl for run_index ∈ runs_filter, return per-turn aggregate.

    Falls back to city_metrics_by_turn/ when turns.jsonl are not available
    (e.g. conversations are zipped).
    Returns list of dicts {turn_index, mean, sem, n_cities}.
    """
    runs_csv = exp_dir / "runs.csv"
    if not runs_csv.exists():
        return []

    # city_id -> turn_index -> list of info_gain values (one per run)
    per_city: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

    with runs_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                run_idx = int(row["run_index"])
            except (KeyError, ValueError, TypeError):
                continue
            if run_idx not in runs_filter:
                continue
            target_id = row.get("target_id")
            conv_path = row.get("conversation_path")
            if not target_id or not conv_path:
                continue
            turns_path = outputs_root / conv_path / "turns.jsonl"
            if not turns_path.exists():
                turns_path = Path(conv_path) / "turns.jsonl"
                if not turns_path.exists():
                    continue
            with turns_path.open("r", encoding="utf-8") as tf:
                for line in tf:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ti = rec.get("turn_index")
                    ig = rec.get("info_gain")
                    if ti is None or ig is None:
                        continue
                    per_city[target_id][ti].append(float(ig))

    # Prefer pre-aggregated city metrics when available and more complete
    metrics = _aggregate_from_city_metrics(exp_dir)
    if metrics and (not per_city or metrics[0]["n_cities"] > len(per_city)):
        return metrics

    if not per_city:
        return []

    # Per (city, turn): mean over the (≤2) runs of that city
    # Per turn across cities: mean + sample std + SE = std / sqrt(n_cities)
    turn_to_city_means: dict[int, list[float]] = defaultdict(list)
    for city, turns in per_city.items():
        for ti, gains in turns.items():
            if gains:
                turn_to_city_means[ti].append(sum(gains) / len(gains))

    out = []
    for ti in sorted(turn_to_city_means.keys()):
        vals = turn_to_city_means[ti]
        n = len(vals)
        if n == 0:
            continue
        m = float(np.mean(vals))
        s = float(np.std(vals, ddof=1)) if n > 1 else 0.0
        sem = s / math.sqrt(n) if n > 1 else 0.0
        out.append({"turn_index": ti, "mean": m, "sem": sem, "n_cities": n})
    return out


def _collect(
    outputs_root: Path,
    oracle: str,
    domain: str,
    runs_filter: set[int],
) -> dict[str, dict[str, dict[str, list[dict]]]]:
    """display_name -> obs -> variant -> aggregate (or {} if missing)."""
    out: dict[str, dict[str, dict[str, list[dict]]]] = {}
    for display, members in COLUMNS:
        out[display] = {obs: {} for obs in OBS_ROWS}
        for slug, variant_kind, _legend in members:
            for exp_dir, obs, variant in _iter_canonical_experiments(
                outputs_root, slug, oracle, domain
            ):
                # Only keep configs that match the declared variant for this slug.
                if variant != variant_kind:
                    continue
                agg = _aggregate_one_exp(exp_dir, outputs_root, runs_filter)
                if agg:
                    out[display][obs][variant_kind] = agg
                    print(f"  ✓ {display:25s} {obs} {variant_kind:7s} "
                          f"{exp_dir.name:50s} n_cities@t1={agg[0]['n_cities']}")
    return out


def _plot_panel(ax, panel_data: dict[str, list[dict]],
                title: str, ylabel: bool, legend_kinds: dict[str, str]):
    """panel_data: variant_kind -> aggregate list."""
    if not panel_data:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, fontsize=11, color="gray")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xticks([]); ax.set_yticks([])
        return

    # Plot no_cot first (so cot draws on top)
    order = ["no_cot", "cot"]
    for kind in order:
        if kind not in panel_data:
            continue
        data = panel_data[kind]
        turns = [d["turn_index"] for d in data]
        mean = np.array([d["mean"] for d in data])
        sem = np.array([d["sem"] for d in data])
        color = COLOR[kind]
        label = legend_kinds[kind]
        ax.plot(turns, mean, color=color, linewidth=2.0, marker="o",
                markersize=3.2, alpha=0.95, label=label)
        ax.fill_between(turns, mean - sem, mean + sem,
                        color=color, alpha=0.18, linewidth=0)

    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.tick_params(axis="both", which="major", labelsize=8)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outputs-root", type=Path, default=Path("outputs"))
    ap.add_argument("--out", type=Path,
                    default=Path("outputs/plots/canonical_ig_grid_v2.png"))
    ap.add_argument("--oracle", default="Qwen3-8B")
    ap.add_argument("--domain", default="geo")
    ap.add_argument("--runs", default="1,2",
                    help="Comma-separated run_index values to include (default: 1,2)")
    args = ap.parse_args()

    runs_filter = {int(r.strip()) for r in args.runs.split(",") if r.strip()}
    print(f"📥 Filtering runs: {sorted(runs_filter)}")
    print(f"📥 Domain: {args.domain}, Oracle/Pruner: {args.oracle}")

    print("\n🔎 Collecting data...")
    data = _collect(args.outputs_root, args.oracle, args.domain, runs_filter)

    # Drop columns with no data in any row
    cols = [(d, members) for d, members in COLUMNS
            if any(data[d][obs] for obs in OBS_ROWS)]
    if not cols:
        print("❌ No data — bailing.")
        return 1

    ncol = len(cols)
    nrow = len(OBS_ROWS)
    print(f"\n📐 Grid: {nrow} rows × {ncol} cols")

    fig, axes = plt.subplots(nrow, ncol, figsize=(2.5 * ncol, 3.0 * nrow),
                             squeeze=False, sharey="row")

    # Build legend label map per column (Thinking/Instruct vs CoT/no-CoT)
    legend_per_col: list[dict[str, str]] = []
    for _display, members in cols:
        lm: dict[str, str] = {}
        for _slug, kind, label in members:
            lm[kind] = label
        legend_per_col.append(lm)

    for r, obs in enumerate(OBS_ROWS):
        for c, (display, _members) in enumerate(cols):
            _plot_panel(axes[r][c], data[display][obs],
                        title=display, ylabel=(c == 0),
                        legend_kinds=legend_per_col[c])

    # Row labels on the left
    for r, obs in enumerate(OBS_ROWS):
        y = 1.0 - (r + 0.5) / nrow
        y = 0.08 + y * (0.96 - 0.08)
        fig.text(0.005, y, OBS_LABEL[obs], rotation=90, fontsize=13,
                 fontweight="bold", ha="center", va="center")

    # Common labels
    fig.supxlabel("Turn", fontsize=12, fontweight="bold", y=0.04)
    fig.supylabel("Average Information Gain (bits)", fontsize=12,
                  fontweight="bold", x=0.025)

    # Legend (uses generic CoT / No-CoT labels)
    handles = [
        plt.Line2D([0], [0], color=COLOR["no_cot"], lw=2, marker="o", markersize=5,
                   label="No CoT (or Instruct)"),
        plt.Line2D([0], [0], color=COLOR["cot"], lw=2, marker="o", markersize=5,
                   label="CoT (or Thinking)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=11,
               frameon=True, bbox_to_anchor=(0.5, -0.005))

    # Per-column legends: small text under each column's bottom panel if both variants exist
    for c, (display, _) in enumerate(cols):
        # Find what's in the bottom row for this column
        lm = legend_per_col[c]
        items = []
        for kind in ("no_cot", "cot"):
            if kind in lm:
                items.append(f"{kind.replace('no_cot','no-CoT').replace('cot','CoT')}={lm[kind]}")
        # Skip annotation if labels are just "no-CoT" / "CoT" / "Instruct" already in legend

    plt.tight_layout(rect=[0.03, 0.06, 1, 0.98])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=160, bbox_inches="tight")
    print(f"\n✅ Saved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
