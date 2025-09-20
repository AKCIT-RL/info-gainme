"""PrunerAgent implementation for deterministic rule-based pruning.

The PrunerAgent analyzes question-answer pairs and determines which nodes
should be pruned from the knowledge graph based on logical rules.
"""

from __future__ import annotations

from typing import Set

from ..data_types import Answer, PruningResult, Question
from ..graph import Node
from .llm_adapter import LLMAdapter


class PrunerAgent:
    """Agent that prunes nodes based on deterministic rules.
    
    This agent applies rule-based logic to eliminate nodes that are
    inconsistent with the Oracle's answers to Seeker's questions.
    """

    def __init__(
        self, 
        llm_adapter: LLMAdapter = None
        ) -> None:
        """Initialize the PrunerAgent.
        
        Args:
            llm_adapter: Optional LLMAdapter for advanced pruning strategies.
                 If None, uses only deterministic rules.
        """
        self._llm_adapter = llm_adapter
        self._pruning_operations = 0

    @property
    def pruning_operations(self) -> int:
        """Get the number of pruning operations performed."""
        return self._pruning_operations

    def prune(
        self, 
        active_nodes: Set[Node], 
        question: Question, 
        answer: Answer
    ) -> PruningResult:
        """Determine which nodes to prune based on question and answer.
        
        Args:
            active_nodes: Set of currently active nodes.
            question: The question that was asked.
            answer: The Oracle's answer to the question.
            
        Returns:
            PruningResult with node IDs to prune and rationale.
            
        Raises:
            ValueError: If inputs are invalid.
        """
        if not active_nodes:
            raise ValueError("No active nodes to prune")
        if not question.text:
            raise ValueError("Question cannot be empty")
        if not answer.text:
            raise ValueError("Answer cannot be empty")
            
        # Apply deterministic rules
        pruned_ids = self._apply_deterministic_rules(
            active_nodes, question.text, answer.text
        )
        
        # Generate rationale
        rationale = self._generate_rationale(question.text, answer.text, len(pruned_ids))
        
        # Track usage
        self._pruning_operations += 1
        
        return PruningResult(pruned_ids=pruned_ids, rationale=rationale)

    def _apply_deterministic_rules(
        self, 
        active_nodes: Set[Node], 
        question_text: str, 
        answer_text: str
    ) -> set[str]:
        """Apply deterministic pruning rules based on question and answer.
        
        Args:
            active_nodes: Set of active nodes to consider.
            question_text: The question that was asked.
            answer_text: The Oracle's answer.
            
        Returns:
            Set of node IDs to prune.
        """
        pruned_ids: set[str] = set()
        answer_lower = answer_text.lower().strip()
        question_lower = question_text.lower()
        
        # Rule 1: Geographic containment
        if "in europe" in question_lower:
            if answer_lower in ("yes", "y"):
                # Keep only European nodes, prune non-European
                pruned_ids.update(
                    node.id for node in active_nodes
                    if not self._is_in_region(node, "europe")
                )
            elif answer_lower in ("no", "n"):
                # Keep only non-European nodes, prune European
                pruned_ids.update(
                    node.id for node in active_nodes
                    if self._is_in_region(node, "europe")
                )
        
        # Rule 2: Capital city status
        elif "capital" in question_lower:
            if answer_lower in ("yes", "y"):
                # Keep only capitals, prune non-capitals
                pruned_ids.update(
                    node.id for node in active_nodes
                    if not self._is_capital(node)
                )
            elif answer_lower in ("no", "n"):
                # Keep only non-capitals, prune capitals
                pruned_ids.update(
                    node.id for node in active_nodes
                    if self._is_capital(node)
                )
        
        # Rule 3: Population size (basic heuristic)
        elif "million" in question_lower and "population" in question_lower:
            if answer_lower in ("yes", "y"):
                # Keep only large cities
                pruned_ids.update(
                    node.id for node in active_nodes
                    if not self._has_large_population(node)
                )
            elif answer_lower in ("no", "n"):
                # Keep only smaller cities
                pruned_ids.update(
                    node.id for node in active_nodes
                    if self._has_large_population(node)
                )
        
        # Rule 4: Coastal location
        elif "coastal" in question_lower:
            if answer_lower in ("yes", "y"):
                # Keep only coastal nodes
                pruned_ids.update(
                    node.id for node in active_nodes
                    if not self._is_coastal(node)
                )
            elif answer_lower in ("no", "n"):
                # Keep only inland nodes
                pruned_ids.update(
                    node.id for node in active_nodes
                    if self._is_coastal(node)
                )
        
        return pruned_ids

    def _is_in_region(self, node: Node, region: str) -> bool:
        """Check if node is in the specified region."""
        # Basic implementation using node attributes
        region_lower = region.lower()
        if "continent" in node.attrs:
            return node.attrs["continent"].lower() == region_lower
        # Fallback: check in label
        return region_lower in node.label.lower()

    def _is_capital(self, node: Node) -> bool:
        """Check if node is a capital city."""
        if "is_capital" in node.attrs:
            return bool(node.attrs["is_capital"])
        # Fallback: check in label
        return "capital" in node.label.lower()

    def _has_large_population(self, node: Node) -> bool:
        """Check if node has large population (>1M)."""
        if "population" in node.attrs:
            try:
                return int(node.attrs["population"]) > 1_000_000
            except (ValueError, TypeError):
                pass
        # Fallback: assume major cities in label
        major_indicators = ["city", "metropolis", "major"]
        return any(indicator in node.label.lower() for indicator in major_indicators)

    def _is_coastal(self, node: Node) -> bool:
        """Check if node is in a coastal location."""
        if "coastal" in node.attrs:
            return bool(node.attrs["coastal"])
        # Fallback: check in label
        coastal_indicators = ["port", "harbor", "coast", "sea"]
        return any(indicator in node.label.lower() for indicator in coastal_indicators)

    def _generate_rationale(self, question: str, answer: str, pruned_count: int) -> str:
        """Generate human-readable rationale for the pruning decision.
        
        Args:
            question: The question that was asked.
            answer: The Oracle's answer.
            pruned_count: Number of nodes pruned.
            
        Returns:
            Human-readable rationale string.
        """
        if pruned_count == 0:
            return f"No nodes to prune. Question '{question}' with answer '{answer}' did not match any pruning rules."
        
        return f"Pruned {pruned_count} nodes based on question '{question}' with answer '{answer}' using deterministic rules."


