"""Centralized logging configuration for clary_quest.

Call `setup_logging()` once at the application entry point.
All modules use `logging.getLogger(__name__)` to get their logger.
"""

from __future__ import annotations

import logging
import sys


def setup_logging(debug: bool = False) -> None:
    """Configure root logger with a timestamped format.

    Args:
        debug: If True, set level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if debug else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if called multiple times
    root.handlers.clear()
    root.addHandler(handler)
