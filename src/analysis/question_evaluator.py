"""Question evaluator for analyzing Seeker's question choices.

This module evaluates whether the Seeker made optimal choices by comparing
the information gain of the chosen question against all considered questions.

IMPORTANT: This module is READ-ONLY. It does NOT:
- Save or modify any plots (graph.plot() is never called)
- Save or modify any turn files (turns.jsonl, seeker.json, etc.)
- Export conversations (Orchestrator.export_conversation() is never called)
- Save graph snapshots (graph_to_text(save_to=...) is never called)

The only output is the evaluation results dictionary returned by evaluate_seeker_choices(),
which should be saved separately by the caller (e.g., in scripts/evaluate_seeker_choices.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from tqdm import tqdm

from ..domain.geo.loader import load_geo_graph
from ..graph import KnowledgeGraph, Node
from ..entropy import Entropy
from ..data_types import Question, Answer, PruningResult
from ..agents.oracle import OracleAgent
from ..agents.pruner import PrunerAgent
from ..agents.llm_adapter import LLMAdapter
from ..agents.llm_config import LLMConfig
from ..utils import ClaryLogger

logger = ClaryLogger.get_logger(__name__)


def load_turns_history(turns_jsonl_path: Path) -> List[Dict[str, Any]]:
    """Load turn history from turns.jsonl file.
    
    Args:
        turns_jsonl_path: Path to turns.jsonl file.
        
    Returns:
        List of turn dictionaries.
    """
    turns = []
    with turns_jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                turns.append(json.loads(line))
    return turns


def reconstruct_graph_state(
    graph: KnowledgeGraph,
    turns_history: List[Dict[str, Any]],
    up_to_turn: int
) -> KnowledgeGraph:
    """Reconstruct graph state by applying prunings up to a specific turn.
    
    Args:
        graph: Original knowledge graph (will be copied).
        turns_history: List of turn dictionaries from turns.jsonl.
        up_to_turn: Turn index (exclusive) - prunings from turns 1 to (up_to_turn-1) will be applied.
        
    Returns:
        Copy of graph with prunings applied.
    """
    graph_copy = KnowledgeGraph(nodes=graph.nodes.copy(), edges=graph.edges.copy())
    
    # Accumulate all pruned_ids from turns 1 to (up_to_turn - 1)
    all_pruned_ids: Set[str] = set()
    for turn in turns_history:
        if turn["turn_index"] < up_to_turn:
            pruning_result = turn.get("pruning_result", {})
            pruned_ids = pruning_result.get("pruned_ids", [])
            all_pruned_ids.update(pruned_ids)
    
    # Apply all prunings at once
    if all_pruned_ids:
        graph_copy.apply_pruning(all_pruned_ids)
    
    return graph_copy


def simulate_oracle_answer(
    question_text: str,
    target_node_id: str,
    target_node: Node,
    oracle_config: LLMConfig
) -> Answer:
    """Simulate Oracle's answer to a question.
    
    Args:
        question_text: The question to answer.
        target_node_id: ID of the target city.
        target_node: Target node object with full details.
        oracle_config: LLM configuration for Oracle.
        
    Returns:
        Answer object with simulated response.
    """
    # OracleAgent needs save_history=True because it appends system prompt in __init__
    oracle_adapter = LLMAdapter(oracle_config, save_history=True)
    oracle = OracleAgent(
        llm_adapter=oracle_adapter,
        target_node_id=target_node_id,
        target_node=target_node
    )
    
    question = Question(text=question_text)
    oracle.add_seeker_question(question)
    answer = oracle.answer_seeker()
    
    return answer


def simulate_pruning(
    graph: KnowledgeGraph,
    question_text: str,
    answer: Answer,
    turn_index: int,
    target_node_id: str,
    pruner_config: LLMConfig
) -> PruningResult:
    """Simulate pruning for a question-answer pair.
    
    Args:
        graph: Current graph state.
        question_text: The question asked.
        answer: Oracle's answer.
        turn_index: Current turn index.
        target_node_id: ID of the target city (must not be pruned).
        pruner_config: LLM configuration for Pruner.
        
    Returns:
        PruningResult with pruned node IDs.
    """
    pruner_adapter = LLMAdapter(pruner_config, save_history=False)
    pruner = PrunerAgent(pruner_adapter)
    
    # NOTE: graph_to_text() called without save_to parameter - read-only operation
    graph_text = graph.graph_to_text()
    active_leaf_nodes = graph.get_active_leaf_nodes()
    
    question = Question(text=question_text)
    pruning_result = pruner.analyze_and_prune(
        graph_text=graph_text,
        turn_index=turn_index,
        question=question,
        answer=answer,
        active_leaf_nodes=active_leaf_nodes,
        target_node_id=target_node_id
    )
    
    return pruning_result


def evaluate_question(
    question_text: str,
    graph: KnowledgeGraph,
    turn_index: int,
    target_node_id: str,
    target_node: Node,
    oracle_config: LLMConfig,
    pruner_config: LLMConfig
) -> Dict[str, Any]:
    """Evaluate a single question by simulating answer and pruning.
    
    Args:
        question_text: The question to evaluate.
        graph: Current graph state.
        turn_index: Current turn index.
        target_node_id: ID of the target city.
        target_node: Target node object.
        oracle_config: LLM configuration for Oracle.
        pruner_config: LLM configuration for Pruner.
        
    Returns:
        Dictionary with evaluation results including info_gain.
    """
    # Calculate entropy before
    active_leaf_nodes_before = graph.get_active_leaf_nodes()
    h_before = Entropy.compute(active_leaf_nodes_before)
    
    # Simulate Oracle answer
    logger.debug("  Simulating Oracle answer for: %s", question_text[:50] + "..." if len(question_text) > 50 else question_text)
    answer = simulate_oracle_answer(question_text, target_node_id, target_node, oracle_config)
    logger.debug("  Oracle answer: %s", answer.text)
    
    # Simulate pruning (create fresh copy with current state)
    graph_copy = KnowledgeGraph(nodes=graph.nodes.copy(), edges=graph.edges.copy())
    # Copy existing prunings to maintain state
    graph_copy.pruned_ids = graph.pruned_ids.copy()
    
    logger.debug("  Simulating pruning...")
    pruning_result = simulate_pruning(
        graph_copy,
        question_text,
        answer,
        turn_index,
        target_node_id,
        pruner_config
    )
    
    # Apply pruning
    graph_copy.apply_pruning(pruning_result.pruned_ids)
    
    # Calculate entropy after
    active_leaf_nodes_after = graph_copy.get_active_leaf_nodes()
    h_after = Entropy.compute(active_leaf_nodes_after)
    
    # Calculate information gain
    info_gain = Entropy.info_gain(h_before, h_after)
    logger.debug("  Info gain: %.3f (H: %.3f -> %.3f, pruned: %d)", 
                 info_gain, h_before, h_after, len(pruning_result.pruned_ids))
    
    return {
        "question": question_text,
        "simulated_answer": answer.text,
        "simulated_pruned_ids": list(pruning_result.pruned_ids),
        "pruned_count": len(pruning_result.pruned_ids),
        "h_before": h_before,
        "h_after": h_after,
        "info_gain": info_gain,
        "active_leaf_nodes_before": len(active_leaf_nodes_before),
        "active_leaf_nodes_after": len(active_leaf_nodes_after)
    }


def evaluate_turn(
    turn_data: Dict[str, Any],
    graph: KnowledgeGraph,
    turns_history: List[Dict[str, Any]],
    target_node_id: str,
    target_node: Node,
    oracle_config: LLMConfig,
    pruner_config: LLMConfig,
    questions_considered: List[str]
) -> Dict[str, Any]:
    """Evaluate a single turn by comparing all considered questions.
    
    Args:
        turn_data: Turn data from seeker_traces.json.
        graph: Original knowledge graph.
        turns_history: List of all turns from turns.jsonl.
        target_node_id: ID of the target city.
        target_node: Target node object.
        oracle_config: LLM configuration for Oracle.
        pruner_config: LLM configuration for Pruner.
        questions_considered: List of questions the Seeker considered.
        
    Returns:
        Dictionary with turn evaluation results.
    """
    turn_index = turn_data["turn_index"]
    chosen_question = turn_data["question"]
    
    # Reconstruct graph state at the beginning of this turn
    logger.info("  Reconstructing graph state for turn %d...", turn_index)
    graph_state = reconstruct_graph_state(graph, turns_history, turn_index)
    active_cities = len(graph_state.get_active_leaf_nodes())
    logger.info("  Active cities at turn %d: %d", turn_index, active_cities)
    
    # Evaluate all considered questions
    logger.info("  Evaluating %d considered questions...", len(questions_considered))
    questions_evaluation = []
    for question_text in tqdm(questions_considered, desc=f"    Turn {turn_index} questions", leave=False):
        logger.debug("    Evaluating: %s", question_text[:60] + "..." if len(question_text) > 60 else question_text)
        try:
            eval_result = evaluate_question(
                question_text,
                graph_state,
                turn_index,
                target_node_id,
                target_node,
                oracle_config,
                pruner_config
            )
            questions_evaluation.append(eval_result)
        except Exception as e:
            # If evaluation fails, still include the question with error info
            questions_evaluation.append({
                "question": question_text,
                "error": str(e),
                "info_gain": -1.0  # Mark as invalid
            })
    
    # Sort by info_gain (descending)
    questions_evaluation.sort(key=lambda x: x.get("info_gain", -1.0), reverse=True)
    
    # Find chosen question's rank and info_gain
    chosen_info_gain = None
    chosen_rank = None
    for i, eval_result in enumerate(questions_evaluation):
        if eval_result["question"] == chosen_question:
            chosen_info_gain = eval_result["info_gain"]
            chosen_rank = i + 1
            break
    
    # Get optimal question (highest info_gain)
    optimal_question = questions_evaluation[0]["question"] if questions_evaluation else None
    optimal_info_gain = questions_evaluation[0].get("info_gain", 0.0) if questions_evaluation else 0.0
    
    return {
        "turn_index": turn_index,
        "chosen_question": chosen_question,
        "chosen_info_gain": chosen_info_gain,
        "chosen_rank": chosen_rank,
        "optimal_question": optimal_question,
        "optimal_info_gain": optimal_info_gain,
        "was_optimal": chosen_rank == 1 if chosen_rank else False,
        "questions_evaluation": questions_evaluation,
        "total_considered": len(questions_considered)
    }


def evaluate_seeker_choices(
    conversation_dir: Path,
    graph_csv_path: Path,
    oracle_config: LLMConfig,
    pruner_config: LLMConfig
) -> Dict[str, Any]:
    """Evaluate Seeker's question choices for a complete game.
    
    This function is READ-ONLY. It only reads existing files and does NOT modify,
    overwrite, or create any plots, turns, or conversation files. The only output
    is the evaluation results dictionary (which should be saved separately by the caller).
    
    Args:
        conversation_dir: Directory containing seeker_traces.json, turns.jsonl, metadata.json.
        graph_csv_path: Path to CSV file for loading the knowledge graph.
        oracle_config: LLM configuration for Oracle simulation.
        pruner_config: LLM configuration for Pruner simulation.
        
    Returns:
        Dictionary with evaluation results for all turns.
        
    Note:
        - Does NOT call graph.plot() (no plots saved)
        - Does NOT call graph.graph_to_text(save_to=...) (no graph snapshots saved)
        - Does NOT use Orchestrator (no conversation export)
        - Only reads files, never writes (except for LLM API calls which are stateless)
    """
    # Load metadata
    logger.info("Loading metadata...")
    metadata_path = conversation_dir / "metadata.json"
    with metadata_path.open("r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    target_info = metadata["target"]
    target_node_id = target_info["id"]
    target_node = Node(
        id=target_node_id,
        label=target_info["label"],
        attrs=target_info.get("attrs", {})
    )
    logger.info("Target: %s (%s)", target_node.label, target_node_id)
    
    # Load seeker traces
    logger.info("Loading seeker traces...")
    seeker_traces_path = conversation_dir / "seeker_traces.json"
    with seeker_traces_path.open("r", encoding="utf-8") as f:
        seeker_traces = json.load(f)
    logger.info("Found %d turns in seeker traces", len(seeker_traces.get("history", [])))
    
    # Load turns history
    logger.info("Loading turns history...")
    turns_jsonl_path = conversation_dir / "turns.jsonl"
    turns_history = load_turns_history(turns_jsonl_path)
    logger.info("Loaded %d turns from history", len(turns_history))
    
    # Load graph
    logger.info("Loading knowledge graph from %s...", graph_csv_path)
    graph = load_geo_graph(graph_csv_path)
    logger.info("Graph loaded: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
    
    # Evaluate each turn
    logger.info("\nStarting evaluation of turns...")
    turns_evaluation = []
    history = seeker_traces.get("history", [])
    total_turns = len(history)
    
    # Filter turns with questions_considered for progress bar
    turns_with_questions = [(idx, td) for idx, td in enumerate(history, 1) 
                           if td.get("reasoning_trace", {}).get("questions_considered")]
    total_to_evaluate = len(turns_with_questions)
    
    logger.info("Found %d turns with questions_considered to evaluate", total_to_evaluate)
    
    for idx, turn_data in tqdm(turns_with_questions, desc="Evaluating turns", unit="turn", total=total_to_evaluate):
        turn_index = turn_data.get("turn_index", idx)
        reasoning_trace = turn_data.get("reasoning_trace", {})
        questions_considered = reasoning_trace.get("questions_considered", [])
        
        # This should not happen since we filtered, but keep for safety
        if not questions_considered:
            continue
        
        logger.info("\n[%d/%d] Evaluating turn %d (%d questions considered)...", 
                   idx, total_turns, turn_index, len(questions_considered))
        try:
            turn_eval = evaluate_turn(
                turn_data,
                graph,
                turns_history,
                target_node_id,
                target_node,
                oracle_config,
                pruner_config,
                questions_considered
            )
            was_optimal = turn_eval.get("was_optimal", False)
            chosen_ig = turn_eval.get("chosen_info_gain")
            optimal_ig = turn_eval.get("optimal_info_gain", 0.0)
            rank = turn_eval.get("chosen_rank")
            
            # Handle None values for logging
            rank_str = str(rank) if rank is not None else "?"
            ig_str = f"{chosen_ig:.3f}" if chosen_ig is not None else "?"
            logger.info("  Turn %d complete: %s (rank %s/%d, IG: %s, optimal: %.3f)", 
                       turn_index, "✅ Optimal" if was_optimal else "❌ Suboptimal", 
                       rank_str, len(questions_considered), ig_str, optimal_ig)
            turns_evaluation.append(turn_eval)
        except Exception as e:
            # Log error but continue
            logger.error("  Turn %d failed: %s", turn_index, e, exc_info=True)
            turns_evaluation.append({
                "turn_index": turn_index,
                "error": str(e)
            })
    
    # Calculate summary statistics
    logger.info("\nCalculating summary statistics...")
    optimal_choices = sum(1 for t in turns_evaluation if t.get("was_optimal", False))
    total_evaluated = len([t for t in turns_evaluation if "error" not in t])
    logger.info("Evaluation complete: %d turns evaluated, %d optimal choices", 
               total_evaluated, optimal_choices)
    
    # Calculate average chosen info gain (only for turns with valid chosen_info_gain)
    # Exclude None values and negative values (which indicate evaluation errors)
    valid_chosen_ig = [t.get("chosen_info_gain") for t in turns_evaluation 
                      if "error" not in t 
                      and t.get("chosen_info_gain") is not None 
                      and t.get("chosen_info_gain") >= 0.0]
    avg_chosen_ig = sum(valid_chosen_ig) / len(valid_chosen_ig) if valid_chosen_ig else 0.0
    
    # Calculate average optimal info gain
    avg_optimal_ig = sum(t.get("optimal_info_gain", 0.0) for t in turns_evaluation 
                        if "error" not in t) / total_evaluated if total_evaluated > 0 else 0.0
    
    # Calculate average number of questions considered per turn
    valid_turns_considered = [t.get("total_considered") for t in turns_evaluation 
                             if "error" not in t and t.get("total_considered") is not None]
    avg_questions_considered = sum(valid_turns_considered) / len(valid_turns_considered) if valid_turns_considered else 0.0
    
    # Count connection errors in question evaluations
    connection_errors = 0
    for turn_eval in turns_evaluation:
        if "error" not in turn_eval:  # Skip turns with evaluation errors
            questions_eval = turn_eval.get("questions_evaluation", [])
            for q_eval in questions_eval:
                error_msg = q_eval.get("error", "")
                if error_msg and ("Connection error" in error_msg or "Connection" in error_msg.lower()):
                    connection_errors += 1
    
    return {
        "conversation_dir": str(conversation_dir),
        "target": {
            "id": target_node_id,
            "label": target_node.label
        },
        "turns_evaluation": turns_evaluation,
        "summary": {
            "total_turns_evaluated": total_evaluated,
            "optimal_choices": optimal_choices,
            "optimal_choice_rate": optimal_choices / total_evaluated if total_evaluated > 0 else 0.0,
            "avg_chosen_info_gain": avg_chosen_ig,
            "avg_optimal_info_gain": avg_optimal_ig,
            "avg_questions_considered_per_turn": avg_questions_considered,
            "total_connection_errors": connection_errors
        }
    }

