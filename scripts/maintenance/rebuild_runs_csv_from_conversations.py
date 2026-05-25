#!/usr/bin/env python3
"""Rebuild missing rows in runs.csv from conversations/*/metadata.json.

Use case: dgx/sync_outputs.sh overwrites a complete runs.csv with a shorter
version from another node (rsync --update on a re-launched experiment).
The conversation directories on disk are untouched, so we can reconstruct
the lost CSV rows from each conversation's metadata.json.

Default: dry-run. Pass --apply to actually append rows.

Usage:
    python3 scripts/maintenance/rebuild_runs_csv_from_conversations.py \
        outputs/models/s_Qwen3-8B__o_Qwen3-8B__p_Qwen3-8B/diseases_160_8b_io_cot/
    # or scan all experiments:
    python3 scripts/maintenance/rebuild_runs_csv_from_conversations.py outputs/models/
    # write changes:
    python3 scripts/maintenance/rebuild_runs_csv_from_conversations.py --apply outputs/models/
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

HEADER = [
    "experiment_name", "seeker_model", "oracle_model", "pruner_model",
    "observability", "max_turns", "target_id", "target_label", "run_index",
    "turns", "h_start", "h_end", "total_info_gain", "avg_info_gain_per_turn",
    "win", "compliance_rate", "conversation_path",
]

RUN_RE = re.compile(r"_run(\d+)$")


def existing_pairs(csv_path: Path) -> set[tuple[str, int]]:
    if not csv_path.exists():
        return set()
    pairs = set()
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            tid = row.get("target_id")
            ri = row.get("run_index")
            if tid and ri and ri.lstrip("-").isdigit():
                pairs.add((tid, int(ri)))
    return pairs


def row_from_metadata(meta: dict, conv_dir: Path, output_base: Path, run_idx: int) -> list:
    cfg = meta.get("config", {})
    tgt = meta.get("target", {})
    res = meta.get("results", {})
    models = cfg.get("models", {})
    try:
        rel_path = str(conv_dir.relative_to(output_base))
    except ValueError:
        rel_path = str(conv_dir)
    return [
        cfg.get("experiment_name", ""),
        models.get("seeker", ""),
        models.get("oracle", ""),
        models.get("pruner", ""),
        cfg.get("observability_mode", ""),
        cfg.get("max_turns", ""),
        tgt.get("id", ""),
        tgt.get("label", ""),
        run_idx,
        res.get("turns_played", ""),
        res.get("h_start", ""),
        res.get("h_end", ""),
        res.get("total_info_gain", ""),
        res.get("avg_info_gain_per_turn", ""),
        int(bool(res.get("win", False))),
        round(float(res.get("compliance_rate", 0.0)), 4),
        rel_path,
    ]


def process_experiment(exp_dir: Path, output_base: Path, apply: bool) -> tuple[int, int]:
    """Returns (rows_added, conversations_scanned)."""
    csv_path = exp_dir / "runs.csv"
    convs_dir = exp_dir / "conversations"
    if not convs_dir.is_dir():
        return 0, 0
    existing = existing_pairs(csv_path)

    new_rows = []
    scanned = 0
    for conv_dir in sorted(convs_dir.iterdir()):
        if not conv_dir.is_dir():
            continue
        m = RUN_RE.search(conv_dir.name)
        if not m:
            continue
        scanned += 1
        run_idx = int(m.group(1))
        meta_path = conv_dir / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            print(f"  WARN: bad json {meta_path}", file=sys.stderr)
            continue
        tid = meta.get("target", {}).get("id")
        if not tid:
            continue
        if (tid, run_idx) in existing:
            continue
        new_rows.append(row_from_metadata(meta, conv_dir, output_base, run_idx))

    if not new_rows:
        return 0, scanned

    rel = exp_dir.relative_to(output_base.parent) if output_base in exp_dir.parents else exp_dir
    print(f"  + {len(new_rows):>4} new rows for {rel}")

    if apply:
        write_header = not csv_path.exists()
        with csv_path.open("a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(HEADER)
            w.writerows(new_rows)

    return len(new_rows), scanned


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", type=Path,
                    help="Single experiment dir, or outputs/models/ (scans recursively).")
    ap.add_argument("--apply", action="store_true",
                    help="Actually append rows (default: dry-run).")
    args = ap.parse_args()

    if not args.path.exists():
        ap.error(f"path not found: {args.path}")

    # output_base = the .../outputs/models dir, so we can build the
    # relative conversation_path correctly (matches BenchmarkRunner).
    p = args.path.resolve()
    # output_base must be the .../outputs dir so conversation_path starts with
    # "models/..." (matches BenchmarkRunner.output_base).
    if p.name == "models":
        output_base = p.parent
        exp_dirs = [d for triple in p.iterdir() if triple.is_dir()
                    for d in triple.iterdir() if d.is_dir() and (d / "conversations").is_dir()]
    elif (p / "conversations").is_dir():
        # single experiment: .../outputs/models/<triple>/<exp>
        output_base = p.parent.parent.parent
        exp_dirs = [p]
    else:
        # maybe a triple dir: .../outputs/models/<triple>
        if any((c / "conversations").is_dir() for c in p.iterdir() if c.is_dir()):
            output_base = p.parent.parent
            exp_dirs = [c for c in p.iterdir() if c.is_dir() and (c / "conversations").is_dir()]
        else:
            ap.error(f"not an experiment / triple / models dir: {p}")

    print(f"{'APPLY' if args.apply else 'DRY-RUN'} | scanning {len(exp_dirs)} experiments under {p}")

    total_added = 0
    total_scanned = 0
    for exp in sorted(exp_dirs):
        added, scanned = process_experiment(exp, output_base, args.apply)
        total_added += added
        total_scanned += scanned

    print(f"\nTotal: {total_added} rows {'appended' if args.apply else 'WOULD be appended'} "
          f"({total_scanned} conversation dirs scanned)")
    if not args.apply and total_added > 0:
        print("Re-run with --apply to write.")


if __name__ == "__main__":
    sys.exit(main())
