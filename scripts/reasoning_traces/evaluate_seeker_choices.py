#!/usr/bin/env python3
"""Evaluate Seeker's question choices by comparing information gain.

This script evaluates whether the Seeker made optimal choices by simulating
all considered questions and comparing their information gain.
"""

import argparse
import json
import sys
from pathlib import Path
from os import getenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from src.analysis.question_evaluator import evaluate_seeker_choices
from src.agents.llm_config import LLMConfig
from src.utils import ClaryLogger

load_dotenv()

logger = ClaryLogger.get_logger(__name__)


def main() -> int:
    """Main entry point for question evaluation."""
    parser = argparse.ArgumentParser(
        description="Evaluate Seeker's question choices by comparing information gain"
    )
    parser.add_argument(
        "conversation_dir",
        type=Path,
        help="Directory containing seeker_traces.json, turns.jsonl, metadata.json"
    )
    parser.add_argument(
        "--graph-csv",
        type=Path,
        default=Path("data/top_40_pop_cities.csv"),
        help="Path to CSV file for loading knowledge graph (default: data/top_40_pop_cities.csv)"
    )
    parser.add_argument(
        "--oracle-model",
        type=str,
        default=None,
        help="LLM model for Oracle simulation (default: use from metadata)"
    )
    parser.add_argument(
        "--pruner-model",
        type=str,
        default=None,
        help="LLM model for Pruner simulation (default: use from metadata)"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000/v1",
        help="Base URL for LLM API (e.g., http://localhost:8000/v1)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key for LLM (defaults to OPENAI_API_KEY env var)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file path (default: conversation_dir/question_evaluation.json)"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    ClaryLogger.configure()
    
    # Validate inputs
    if not args.conversation_dir.exists():
        logger.error("Conversation directory not found: %s", args.conversation_dir)
        return 1
    
    if not args.graph_csv.exists():
        logger.error("Graph CSV file not found: %s", args.graph_csv)
        return 1
    
    # Load metadata to get model configs
    metadata_path = args.conversation_dir / "metadata.json"
    if not metadata_path.exists():
        logger.error("metadata.json not found in %s", args.conversation_dir)
        return 1
    
    with metadata_path.open("r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    models_config = metadata.get("config", {}).get("models", {})
    oracle_model = args.oracle_model or models_config.get("oracle", "gpt-4o-mini")
    pruner_model = args.pruner_model or models_config.get("pruner", "gpt-4o-mini")
    
    logger.info("🔍 Evaluating Seeker Question Choices")
    logger.info("=" * 60)
    logger.info("📁 Conversation: %s", args.conversation_dir)
    logger.info("📊 Graph CSV: %s", args.graph_csv)
    logger.info("🤖 Oracle Model: %s", oracle_model)
    logger.info("🤖 Pruner Model: %s", pruner_model)
    
    # Create LLM configs
    oracle_config = LLMConfig(
        model=oracle_model,
        api_key=args.api_key,
        base_url=args.base_url
    )
    
    pruner_config = LLMConfig(
        model=pruner_model,
        api_key=args.api_key,
        base_url=args.base_url
    )
    
    # Evaluate choices
    try:
        results = evaluate_seeker_choices(
            conversation_dir=args.conversation_dir,
            graph_csv_path=args.graph_csv,
            oracle_config=oracle_config,
            pruner_config=pruner_config
        )
    except Exception as e:
        logger.error("Error evaluating choices: %s", e, exc_info=True)
        return 1
    
    # Save results
    output_path = args.output or (args.conversation_dir / "question_evaluation.json")
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info("\n--- Evaluation Results ---")
    logger.info("✅ Optimal choices: %d / %d (%.1f%%)",
                results["summary"]["optimal_choices"],
                results["summary"]["total_turns_evaluated"],
                results["summary"]["optimal_choice_rate"] * 100)
    logger.info("📊 Avg chosen info gain: %.3f", results["summary"]["avg_chosen_info_gain"])
    logger.info("📊 Avg optimal info gain: %.3f", results["summary"]["avg_optimal_info_gain"])
    logger.info("\n💾 Results saved to: %s", output_path)
    
    return 0


if __name__ == "__main__":
    exit(main())

