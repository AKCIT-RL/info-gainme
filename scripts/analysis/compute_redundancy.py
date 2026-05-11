"""Compute question redundancy rate per experiment (RQ7).

For each experiment, reads all turns.jsonl files and computes pairwise
redundancy between questions asked across a game using:

  Primary:  cosine similarity via sentence-transformers (all-MiniLM-L6-v2)
  Fallback: Jaccard similarity on word n-grams (if sentence-transformers unavailable)

A pair of questions is "redundant" if similarity >= THRESHOLD.
Redundancy rate = fraction of question pairs that are redundant, per game,
averaged across all games per experiment.

Outputs: outputs/rq7_question_redundancy.json

Usage:
    python scripts/compute_redundancy.py [outputs_dir]
    python scripts/compute_redundancy.py [outputs_dir] --jaccard   # force Jaccard
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Cosine threshold — pairs above this count as redundant
COSINE_THRESHOLD = 0.85
# Jaccard threshold for word unigrams
JACCARD_THRESHOLD = 0.40


# ── Similarity implementations ───────────────────────────────────────────────

def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity on word unigrams."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _pairwise_redundancy_jaccard(questions: list[str]) -> float:
    """Returns fraction of question pairs that are redundant (Jaccard)."""
    n = len(questions)
    if n < 2:
        return 0.0
    redundant = 0
    total = 0
    for i in range(n):
        for j in range(i + 1, n):
            sim = _jaccard(questions[i], questions[j])
            if sim >= JACCARD_THRESHOLD:
                redundant += 1
            total += 1
    return redundant / total if total > 0 else 0.0


def _pairwise_redundancy_cosine(embeddings: list[list[float]]) -> float:
    """Returns fraction of embedding pairs that are redundant (cosine)."""
    n = len(embeddings)
    if n < 2:
        return 0.0
    redundant = 0
    total = 0
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim >= COSINE_THRESHOLD:
                redundant += 1
            total += 1
    return redundant / total if total > 0 else 0.0


# ── Embedding loader (lazy, cached) ─────────────────────────────────────────

_encoder = None

def _get_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
    return _encoder


def _embed_batch(questions: list[str]) -> list[list[float]]:
    enc = _get_encoder()
    vecs = enc.encode(questions, show_progress_bar=False)
    return [v.tolist() for v in vecs]


# ── Main ─────────────────────────────────────────────────────────────────────

def main(outputs_dir: Path, force_jaccard: bool = False) -> None:
    models_dir = outputs_dir / "models"
    if not models_dir.exists():
        print(f"❌ outputs/models not found at {models_dir}")
        sys.exit(1)

    # Decide method
    use_cosine = False
    if not force_jaccard:
        try:
            import sentence_transformers  # noqa: F401
            use_cosine = True
            print("📐 Using cosine similarity (sentence-transformers)")
        except ImportError:
            print("⚠️  sentence-transformers not installed — falling back to Jaccard")

    print(f"🔍 Scanning turns.jsonl files under {models_dir} …")

    # Per-experiment: list of per-game redundancy rates
    exp_game_rates: dict[str, list[float]] = defaultdict(list)

    for turns_path in sorted(models_dir.glob("**/conversations/*/turns.jsonl")):
        experiment = turns_path.parts[-4] if len(turns_path.parts) >= 4 else "unknown"
        try:
            lines = [l.strip() for l in turns_path.read_text().splitlines() if l.strip()]
        except Exception:
            continue

        questions: list[str] = []
        for line in lines:
            try:
                turn = json.loads(line)
                q_text = turn.get("question", {}).get("text", "")
                if q_text:
                    questions.append(q_text)
            except Exception:
                continue

        if len(questions) < 2:
            continue

        if use_cosine:
            try:
                embeddings = _embed_batch(questions)
                rate = _pairwise_redundancy_cosine(embeddings)
            except Exception as e:
                print(f"⚠️  Embedding failed for {turns_path}: {e} — using Jaccard")
                rate = _pairwise_redundancy_jaccard(questions)
        else:
            rate = _pairwise_redundancy_jaccard(questions)

        exp_game_rates[experiment].append(rate)

    if not exp_game_rates:
        print("⚠️  No games with ≥2 questions found.")
        sys.exit(1)

    # Summarise
    experiments_out: dict[str, dict] = {}
    global_rates: list[float] = []

    for exp, rates in sorted(exp_game_rates.items()):
        n = len(rates)
        mean = sum(rates) / n
        variance = sum((r - mean) ** 2 for r in rates) / n
        std = variance ** 0.5
        experiments_out[exp] = {
            "n_games": n,
            "mean_redundancy": round(mean, 4),
            "std_redundancy": round(std, 4),
            "max_redundancy": round(max(rates), 4),
            "min_redundancy": round(min(rates), 4),
        }
        global_rates.extend(rates)

    total_n = len(global_rates)
    global_mean = sum(global_rates) / total_n
    global_var = sum((r - global_mean) ** 2 for r in global_rates) / total_n
    global_std = global_var ** 0.5

    output = {
        "method": "cosine" if use_cosine else "jaccard",
        "threshold": COSINE_THRESHOLD if use_cosine else JACCARD_THRESHOLD,
        "total_games": total_n,
        "global_mean_redundancy": round(global_mean, 4),
        "global_std_redundancy": round(global_std, 4),
        "per_experiment": experiments_out,
    }

    out_path = outputs_dir / "rq7_question_redundancy.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\n✅ Written → {out_path}")

    print(f"\n📊 Global redundancy ({output['method']}, threshold={output['threshold']}):")
    print(f"  Mean: {global_mean:.2%}  Std: {global_std:.2%}  N games: {total_n:,}")
    print("\n📊 Per-experiment:")
    for exp, stats in sorted(experiments_out.items(), key=lambda x: x[1]["mean_redundancy"], reverse=True):
        print(f"  {exp[:60]:60s}  mean={stats['mean_redundancy']:.2%}  "
              f"std={stats['std_redundancy']:.2%}  n={stats['n_games']}")


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    outputs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root / "outputs"
    force_jaccard = "--jaccard" in sys.argv
    main(outputs_dir, force_jaccard=force_jaccard)
