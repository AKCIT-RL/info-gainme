#!/usr/bin/env python3
"""Demo for flat (non-hierarchical) object dataset.

Loads objects from CSV (objects_test.csv or objects_full.csv).
"""

from os import getenv
from dotenv import load_dotenv
from random import choice

from src.orchestrator import Orchestrator
from src.agents.llm_config import LLMConfig
from src.data_types import ObservabilityMode
from src.domain.objects import load_flat_object_candidates
from src.benchmark_config import BenchmarkConfig
from pathlib import Path
import os

OPENAI_API_KEY = getenv("OPENAI_API_KEY")
OBSERVABILITY_MODE = ObservabilityMode.FULLY_OBSERVABLE
MAX_TURNS = 20
OUTPUT_PATH = Path("outputs")
OBJECTS_CSV = Path("data/objects/objects_test.csv")  # or objects_full.csv
MODEL = "gpt-4o-mini"

os.makedirs(OUTPUT_PATH, exist_ok=True)


def main() -> None:
    """Run the benchmark with flat object dataset."""
    load_dotenv()

    print("Clary Quest - Objects Benchmark (non-hierarchical)")
    print("=" * 50)

    pool, domain_config = load_flat_object_candidates(csv_path=OBJECTS_CSV)
    candidates = pool.get_active()

    print(f"Candidate Pool: {len(candidates)} objects")
    categories: dict = {}
    for c in candidates:
        cat = c.attrs.get("category", "other")
        categories.setdefault(cat, []).append(c.label)
    for cat in sorted(categories.keys()):
        print(f"   {cat}: {len(categories[cat])} items")

    llm_config = LLMConfig(model=MODEL, api_key=OPENAI_API_KEY)
    bm_config = BenchmarkConfig(
        seeker_config=llm_config,
        oracle_config=llm_config,
        pruner_config=llm_config,
        observability_mode=OBSERVABILITY_MODE,
        max_turns=MAX_TURNS,
        domain_config=domain_config,
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
        domain_config=domain_config,
    )

    print(f"\nConfiguration:")
    print(f"   - Target: {target.id} ({target.label})")
    print(f"   - Category: {target.attrs.get('category')}")
    print(f"   - Seeker observability: {bm_config.observability_mode.name}")
    print(f"   - Max turns: {bm_config.max_turns}")
    print(f"   - Model: {bm_config.seeker_config.model}")

    print(f"\nStarting benchmark run...\n")

    orchestrator.run(debug=True)

    if orchestrator.turns:
        last_turn = orchestrator.turns[-1]
        if last_turn.answer.game_over:
            print(
                f"\nSuccess! Seeker found the target in {len(orchestrator.turns)} turns!"
            )
        else:
            print(
                f"\nGame ended after {len(orchestrator.turns)} turns without finding the target."
            )

    print("\nBenchmark completed!")


if __name__ == "__main__":
    main()
