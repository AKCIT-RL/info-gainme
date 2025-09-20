"""Benchmark runner without pruning.

Coordinates turns between `SeekerAgent` and `OracleAgent`, computes entropy
metrics with `Entropy`, and records `TurnState`. This version intentionally
omits the `PrunerAgent` and does not change the active set of nodes.
"""

from __future__ import annotations

from typing import List

from .entropy import Entropy
from .graph import KnowledgeGraph
from .data_types import TurnState, Question, Answer
from .agents.seeker import SeekerAgent
from .agents.oracle import OracleAgent


class BenchmarkRunner:
    """Runs a benchmark loop without pruning.

    Args:
        graph: Knowledge graph with nodes/edges and pruning state.
        seeker: SeekerAgent instance responsible for generating questions.
        oracle: OracleAgent instance responsible for generating answers.
        entropy: Entropy helper for computing entropy and information gain.
        max_turns: Maximum number of turns to execute.
        h_threshold: Optional entropy threshold to stop early.
    """

    def __init__(
        self,
        *,
        graph: KnowledgeGraph,
        seeker: SeekerAgent,
        oracle: OracleAgent,
        entropy: Entropy,
        max_turns: int,
        h_threshold: float | None = None,
    ) -> None:
        if graph is None:
            raise ValueError("graph cannot be None")
        if seeker is None:
            raise ValueError("seeker cannot be None")
        if oracle is None:
            raise ValueError("oracle cannot be None")
        if entropy is None:
            raise ValueError("entropy cannot be None")
        if max_turns <= 0:
            raise ValueError("max_turns must be > 0")

        self._graph = graph
        self._seeker = seeker
        self._oracle = oracle
        self._entropy = entropy
        self._max_turns = max_turns
        self._h_threshold = h_threshold

        self._current_turn: int = 0
        self._turns: List[TurnState] = []

    @property
    def turns(self) -> List[TurnState]:
        return self._turns

    @property
    def current_turn(self) -> int:
        return self._current_turn

    def run(self) -> None:
        """Execute the benchmark loop without pruning.

        The set of active nodes does not change in this mode. Entropy is
        computed before and after each turn and information gain is recorded
        (which will be zero without pruning).
        """
        for turn in range(1, self._max_turns + 1):
            self._current_turn = turn

            active_nodes = self._graph.get_active_nodes()
            h_before = self._entropy.compute(active_nodes)

            # Stop early if threshold satisfied
            if self._h_threshold is not None and h_before <= self._h_threshold:
                break

            # Seeker asks a question
            question: Question = self._seeker.question_to_oracle(active_nodes, turn)

            # Oracle receives and answers
            self._oracle.add_seeker_question(question)
            answer: Answer = self._oracle.answer_seeker()

            # Seeker integrates the oracle's answer and (optionally) context
            self._seeker.add_oracle_answer_and_pruning(answer, active_nodes, turn)

            # No pruning yet → active set unchanged
            h_after = self._entropy.compute(active_nodes)
            info_gain = self._entropy.info_gain(h_before, h_after)

            self._turns.append(
                TurnState(
                    turn_index=turn,
                    h_before=h_before,
                    h_after=h_after,
                    info_gain=info_gain,
                    pruned_count=0,
                    question=question,
                    answer=answer,
                )
            )

            # Optional: stop if entropy not changing across turns
            if self._h_threshold is not None and h_after <= self._h_threshold:
                break

    def get_summary(self) -> dict:
        """Return a simple summary of the run."""
        return {
            "turns": len(self._turns),
            "current_turn": self._current_turn,
            "h_start": self._turns[0].h_before if self._turns else None,
            "h_end": self._turns[-1].h_after if self._turns else None,
            "total_info_gain": sum(t.info_gain for t in self._turns),
        }


