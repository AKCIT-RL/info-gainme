"""Simple configuration loader for benchmark experiments."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from ..data_types import ObservabilityMode
from ..agents.llm_config import LLMConfig
from ..benchmark_config import BenchmarkConfig
from ..domain.types import GEO_DOMAIN, OBJECTS_DOMAIN, DISEASES_DOMAIN


def _load_servers(config_path: Path) -> Dict[str, str]:
    """Load servers.yaml by walking up from config_path to find the configs/ root."""
    p = config_path.resolve().parent
    while p.name != "configs" and p != p.parent:
        p = p.parent
    servers_path = p / "servers.yaml"
    if not servers_path.exists():
        return {}
    with servers_path.open("r") as f:
        data = yaml.safe_load(f)
    return data.get("servers", {}) if data else {}


def load_benchmark_config(config_path: Path, api_key: str) -> tuple[BenchmarkConfig, Dict[str, Any]]:
    """Load benchmark configuration from YAML file.

    Args:
        config_path: Path to YAML configuration file.
        api_key: OpenAI API key.

    Returns:
        Tuple of (BenchmarkConfig, full_config_dict).
    """
    with config_path.open("r") as f:
        config = yaml.safe_load(f)

    servers = _load_servers(config_path)

    # Create LLM configs
    def create_llm_config(model_config: Dict[str, Any]) -> LLMConfig:
        # Extract extra parameters (all non-standard parameters)
        extra_params = {}
        standard_params = {
            "model", "base_url", "timeout", "temperature", 
            "max_tokens", "use_reasoning", "user", "response_format"
        }
        
        for key, value in model_config.items():
            if key not in standard_params:
                extra_params[key] = value
        
        model_name = model_config["model"]
        base_url: Optional[str] = model_config.get("base_url") or servers.get(model_name)

        return LLMConfig(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            timeout=model_config.get("timeout"),
            temperature=model_config.get("temperature"),  # Allow None to use model default
            max_tokens=model_config.get("max_tokens"),
            user=model_config.get("user"),
            response_format=model_config.get("response_format"),
            use_reasoning=model_config.get("use_reasoning", False),
            extra=extra_params
        )
    
    # Parse observability mode
    mode_str = config["game"]["observability_mode"].upper()
    if mode_str in ["FULLY_OBSERVABLE", "FO"]:
        observability_mode = ObservabilityMode.FULLY_OBSERVABLE
    elif mode_str in ["PARTIALLY_OBSERVABLE", "PO"]:
        observability_mode = ObservabilityMode.PARTIALLY_OBSERVABLE
    else:
        raise ValueError(f"Unknown observability mode: {mode_str}")
    
    models = config["models"]
    dataset_type = config.get("dataset", {}).get("type", "geo")
    if dataset_type == "objects":
        domain_config = OBJECTS_DOMAIN
    elif dataset_type == "diseases":
        domain_config = DISEASES_DOMAIN
    else:
        domain_config = GEO_DOMAIN

    benchmark_config = BenchmarkConfig(
        seeker_config=create_llm_config(models["seeker"]),
        oracle_config=create_llm_config(models["oracle"]),
        pruner_config=create_llm_config(models["pruner"]),
        observability_mode=observability_mode,
        max_turns=config["game"]["max_turns"],
        domain_config=domain_config,
        experiment_name=config["experiment"]["name"],
        tags=config["experiment"].get("tags", {}),
        save_conversations=config["output"]["save_conversations"],
        save_graph_plots=config["output"]["save_graph_plots"],
    )

    return benchmark_config, config