"""BenchmarkRunner for multi-game experiments.

Runs multiple games across targets and writes incremental results to CSV.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable
import csv
import json

from .benchmark_config import BenchmarkConfig
from .graph import KnowledgeGraph, Node
from .orchestrator import Orchestrator


def _safe_name(text: str) -> str:
    return (
        text.replace("/", "-")
        .replace("\\", "-")
        .replace(":", "-")
        .replace(" ", "_")
    )


class BenchmarkRunner:
    """Run multi-game benchmarks and persist results incrementally.

    Attributes:
        config: Benchmark configuration grouping agent models and options.
        output_base: Base directory to store results.
    """

    def __init__(self, config: BenchmarkConfig, output_base: str | Path = "outputs") -> None:
        self.config = config
        self.output_base = Path(output_base)

    def _output_dir(self) -> Path:
        seeker = _safe_name(self.config.seeker_config.model)
        oracle = _safe_name(self.config.oracle_config.model)
        pruner = _safe_name(self.config.pruner_config.model)
        exp = _safe_name(self.config.experiment_name or "default")
        # Organize by models, then experiment name
        return self.output_base / f"models/s_{seeker}__o_{oracle}__p_{pruner}" / exp

    def _csv_path(self) -> Path:
        return self._output_dir() / "runs.csv"

    def _ensure_header(self, csv_path: Path) -> None:
        if csv_path.exists():
            return
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "experiment_name",
                    "seeker_model",
                    "oracle_model",
                    "pruner_model",
                    "observability",
                    "max_turns",
                    "target_id",
                    "target_label",
                    "run_index",
                    "turns",
                    "h_start",
                    "h_end",
                    "total_info_gain",
                    "win",
                    "compliance_rate",
                    "conversation_path",
                ]
            )

    def run(
        self,
        *,
        graph: KnowledgeGraph,
        targets: Iterable[Node],
        runs_per_target: int = 1,
        debug: bool = False,
    ) -> Path:
        """Run the benchmark across targets and append results to CSV.
        
        Optionally saves agent conversations to JSON files if save_conversations is True.

        Returns:
            Path to the 'runs.csv' file with appended results.
        """

        csv_path = self._csv_path()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_header(csv_path)
        
        game_counter = 1

        for target in targets:
            if debug:
                print(f"Running target: {target.label} - {target.id}")
            for run_idx in range(1, int(runs_per_target) + 1):
                # Reset graph pruning state before each game
                graph.reset_pruning()
                
                # Create a fresh orchestrator for each game
                orch = Orchestrator.from_target(
                    target_node=target,
                    graph=graph,
                    seeker_config=self.config.seeker_config,
                    oracle_config=self.config.oracle_config,
                    pruner_config=self.config.pruner_config,
                    observability_mode=self.config.observability_mode,
                    max_turns=self.config.max_turns,
                )

                orch.run(debug=debug)

                # Save conversation if enabled
                conv_path_str = ""
                if self.config.save_conversations:
                    # Create descriptive directory name
                    safe_label = target.label.replace(" ", "_").replace("/", "-")
                    safe_id = target.id.replace(":", "")
                    conv_dir = self._output_dir() / "conversations" / \
                              f"game_{game_counter:03d}_{safe_label}_{safe_id}"
                    
                    orch.export_conversation(conv_dir)
                    
                    # Update metadata with game_id and experiment_name
                    metadata_path = conv_dir / "metadata.json"
                    if metadata_path.exists():
                        metadata = json.loads(metadata_path.read_text())
                        metadata["game_id"] = game_counter
                        metadata["config"]["experiment_name"] = self.config.experiment_name
                        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
                    
                    # Store relative path from output_base
                    conv_path_str = str(conv_dir.relative_to(self.output_base))
                
                game_counter += 1

                # Aggregate per-game metrics
                turns = orch.turns
                win = any(t.answer.game_over for t in turns)
                compliance_rate = (sum(1 for t in turns if t.answer.compliant) / len(turns)) if turns else 0.0
                summary = orch.get_summary()

                # Append row
                with csv_path.open("a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            self.config.experiment_name or "default",
                            self.config.seeker_config.model,
                            self.config.oracle_config.model,
                            self.config.pruner_config.model,
                            self.config.observability_mode.name,
                            self.config.max_turns,
                            target.id,
                            target.label,
                            run_idx,
                            summary.get("turns"),
                            summary.get("h_start"),
                            summary.get("h_end"),
                            summary.get("total_info_gain"),
                            int(win),
                            round(compliance_rate, 4),
                            conv_path_str,
                        ]
                    )

        return csv_path

 