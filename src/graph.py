"""Knowledge graph core models and operations.

Implements `KnowledgeGraph`, `Node`, and `Edge` with minimal yet typed API.
The graph maintains a set of pruned node ids and exposes methods to retrieve
active nodes and to apply pruning operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Set, Optional
from types import MappingProxyType


@dataclass(frozen=True)
class Node:
    """Graph node.

    Attributes:
        id: Unique node identifier.
        label: Human-readable label/name.
        attrs: Arbitrary attributes dictionary (immutable).
    """

    id: str
    label: str
    attrs: MappingProxyType[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    
    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(frozen=True)
class Edge:
    """Directed edge between nodes.

    Attributes:
        source_id: Source node id.
        target_id: Target node id.
        relation: Relation label (e.g., "contains", "located_in").
    """

    source_id: str
    target_id: str
    relation: str


class KnowledgeGraph:
    """In-memory knowledge graph with pruning state.

    Args:
        nodes: Optional iterable of initial nodes.
        edges: Optional iterable of initial edges.
    """

    def __init__(self, nodes: Iterable[Node] | None = None, edges: Iterable[Edge] | None = None) -> None:
        self.nodes: Set[Node] = set(nodes or [])
        self.edges: Set[Edge] = set(edges or [])
        self.pruned_ids: Set[str] = set()

    def get_active_nodes(self) -> Set[Node]:
        """Return nodes that have not been pruned."""
        return {n for n in self.nodes if n.id not in self.pruned_ids}

    def apply_pruning(self, pruned: Set[str]) -> None:
        """Apply pruning by adding node ids to the internal pruned set.

        Args:
            pruned: Set of node ids to mark as pruned.
        """
        if not pruned:
            return
        self.pruned_ids.update(pruned)

    def plot(
        self,
        output_path: Optional[str] = None,
        *,
        show_pruned: bool = False,
        node_size: int = 300,
        figsize: tuple[int, int] = (10, 8),
        title: str = "Knowledge Graph",
    ) -> None:
        """Plot the knowledge graph using networkx and matplotlib.

        Args:
            output_path: If provided, save plot to this path instead of showing.
            show_pruned: If True, show pruned nodes with different styling.
            node_size: Size of nodes in the plot.
            figsize: Figure size (width, height).
            title: Plot title.

        Raises:
            ImportError: If networkx or matplotlib are not available.
        """
        try:
            import networkx as nx
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise ImportError(
                "Plotting requires networkx and matplotlib. "
                "Install with: pip install networkx matplotlib"
            ) from exc

        # Create directed graph
        G = nx.DiGraph()

        # Add nodes
        active_ids = {n.id for n in self.get_active_nodes()}
        for node in self.nodes:
            is_active = node.id in active_ids
            if is_active or show_pruned:
                G.add_node(node.id, label=node.label, active=is_active)

        # Add edges
        for edge in self.edges:
            if G.has_node(edge.source_id) and G.has_node(edge.target_id):
                G.add_edge(edge.source_id, edge.target_id, relation=edge.relation)

        if not G.nodes():
            print("No nodes to plot.")
            return

        # Create plot
        fig, ax = plt.subplots(figsize=figsize)

        # Use hierarchical layout if possible, fallback to spring layout
        try:
            pos = nx.nx_agraph.graphviz_layout(G, prog="dot")
        except (ImportError, Exception):
            try:
                pos = nx.spring_layout(G, k=1, iterations=50)
            except Exception:
                pos = nx.random_layout(G)

        # Color nodes based on status
        node_colors = []
        for node_id in G.nodes():
            if G.nodes[node_id].get("active", True):
                node_colors.append("lightblue")
            else:
                node_colors.append("lightcoral")

        # Draw the graph
        nx.draw_networkx_nodes(
            G, pos, node_color=node_colors, node_size=node_size, ax=ax
        )
        nx.draw_networkx_edges(G, pos, edge_color="gray", arrows=True, ax=ax)

        # Add labels
        labels = {node_id: G.nodes[node_id]["label"] for node_id in G.nodes()}
        nx.draw_networkx_labels(G, pos, labels, font_size=8, ax=ax)

        # Add edge labels
        edge_labels = nx.get_edge_attributes(G, "relation")
        nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=6, ax=ax)

        ax.set_title(title)
        ax.axis("off")

        # Legend
        if show_pruned and self.pruned_ids:
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor="lightblue", label="Active nodes"),
                Patch(facecolor="lightcoral", label="Pruned nodes"),
            ]
            ax.legend(handles=legend_elements, loc="upper right")

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            print(f"Plot saved to: {output_path}")
        else:
            plt.show()

        plt.close()


if __name__ == "__main__":
    # Self-tests similares ao adapter, sem dependências externas.

    def _build_sample_graph() -> KnowledgeGraph:
        # A -> B -> C
        a = Node(id="A", label="Region A")
        b = Node(id="B", label="Region B")
        c = Node(id="C", label="Region C")
        e1 = Edge(source_id="A", target_id="B", relation="contains")
        e2 = Edge(source_id="B", target_id="C", relation="contains")
        return KnowledgeGraph(nodes=[a, b, c], edges=[e1, e2])

    def _test_active_and_pruning() -> None:
        kg = _build_sample_graph()
        active = kg.get_active_nodes()
        assert {n.id for n in active} == {"A", "B", "C"}

        kg.apply_pruning({"B"})
        active_after = kg.get_active_nodes()
        assert {n.id for n in active_after} == {"A", "C"}
        assert "B" in kg.pruned_ids

        # idempotência de aplicar poda vazia
        kg.apply_pruning(set())
        assert {n.id for n in kg.get_active_nodes()} == {"A", "C"}

    def _test_plot() -> None:
        kg = _build_sample_graph()
        kg.apply_pruning({"B"})
        
        # Test plot to file (should work if dependencies available)
        try:
            kg.plot(output_path="outputs/test_graph.png", show_pruned=True, title="Test Graph")
            print("Plot test: OK (saved to outputs/test_graph.png)")
        except ImportError:
            print("Plot test: SKIPPED (networkx/matplotlib not available)")
        except Exception as e:
            print(f"Plot test: WARNING ({e})")

    _test_active_and_pruning()
    _test_plot()
    print("KnowledgeGraph self-tests: OK")


