"""Geo graph loader.

Loads a hierarchical geographic graph from `data/world_flat.csv` for the benchmark.
Creates a KnowledgeGraph with region -> subregion -> country -> state -> city hierarchy.
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path
from typing import Set
import sys
from pathlib import Path

# Add src to path for absolute imports
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from graph import KnowledgeGraph, Node, Edge



def create_sample_graph() -> KnowledgeGraph:
    """Create a small knowledge graph for testing."""
    nodes = {
        Node(
            id="paris", 
            label="Paris", 
            attrs={"continent": "europe", "country": "france", "capital": "true", "population": "2161000"}
        ),
        Node(
            id="london", 
            label="London", 
            attrs={"continent": "europe", "country": "uk", "capital": "true", "population": "8982000"}
        ),
        Node(
            id="berlin", 
            label="Berlin", 
            attrs={"continent": "europe", "country": "germany", "capital": "true", "population": "3669000"}
        ),
        Node(
            id="rome", 
            label="Rome", 
            attrs={"continent": "europe", "country": "italy", "capital": "true", "population": "2873000"}
        ),
        Node(
            id="madrid", 
            label="Madrid", 
            attrs={"continent": "europe", "country": "spain", "capital": "true", "population": "3223000"}
        ),
    }
    return KnowledgeGraph(nodes=nodes)


def load_geo_graph(
    csv_path: Path
    ) -> KnowledgeGraph:
    """Load geographic knowledge graph from world_flat.csv.
    
    Creates a hierarchical graph: region -> subregion -> country -> state -> city.
    Samples unique cities and builds the complete hierarchy.
    
    Args:
        csv_path: Path to the CSV file containing the geographic data.
        
    Returns:
        KnowledgeGraph with geographic hierarchy.
        
    Raises:
        FileNotFoundError: If data/world_flat.csv doesn't exist.
        ValueError: If insufficient data after filtering.
    """
    # Load data
    assert csv_path.exists(), f"Data file not found: {csv_path}"
    
    df_flat = pd.read_csv(csv_path, low_memory=False)
    
    # Use correct column names from the dataset
    col_city_id = "city_id"
    col_city_name = "city_name"
    col_state_id = "state_id"
    col_state_name = "state_name"
    col_country_id = "country_id"
    col_country_name = "country_name"
    col_region_id = "region_id"
    col_region_name = "region_name"
    col_subregion_id = "subregion_id"
    col_subregion_name = "subregion_name"
    
    # Keep relevant columns and filter
    cols_needed = [
        col_city_id, col_city_name,
        col_state_id, col_state_name,
        col_country_id, col_country_name,
        col_region_id, col_region_name,
        col_subregion_id, col_subregion_name,
    ]
    
    df_min = df_flat[cols_needed].dropna(subset=[col_city_id, col_state_id, col_country_id]).copy()
    
    unique_cities = df_min.drop_duplicates(subset=[col_city_id])
    
    # Build graph
    nodes: Set[Node] = set()
    edges: Set[Edge] = set()
    
    # Helper to create stable node IDs
    def make_node_id(kind: str, id_val: int) -> str:
        return f"{kind}:{int(id_val)}"
    
    # Add regions (layer 0)
    for _, row in unique_cities[[col_region_id, col_region_name]].drop_duplicates().iterrows():
        if pd.notna(row[col_region_id]):
            node_id = make_node_id("region", row[col_region_id])
            node = Node(
                id=node_id,
                label=str(row[col_region_name]),
                attrs={"type": "region", "layer": 0}
            )
            nodes.add(node)
    
    # Add subregions (layer 1)
    for _, row in unique_cities[[col_subregion_id, col_subregion_name, col_region_id]].drop_duplicates().iterrows():
        if pd.notna(row[col_subregion_id]):
            node_id = make_node_id("subregion", row[col_subregion_id])
            nodes.add(Node(
                id=node_id,
                label=str(row[col_subregion_name]),
                attrs={"type": "subregion", "layer": 1}
            ))
            
            # Connect to region if available
            if pd.notna(row[col_region_id]):
                region_id = make_node_id("region", row[col_region_id])
                edges.add(Edge(
                    source_id=region_id,
                    target_id=node_id,
                    relation="contains"
                ))
    
    # Add countries (layer 2)
    for _, row in unique_cities[[col_country_id, col_country_name, col_subregion_id, col_region_id]].drop_duplicates().iterrows():
        if pd.notna(row[col_country_id]):
            node_id = make_node_id("country", row[col_country_id])
            nodes.add(Node(
                id=node_id,
                label=str(row[col_country_name]),
                attrs={"type": "country", "layer": 2}
            ))
            
            # Connect to subregion or region
            if pd.notna(row[col_subregion_id]):
                subregion_id = make_node_id("subregion", row[col_subregion_id])
                edges.add(Edge(
                    source_id=subregion_id,
                    target_id=node_id,
                    relation="contains"
                ))
            elif pd.notna(row[col_region_id]):
                region_id = make_node_id("region", row[col_region_id])
                edges.add(Edge(
                    source_id=region_id,
                    target_id=node_id,
                    relation="contains"
                ))
    
    # Add states (layer 3)
    for _, row in unique_cities[[col_state_id, col_state_name, col_country_id]].drop_duplicates().iterrows():
        if pd.notna(row[col_state_id]):
            node_id = make_node_id("state", row[col_state_id])
            nodes.add(Node(
                id=node_id,
                label=str(row[col_state_name]),
                attrs={"type": "state", "layer": 3}
            ))
            
            # Connect to country
            if pd.notna(row[col_country_id]):
                country_id = make_node_id("country", row[col_country_id])
                edges.add(Edge(
                    source_id=country_id,
                    target_id=node_id,
                    relation="contains"
                ))
    
    # Add cities (layer 4)
    for _, row in unique_cities[[col_city_id, col_city_name, col_state_id]].iterrows():
        if pd.notna(row[col_city_id]):
            node_id = make_node_id("city", row[col_city_id])
            nodes.add(Node(
                id=node_id,
                label=str(row[col_city_name]),
                attrs={"type": "city", "layer": 4}
            ))
            
            # Connect to state
            if pd.notna(row[col_state_id]):
                state_id = make_node_id("state", row[col_state_id])
                edges.add(Edge(
                    source_id=state_id,
                    target_id=node_id,
                    relation="contains"
                ))
    
    return KnowledgeGraph(nodes=nodes, edges=edges)


if __name__ == "__main__":
    # Test the loader
    try:
        graph = load_geo_graph(Path("data/top_10_pop_cities.csv"))
        print(f"Loaded graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

        graph.plot(output_path="output/sample_graph.png")
        text_graph = graph.graph_to_text()
        
        with open("output/sample_graph.txt", "w") as f:
            f.write(text_graph)
        
        # Show sample nodes by type
        nodes_by_type = {}
        for node in graph.nodes:
            node_type = node.attrs.get("type", "unknown")
            nodes_by_type.setdefault(node_type, []).append(node.label)
        
        for node_type, labels in nodes_by_type.items():
            print(f"{node_type}: {len(labels)} items")
            if len(labels) <= 3:
                print(f"  Examples: {', '.join(labels)}")
            else:
                print(f"  Examples: {', '.join(labels[:3])}...")
                
    except Exception as e:
        print(f"Error loading graph: {e}")
