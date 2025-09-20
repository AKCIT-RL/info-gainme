#!/usr/bin/env python3
"""Main entry point for running the benchmark.

This script demonstrates the complete benchmark flow:
1. Load a simple knowledge graph
2. Set up Seeker and Oracle agents
3. Run the benchmark without pruning
4. Display results
"""

from os import getenv
from dotenv import load_dotenv

from src.runner import BenchmarkRunner
from src.graph import KnowledgeGraph, Node
from src.entropy import Entropy
from src.agents.llm_adapter import LLMAdapter, LLMConfig
from src.agents.seeker import SeekerAgent
from src.agents.oracle import OracleAgent
from src.data_types import ObservabilityMode


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


def main() -> None:
    """Run the benchmark demonstration."""
    load_dotenv()
    
    print("🎮 Clary Quest - Geographic Benchmark")
    print("=" * 50)
    
    # Create knowledge graph
    graph = create_sample_graph()
    active_nodes = graph.get_active_nodes()
    
    print(f"📍 Knowledge Graph: {len(active_nodes)} nodes")
    for node in sorted(active_nodes, key=lambda n: n.id):
        attrs_str = ", ".join(f"{k}={v}" for k, v in node.attrs.items())
        print(f"   - {node.id}: {node.label} ({attrs_str})")
    
    # Set up LLM configuration
    api_key = getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY not found in environment")
        print("   Please set your OpenAI API key in .env file or environment")
        return
    
    config = LLMConfig(
        model="gpt-4o-mini",
        api_key=api_key
    )
    
    # Create separate LLM adapters for each agent
    seeker_adapter = LLMAdapter(config)
    oracle_adapter = LLMAdapter(config)
    
    # Choose target randomly or fix it for testing
    target_node = next(n for n in active_nodes if n.id == "paris")
    
    # Create agents
    seeker = SeekerAgent(seeker_adapter, ObservabilityMode.FULLY_OBSERVED)
    oracle = OracleAgent(
        model="gpt-4o-mini",
        llm_adapter=oracle_adapter,
        target_node_id=target_node.id,
        target_node=target_node
    )
    
    # Create entropy calculator
    entropy = Entropy()
    
    # Create benchmark runner
    runner = BenchmarkRunner(
        graph=graph,
        seeker=seeker,
        oracle=oracle,
        entropy=entropy,
        max_turns=7,
        h_threshold=None,
    )
    
    print(f"\n🎯 Configuration:")
    print(f"   - Target: {oracle.target_node_id} ({target_node.label})")
    print(f"   - Seeker observability: {seeker.observability_mode.name}")
    print(f"   - Max turns: 7")
    print(f"   - Model: {config.model}")
    
    try:
        # Run the benchmark
        print(f"\n🚀 Starting benchmark run...")
        print("   (This may take a moment as agents generate responses...)\n")
        
        runner.run()
        
        # Show summary
        summary = runner.get_summary()
        print(f"📊 Benchmark Summary:")
        print(f"   - Turns completed: {summary['turns']}")
        if summary['h_start'] is not None:
            print(f"   - Initial entropy: {summary['h_start']:.3f}")
        if summary['h_end'] is not None:
            print(f"   - Final entropy: {summary['h_end']:.3f}")
        print(f"   - Total info gain: {summary['total_info_gain']:.3f}")
        
        # Show detailed turn history
        print(f"\n💬 Turn-by-Turn History:")
        for turn in runner.turns:
            print(f"\n🔄 Turn {turn.turn_index}:")
            print(f"   🤖 Seeker: \"{turn.question.text}\"")
            print(f"   🔮 Oracle: \"{turn.answer.text}\" (compliant: {turn.answer.compliant})")
            print(f"   📈 Entropy: {turn.h_before:.3f} → {turn.h_after:.3f} (gain: {turn.info_gain:.3f})")
            print(f"   ✂️  Pruned: {turn.pruned_count} nodes")
        
        # Show agent usage stats
        print(f"\n📊 Agent Statistics:")
        print(f"   - Seeker questions asked: {seeker.questions_asked}")
        print(f"   - Oracle answers given: {oracle.answers_given}")
        
        # Final result
        if runner.turns:
            last_turn = runner.turns[-1]
            if "paris" in last_turn.question.text.lower() and last_turn.answer.text.lower().strip() == "yes":
                print(f"\n🎉 Success! Seeker found the target in {len(runner.turns)} turns!")
            else:
                print(f"\n🤔 Game ended after {len(runner.turns)} turns without finding the target.")
        
    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        print("   This might be due to:")
        print("   - OpenAI API issues or rate limits")
        print("   - Network connectivity problems")
        print("   - Invalid API key")
        print(f"   - Error details: {type(e).__name__}")
    
    print("\n🎯 Benchmark completed!")


if __name__ == "__main__":
    main()
