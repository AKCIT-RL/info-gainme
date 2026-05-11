#!/bin/bash
#SBATCH --job-name=traces-vllm
#SBATCH --partition=h100n2
#SBATCH --gres=gpu:2
#SBATCH --mem=60G
#SBATCH --time=1-00:00:00
#SBATCH --output=/raid/user_danielpedrozo/projects/info-gainme_dev/logs/%x-%j.log
#
# Sobe um vLLM próprio (2× H100, tensor-parallel=2) e roda
# scripts/reasoning_traces/synthesize_traces.py contra ele num único job.
# Para traces-only contra vLLM já existente, use run_synthesize_traces.sh.
#
# Lançamento típico:
#   sbatch --partition=h100n2 --gres=gpu:2 \
#     --export=ALL,SAMPLE_INDICES=0_10_20_30_40_50_60_70_80_90_100_110_120_130_140_150 \
#     bash_scripts/dgx/run_synthesize_traces_with_vllm.sh
#
# Variáveis de ambiente (todos opcionais — defaults entre parênteses):
#   MODEL           HF repo do synthesizer        (google/gemma-4-31B-it)
#   MODEL_NAME      served-model-name             (google/gemma-4-31B-it)
#   MAX_LEN         --max-model-len               (32000)
#   GPU_MEM         --gpu-memory-utilization      (0.92)
#   REASONING_PARSER --reasoning-parser           (auto: qwen3/openai_gptoss/olmo3; vazio pra Gemma)
#
# Synthesize args (espelham scripts/reasoning_traces/synthesize_traces.py):
#   WORKERS          conversas em paralelo                (8)
#   TURN_WORKERS     LLM calls paralelos por conversa     (4)
#   RUNS_PATH        runs.csv específico                  (vazio → --all)
#   RUN_INDEX        filtra _runNN                        (vazio = todos)
#   SAMPLE_INDICES   posições por stratum, separadas por _
#                    (ex: 0_10_20_30 = 4 alvos por runs.csv)

set -uo pipefail
umask 002

# ============================================
# Configuration
# ============================================
PROJECT_DIR="/raid/user_danielpedrozo/projects/info-gainme_dev"
SHARED_GROUP="sd22"
SINGULARITY_IMAGE="/raid/user_danielpedrozo/images/vllm_openai_latest.sif"

export MODEL="${MODEL:-google/gemma-4-31B-it}"
export MODEL_NAME="${MODEL_NAME:-google/gemma-4-31B-it}"
export MAX_LEN="${MAX_LEN:-32000}"
export GPU_MEM="${GPU_MEM:-0.92}"

# Auto-detect reasoning parser from MODEL_NAME (mesma lógica do run_full_benchmark.sh)
auto_reasoning_parser() {
    local name="${1,,}"
    case "$name" in
        *gpt-oss*)           echo "openai_gptoss" ;;
        *qwen3*)             echo "qwen3" ;;
        *olmo*think*|*olmo*) echo "olmo3" ;;
        *)                   echo "" ;;
    esac
}
[ -z "${REASONING_PARSER+x}" ] && REASONING_PARSER=$(auto_reasoning_parser "${MODEL_NAME}")
[ "${REASONING_PARSER}" = "none" ] && REASONING_PARSER=""

# Synthesize args
WORKERS="${WORKERS:-8}"
TURN_WORKERS="${TURN_WORKERS:-4}"
RUNS_PATH="${RUNS_PATH:-}"

# Port baseado em SLURM_JOB_ID com salto pra evitar colisões
BASE_PORT=$((8000 + (SLURM_JOB_ID % 500) * 10))
port_in_use() { ss -tln 2>/dev/null | awk '{print $4}' | grep -qE ":$1$"; }
while port_in_use $BASE_PORT; do BASE_PORT=$((BASE_PORT + 1)); done
PORT="${PORT:-$BASE_PORT}"

# Detecta GPUs alocadas pelo SLURM
if [ -z "${CUDA_VISIBLE_DEVICES:-}" ]; then
    echo "ERROR: CUDA_VISIBLE_DEVICES not set by SLURM"
    exit 1
fi
IFS=',' read -ra GPU_ARRAY <<< "${CUDA_VISIBLE_DEVICES}"
TOTAL_GPUS=${#GPU_ARRAY[@]}
TP="${TP:-$TOTAL_GPUS}"

# vLLM tuning
export VLLM_LOGGING_LEVEL="${VLLM_LOGGING_LEVEL:-INFO}"
export VLLM_ENGINE_READY_TIMEOUT_S="${VLLM_ENGINE_READY_TIMEOUT_S:-1800}"
export VLLM_MAX_NUM_SEQS="${VLLM_MAX_NUM_SEQS:-64}"
export VLLM_MAX_NUM_BATCHED_TOKENS="${VLLM_MAX_NUM_BATCHED_TOKENS:-16384}"
if [ -z "${VLLM_ENFORCE_EAGER:-}" ]; then
    if [[ "${SLURM_JOB_PARTITION:-}" == *b200* ]]; then
        VLLM_ENFORCE_EAGER="false"
    else
        VLLM_ENFORCE_EAGER="true"
    fi
fi

export HF_HOME=/workspace/hf-cache
source "${PROJECT_DIR}/.env"
export HF_TOKEN="${HF_TOKEN:?HF_TOKEN não definido no .env}"

mkdir -p "${PROJECT_DIR}/logs" "${PROJECT_DIR}/hf-cache"
cd "${PROJECT_DIR}"

VLLM_LOG="${PROJECT_DIR}/logs/traces-vllm-${SLURM_JOB_ID}-vllm-${MODEL_NAME//\//_}.log"

echo "=========================================="
echo "Synthesize Traces + vLLM — $(date)"
echo "  Job:             ${SLURM_JOB_ID} @ ${SLURM_JOB_PARTITION} / $(hostname)"
echo "  GPUs:            ${TOTAL_GPUS} (CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES})"
echo "  Synthesizer:     ${MODEL_NAME}"
echo "  HF repo:         ${MODEL}"
echo "  TP size:         ${TP}"
echo "  Port:            ${PORT}"
echo "  Max model len:   ${MAX_LEN}"
echo "  GPU mem util:    ${GPU_MEM}"
echo "  Reasoning parser: ${REASONING_PARSER:-(none)}"
echo "  vLLM log:        ${VLLM_LOG}"
echo "  enforce_eager=${VLLM_ENFORCE_EAGER} | max_num_seqs=${VLLM_MAX_NUM_SEQS}"
echo "------------------------------------------"
echo "  Synth WORKERS:        ${WORKERS} (conversas em paralelo)"
echo "  Synth TURN_WORKERS:   ${TURN_WORKERS} (LLM calls por conversa)"
echo "  Synth max paralelo:   $(( WORKERS * TURN_WORKERS )) requests"
echo "  Synth RUNS_PATH:      ${RUNS_PATH:-(--all)}"
echo "  Synth RUN_INDEX:      ${RUN_INDEX:-(none)}"
echo "  Synth SAMPLE_INDICES: ${SAMPLE_INDICES:-(none)}"
echo "=========================================="

# ============================================
# Start vLLM
# ============================================
start_vllm_server() {
    local model=$1 name=$2 port=$3 gpu_mem=$4 max_len=$5 log=$6 parser=${7:-""} tp=${8:-1}
    echo "Starting vLLM (${name}, TP=${tp}, port=${port})..."

    local cmd="/usr/bin/python3 -m vllm.entrypoints.openai.api_server \
        --model ${model} \
        --served-model-name ${name} \
        --download-dir /workspace/hf-cache/hub \
        --port ${port} --host 0.0.0.0 \
        --gpu-memory-utilization ${gpu_mem} \
        --max-num-seqs ${VLLM_MAX_NUM_SEQS} \
        --max-num-batched-tokens ${VLLM_MAX_NUM_BATCHED_TOKENS} \
        --max-model-len ${max_len} \
        --tensor-parallel-size ${tp} \
        --enable-prefix-caching"
    [ "${VLLM_ENFORCE_EAGER}" = "true" ] && cmd="${cmd} --enforce-eager"
    [ -n "${parser}" ] && cmd="${cmd} --reasoning-parser ${parser}"

    singularity exec --nv \
        --bind /raid/user_danielpedrozo:/workspace \
        --bind /dev/shm:/dev/shm \
        --pwd /workspace \
        --env HF_TOKEN=${HF_TOKEN} \
        --env VLLM_LOGGING_LEVEL=${VLLM_LOGGING_LEVEL} \
        --env HF_HOME=${HF_HOME} \
        --env CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES} \
        "${SINGULARITY_IMAGE}" \
        bash -c "${cmd}" >> "${log}" 2>&1 &
    echo $!
}

wait_vllm_ready() {
    local pid=$1 port=$2 name=$3 timeout=${4:-1800}
    local elapsed=0
    echo "Waiting up to ${timeout}s for ${name} on port ${port} (pid=${pid})..."
    while ! curl -s "http://localhost:${port}/v1/models" > /dev/null 2>&1; do
        if ! kill -0 ${pid} 2>/dev/null; then
            echo "ERROR: vLLM (${pid}) died before readiness"
            tail -n 50 "${VLLM_LOG}" 2>/dev/null || true
            exit 1
        fi
        if [ ${elapsed} -ge ${timeout} ]; then
            echo "ERROR: ${name} not ready after ${timeout}s — aborting"
            tail -n 50 "${VLLM_LOG}" 2>/dev/null || true
            kill ${pid} 2>/dev/null || true
            exit 1
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done
    echo "✓ ${name} ready after ${elapsed}s"
}

VLLM_PID=$(start_vllm_server "${MODEL}" "${MODEL_NAME}" "${PORT}" "${GPU_MEM}" "${MAX_LEN}" "${VLLM_LOG}" "${REASONING_PARSER}" "${TP}")
wait_vllm_ready "${VLLM_PID}" "${PORT}" "${MODEL_NAME}" "${VLLM_ENGINE_READY_TIMEOUT_S}"

# Cleanup garantido: mata vLLM mesmo se synth falhar / Ctrl+C / timeout
trap 'echo "Cleaning up vLLM PID=${VLLM_PID}..."; kill ${VLLM_PID} 2>/dev/null; wait ${VLLM_PID} 2>/dev/null; echo "vLLM stopped."' EXIT INT TERM

# ============================================
# Run synthesize traces against the local vLLM
# ============================================
EXTRA_FLAGS=""
[[ -n "${RUN_INDEX:-}" ]]      && EXTRA_FLAGS+=" --run-index ${RUN_INDEX}"
[[ -n "${SAMPLE_INDICES:-}" ]] && EXTRA_FLAGS+=" --sample-indices ${SAMPLE_INDICES//_/,}"
[[ "${FORCE:-0}" == "1" ]]     && EXTRA_FLAGS+=" --force"

if [ -n "${RUNS_PATH}" ]; then
    SOURCE_FLAG="--runs '${RUNS_PATH}'"
else
    SOURCE_FLAG="--all"
fi

BASE_URL="http://localhost:${PORT}/v1"
echo ""
echo "=========================================="
echo "Iniciando synthesize às $(date '+%H:%M:%S')"
echo "  endpoint:    ${BASE_URL}"
echo "  source:      ${SOURCE_FLAG}"
echo "  flags:       --workers ${WORKERS} --turn-workers ${TURN_WORKERS}${EXTRA_FLAGS}"
echo "=========================================="

sg "${SHARED_GROUP}" -c "
    singularity exec \
        --bind /raid/user_danielpedrozo:/workspace \
        --pwd /workspace/projects/info-gainme_dev \
        '${SINGULARITY_IMAGE}' \
        bash -c \"
            pip install --quiet --user -r requirements.txt
            python3 scripts/reasoning_traces/synthesize_traces.py \
                ${SOURCE_FLAG} \
                --base-url '${BASE_URL}' \
                --api-key  EMPTY \
                --model    '${MODEL_NAME}' \
                --workers ${WORKERS} \
                --turn-workers ${TURN_WORKERS}${EXTRA_FLAGS}
        \"
"
SYNTH_RC=$?

echo ""
echo "=========================================="
echo "Synthesize exited com código ${SYNTH_RC} — $(date)"
echo "Output:  ${PROJECT_DIR}/outputs/seeker_traces.jsonl"
echo "=========================================="
exit ${SYNTH_RC}
