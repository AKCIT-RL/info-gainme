#!/usr/bin/env python3
"""Run multi-game benchmark experiments using YAML configuration."""

import argparse
from os import getenv
from pathlib import Path
from dotenv import load_dotenv

from src.domain.geo.loader import load_geo_graph
from src.utils.config_loader import load_benchmark_config
from src.benchmark import BenchmarkRunner


def main() -> None:
    """Run the full benchmark experiment."""
    parser = argparse.ArgumentParser(description="Run benchmark experiments")
    parser.add_argument("--config", type=Path, default="benchmark_config.yaml")
    args = parser.parse_args()
    
    load_dotenv()
    api_key = getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY environment variable not set!")
        return
    
    try:
        benchmark_config, config = load_benchmark_config(args.config, api_key)
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return
    
    # Extract config values
    csv_path = Path(config["dataset"]["csv_path"])
    num_targets = config["dataset"]["num_targets"] 
    runs_per_target = config["dataset"]["runs_per_target"]
    output_base = Path(config["output"]["base_dir"])
    debug = config["debug"]["enabled"]
    
    # Load graph and select targets
    graph = load_geo_graph(csv_path=csv_path)
    all_cities = sorted(
        [n for n in graph.get_active_nodes() if n.attrs.get("type") == "city"],
        key=lambda n: n.id
    )
    target_cities = all_cities[:num_targets] if num_targets else all_cities
    
    print("🎯 Clary Quest - Multi-Game Benchmark")
    print(f"📊 Config: {args.config}")
    print(f"📊 Experiment: {benchmark_config.experiment_name}")
    print(f"📊 Models: {benchmark_config.seeker_config.model} | {benchmark_config.oracle_config.model} | {benchmark_config.pruner_config.model}")
    print(f"📊 Settings: {benchmark_config.observability_mode.name} | {benchmark_config.max_turns} turns | {runs_per_target} runs/target")
    print(f"📊 Target Cities: {len(target_cities)} | Total Games: {len(target_cities) * runs_per_target}")
    
    # Run benchmark
    runner = BenchmarkRunner(config=benchmark_config, output_base=output_base)
    csv_path = runner.run(
        graph=graph,
        targets=target_cities,
        runs_per_target=runs_per_target,
        debug=debug
    )
    
    print(f"\n✅ Benchmark Complete! Results: {csv_path}")


if __name__ == "__main__":
    main()

