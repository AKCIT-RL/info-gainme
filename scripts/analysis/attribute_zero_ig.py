"""Attribute root causes to every zero-IG turn (RQ7).

For each zero-IG turn across all experiments, classifies the cause into one of:

  only_one_candidate    — only 1 candidate remained; IG is mathematically 0
  pruner_error          — pruner pruned 0 candidates (compliance issue or parse fail)
  genuinely_uninformative — question asked, oracle answered, but pool barely changed
                            (ratio of pruned_count to active_before < threshold)

Outputs: outputs/rq7_zero_ig_attribution.json

Usage:
    python scripts/attribute_zero_ig.py [outputs_dir]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# Threshold: if pruned_count / active_before < this, consider "genuinely uninformative"
_UNINFORMATIVE_RATIO = 0.01  # < 1% of candidates pruned → uninformative

# Threshold: IG considered "zero" if below this (floating-point tolerance)
_IG_ZERO_THRESHOLD = 1e-9


def _classify_zero_turn(turn: dict) -> str:
    """Classify a single zero-IG turn into a root-cause bucket."""
    active_before = turn.get("active_candidates_before", 0)
    pruned_count = turn.get("pruned_count", 0)
    active_after = turn.get("active_candidates_after", active_before)

    # Case 1: Only 1 candidate left — nothing left to prune, IG must be 0
    if active_before <= 1:
        return "only_one_candidate"

    # Case 2: Pruner returned 0 pruned candidates (pruner failure / non-compliance)
    if pruned_count == 0 and active_after == active_before:
        return "pruner_error"

    # Case 3: Genuinely uninformative question (almost nothing pruned despite >1 candidates)
    ratio = pruned_count / active_before if active_before > 0 else 0
    if ratio < _UNINFORMATIVE_RATIO:
        return "genuinely_uninformative"

    # Fallback — shouldn't happen often; IG rounds to 0 despite small pruning
    return "genuinely_uninformative"


def main(outputs_dir: Path) -> None:
    models_dir = outputs_dir / "models"
    if not models_dir.exists():
        print(f"❌ outputs/models not found at {models_dir}")
        sys.exit(1)

    print(f"🔍 Scanning turns.jsonl files under {models_dir} …")

    total_turns = 0
    total_zero_turns = 0

    # Counters keyed by experiment
    per_experiment: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    global_counts: dict[str, int] = defaultdict(int)

    # Also track zero-IG turn rate per experiment for summary
    exp_turn_totals: dict[str, int] = defaultdict(int)
    exp_zero_totals: dict[str, int] = defaultdict(int)

    for turns_path in sorted(models_dir.glob("**/conversations/*/turns.jsonl")):
        experiment = turns_path.parts[-4] if len(turns_path.parts) >= 4 else "unknown"
        try:
            lines = [l.strip() for l in turns_path.read_text().splitlines() if l.strip()]
        except Exception:
            continue

        for line in lines:
            try:
                turn = json.loads(line)
            except Exception:
                continue

            total_turns += 1
            exp_turn_totals[experiment] += 1
            ig = float(turn.get("info_gain", 0.0))

            if ig > _IG_ZERO_THRESHOLD:
                continue

            total_zero_turns += 1
            exp_zero_totals[experiment] += 1

            cause = _classify_zero_turn(turn)
            per_experiment[experiment][cause] += 1
            global_counts[cause] += 1

    if total_turns == 0:
        print("⚠️  No turns found.")
        sys.exit(1)

    zero_frac = total_zero_turns / total_turns

    output = {
        "total_turns": total_turns,
        "total_zero_ig_turns": total_zero_turns,
        "zero_ig_fraction": round(zero_frac, 4),
        "global_attribution": {
            k: {
                "count": v,
                "fraction_of_zero": round(v / total_zero_turns, 4) if total_zero_turns else 0,
                "fraction_of_all": round(v / total_turns, 4) if total_turns else 0,
            }
            for k, v in sorted(global_counts.items(), key=lambda x: x[1], reverse=True)
        },
        "per_experiment": {},
    }

    for exp, causes in sorted(per_experiment.items()):
        exp_zero = exp_zero_totals[exp]
        exp_total = exp_turn_totals[exp]
        output["per_experiment"][exp] = {
            "total_turns": exp_total,
            "zero_ig_turns": exp_zero,
            "zero_ig_fraction": round(exp_zero / exp_total, 4) if exp_total else 0,
            "attribution": {
                k: {
                    "count": v,
                    "fraction_of_zero": round(v / exp_zero, 4) if exp_zero else 0,
                }
                for k, v in sorted(causes.items(), key=lambda x: x[1], reverse=True)
            },
        }

    out_path = outputs_dir / "rq7_zero_ig_attribution.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\n✅ Written → {out_path}")

    print(f"\n📊 Global summary:")
    print(f"  Total turns:     {total_turns:,}")
    print(f"  Zero-IG turns:   {total_zero_turns:,}  ({zero_frac:.1%})")
    print(f"\n  Root-cause breakdown (of zero-IG turns):")
    for cause, stats in output["global_attribution"].items():
        print(f"    {cause:30s} {stats['count']:6,}  ({stats['fraction_of_zero']:.1%})")


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    outputs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root / "outputs"
    main(outputs_dir)
