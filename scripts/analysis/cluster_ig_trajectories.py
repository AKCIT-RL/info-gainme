"""Cluster IG trajectories of losing games (RQ7).

For every losing game across all experiments, extracts the per-turn info-gain
sequence, computes a fixed-length feature vector, and runs k-means (k=3) to
identify trajectory patterns:

  stall     — IG starts near zero and stays zero  (seeker gets stuck early)
  volatile  — IG oscillates heavily turn-to-turn  (inconsistent questioning)
  mixed     — some initial progress then stalls    (partial success)

Outputs: outputs/rq7_ig_trajectory_clusters.json

Usage:
    python scripts/cluster_ig_trajectories.py [outputs_dir]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Feature extraction ────────────────────────────────────────────────────────

def _extract_features(ig_seq: list[float]) -> list[float]:
    """Convert a variable-length IG sequence into a fixed 6-dim feature vector.

    Features:
      0  mean_ig           — overall avg IG per turn
      1  std_ig            — spread of IG values
      2  zero_frac         — fraction of turns with IG == 0
      3  early_mean_ig     — mean IG in first third of turns
      4  late_mean_ig      — mean IG in last third of turns
      5  cv                — coefficient of variation (std/mean, 0 if mean==0)
    """
    if not ig_seq:
        return [0.0] * 6

    n = len(ig_seq)
    mean = sum(ig_seq) / n
    variance = sum((x - mean) ** 2 for x in ig_seq) / n
    std = variance ** 0.5
    zero_frac = sum(1 for x in ig_seq if x == 0.0) / n

    third = max(1, n // 3)
    early_mean = sum(ig_seq[:third]) / third
    late_mean = sum(ig_seq[-third:]) / len(ig_seq[-third:])

    cv = std / mean if mean > 0 else 0.0

    return [mean, std, zero_frac, early_mean, late_mean, cv]


# ── K-means (vanilla, no sklearn dependency) ──────────────────────────────────

def _euclidean(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _kmeans(features: list[list[float]], k: int = 3, max_iter: int = 100, seed: int = 42) -> list[int]:
    """Simple k-means returning cluster labels."""
    import random
    rng = random.Random(seed)
    centroids = rng.sample(features, k)

    labels = [0] * len(features)
    for _ in range(max_iter):
        # Assignment step
        new_labels = [
            min(range(k), key=lambda c: _euclidean(feat, centroids[c]))
            for feat in features
        ]
        if new_labels == labels:
            break
        labels = new_labels

        # Update step
        new_centroids = []
        for c in range(k):
            members = [features[i] for i, l in enumerate(labels) if l == c]
            if members:
                dim = len(members[0])
                centroid = [sum(m[d] for m in members) / len(members) for d in range(dim)]
            else:
                centroid = centroids[c]
            new_centroids.append(centroid)
        centroids = new_centroids

    return labels


def _label_clusters(cluster_stats: dict) -> dict[int, str]:
    """Assign semantic names to clusters based on their mean feature vectors."""
    names: dict[int, str] = {}
    # Sort clusters by zero_frac (feature index 2) descending → most-stalled first
    sorted_by_zero = sorted(cluster_stats.items(), key=lambda x: x[1]["mean_zero_frac"], reverse=True)
    # Sort clusters by std (feature index 1) descending → most-volatile first
    sorted_by_std = sorted(cluster_stats.items(), key=lambda x: x[1]["mean_std"], reverse=True)

    stall_cid = sorted_by_zero[0][0]
    volatile_cid = sorted_by_std[0][0]
    remaining = [cid for cid, _ in cluster_stats.items() if cid not in {stall_cid, volatile_cid}]

    if stall_cid == volatile_cid:
        # Edge case: same cluster is both — pick next volatile
        volatile_cid = sorted_by_std[1][0]
        remaining = [cid for cid, _ in cluster_stats.items() if cid not in {stall_cid, volatile_cid}]

    names[stall_cid] = "stall"
    names[volatile_cid] = "volatile"
    for cid in remaining:
        names[cid] = "mixed"
    return names


# ── Main ─────────────────────────────────────────────────────────────────────

def main(outputs_dir: Path) -> None:
    models_dir = outputs_dir / "models"
    if not models_dir.exists():
        print(f"❌ outputs/models not found at {models_dir}")
        sys.exit(1)

    print(f"🔍 Scanning losing games under {models_dir} …")

    records: list[dict] = []  # {experiment, target_id, ig_seq, features}

    for metadata_path in sorted(models_dir.glob("**/conversations/*/metadata.json")):
        try:
            meta = json.loads(metadata_path.read_text())
        except Exception:
            continue

        if meta.get("results", {}).get("win", True):
            continue  # only losing games

        turns_path = metadata_path.parent / "turns.jsonl"
        if not turns_path.exists():
            continue

        ig_seq: list[float] = []
        try:
            for line in turns_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                turn = json.loads(line)
                ig_seq.append(float(turn.get("info_gain", 0.0)))
        except Exception:
            continue

        if not ig_seq:
            continue

        experiment = metadata_path.parts[-4] if len(metadata_path.parts) >= 4 else "unknown"
        target_id = meta.get("target", {}).get("id", metadata_path.parent.name)
        model_dir = metadata_path.parts[-5] if len(metadata_path.parts) >= 5 else "unknown"

        records.append({
            "experiment": experiment,
            "model_dir": model_dir,
            "target_id": target_id,
            "ig_seq": ig_seq,
            "features": _extract_features(ig_seq),
        })

    if len(records) < 3:
        print(f"⚠️  Only {len(records)} losing games found — need at least 3 for clustering")
        sys.exit(1)

    print(f"📊 Found {len(records)} losing games — clustering …")

    feature_matrix = [r["features"] for r in records]
    labels = _kmeans(feature_matrix, k=3)

    # Compute per-cluster statistics
    cluster_groups: dict[int, list[dict]] = defaultdict(list)
    for rec, label in zip(records, labels):
        cluster_groups[label].append(rec)

    cluster_stats: dict[int, dict] = {}
    for cid, members in cluster_groups.items():
        all_mean = [m["features"][0] for m in members]
        all_std  = [m["features"][1] for m in members]
        all_zf   = [m["features"][2] for m in members]
        all_em   = [m["features"][3] for m in members]
        all_lm   = [m["features"][4] for m in members]
        n = len(members)
        cluster_stats[cid] = {
            "count": n,
            "fraction": n / len(records),
            "mean_mean_ig":    sum(all_mean) / n,
            "mean_std":        sum(all_std)  / n,
            "mean_zero_frac":  sum(all_zf)   / n,
            "mean_early_ig":   sum(all_em)   / n,
            "mean_late_ig":    sum(all_lm)   / n,
        }

    cluster_names = _label_clusters(cluster_stats)

    # Build output
    output: dict = {
        "total_losing_games": len(records),
        "k": 3,
        "clusters": {},
        "per_experiment": defaultdict(lambda: defaultdict(int)),
    }

    for cid, stats in cluster_stats.items():
        name = cluster_names[cid]
        output["clusters"][name] = {**stats, "cluster_id": cid}

    for rec, label in zip(records, labels):
        name = cluster_names[label]
        output["per_experiment"][rec["experiment"]][name] = (
            output["per_experiment"][rec["experiment"]].get(name, 0) + 1
        )

    # Convert defaultdict to regular dict for JSON serialisation
    output["per_experiment"] = {
        exp: dict(counts)
        for exp, counts in output["per_experiment"].items()
    }

    out_path = outputs_dir / "rq7_ig_trajectory_clusters.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\n✅ Written → {out_path}")

    print("\n📊 Cluster summary:")
    for name, stats in output["clusters"].items():
        print(f"  {name:10s} — {stats['count']:4d} games ({stats['fraction']:.1%}) "
              f"| zero_frac={stats['mean_zero_frac']:.2f} "
              f"| mean_ig={stats['mean_mean_ig']:.4f} "
              f"| std={stats['mean_std']:.4f}")


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    outputs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root / "outputs"
    main(outputs_dir)
