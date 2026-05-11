# RQ7 Failure Analysis Scripts

Scripts for analyzing *how and why* LLMs fail in the InfoGainme benchmark (Research Question 7).

## Overview

Four standalone scripts, all reading from `outputs/` and writing JSON results back there.
No external dependencies beyond `sentence-transformers` (optional, for cosine redundancy).

Run **after** the main analysis pipeline (`dgx/run_analyze_results.sh`, etc.).

---

## Scripts

### 1. `scripts/cluster_ig_trajectories.py`

K-means clustering (k=3, pure stdlib — no sklearn required) of the per-turn IG sequences of **losing games**.

Each losing game is projected to a 6-dimensional feature vector:

| Feature | Description |
|---------|-------------|
| `mean_ig` | Average IG per turn |
| `std_ig` | Spread of IG values across turns |
| `zero_frac` | Fraction of turns with IG = 0 |
| `early_mean_ig` | Mean IG in first third of turns |
| `late_mean_ig` | Mean IG in last third of turns |
| `cv` | Coefficient of variation (std/mean) |

Clusters are automatically labeled:
- **`stall`** — high zero_frac, near-zero IG throughout; seeker gets stuck early
- **`volatile`** — high std, oscillating IG; inconsistent questioning
- **`mixed`** — some initial progress then stalls

**Run:**
```bash
python scripts/analysis/cluster_ig_trajectories.py              # uses outputs/
python scripts/analysis/cluster_ig_trajectories.py /path/to/outputs
```

**Output:** `outputs/rq7_ig_trajectory_clusters.json`

---

### 2. `scripts/attribute_zero_ig.py`

Classifies every zero-IG turn across all experiments into a root cause:

| Cause | Condition |
|-------|-----------|
| `only_one_candidate` | `active_candidates_before ≤ 1` — IG is mathematically 0 |
| `pruner_error` | Pruner returned 0 pruned candidates despite >1 candidates remaining |
| `genuinely_uninformative` | `pruned_count / active_before < 1%` — question was asked but barely moved the pool |

**Run:**
```bash
python scripts/analysis/attribute_zero_ig.py              # uses outputs/
python scripts/analysis/attribute_zero_ig.py /path/to/outputs
```

**Output:** `outputs/rq7_zero_ig_attribution.json`

---

### 3. `scripts/compute_target_difficulty.py`

Computes a difficulty score per target (city / disease / object):

```
difficulty = mean_turns_to_lose × (1 − win_rate)
```

Harder targets = many turns wasted on losses + low win rate. Results are broken down by geographic region (for the geo domain, extracted from target IDs) or domain (diseases, objects).

**Run:**
```bash
python scripts/analysis/compute_target_difficulty.py              # uses outputs/
python scripts/analysis/compute_target_difficulty.py /path/to/outputs
```

**Output:** `outputs/rq7_target_difficulty.json`

---

### 4. `scripts/compute_redundancy.py`

Computes pairwise question redundancy per game, averaged per experiment.

**Primary method:** cosine similarity via `sentence-transformers` (`all-MiniLM-L6-v2`).
Threshold: ≥ 0.85 similarity → redundant pair.

**Fallback (no sentence-transformers):** Jaccard similarity on word unigrams.
Threshold: ≥ 0.40.

Redundancy rate = fraction of question pairs per game above threshold, averaged across all games in the experiment.

**Run:**
```bash
pip install sentence-transformers           # optional; needed for cosine mode
python scripts/analysis/compute_redundancy.py              # uses outputs/, auto-selects method
python scripts/analysis/compute_redundancy.py /path/to/outputs
python scripts/analysis/compute_redundancy.py /path/to/outputs --jaccard   # force Jaccard
```

**Output:** `outputs/rq7_question_redundancy.json`

---

## Pre-generated Results

The following output files were generated from the full benchmark run (all models, all domains) and are tracked in the HuggingFace dataset repository (`akcit-rl/info-gainme`):

| File | Description |
|------|-------------|
| `outputs/rq7_trajectory_clusters.json` | IG trajectory clusters for all losing games |
| `outputs/rq7_trajectory_clusters.txt` | Human-readable summary |
| `outputs/rq7_zero_ig_attribution.json` | Zero-IG root-cause breakdown |
| `outputs/rq7_zero_ig_attribution.txt` | Human-readable summary |
| `outputs/rq7_target_difficulty.json` | Per-target difficulty scores |
| `outputs/rq7_target_difficulty.txt` | Human-readable summary |
| `outputs/rq7_redundancy.json` | Question redundancy rates per experiment |
| `outputs/rq7_redundancy.txt` | Human-readable summary |
| `outputs/rq1_2_4_5_6_results.json` | Metadata-based RQ results (CoT, size, efficiency, priors) |
| `outputs/rq3_question_types.json` | Question type taxonomy |
| `outputs/rq3_traces_and_coverage.json` | Reasoning trace analysis |
| `outputs/unified_experiments.csv` | All experiments merged |
| `outputs/model_summary.csv` | Per-model aggregated metrics |

### Key findings (from the full run)

- **52%** of losing games are `stall`-type trajectories
- **46%** of all turns have zero IG
- **43%** of zero-IG turns: only 1 candidate remaining (failure was already decided)
- Redundancy: CoT at 30B eliminates redundancy entirely (5.7% → 0%); smaller models persist at 3–8%

Figures generated from these results: `figures/fig3_trajectories.pdf`, `figures/fig4_zero_ig.pdf`, `figures/fig7_redundancy.pdf`, `figures/fig8_domain_difficulty.pdf`.
