#!/usr/bin/env python3
"""Demo for diseases dataset.

Loads diseases from CSV (diseases_test.csv or diseases_full.csv).
Preprocess first: python scripts/prepare_diseases_csv.py
"""

from os import getenv
from dotenv import load_dotenv
from random import choice

from src.orchestrator import Orchestrator
from src.agents.llm_config import LLMConfig
from src.data_types import ObservabilityMode
from src.domain.diseases import load_flat_disease_candidates
from src.benchmark_config import BenchmarkConfig
from pathlib import Path
import os

OPENAI_API_KEY = getenv("OPENAI_API_KEY")
OBSERVABILITY_MODE = ObservabilityMode.FULLY_OBSERVABLE
MAX_TURNS = 20
OUTPUT_PATH = Path("outputs")
DISEASES_CSV = Path("data/diseases/diseases_test.csv")
MODEL = "gpt-4o-mini"

os.makedirs(OUTPUT_PATH, exist_ok=True)


def main() -> None:
    """Run the benchmark with diseases dataset."""
    load_dotenv()

    print("Clary Quest - Diseases Benchmark")
    print("=" * 50)

    pool, domain_config = load_flat_disease_candidates(csv_path=DISEASES_CSV)
    candidates = pool.get_active()

    print(f"Candidate Pool: {len(candidates)} diseases")

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
    symptoms = target.attrs.get("symptoms", [])
    print(f"   - Symptoms count: {len(symptoms)}")
    if symptoms:
        print(f"   - Sample symptoms: {symptoms[:5]}")
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
