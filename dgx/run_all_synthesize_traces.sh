#!/bin/bash
# Sintetiza reasoning traces de todos os experimentos CoT sob outputs/
# Uso:
#   ./dgx/run_all_synthesize_traces.sh
#   ./dgx/run_all_synthesize_traces.sh path/to/runs.csv

umask 002

CSV_PATH="${1:-}"
PROJECT_DIR="/raid/user_danielpedrozo/projects/info-gainme_dev"
SINGULARITY_IMAGE="/raid/user_danielpedrozo/images/vllm_openai_latest.sif"

echo "=========================================="
echo "Info Gainme - Synthesize Traces - $(date)"
echo "=========================================="

singularity exec \
    --bind /raid/user_danielpedrozo:/workspace \
    --pwd /workspace/projects/info-gainme_dev \
    "${SINGULARITY_IMAGE}" \
    bash -c "
        python3 scripts/multi_synthesize_reasoning_traces.py --all
    "

echo "=========================================="
echo "Síntese de traces finalizada - $(date)"
echo "=========================================="
