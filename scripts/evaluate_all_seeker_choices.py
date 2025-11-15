#!/usr/bin/env python3
"""Evaluate Seeker's question choices for all conversations in a runs.csv.

This script reads a runs.csv file, extracts unique conversation directories,
and evaluates the Seeker's question choices for each conversation.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from os import getenv
from typing import List, Set, Dict, Any
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.question_evaluator import evaluate_seeker_choices
from src.agents.llm_config import LLMConfig
from src.utils import ClaryLogger

load_dotenv()

logger = ClaryLogger.get_logger(__name__)


def find_conversation_dirs_from_runs_csv(
    runs_csv_path: Path, 
    outputs_base_dir: Path
) -> List[Path]:
    """
    Reads a runs.csv file and returns a list of unique conversation directory paths.
    
    Args:
        runs_csv_path: Path to runs.csv file.
        outputs_base_dir: Base directory where conversation paths are relative to.
        
    Returns:
        List of conversation directory paths.
    """
    conversation_dirs = set()
    
    if not runs_csv_path.exists():
        raise FileNotFoundError(f"runs.csv not found: {runs_csv_path}")
    
    with runs_csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            conversation_path_str = row.get("conversation_path")
            if conversation_path_str:
                # conversation_path is relative to outputs_base_dir
                full_conversation_path = outputs_base_dir / conversation_path_str
                if full_conversation_path.exists():
                    conversation_dirs.add(full_conversation_path)
                else:
                    logger.warning("Conversation directory not found: %s", full_conversation_path)
    
    return sorted(list(conversation_dirs))


def process_single_conversation(
    conversation_dir: Path,
    graph_csv_path: Path,
    oracle_config: LLMConfig,
    pruner_config: LLMConfig,
    force: bool = False
) -> Dict[str, Any]:
    """Process a single conversation directory.
    
    Args:
        conversation_dir: Path to conversation directory.
        graph_csv_path: Path to CSV file for loading knowledge graph.
        oracle_config: LLM configuration for Oracle simulation.
        pruner_config: LLM configuration for Pruner simulation.
        force: Whether to overwrite existing question_evaluation.json.
        
    Returns:
        Dictionary with processing result.
    """
    output_path = conversation_dir / "question_evaluation.json"
    
    # Check if file exists and is valid (not empty/incomplete)
    if output_path.exists() and not force:
        try:
            with output_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                # Check if file is valid (has turns_evaluation and summary)
                if (data.get("turns_evaluation") and 
                    len(data.get("turns_evaluation", [])) > 0 and
                    data.get("summary")):
                    return {
                        "status": "skipped",
                        "conversation_dir": str(conversation_dir),
                        "output_path": str(output_path),
                        "reason": "already exists and valid"
                    }
                # File exists but is empty/incomplete - will reprocess
        except (json.JSONDecodeError, Exception) as e:
            # File exists but is corrupted - will reprocess
            logger.debug("Existing file is corrupted: %s", e)
    
    # Check if required files exist
    required_files = ["seeker_traces.json", "turns.jsonl", "metadata.json"]
    missing_files = [f for f in required_files if not (conversation_dir / f).exists()]
    if missing_files:
        return {
            "status": "error",
            "conversation_dir": str(conversation_dir),
            "output_path": str(output_path),
            "reason": f"Missing required files: {', '.join(missing_files)}"
        }
    
    try:
        results = evaluate_seeker_choices(
            conversation_dir,
            graph_csv_path,
            oracle_config,
            pruner_config
        )
        
        # Save results
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        return {
            "status": "success",
            "conversation_dir": str(conversation_dir),
            "output_path": str(output_path),
            "size_bytes": output_path.stat().st_size,
            "turns_evaluated": results["summary"]["total_turns_evaluated"],
            "optimal_choices": results["summary"]["optimal_choices"],
            "optimal_choice_rate": results["summary"]["optimal_choice_rate"]
        }
    except Exception as e:
        logger.error("Error processing %s: %s", conversation_dir, e, exc_info=True)
        return {
            "status": "error",
            "conversation_dir": str(conversation_dir),
            "output_path": str(output_path),
            "reason": str(e)
        }


def main():
    """Main entry point for batch evaluation."""
    parser = argparse.ArgumentParser(
        description="Evaluate Seeker's question choices for all conversations in a runs.csv"
    )
    parser.add_argument(
        "runs_csv_path",
        type=Path,
        help="Path to the runs.csv file"
    )
    parser.add_argument(
        "--outputs-base-dir",
        type=Path,
        default=Path("outputs"),
        help="Base directory where conversation paths in runs.csv are relative to (default: ./outputs)"
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
        default="Qwen3-8B",
        help="LLM model to use for Oracle simulation (default: Qwen3-8B)"
    )
    parser.add_argument(
        "--pruner-model",
        type=str,
        default="Qwen3-8B",
        help="LLM model to use for Pruner simulation (default: Qwen3-8B)"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000/v1",
        help="Base URL for LLM API (default: http://localhost:8000/v1)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key for LLM (defaults to OPENAI_API_KEY env var if not provided)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Temperature for LLM generation (default: None, API decides)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing question_evaluation.json files, even if valid"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Maximum number of parallel workers (default: 1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without actually processing"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    ClaryLogger.configure()
    
    logger.info("🔍 Evaluating Seeker Question Choices from runs.csv")
    logger.info("=" * 60)
    logger.info("📁 runs.csv: %s", args.runs_csv_path)
    logger.info("📁 Outputs base: %s", args.outputs_base_dir)
    logger.info("📊 Graph CSV: %s", args.graph_csv)
    logger.info("🤖 Oracle Model: %s", args.oracle_model)
    logger.info("🤖 Pruner Model: %s", args.pruner_model)
    if args.base_url:
        logger.info("🌐 Base URL: %s", args.base_url)
    if args.temperature is not None:
        logger.info("🌡️  Temperature: %s", args.temperature)
    logger.info("⚙️  Max workers: %s", args.max_workers)
    logger.info("🔄 Force: %s", args.force)
    
    # Find all conversation directories
    try:
        conversation_dirs = find_conversation_dirs_from_runs_csv(
            args.runs_csv_path, 
            args.outputs_base_dir
        )
    except FileNotFoundError as e:
        logger.error("Error: %s", e)
        return 1
    
    if not conversation_dirs:
        logger.error("No conversation directories found from %s", args.runs_csv_path)
        return 1
    
    logger.info("📊 Found %d unique conversation directories", len(conversation_dirs))
    
    if args.dry_run:
        logger.info("\n--- Dry Run: Conversations to be processed ---")
        for i, conv_dir in enumerate(conversation_dirs, 1):
            output_path = conv_dir / "question_evaluation.json"
            status = "Process"
            if output_path.exists():
                try:
                    with output_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                        if (data.get("turns_evaluation") and 
                            len(data.get("turns_evaluation", [])) > 0 and
                            data.get("summary")):
                            status = "Skip (exists and valid)"
                        else:
                            status = "Process (exists but invalid)"
                except (json.JSONDecodeError, Exception):
                    status = "Process (exists but corrupted)"
            logger.info("[%d/%d] %s: %s", i, len(conversation_dirs), status, conv_dir)
        logger.info("\nDry run complete. No conversations were actually processed.")
        return 0
    
    logger.info("\n🔄 Processing conversations...")
    
    # Create LLM configs for simulation
    oracle_config = LLMConfig(
        model=args.oracle_model,
        api_key=args.api_key or getenv("OPENAI_API_KEY"),
        base_url=args.base_url,
        temperature=args.temperature
    )
    pruner_config = LLMConfig(
        model=args.pruner_model,
        api_key=args.api_key or getenv("OPENAI_API_KEY"),
        base_url=args.base_url,
        temperature=args.temperature
    )
    
    results = []
    if args.max_workers > 1:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {
                executor.submit(
                    process_single_conversation,
                    conv_dir,
                    args.graph_csv,
                    oracle_config,
                    pruner_config,
                    args.force
                ): conv_dir 
                for conv_dir in conversation_dirs
            }
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                results.append(result)
                status_emoji = "✅" if result["status"] == "success" else "⏭️" if result["status"] == "skipped" else "❌"
                logger.info(
                    "[%d/%d] %s %s: %s", 
                    i, 
                    len(conversation_dirs), 
                    status_emoji,
                    result["status"].capitalize(), 
                    result["conversation_dir"]
                )
    else:
        try:
            from tqdm import tqdm
        except ImportError:
            def tqdm(iterable, *args, **kwargs):
                return iterable
        
        for i, conv_dir in enumerate(tqdm(conversation_dirs, desc="Evaluating conversations", unit="conv"), 1):
            result = process_single_conversation(
                conv_dir,
                args.graph_csv,
                oracle_config,
                pruner_config,
                args.force
            )
            results.append(result)
            status_emoji = "✅" if result["status"] == "success" else "⏭️" if result["status"] == "skipped" else "❌"
            logger.info(
                "[%d/%d] %s %s: %s", 
                i, 
                len(conversation_dirs), 
                status_emoji,
                result["status"].capitalize(), 
                result["conversation_dir"]
            )
    
    # Summary statistics
    success_count = sum(1 for r in results if r["status"] == "success")
    skipped_count = sum(1 for r in results if r["status"] == "skipped")
    error_count = sum(1 for r in results if r["status"] == "error")
    
    # Calculate aggregate statistics from successful evaluations
    successful_results = [r for r in results if r["status"] == "success"]
    if successful_results:
        total_turns = sum(r.get("turns_evaluated", 0) for r in successful_results)
        total_optimal = sum(r.get("optimal_choices", 0) for r in successful_results)
        avg_rate = sum(r.get("optimal_choice_rate", 0.0) for r in successful_results) / len(successful_results) if successful_results else 0.0
        
        logger.info("\n--- Evaluation Summary ---")
        logger.info("✅ Sucessos: %d", success_count)
        logger.info("⏭️  Pulados (já existentes e válidos): %d", skipped_count)
        logger.info("❌ Erros: %d", error_count)
        logger.info("Total processado/tentado: %d", len(conversation_dirs))
        logger.info("\n--- Aggregate Statistics (from successful evaluations) ---")
        logger.info("Total turns evaluated: %d", total_turns)
        logger.info("Total optimal choices: %d", total_optimal)
        logger.info("Average optimal choice rate: %.2f%%", avg_rate * 100)
    else:
        logger.info("\n--- Evaluation Summary ---")
        logger.info("✅ Sucessos: %d", success_count)
        logger.info("⏭️  Pulados (já existentes e válidos): %d", skipped_count)
        logger.info("❌ Erros: %d", error_count)
        logger.info("Total processado/tentado: %d", len(conversation_dirs))
    
    if error_count > 0:
        logger.error("Algumas conversas falharam na avaliação. Verifique os logs acima para detalhes.")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())

