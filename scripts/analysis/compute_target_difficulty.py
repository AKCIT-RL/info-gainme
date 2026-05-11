"""Compute per-target difficulty scores (RQ7).

Produces a difficulty score for each target (city / disease / object) based on:

  difficulty = mean_turns_on_losses × (1 - win_rate)
             + max_turns × win_rate  [inverted: harder targets won quickly are less hard]

Simplified to:
  difficulty = mean_turns_to_lose × (1 - win_rate)

Intuitively: targets that take many turns to lose (seeker can't identify them)
AND have a low win rate are the hardest.

Also reports:
  - win_rate per target
  - mean_turns (wins + losses)
  - region / domain breakdown (geo → uses target id prefix; others → flat)

Outputs: outputs/rq7_target_difficulty.json

Usage:
    python scripts/compute_target_difficulty.py [outputs_dir]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _region_from_target_id(target_id: str) -> str:
    """Extract region label from geo target ids like 'region:europe:country:france:city:paris:5'."""
    parts = target_id.split(":")
    # geo ids: region:<name>:country:<name>:city:<name>:<idx>
    if "region" in parts:
        idx = parts.index("region")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    # diseases: disease:<name>:<idx>
    if "disease" in parts:
        return "diseases"
    # objects: object:<name>:<idx>
    if "object" in parts:
        return "objects"
    return "unknown"


def main(outputs_dir: Path) -> None:
    models_dir = outputs_dir / "models"
    if not models_dir.exists():
        print(f"❌ outputs/models not found at {models_dir}")
        sys.exit(1)

    print(f"🔍 Scanning metadata.json files under {models_dir} …")

    # target_id → list of game records {win, turns_played, experiment}
    target_records: dict[str, list[dict]] = defaultdict(list)

    for metadata_path in sorted(models_dir.glob("**/conversations/*/metadata.json")):
        try:
            meta = json.loads(metadata_path.read_text())
        except Exception:
            continue

        results = meta.get("results", {})
        target = meta.get("target", {})
        experiment = metadata_path.parts[-4] if len(metadata_path.parts) >= 4 else "unknown"

        target_id = target.get("id", metadata_path.parent.name)
        target_label = target.get("label", target_id)
        win = bool(results.get("win", False))
        turns = int(results.get("turns_played", 0))

        target_records[target_id].append({
            "label": target_label,
            "win": win,
            "turns": turns,
            "experiment": experiment,
        })

    if not target_records:
        print("⚠️  No games found.")
        sys.exit(1)

    print(f"📊 Computing difficulty for {len(target_records)} unique targets …")

    targets_out: list[dict] = []
    region_stats: dict[str, list[float]] = defaultdict(list)

    for target_id, records in target_records.items():
        label = records[0]["label"]
        wins = [r for r in records if r["win"]]
        losses = [r for r in records if not r["win"]]
        n = len(records)
        win_rate = len(wins) / n

        mean_turns_all = sum(r["turns"] for r in records) / n
        mean_turns_losses = (
            sum(r["turns"] for r in losses) / len(losses)
            if losses else 0.0
        )

        # difficulty: harder = more turns to lose AND lower win rate
        difficulty = mean_turns_losses * (1.0 - win_rate)

        region = _region_from_target_id(target_id)

        entry = {
            "target_id": target_id,
            "label": label,
            "region": region,
            "n_games": n,
            "win_rate": round(win_rate, 4),
            "mean_turns": round(mean_turns_all, 2),
            "mean_turns_losses": round(mean_turns_losses, 2),
            "difficulty": round(difficulty, 4),
            "experiments": sorted({r["experiment"] for r in records}),
        }
        targets_out.append(entry)
        region_stats[region].append(difficulty)

    # Sort by difficulty descending
    targets_out.sort(key=lambda x: x["difficulty"], reverse=True)

    # Region summary
    region_summary: dict[str, dict] = {}
    for region, diffs in sorted(region_stats.items()):
        n = len(diffs)
        mean_diff = sum(diffs) / n
        region_summary[region] = {
            "n_targets": n,
            "mean_difficulty": round(mean_diff, 4),
            "max_difficulty": round(max(diffs), 4),
            "min_difficulty": round(min(diffs), 4),
        }

    output = {
        "total_targets": len(targets_out),
        "region_summary": region_summary,
        "targets": targets_out,
    }

    out_path = outputs_dir / "rq7_target_difficulty.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\n✅ Written → {out_path}")

    print("\n📊 Top 10 hardest targets:")
    for entry in targets_out[:10]:
        print(f"  [{entry['region']:12s}] {entry['label']:40s}  "
              f"difficulty={entry['difficulty']:.3f}  "
              f"win_rate={entry['win_rate']:.2%}  "
              f"mean_turns_loss={entry['mean_turns_losses']:.1f}")

    print("\n📊 Region difficulty summary:")
    for region, stats in sorted(region_summary.items(), key=lambda x: x[1]["mean_difficulty"], reverse=True):
        print(f"  {region:15s} — {stats['n_targets']:4d} targets, "
              f"mean_difficulty={stats['mean_difficulty']:.3f}, "
              f"max={stats['max_difficulty']:.3f}")


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    outputs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root / "outputs"
    main(outputs_dir)
