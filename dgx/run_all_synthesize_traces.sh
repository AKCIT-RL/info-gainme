#!/bin/bash
# Roda análise direto na DGX (sem SLURM)
# Uso:
#   ./run_analysis.sh              # analisa todos os runs.csv sob outputs/
#   ./run_analysis.sh path/to.csv  # analisa um CSV específico

umask 002

CSV_PATH="${1:-}"
PROJECT_DIR="/raid/user_danielpedrozo/projects/info-gainme_dev"
SINGULARITY_IMAGE="/raid/user_danielpedrozo/images/vllm_openai_latest.sif"

echo "=========================================="
echo "Info Gainme Analysis - $(date)"
if [ -n "${CSV_PATH}" ]; then
    echo "CSV: ${CSV_PATH}"
else
    echo "Modo: --all (todos os runs.csv sob outputs/)"
fi
echo "=========================================="

if [ -n "${CSV_PATH}" ]; then
    ANALYSIS_CMD="python3 scripts/analyze_results.py '${CSV_PATH}'"
else
    ANALYSIS_CMD="python3 scripts/analyze_results.py --all"
fi

singularity exec \
    --bind /raid/user_danielpedrozo:/workspace \
    --pwd /workspace/projects/info-gainme_dev \
    "${SINGULARITY_IMAGE}" \
    bash -c "
        ${ANALYSIS_CMD}
        python3 scripts/generate_unified_csv.py
        python3 scripts/multi_synthesize_reasoning_traces.py --all
    "

echo "=========================================="
echo "Análise finalizada - $(date)"
echo "=========================================="
