"""Gera um CSV unificado com métricas globais de todos os experimentos.

Usage:
    # Varre ./outputs e salva em ./outputs/unified_experiments.csv
    python scripts/generate_unified_csv.py

    # Informar diretório base de outputs e caminho de saída
    python scripts/generate_unified_csv.py [base_outputs_dir] [output_csv_path]

Colunas geradas:
    Experimento, Seeker Model, Observabilidade, Total Runs, Win Rate,
    Mean Turns, Mean Info Gain/Turn, Mean Info Gain,
    Mean Seeker Tokens, Mean Seeker Reasoning Tokens, Mean Seeker Final Tokens
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

# Garantir imports do projeto
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis.loader import load_experiment_results


HEADERS = [
    "Experimento",
    "Seeker Model",
    "Observabilidade",
    "Total Runs",
    "Win Rate",
    "Mean Turns",
    "Mean Info Gain/Turn",
    "Mean Info Gain",
    "Mean Seeker Tokens",
    "Mean Seeker Reasoning Tokens",
    "Mean Seeker Final Tokens",
    "id",
]


def _extract_from_summary(summary_path: Path) -> dict | None:
    """Extrai métricas do summary.json se existir."""
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        global_metrics = data.get("global_metrics", {}) or {}
        return {
            "Experimento": data.get("experiment_name"),
            "Seeker Model": (data.get("models", {}) or {}).get("seeker"),
            "Observabilidade": (data.get("config", {}) or {}).get("observability"),
            "Total Runs": global_metrics.get("total_runs"),
            "Win Rate": global_metrics.get("win_rate"),
            "Mean Turns": global_metrics.get("mean_turns"),
            "Mean Info Gain/Turn": global_metrics.get("mean_avg_info_gain_per_turn"),
            "Mean Info Gain": global_metrics.get("mean_info_gain"),
            "Mean Seeker Tokens": global_metrics.get("mean_seeker_tokens"),
            "Mean Seeker Reasoning Tokens": global_metrics.get("mean_seeker_reasoning_tokens"),
            "Mean Seeker Final Tokens": global_metrics.get("mean_seeker_final_tokens"),
        }
    except Exception:
        return None


def _extract_from_runs_csv(runs_csv: Path) -> dict | None:
    """Calcula métricas carregando o runs.csv se summary.json não existir."""
    try:
        results = load_experiment_results(runs_csv)
        return {
            "Experimento": results.experiment_name,
            "Seeker Model": results.seeker_model,
            "Observabilidade": results.observability,
            "Total Runs": results.total_runs,
            "Win Rate": round(results.global_win_rate, 4),
            "Mean Turns": round(results.mean_turns, 2),
            "Mean Info Gain/Turn": round(results.mean_avg_info_gain_per_turn, 4),
            "Mean Info Gain": round(results.mean_info_gain, 4),
            "Mean Seeker Tokens": round(results.mean_seeker_tokens, 0),
            "Mean Seeker Reasoning Tokens": round(results.mean_seeker_reasoning_tokens, 0) if results.mean_seeker_reasoning_tokens is not None else None,
            "Mean Seeker Final Tokens": round(results.mean_seeker_final_tokens, 0),
        }
    except Exception:
        return None


def _iter_experiments(base_outputs_dir: Path) -> list[dict]:
    """Percorre o diretório base e coleta linhas para o CSV unificado."""
    rows: list[dict] = []
    # Preferir summary.json quando disponível
    for summary_path in sorted(base_outputs_dir.rglob("summary.json")):
        row = _extract_from_summary(summary_path)
        if row:
            # Add composed id
            row["id"] = f"{row.get('Seeker Model','')}_{row.get('Observabilidade','')}_{row.get('Experimento','')}"
            rows.append(row)

    # Para pastas sem summary.json, tentar via runs.csv
    # Evitar duplicar itens: só adicionar se não houver Experimento já incluso
    seen_experiments = {row["Experimento"] for row in rows if row.get("Experimento")}
    for runs_csv in sorted(base_outputs_dir.rglob("runs.csv")):
        # Se existe summary no mesmo dir, já capturado
        if (runs_csv.parent / "summary.json").exists():
            continue
        row = _extract_from_runs_csv(runs_csv)
        if row and row.get("Experimento") not in seen_experiments:
            row["id"] = f"{row.get('Seeker Model','')}_{row.get('Observabilidade','')}_{row.get('Experimento','')}"
            rows.append(row)
            seen_experiments.add(row.get("Experimento"))

    return rows


def main() -> int:
    """Ponto de entrada para geração do CSV unificado."""
    repo_root = Path(__file__).parent.parent
    default_base = repo_root / "outputs"
    default_out = default_base / "unified_experiments.csv"

    # Argumentos opcionais
    if len(sys.argv) >= 2:
        base_outputs_dir = Path(sys.argv[1])
    else:
        base_outputs_dir = default_base

    if len(sys.argv) >= 3:
        output_csv = Path(sys.argv[2])
    else:
        output_csv = default_out

    if not base_outputs_dir.exists():
        print(f"❌ Diretório de outputs não encontrado: {base_outputs_dir}")
        print(f"Usage: python {Path(__file__).name} [base_outputs_dir] [output_csv]")
        return 1

    print(f"🔎 Lendo experimentos em: {base_outputs_dir}")
    rows = _iter_experiments(base_outputs_dir)

    if not rows:
        print("❌ Nenhum experimento encontrado (summary.json ou runs.csv)")
        return 1

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"✅ CSV unificado salvo em: {output_csv}")
    print(f"📦 Total de experimentos: {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


