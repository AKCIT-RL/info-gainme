"""Helpers to capture git state at runtime for experiment reproducibility."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path


def _run(args: list[str]) -> str | None:
    try:
        out = subprocess.run(
            args,
            cwd=Path(__file__).resolve().parent.parent.parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip() or None
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


@lru_cache(maxsize=1)
def get_git_info() -> dict[str, str | bool | None]:
    """Return current repo git state: commit, short commit, branch, dirty flag.

    Cached per-process — safe to call from every orchestrator instance.
    Returns all None/False if not inside a git repo.
    """
    commit = _run(["git", "rev-parse", "HEAD"])
    status = _run(["git", "status", "--porcelain"])
    return {
        "commit": commit,
        "commit_short": commit[:8] if commit else None,
        "branch": _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "dirty": bool(status) if status is not None else None,
    }
