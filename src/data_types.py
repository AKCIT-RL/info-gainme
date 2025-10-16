"""Shared types (skeleton).

Provides `TurnState`, `PruningResult`, and enums per UML.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ObservabilityMode(Enum):
    FULLY_OBSERVED = "FO"
    PARTIALLY_OBSERVED = "PO"


@dataclass
class Question:
    text: str


@dataclass
class Answer:
    text: str
    compliant: bool
    game_over: bool = False


@dataclass
class PruningResult:
    pruned_ids: set[str]
    rationale: str


@dataclass
class TurnState:
    turn_index: int
    h_before: float
    h_after: float
    info_gain: float
    pruned_count: int
    question: Question
    answer: Answer
    
    # Additional metadata for conversation export
    pruning_result: Optional[PruningResult] = None
    active_nodes_before: Optional[int] = None
    active_nodes_after: Optional[int] = None
    active_leaf_nodes_before: Optional[int] = None
    active_leaf_nodes_after: Optional[int] = None
    timestamp_start: Optional[str] = None
    timestamp_end: Optional[str] = None
    duration_seconds: Optional[float] = None
    graph_snapshot: Optional[str] = None


