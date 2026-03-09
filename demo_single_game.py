#!/usr/bin/env python3
"""Demo for geographic dataset.

Loads cities from CSV and runs a single game.
"""

from os import getenv
from dotenv import load_dotenv
from src.orchestrator import Orchestrator
from src.agents.llm_adapter import LLMConfig
from src.data_types import ObservabilityMode
from src.domain.geo.loader import load_geo_candidates
from src.benchmark_config import BenchmarkConfig
from pathlib import Path
from random import choice
import os

OPENAI_API_KEY = getenv("OPENAI_API_KEY")
OBSERVABILITY_MODE = ObservabilityMode.PARTIALLY_OBSERVABLE
MAX_TURNS = 15
CSV_PATH = Path("data/top_10_pop_cities.csv")
OUTPUT_PATH = Path("outputs")
MODEL = "gpt-4o-mini"

os.makedirs(OUTPUT_PATH, exist_ok=True)


def main() -> None:
    """Run the benchmark demonstration."""
    load_dotenv()

    print("Clary Quest - Geographic Benchmark")
    print("=" * 50)

    pool, domain_config = load_geo_candidates(csv_path=CSV_PATH)
    candidates = pool.get_active()

    print(f"Candidate Pool: {len(candidates)} cities")
    for c in sorted(candidates, key=lambda c: c.label)[:10]:
        attrs_str = ", ".join(f"{k}={v}" for k, v in c.attrs.items())
        print(f"   - {c.id}: {c.label} ({attrs_str})")

    llm_config = LLMConfig(model=MODEL, api_key=OPENAI_API_KEY)
    bm_config = BenchmarkConfig(
        seeker_config=llm_config,
        oracle_config=llm_config,
        pruner_config=llm_config,
        observability_mode=OBSERVABILITY_MODE,
        max_turns=MAX_TURNS,
    )

    target = choice(candidates)

    orchestrator = Orchestrator.from_target(
        target=target,
        pool=pool,
        seeker_config=bm_config.seeker_config,
        oracle_config=bm_config.oracle_config,
        pruner_config=bm_config.pruner_config,
        observability_mode=bm_config.observability_mode,
        max_turns=bm_config.max_turns,
    )

    print(f"\nConfiguration:")
    print(f"   - Target: {target.id} ({target.label})")
    print(f"   - Seeker observability: {bm_config.observability_mode.name}")
    print(f"   - Max turns: {bm_config.max_turns}")
    print(f"   - Model: {bm_config.seeker_config.model}")

    print(f"\nStarting benchmark run...")
    print("   (This may take a moment as agents generate responses...)\n")

    orchestrator.run(debug=True)

    if orchestrator.turns:
        last_turn = orchestrator.turns[-1]
        if last_turn.answer.game_over:
            print(f"\nSuccess! Seeker found the target in {len(orchestrator.turns)} turns!")
        else:
            print(f"\nGame ended after {len(orchestrator.turns)} turns without finding the target.")

    print("\nBenchmark completed!")


if __name__ == "__main__":
    main()
