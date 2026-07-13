#!/usr/bin/env python3
"""Upload canonical benchmark runs to HuggingFace dataset.

Selects only canonical experiments:
  - Oracle/pruner = Qwen3-8B  (model dir contains o_Qwen3-8B__p_Qwen3-8B)
  - Seeker in the 10 canonical paper models
  - Experiment name free of _ont / _ablation (_with_prior included)
  - When a _with_kickoff variant exists, prefers it; skips the plain version

Per-experiment files uploaded (conversations/ tree excluded — zip only):
  runs.csv, summary.json, summary_run01.json,
  variance.json, variance_run01.json,
  conversations.zip,
  question_evaluations_summary.json,
  oracle_judge_eval.json, pruner_judge_eval.json

Top-level extras uploaded:
  outputs/views_artigo/*.csv  → views_artigo/

Run ``scripts/hf/zip_experiments.py`` first — conversations.zip must exist.

Files are grouped into batched commits (HF caps ~128 commits/hour; one commit
per file gets 429-throttled part-way through). Re-running is safe: files already
present in the repo are skipped.

Requires HF_TOKEN. ``python-dotenv`` is optional and often absent, so export the
env yourself rather than relying on the .env being auto-loaded:

    set -a && . ./.env && set +a

Usage:
    python scripts/hf/upload_runs_hf.py
    python scripts/hf/upload_runs_hf.py --repo-id akcit-rl/infogainme-runs
    python scripts/hf/upload_runs_hf.py --dry-run
    python scripts/hf/upload_runs_hf.py --outputs-dir /raid/.../outputs --batch-size 40
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── canonical model configuration ─────────────────────────────────────────────

CANONICAL_ORACLE = "o_Qwen3-8B__p_Qwen3-8B"

CANONICAL_SEEKER_SLUGS: set[str] = {
    "Llama-3.1-8B-Instruct",
    "paprika_Meta-Llama-3.1-8B-Instruct",
    "Qwen3-4B-Instruct-2507",
    "Qwen3-4B-Thinking-2507",
    "Qwen3-8B",
    "Qwen3-30B-A3B-Instruct-2507",
    "Qwen3-30B-A3B-Thinking-2507",
    "google-gemma-4-E4B-it",
    "google-gemma-4-31B-it",
    "Nemotron-Cascade-8B",
}

_NON_CANONICAL_RE = re.compile(r"(_ont|_ablation)($|_)", re.IGNORECASE)

# Per-experiment files to include (relative to the experiment dir)
EXP_FILES = [
    "runs.csv",
    "summary.json",
    "summary_run01.json",
    "variance.json",
    "variance_run01.json",
    "conversations.zip",
    "question_evaluations_summary.json",
    "oracle_judge_eval.json",
    "pruner_judge_eval.json",
]


# ── filtering logic ────────────────────────────────────────────────────────────

def _seeker_slug(model_dir: Path) -> str:
    return model_dir.name.split("__o_")[0].removeprefix("s_")


def _is_canonical_model_dir(model_dir: Path) -> bool:
    name = model_dir.name
    if CANONICAL_ORACLE not in name:
        return False
    slug = _seeker_slug(model_dir)
    return slug in CANONICAL_SEEKER_SLUGS


def _canonical_experiments(model_dir: Path) -> list[Path]:
    """Return canonical experiment dirs inside a model_dir.

    Prefers _with_kickoff over plain: if both geo_x_cot and geo_x_cot_with_kickoff
    exist, only geo_x_cot_with_kickoff is included.
    """
    exps = [d for d in model_dir.iterdir() if d.is_dir()]
    names = {d.name for d in exps}

    result = []
    for exp in exps:
        name = exp.name
        if _NON_CANONICAL_RE.search(name):
            continue
        # skip plain version when a _with_kickoff variant exists
        if "_with_kickoff" not in name and (name + "_with_kickoff") in names:
            continue
        result.append(exp)
    return sorted(result)


# ── file collection ────────────────────────────────────────────────────────────

def collect_upload_pairs(
    outputs_dir: Path,
) -> list[tuple[Path, str]]:
    """Return list of (local_path, repo_path) pairs to upload."""
    pairs: list[tuple[Path, str]] = []

    models_root = outputs_dir / "models"
    if not models_root.exists():
        print(f"ERROR: {models_root} not found", file=sys.stderr)
        return pairs

    for model_dir in sorted(models_root.iterdir()):
        if not model_dir.is_dir():
            continue
        if not _is_canonical_model_dir(model_dir):
            continue

        for exp_dir in _canonical_experiments(model_dir):
            # strip _with_kickoff suffix in the HF repo path
            exp_name_hf = exp_dir.name.removesuffix("_with_kickoff")
            for fname in EXP_FILES:
                fpath = exp_dir / fname
                if fpath.exists():
                    repo_path = str(
                        Path("models") / model_dir.name / exp_name_hf / fname
                    )
                    pairs.append((fpath, repo_path))

    return pairs


# ── upload ────────────────────────────────────────────────────────────────────

def _commit_batch(
    api,
    batch: list[tuple[Path, str]],
    repo_id: str,
    message: str,
    attempts: int = 5,
) -> tuple[bool, str]:
    """Commit one batch of files in a SINGLE commit. Returns (success, message).

    HF caps repository commits at ~128/hour. One commit per file blows through
    that after ~250 files (HTTP 429), so files are grouped per commit instead.
    """
    import time

    from huggingface_hub import CommitOperationAdd

    ops = [
        CommitOperationAdd(path_in_repo=repo_path, path_or_fileobj=str(local))
        for local, repo_path in batch
    ]
    for i in range(attempts):
        try:
            api.create_commit(
                repo_id=repo_id,
                repo_type="dataset",
                operations=ops,
                commit_message=message,
            )
            return True, "ok"
        except Exception as exc:
            text = str(exc)
            if i == attempts - 1:
                return False, text
            # 429 needs a long cooldown; the commit budget refills hourly.
            wait = 300 * (i + 1) if ("429" in text or "rate limit" in text.lower()) else 15 * (i + 1)
            print(f"  retry in {wait}s ({text[:120]})", flush=True)
            time.sleep(wait)
    return False, "unknown"


def upload(
    pairs: list[tuple[Path, str]],
    repo_id: str,
    token: str,
    batch_size: int,
    dry_run: bool,
) -> None:
    total_bytes = sum(p.stat().st_size for p, _ in pairs)
    print(f"\n{len(pairs)} files  |  {total_bytes / 1e9:.2f} GB")

    if dry_run:
        print(f"[dry-run] Would upload to: https://huggingface.co/datasets/{repo_id}")
        for local, repo in pairs[:20]:
            print(f"  {repo}  ({local.stat().st_size // 1024} KB)")
        if len(pairs) > 20:
            print(f"  … and {len(pairs) - 20} more")
        return

    from huggingface_hub import HfApi
    api = HfApi(token=token)

    # ensure repo exists
    try:
        api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    except Exception as exc:
        print(f"Warning: could not create/verify repo: {exc}", file=sys.stderr)

    # Resume: skip files already present in the repo.
    try:
        existing = set(api.list_repo_files(repo_id=repo_id, repo_type="dataset"))
    except Exception:
        existing = set()
    todo = [(l, r) for l, r in pairs if r not in existing]
    skipped = len(pairs) - len(todo)
    if skipped:
        print(f"Resume: {skipped} already in repo, {len(todo)} left.")
    if not todo:
        print(f"\nNothing to do. Dataset: https://huggingface.co/datasets/{repo_id}")
        return

    batches = [todo[i:i + batch_size] for i in range(0, len(todo), batch_size)]
    print(f"Uploading {len(todo)} files in {len(batches)} commits "
          f"({batch_size} files/commit)…\n", flush=True)

    ok = failed = 0
    for n, batch in enumerate(batches, 1):
        msg = f"Upload canonical runs ({n}/{len(batches)})"
        success, err = _commit_batch(api, batch, repo_id, msg)
        if success:
            ok += len(batch)
            print(f"  [commit {n}/{len(batches)}] {ok}/{len(todo)} files uploaded", flush=True)
        else:
            failed += len(batch)
            print(f"  FAIL commit {n}/{len(batches)}: {err[:200]}", flush=True)

    print(f"\nDone. {ok} uploaded, {failed} failed.")
    if ok:
        print(f"Dataset: https://huggingface.co/datasets/{repo_id}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo-id", default="akcit-rl/infogainme-runs")
    p.add_argument("--outputs-dir", type=Path, default=Path("outputs"))
    p.add_argument("--token", default=None,
                   help="HF write token (default: HF_TOKEN env var)")
    p.add_argument("--batch-size", type=int, default=40,
                   help="Files per commit (default: 40). HF caps ~128 commits/hour, "
                        "so one commit per file gets 429-throttled.")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be uploaded without uploading")
    args = p.parse_args()

    token = args.token or os.getenv("HF_TOKEN")
    if not token and not args.dry_run:
        print("ERROR: HF_TOKEN not set. Pass --token or export HF_TOKEN.", file=sys.stderr)
        return 1

    outputs_dir = args.outputs_dir.resolve()
    if not outputs_dir.exists():
        print(f"ERROR: outputs dir not found: {outputs_dir}", file=sys.stderr)
        return 1

    print(f"Scanning {outputs_dir} for canonical experiments…")
    pairs = collect_upload_pairs(outputs_dir)

    if not pairs:
        print("Nothing to upload.")
        return 0

    # summary by model
    from collections import Counter
    model_counts: Counter = Counter()
    for _, repo_path in pairs:
        parts = Path(repo_path).parts
        if len(parts) >= 2 and parts[0] == "models":
            model_counts[parts[1]] += 1

    print(f"\nCanonical model dirs ({len(model_counts)}):")
    for model, n in sorted(model_counts.items()):
        print(f"  {model}  ({n} files)")

    upload(pairs, args.repo_id, token, args.batch_size, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
