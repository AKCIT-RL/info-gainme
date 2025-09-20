"""Entropy utilities for information theory calculations.

Implements Shannon entropy computation and information gain calculations
for measuring uncertainty reduction in the knowledge graph.
"""

from __future__ import annotations

import math
from typing import Set

from .graph import Node


class Entropy:
    """Shannon entropy calculator for knowledge graph nodes.
    
    Uses uniform distribution assumption: each active node has equal probability
    of being the target, providing a simple yet effective uncertainty measure.
    """

    @staticmethod
    def compute(active_nodes: Set[Node]) -> float:
        """Compute Shannon entropy for a set of active nodes.
        
        Args:
            active_nodes: Set of nodes that haven't been pruned.
            
        Returns:
            Shannon entropy in bits. Returns 0.0 for empty or single-node sets.
            
        Note:
            Uses uniform distribution: H = log2(N) where N = |active_nodes|.
            This assumes each node has equal probability of being the target.
        """
        n = len(active_nodes)
        if n <= 1:
            return 0.0
        return math.log2(n)

    @staticmethod
    def info_gain(h_before: float, h_after: float) -> float:
        """Calculate information gain from entropy reduction.
        
        Args:
            h_before: Entropy before an operation (e.g., before pruning).
            h_after: Entropy after an operation (e.g., after pruning).
            
        Returns:
            Information gain in bits. Always non-negative due to max(0, ...).
            
        Note:
            Information gain = H(before) - H(after). The max() ensures we never
            report negative gains due to floating-point precision issues.
        """

        info_gain = h_before - h_after
        # TODO: Add a weight that uses de level of the node
        
        return max(0.0, info_gain)


if __name__ == "__main__":
    # Self-tests para o módulo de entropia
    
    def _test_entropy_edge_cases() -> None:
        """Test entropy computation for edge cases."""
        # Empty set
        assert Entropy.compute(set()) == 0.0
        
        # Single node
        single_node = {Node(id="A", label="Node A")}
        assert Entropy.compute(single_node) == 0.0
    
    def _test_entropy_computation() -> None:
        """Test entropy computation for various set sizes."""
        
        # 2 nodes: H = log2(2) = 1.0
        nodes_2 = {
            Node(id="A", label="Node A"),
            Node(id="B", label="Node B")
        }
        assert abs(Entropy.compute(nodes_2) - 1.0) < 1e-10
        
        # 4 nodes: H = log2(4) = 2.0 
        nodes_4 = {
            Node(id="A", label="Node A"),
            Node(id="B", label="Node B"),
            Node(id="C", label="Node C"),
            Node(id="D", label="Node D")
        }
        assert abs(Entropy.compute(nodes_4) - 2.0) < 1e-10
        
        # 8 nodes: H = log2(8) = 3.0
        nodes_8 = {Node(id=f"node_{i}", label=f"Node {i}") for i in range(8)}
        assert abs(Entropy.compute(nodes_8) - 3.0) < 1e-10
    
    def _test_info_gain() -> None:
        """Test information gain calculation."""
        # Perfect gain: from 3 bits to 0 bits
        assert Entropy.info_gain(3.0, 0.0) == 3.0
        
        # Partial gain: from 4 bits to 2 bits  
        assert Entropy.info_gain(4.0, 2.0) == 2.0
        
        # No gain
        assert Entropy.info_gain(2.0, 2.0) == 0.0
        
        # Negative gain clamped to 0 (floating-point protection)
        assert Entropy.info_gain(1.0, 1.1) == 0.0
    
    def _test_realistic_scenario() -> None:
        """Test a realistic pruning scenario."""
        
        # Start with 16 nodes (4 bits of entropy)
        initial_nodes = {Node(id=f"city_{i}", label=f"City {i}") for i in range(16)}
        h_initial = Entropy.compute(initial_nodes)
        assert abs(h_initial - 4.0) < 1e-10
        
        # After pruning, 4 nodes remain (2 bits of entropy)
        remaining_nodes = {Node(id=f"city_{i}", label=f"City {i}") for i in range(4)}
        h_after = Entropy.compute(remaining_nodes)
        assert abs(h_after - 2.0) < 1e-10
        
        # Information gain should be 2 bits
        gain = Entropy.info_gain(h_initial, h_after)
        assert abs(gain - 2.0) < 1e-10

    _test_entropy_edge_cases()
    _test_entropy_computation()
    _test_info_gain()
    _test_realistic_scenario()
    print("Entropy self-tests: OK")


