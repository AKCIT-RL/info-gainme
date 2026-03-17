#!/bin/bash
# Submete benchmarks de teste via SLURM
#
# Uso:
#   ./dgx/run_all_tests.sh                  # submete 8b (padrão)
#   ./dgx/run_all_tests.sh --model 30b      # submete 30b
#   ./dgx/run_all_tests.sh --dep 16130      # com dependency=after:16130
#   ./dgx/run_all_tests.sh --model 30b --dep 16130

PROJECT_DIR="/raid/user_danielpedrozo/projects/info-gainme_dev"
MODEL="8b"
DEPENDENCY=""

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --dep)   DEPENDENCY="$2"; shift 2 ;;
        *)       echo "Arg desconhecido: $1"; exit 1 ;;
    esac
done

# Configs por modelo
declare -A CONFIGS_8B=(
    [diseases_test_po_cot]="configs/8b/diseases_test_po_cot.yaml"
    [diseases_test_po_no_cot]="configs/8b/diseases_test_po_no_cot.yaml"
    [diseases_test_fo_cot]="configs/8b/diseases_test_fo_cot.yaml"
    [diseases_test_fo_no_cot]="configs/8b/diseases_test_fo_no_cot.yaml"
    [objects_test_po_cot]="configs/8b/objects_test_po_cot.yaml"
    [objects_test_po_no_cot]="configs/8b/objects_test_po_no_cot.yaml"
    [objects_test_fo_cot]="configs/8b/objects_test_fo_cot.yaml"
    [objects_test_fo_no_cot]="configs/8b/objects_test_fo_no_cot.yaml"
    [geo_full_cot]="configs/8b/geo_full_cot.yaml"
    [geo_full_no_cot]="configs/8b/geo_full_no_cot.yaml"
)

declare -A CONFIGS_30B=(
    [diseases_test_30b_po_cot]="configs/30b/diseases_test_30b_po_cot.yaml"
    [diseases_test_30b_po_no_cot]="configs/30b/diseases_test_30b_po_no_cot.yaml"
    [diseases_test_30b_fo_cot]="configs/30b/diseases_test_30b_fo_cot.yaml"
    [diseases_test_30b_fo_no_cot]="configs/30b/diseases_test_30b_fo_no_cot.yaml"
    [objects_test_30b_po_cot]="configs/30b/objects_test_30b_po_cot.yaml"
    [objects_test_30b_po_no_cot]="configs/30b/objects_test_30b_po_no_cot.yaml"
    [objects_test_30b_fo_cot]="configs/30b/objects_test_30b_fo_cot.yaml"
    [objects_test_30b_fo_no_cot]="configs/30b/objects_test_30b_fo_no_cot.yaml"
    [geo_full_30b_cot]="configs/30b/geo_full_30b_cot.yaml"
    [geo_full_30b_no_cot]="configs/30b/geo_full_30b_no_cot.yaml"
)

if [[ "$MODEL" == "30b" ]]; then
    declare -n CONFIGS=CONFIGS_30B
else
    declare -n CONFIGS=CONFIGS_8B
fi

SBATCH_ARGS=""
if [ -n "${DEPENDENCY}" ]; then
    SBATCH_ARGS="--dependency=after:${DEPENDENCY}"
fi

echo "=========================================="
echo "Submetendo ${#CONFIGS[@]} benchmarks — modelo: ${MODEL}"
[ -n "${DEPENDENCY}" ] && echo "Dependency: after:${DEPENDENCY}"
echo "=========================================="

for NAME in "${!CONFIGS[@]}"; do
    CONFIG="${CONFIGS[$NAME]}"
    JOB_ID=$(sbatch ${SBATCH_ARGS} "${PROJECT_DIR}/dgx/run_benchmark.sh" "${CONFIG}" | awk '{print $4}')
    echo "  ✓ ${NAME} → job ${JOB_ID}"
done

echo "=========================================="
echo "Todos submetidos. Acompanhe com: squeue -u \$USER"
echo "=========================================="
