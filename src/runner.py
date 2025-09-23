"""Benchmark runner with pruning support.

Coordinates turns between `SeekerAgent`, `OracleAgent`, and `PrunerAgent`, 
computes entropy metrics with `Entropy`, and records `TurnState`. 
Includes optional pruning functionality.
"""

from __future__ import annotations

from typing import List, Optional

from .entropy import Entropy
from .graph import KnowledgeGraph
from .data_types import TurnState, Question, Answer
from .agents.seeker import SeekerAgent
from .agents.oracle import OracleAgent
from .agents.pruner import PrunerAgent


class BenchmarkRunner:
    """Runs a benchmark loop with optional pruning.

    Args:
        graph: Knowledge graph with nodes/edges and pruning state.
        seeker: SeekerAgent instance responsible for generating questions.
        oracle: OracleAgent instance responsible for generating answers.
        entropy: Entropy helper for computing entropy and information gain.
        max_turns: Maximum number of turns to execute.
        h_threshold: Optional entropy threshold to stop early.
        pruner: Optional PrunerAgent for deterministic pruning.
    """

    def __init__(
        self,
        *,
        graph: KnowledgeGraph,
        seeker: SeekerAgent,
        oracle: OracleAgent,
        pruner: PrunerAgent,
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
        self._pruner = pruner

        self._current_turn: int = 0
        self._turns: List[TurnState] = []

    @property
    def turns(self) -> List[TurnState]:
        return self._turns

    @property
    def current_turn(self) -> int:
        return self._current_turn

    def show_turn(self, turn: TurnState) -> None:
        """Show the turn state with detailed information."""
        print(f"\n🔄 Turn {turn.turn_index}")
        print("=" * 50)
        
        # Show question and answer
        print(f"❓ Question: {turn.question.text}")
        print(f"💬 Answer: {turn.answer.text}")
        print(f"✅ Compliant: {turn.answer.compliant}")
        
        # Show entropy metrics
        print(f"📊 Entropy: {turn.h_before:.4f} → {turn.h_after:.4f}")
        print(f"📈 Info Gain: {turn.info_gain:.4f}")
        print(f"✂️  Pruned: {turn.pruned_count} nodes")
        
        # Show current active nodes count
        active_count = len(self._graph.get_active_nodes())
        print(f"🎯 Active Nodes: {active_count}")
        
        # Show progress
        progress = (turn.turn_index / self._max_turns) * 100
        print(f"⏳ Progress: {progress:.1f}% ({turn.turn_index}/{self._max_turns})")
        
        print("-" * 50)

    def run(self, debug: bool = False) -> None:
        """Execute the benchmark loop.

        Delegates pruning decisions to the configured `PrunerAgent`, which is LLM-driven. Entropy is computed before and after each turn.
        """
        for turn in range(1, self._max_turns + 1):
            self._current_turn = turn

            active_nodes = self._graph.get_active_nodes()
            h_before = self._entropy.compute(active_nodes)

            # Seeker asks a question
            question: Question = self._seeker.question_to_oracle(active_nodes, turn)

            # Oracle receives and answers
            self._oracle.add_seeker_question(question)
            answer: Answer = self._oracle.answer_seeker()

            # Seeker integrates the oracle's answer and (optionally) context
            self._seeker.add_oracle_answer_and_pruning(answer, active_nodes, turn)

            # Apply pruning via PrunerAgent (LLM-driven)
            pruned_count = 0
            graph_text = self._graph.graph_to_text()
            pruning_result = self._pruner.analyze_and_prune(
                graph_text=graph_text,
                turn_index=turn,
                question=question,
                answer=answer,
            )
            if pruning_result.pruned_ids:
                self._graph.apply_pruning(pruning_result.pruned_ids)
                pruned_count = len(pruning_result.pruned_ids)
                if debug:
                    print(f"🔍 Pruning: {pruning_result.rationale}")

            # Compute entropy after pruning
            h_after = self._entropy.compute(self._graph.get_active_nodes())
            info_gain = self._entropy.info_gain(h_before, h_after)

            self._turns.append(
                TurnState(
                    turn_index=turn,
                    h_before=h_before,
                    h_after=h_after,
                    info_gain=info_gain,
                    pruned_count=pruned_count,
                    question=question,
                    answer=answer,
                )
            )

            if debug:
                self.show_turn(self._turns[-1])
            
            # Check if game is over
            if answer.game_over:
                if debug:
                    print(f"\n🎉 Game Over! Seeker found the target in {turn} turns!")
                break
        
        # Show final summary if debug is enabled
        if debug and self._turns:
            print("\n🏁 Benchmark Complete!")
            print("=" * 50)
            summary = self.get_summary()
            print(f"📊 Total Turns: {summary['turns']}")
            print(f"📈 Start Entropy: {summary['h_start']:.4f}")
            print(f"📉 End Entropy: {summary['h_end']:.4f}")
            print(f"🎯 Total Info Gain: {summary['total_info_gain']:.4f}")
            print("=" * 50)


    def get_summary(self) -> dict:
        """Return a simple summary of the run."""
        return {
            "turns": len(self._turns),
            "current_turn": self._current_turn,
            "h_start": self._turns[0].h_before if self._turns else None,
            "h_end": self._turns[-1].h_after if self._turns else None,
            "total_info_gain": sum(t.info_gain for t in self._turns),
        }


