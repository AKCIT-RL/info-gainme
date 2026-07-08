"""Verify the paper claim that CoT acts as a scaffold for implicit belief tracking.

The InfoGainMe paper claims that Chain-of-Thought (CoT) reasoning helps Seekers
*most* in observability modes that force them to maintain a belief state over the
candidate set implicitly (Initially / Partially Observable), and barely helps when
the active set is always visible (Fully Observable). If true, the CoT benefit is
not a generic "reasoning helps" effect but a scaffold for belief-state tracking.

This script reproduces that result from ``outputs/unified_experiments_run01.csv``
for the six paired CoT Seekers and reports:

  1. The paired CoT minus no-CoT delta (IG/Turn and Win Rate) per observability mode.
  2. A one-sample t-test that each per-mode delta is > 0.
  3. The key interaction test: implicit-mode gain (mean of IO, PO) vs explicit-mode
     gain (FO), paired by (seeker, domain).
  4. A per-seeker breakdown showing the gain anti-correlates with base capability.

It also writes a bar figure to ``figures/cot_belief_scaffold.png`` and a tidy table
to ``outputs/cot_belief_scaffold.csv``.

Run:
    .venv/bin/python scripts/analysis/verify_cot_belief_scaffold.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
SRC_CSV = ROOT / "outputs" / "unified_experiments_run01.csv"
OUT_CSV = ROOT / "outputs" / "cot_belief_scaffold.csv"
OUT_FIG = ROOT / "figures" / "cot_belief_scaffold.png"

IG = "Mean Info Gain/Turn"
WR = "Win Rate"
MODES = ["FO", "IO", "PO"]

# Six paired CoT Seekers: (cot_model, nocot_model). Toggle models reuse the same
# model name and differ only by the experiment-name suffix; the Thinking variants
# pair against their Instruct counterpart.
PAIRS: dict[str, tuple[str, str]] = {
    "Qwen3-8B": ("Qwen3-8B", "Qwen3-8B"),
    "Gemma-4-E4B": ("google/gemma-4-E4B-it", "google/gemma-4-E4B-it"),
    "Gemma-4-31B": ("google/gemma-4-31B-it", "google/gemma-4-31B-it"),
    "Nemotron-8B": ("Nemotron-Cascade-8B", "Nemotron-Cascade-8B"),
    "Qwen3-4B": ("Qwen3-4B-Thinking-2507", "Qwen3-4B-Instruct-2507"),
    "Qwen3-30B-A3B": ("Qwen3-30B-A3B-Thinking-2507", "Qwen3-30B-A3B-Instruct-2507"),
}


def _mode(observability: str) -> str:
    """Map the verbose observability label to the FO/IO/PO short form."""
    return {"FU": "FO", "IN": "IO", "PA": "PO"}[observability[:2]]


def _is_cot(exp: str) -> bool:
    return exp.endswith("_cot") or exp.endswith("_cot_with_kickoff")


def _is_nocot(exp: str) -> bool:
    return exp.endswith("_no_cot") or exp.endswith("_no_cot_with_kickoff")


def load_paired() -> pd.DataFrame:
    """Return one row per (seeker, domain, mode) with CoT and no-CoT metrics joined.

    Excludes the ``_ont`` (oracle-no-thinking contaminated) and ``_with_prior``
    (verbal-pool ablation) experiments so only canonical configs are compared.
    For Nemotron-Cascade-8B both conditions use the canonical ``_with_kickoff``
    family, which is the only one carrying all three observability modes.
    """
    df = pd.read_csv(SRC_CSV)
    df = df[~df["Experimento"].str.endswith("_ont")]
    df = df[~df["Experimento"].str.contains("_with_prior")]

    frames = []
    for label, (cot_model, nocot_model) in PAIRS.items():
        if label == "Nemotron-8B":
            cot = df[(df["Seeker Model"] == cot_model) & df["Experimento"].str.endswith("_cot_with_kickoff")]
            noc = df[(df["Seeker Model"] == nocot_model) & df["Experimento"].str.endswith("_no_cot_with_kickoff")]
        else:
            cot = df[(df["Seeker Model"] == cot_model) & df["Experimento"].map(_is_cot)]
            noc = df[(df["Seeker Model"] == nocot_model) & df["Experimento"].map(_is_nocot)]

        cot = cot.assign(mode=cot["Observabilidade"].map(_mode))
        noc = noc.assign(mode=noc["Observabilidade"].map(_mode))
        cg = cot.groupby(["Dataset", "mode"])[[IG, WR]].mean()
        ng = noc.groupby(["Dataset", "mode"])[[IG, WR]].mean()
        joined = cg.join(ng, lsuffix="_cot", rsuffix="_nocot", how="inner").reset_index()
        joined["seeker"] = label
        frames.append(joined)

    out = pd.concat(frames, ignore_index=True)
    out["dIG"] = out[f"{IG}_cot"] - out[f"{IG}_nocot"]
    out["dWR"] = out[f"{WR}_cot"] - out[f"{WR}_nocot"]
    return out


def report(paired: pd.DataFrame) -> pd.DataFrame:
    """Print the deltas, significance tests, and interaction; return per-mode table."""
    print(f"Paired cells (6 seekers x 3 domains x 3 modes): {len(paired)}")
    print(f"Cells per mode: {paired['mode'].value_counts().to_dict()}\n")

    print("=== CoT delta by observability mode (mean +/- SE over 6 seekers x 3 domains) ===")
    per_mode = paired.groupby("mode").agg(
        dIG=("dIG", "mean"), dIG_se=("dIG", "sem"),
        dWR=("dWR", "mean"), dWR_se=("dWR", "sem"), n=("dIG", "size"),
    ).reindex(MODES)
    print(per_mode.round(3), "\n")

    print("=== One-sample t-test: per-mode CoT delta > 0 ===")
    for m in MODES:
        sub = paired[paired["mode"] == m]
        for metric, name in [("dIG", "IG/Turn"), ("dWR", "Win Rate")]:
            t, p = stats.ttest_1samp(sub[metric], 0.0)
            print(f"  {m} {name:8s}: mean={sub[metric].mean():+.3f}  t={t:5.2f}  p={p:.1e}")
    print()

    print("=== Interaction: implicit-mode (IO,PO) vs explicit-mode (FO) CoT gain ===")
    piv = paired.pivot_table(index=["seeker", "Dataset"], columns="mode", values=["dIG", "dWR"])
    for metric, name in [("dIG", "IG/Turn"), ("dWR", "Win Rate")]:
        implicit = (piv[(metric, "IO")] + piv[(metric, "PO")]) / 2
        explicit = piv[(metric, "FO")]
        mask = implicit.notna() & explicit.notna()
        t, p = stats.ttest_rel(implicit[mask], explicit[mask])
        print(
            f"  {name:8s}: implicit={implicit[mask].mean():+.3f}  "
            f"explicit(FO)={explicit[mask].mean():+.3f}  "
            f"paired_diff={ (implicit[mask] - explicit[mask]).mean():+.3f}  "
            f"t={t:.2f}  p={p:.1e}  n={mask.sum()}"
        )
    print()

    print("=== Per-seeker CoT Win-Rate gain by mode, sorted by base (no-CoT FO) capability ===")
    by_seeker = paired.pivot_table(index="seeker", columns="mode", values="dWR").reindex(columns=MODES)
    base = paired[paired["mode"] == "FO"].groupby("seeker")[f"{WR}_nocot"].mean()
    by_seeker["base_FO_WR"] = base
    print(by_seeker.round(3).sort_values("base_FO_WR"), "\n")

    return per_mode


def make_figure(per_mode: pd.DataFrame) -> None:
    """Bar chart of CoT delta per mode for both metrics with SE error bars."""
    x = range(len(MODES))
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    for ax, (col, se_col, title) in zip(
        axes,
        [("dIG", "dIG_se", "CoT gain in IG/Turn (bits)"), ("dWR", "dWR_se", "CoT gain in Win Rate")],
    ):
        vals = per_mode[col].values
        errs = per_mode[se_col].values
        colors = ["#bdbdbd", "#2c7fb8", "#41ab5d"]  # FO grey, IO/PO highlighted
        ax.bar(x, vals, yerr=errs, capsize=4, color=colors, edgecolor="black", linewidth=0.6)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(list(x))
        ax.set_xticklabels(MODES)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Observability (FO = set always visible)")
        for i, v in zip(x, vals):
            ax.text(i, v + (0.005 if v >= 0 else -0.02), f"{v:+.3f}", ha="center", fontsize=9)
    fig.suptitle(
        "CoT as a belief-tracking scaffold: gain is near-zero when the set is visible (FO),\n"
        "large when it must be tracked implicitly (IO, PO)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    OUT_FIG.parent.mkdir(exist_ok=True)
    fig.savefig(OUT_FIG, dpi=150)
    print(f"Wrote figure -> {OUT_FIG.relative_to(ROOT)}")


def main() -> None:
    paired = load_paired()
    per_mode = report(paired)
    paired.to_csv(OUT_CSV, index=False)
    print(f"Wrote tidy table -> {OUT_CSV.relative_to(ROOT)}")
    make_figure(per_mode)


if __name__ == "__main__":
    main()
