#!/usr/bin/env python3
"""Aggregate seeker_traces.jsonl into a summary JSON report.

Reads outputs/seeker_traces.jsonl (produced by synthesize_traces.py) and
writes outputs/reasoning_traces_analysis.json with per-experiment and global
aggregations: question frequency, decision patterns, turn distributions.

Usage:
    python3 scripts/reasoning_traces/analyze_traces.py
    python3 scripts/reasoning_traces/analyze_traces.py --input-jsonl outputs/seeker_traces.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_traces(jsonl_path: Path) -> dict[str, list[dict]]:
    """Load JSONL and group conversations by experiment name."""
    traces_by_exp: dict[str, list[dict]] = defaultdict(list)
    skipped = 0
    for i, line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except Exception as e:
            print(f"  ⚠️  skip line {i}: {e}", file=sys.stderr)
            skipped += 1
            continue
        # Derive experiment name from seeker_path:
        # outputs/models/<slug>/<experiment>/conversations/<target>/seeker.json
        seeker_path = record.get("seeker_path", "")
        parts = Path(seeker_path).parts
        try:
            conv_idx = parts.index("conversations")
            exp_name = parts[conv_idx - 1]
        except (ValueError, IndexError):
            exp_name = "unknown"
        traces_by_exp[exp_name].append(record)
    if skipped:
        print(f"  ⚠️  {skipped} malformed line(s) skipped", file=sys.stderr)
    return dict(traces_by_exp)


def aggregate(traces_by_exp: dict[str, list[dict]]) -> dict[str, Any]:
    global_questions: Counter[str] = Counter()
    global_decisions: Counter[str] = Counter()
    total_turns = 0
    exp_stats: dict[str, Any] = {}

    for exp_name, records in traces_by_exp.items():
        turn_counts = []
        questions_in_exp: Counter[str] = Counter()
        decisions_in_exp: Counter[str] = Counter()

        for record in records:
            turns = record.get("turns", [])
            turn_counts.append(len(turns))
            for turn in turns:
                rt = turn.get("reasoning_trace", {}) or {}
                for q in rt.get("questions_considered", []):
                    if isinstance(q, str) and q.strip():
                        questions_in_exp[q.strip()] += 1
                        global_questions[q.strip()] += 1
                decision = rt.get("decision_rationale", "")
                if decision:
                    fp = decision[:80].strip()
                    decisions_in_exp[fp] += 1
                    global_decisions[fp] += 1
                total_turns += 1

        if turn_counts:
            exp_stats[exp_name] = {
                "num_conversations": len(records),
                "total_turns": sum(turn_counts),
                "avg_turns": round(statistics.mean(turn_counts), 2),
                "median_turns": statistics.median(turn_counts),
                "min_turns": min(turn_counts),
                "max_turns": max(turn_counts),
                "top_questions": questions_in_exp.most_common(10),
                "top_decisions": decisions_in_exp.most_common(5),
            }

    return {
        "total_conversations": sum(len(v) for v in traces_by_exp.values()),
        "total_turns": total_turns,
        "num_experiments": len(traces_by_exp),
        "experiments": exp_stats,
        "global_top_questions": global_questions.most_common(20),
        "global_top_decisions": global_decisions.most_common(15),
        "global_unique_questions": len(global_questions),
    }


def print_report(agg: dict[str, Any]) -> None:
    print("\n" + "=" * 80)
    print("📊 REASONING TRACES ANALYSIS")
    print("=" * 80)
    print(f"\n  Conversations : {agg['total_conversations']}")
    print(f"  Turns         : {agg['total_turns']}")
    print(f"  Experiments   : {agg['num_experiments']}")
    print(f"  Unique questions considered: {agg['global_unique_questions']}")

    print("\n" + "-" * 80)
    print("PER-EXPERIMENT:")
    for exp, stats in sorted(agg["experiments"].items()):
        print(f"\n  {exp}")
        print(f"    conversations={stats['num_conversations']}  "
              f"avg_turns={stats['avg_turns']}  "
              f"min={stats['min_turns']}  max={stats['max_turns']}")
        for q, n in stats["top_questions"][:3]:
            print(f"    • {n}x  {q[:80]}")

    print("\n" + "-" * 80)
    print("TOP 20 QUESTIONS CONSIDERED (global):")
    for i, (q, n) in enumerate(agg["global_top_questions"], 1):
        print(f"  {i:2d}. {n:5d}x  {q[:80]}")

    print("\n" + "=" * 80)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--input-jsonl",
        type=Path,
        default=Path("outputs/seeker_traces.jsonl"),
        help="JSONL produced by synthesize_traces.py.",
    )
    p.add_argument(
        "--out-json",
        type=Path,
        default=Path("outputs/reasoning_traces_analysis.json"),
        help="Output summary JSON.",
    )
    args = p.parse_args()

    if not args.input_jsonl.exists():
        print(f"ERROR: {args.input_jsonl} not found. Run synthesize_traces.py first.", file=sys.stderr)
        return 1

    print(f"Loading {args.input_jsonl}...")
    traces_by_exp = load_traces(args.input_jsonl)
    print(f"  {sum(len(v) for v in traces_by_exp.values())} conversations across {len(traces_by_exp)} experiments")

    agg = aggregate(traces_by_exp)
    print_report(agg)

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(agg, indent=2, ensure_ascii=False, default=str))
    print(f"\nWrote: {args.out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
