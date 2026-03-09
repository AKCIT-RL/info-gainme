#!/usr/bin/env python3
"""Run multi-game benchmark experiments using YAML configuration.

Supports both geographic (geo) and flat object/disease datasets via dataset.type in config.
"""

import argparse
from os import getenv
from pathlib import Path
from dotenv import load_dotenv

from src.domain.geo.loader import load_geo_candidates
from src.domain.objects import load_flat_object_candidates
from src.domain.diseases import load_flat_disease_candidates
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
        print("OPENAI_API_KEY environment variable not set!")
        return

    try:
        benchmark_config, config = load_benchmark_config(args.config, api_key)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return

    dataset_cfg = config.get("dataset", {})
    dataset_type = dataset_cfg.get("type", "geo")
    num_targets = dataset_cfg.get("num_targets")
    runs_per_target = dataset_cfg.get("runs_per_target", 1)
    output_base = Path(config["output"]["base_dir"])
    debug = config["debug"]["enabled"]

    if dataset_type == "objects":
        csv_path = Path(dataset_cfg["csv_path"])
        pool, _ = load_flat_object_candidates(csv_path=csv_path)
        all_targets = sorted(pool.candidates, key=lambda c: c.id)
    elif dataset_type == "diseases":
        csv_path = Path(dataset_cfg["csv_path"])
        pool, _ = load_flat_disease_candidates(csv_path=csv_path)
        all_targets = sorted(pool.candidates, key=lambda c: c.id)
    else:
        csv_path = Path(dataset_cfg["csv_path"])
        pool, _ = load_geo_candidates(csv_path=csv_path)
        all_targets = sorted(pool.candidates, key=lambda c: c.id)

    targets = all_targets[:num_targets] if num_targets else all_targets
    total_games = len(targets) * runs_per_target

    print("Clary Quest - Multi-Game Benchmark")
    print(f"Config: {args.config}")
    print(f"Dataset: {dataset_type} | Targets: {len(targets)} | Runs/target: {runs_per_target}")
    print(f"Experiment: {benchmark_config.experiment_name}")
    print(f"Models: {benchmark_config.seeker_config.model} | {benchmark_config.oracle_config.model} | {benchmark_config.pruner_config.model}")
    print(f"Settings: {benchmark_config.observability_mode.name} | {benchmark_config.max_turns} turns")
    print(f"Total games: {total_games}")

    runner = BenchmarkRunner(config=benchmark_config, output_base=output_base)
    csv_path = runner.run(
        pool=pool,
        targets=targets,
        runs_per_target=runs_per_target,
        debug=debug,
    )

    print(f"\nBenchmark complete. Results: {csv_path}")


if __name__ == "__main__":
    main()
