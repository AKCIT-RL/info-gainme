#!/usr/bin/env python3
"""Download outputs/ from a HuggingFace Dataset repository.

Usage:
    python scripts/hf/download_from_hf.py
    python scripts/hf/download_from_hf.py --repo-id akcit-rl/info-gainme
    python scripts/hf/download_from_hf.py --outputs-dir outputs/ --num-workers 16
    python scripts/hf/download_from_hf.py --dry-run

Requirements:
    pip install huggingface_hub
    HF_TOKEN must be set in .env or as an environment variable.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import hf_hub_download, snapshot_download
from huggingface_hub.utils import EntryNotFoundError

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download outputs/ from a HuggingFace Dataset repository",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repo-id",
        type=str,
        default="akcit-rl/info-gainme",
        help="HuggingFace repository ID",
    )
    parser.add_argument(
        "--outputs-dir",
        type=Path,
        default=Path("outputs"),
        help="Local directory to download into",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="HuggingFace token (defaults to HF_TOKEN env var)",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=2,
        help="Parallel download workers",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be downloaded without downloading",
    )
    parser.add_argument(
        "--ignore-file",
        type=Path,
        default=None,
        help=(
            "File with glob patterns to ignore (one per line, # comments allowed). "
            "If omitted, defaults to <outputs-dir>/.hf-ignore when present."
        ),
    )

    args = parser.parse_args()

    token = args.token or os.getenv("HF_TOKEN")
    if not token:
        print(
            "Error: HuggingFace token not found.\n"
            "  Set HF_TOKEN in .env, export it as an env var, or pass --token <value>."
        )
        return 1

    outputs_dir = args.outputs_dir.resolve()
    repo_id = args.repo_id

    # Build ignore_patterns: always exclude loose conversations/ trees
    # (we only want conversations.zip). Append patterns from .hf-ignore
    # if provided / present.
    ignore_patterns: list[str] = ["**/conversations/**"]

    ignore_file = args.ignore_file
    if ignore_file is None:
        candidate = outputs_dir / ".hf-ignore"
        if candidate.exists():
            ignore_file = candidate

    if ignore_file and ignore_file.exists():
        extra = [
            line.strip()
            for line in ignore_file.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        # de-dupe while preserving order
        for pat in extra:
            if pat not in ignore_patterns:
                ignore_patterns.append(pat)
        print(f"Loaded {len(extra)} ignore patterns from {ignore_file}")

    if args.dry_run:
        print(f"[Dry run] Would download from: https://huggingface.co/datasets/{repo_id}")
        print(f"[Dry run] Destination: {outputs_dir}")
        print(f"[Dry run] workers={args.num_workers}")
        print(f"[Dry run] ignore_patterns ({len(ignore_patterns)}):")
        for pat in ignore_patterns:
            print(f"           {pat}")
        return 0

    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Pull the unified index CSV first so it's available for inspection even
    # if the full download is interrupted.
    index_filename = "unified_experiments.csv"
    print(f"Fetching index: {index_filename} ...")
    try:
        hf_hub_download(
            repo_id=repo_id,
            repo_type="dataset",
            filename=index_filename,
            local_dir=str(outputs_dir),
            token=token,
        )
        print(f"  → {outputs_dir / index_filename}\n")
    except EntryNotFoundError:
        print(f"  (index not found in repo — skipping)\n")
    except Exception as exc:
        print(f"  (index fetch failed: {exc} — continuing with full download)\n")

    print(f"Downloading {repo_id} → {outputs_dir} ...")
    print("Download is resumable — safe to interrupt and re-run.\n")

    max_attempts = 200
    for attempt in range(1, max_attempts + 1):
        try:
            snapshot_download(
                repo_id=repo_id,
                repo_type="dataset",
                local_dir=str(outputs_dir),
                local_dir_use_symlinks=False,
                token=token,
                max_workers=args.num_workers,
                # Conversations live inside conversations.zip (one per
                # experiment) — see scripts/hf/zip_experiments.py. The
                # loose conversations/ trees may still be present in the
                # repo from older uploads; ignore them so we don't pull
                # the same data twice. Extra patterns come from
                # .hf-ignore (see --ignore-file).
                ignore_patterns=ignore_patterns,
            )
            break
        except Exception as exc:
            if attempt == max_attempts:
                print(f"\nDownload failed after {attempt} attempts: {exc}")
                return 1
            delay = min(300, 2 ** attempt + (30 if "429" in str(exc) else 0))
            print(f"\nAttempt {attempt} failed ({exc}). Retrying in {delay}s...")
            time.sleep(delay)

    print(f"\nDone! Local copy at: {outputs_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
