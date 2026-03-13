#!/bin/bash
# Submete todos os benchmarks de teste (diseases + objects, PO + FO, COT + no_COT)
# Uso:
#   ./slurm/run_all_tests.sh              # submete todos
#   ./slurm/run_all_tests.sh <VLLM_JOB>  # submete com dependency=after:<VLLM_JOB>

DEPENDENCY="${1:-}"
PROJECT_DIR="/raid/user_danielpedrozo/projects/info-gainme_dev"

CONFIGS=(
    configs/diseases_test_po_cot.yaml
    configs/diseases_test_po_no_cot.yaml
    configs/diseases_test_fo_cot.yaml
    configs/diseases_test_fo_no_cot.yaml
    configs/objects_test_po_cot.yaml
    configs/objects_test_po_no_cot.yaml
    configs/objects_test_fo_cot.yaml
    configs/objects_test_fo_no_cot.yaml
)

SBATCH_ARGS=""
if [ -n "${DEPENDENCY}" ]; then
    SBATCH_ARGS="--dependency=after:${DEPENDENCY}"
    echo "Dependency: after:${DEPENDENCY}"
fi

echo "=========================================="
echo "Submetendo ${#CONFIGS[@]} benchmarks de teste"
echo "=========================================="

for CONFIG in "${CONFIGS[@]}"; do
    JOB_ID=$(sbatch ${SBATCH_ARGS} "${PROJECT_DIR}/slurm/run_benchmark.sh" "${CONFIG}" | awk '{print $4}')
    echo "  ✓ $CONFIG → job $JOB_ID"
done

echo "=========================================="
echo "Todos submetidos. Acompanhe com: squeue -u \$USER"
echo "=========================================="
