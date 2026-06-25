#!/bin/bash
#SBATCH --job-name=belief-states
#SBATCH --partition=h100n2
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=2-00:00:00
#SBATCH --output=/raid/user_danielpedrozo/projects/info-gainme_dev/logs/%x-%j.log
#
# Sobe um vLLM Gemma-4-31B-it localmente e roda a extração de belief states
# (extract_belief_states.py) contra ele, depois agrega (analyze_belief_states.py).
#
# A extração é RESUMÍVEL: como grava no mesmo --unified-jsonl, ela pula as
# conversas já feitas e processa só as novas (ex.: os PO recém-copiados do 30B
# e o 8B-objects-PO). Para reextrair tudo, use FORCE=1 ou um UNIFIED_JSONL novo.
#
# Submissão:
#   sbatch bash_scripts/dgx/run_belief_states_slurm.sh
#   # ou customizando:
#   sbatch --export=ALL,SEEKERS=...,SAMPLE_INDICES=...,UNIFIED_JSONL=... \
#     bash_scripts/dgx/run_belief_states_slurm.sh
#
# Vars (com defaults):
#   VLLM_PORT(8431) MODEL_GPU_MEM(0.90) MODEL_MAX_LEN(32000) MODEL_MAX_NUM_SEQS(32)
#   API_KEY(capacete) MAX_WORKERS(8) FORCE(0) DRY_RUN(0)
#   SEEKERS, ORACLE_PRUNER(Qwen3-8B), ONLY_RUN_INDEX(1), SAMPLE_INDICES(10..150)
#   UNIFIED_JSONL(outputs/belief_states.jsonl)
#   VLLM_IMAGE(.../images/vllm_openai_nightly.sif)  # gemma-4 precisa do nightly
#   VLLM_ENGINE_READY_TIMEOUT_S(1800)

set -euo pipefail
umask 002

PROJECT_DIR="/raid/user_danielpedrozo/projects/info-gainme_dev"
HOST_RAID="/raid/user_danielpedrozo"
VLLM_IMAGE="${VLLM_IMAGE:-${HOST_RAID}/images/vllm_openai_nightly.sif}"

# ---- vLLM config (espelha o script de referência do gemma-31b) ----
export VLLM_PORT="${VLLM_PORT:-8431}"
export MODEL="${MODEL:-google/gemma-4-31B-it}"
export MODEL_NAME="${MODEL_NAME:-google/gemma-4-31B-it}"
export MODEL_GPU_MEM="${MODEL_GPU_MEM:-0.90}"
export MODEL_MAX_LEN="${MODEL_MAX_LEN:-32000}"
export MODEL_MAX_NUM_SEQS="${MODEL_MAX_NUM_SEQS:-32}"
export API_KEY="${API_KEY:-capacete}"
export NUM_GPUS="${NUM_GPUS:-1}"

export VLLM_LOGGING_LEVEL="${VLLM_LOGGING_LEVEL:-INFO}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export VLLM_ENGINE_READY_TIMEOUT_S="${VLLM_ENGINE_READY_TIMEOUT_S:-1800}"

# Singularity tmp/cache por-usuário (evita colisão de permissão entre usuários).
export SINGULARITY_TMPDIR="${SINGULARITY_TMPDIR:-${HOST_RAID}/tmp/singularity-${USER}}"
export APPTAINER_TMPDIR="${APPTAINER_TMPDIR:-${SINGULARITY_TMPDIR}}"
export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-${HOST_RAID}/tmp/apptainer-cache-${USER}}"
mkdir -p "${PROJECT_DIR}/logs" "${HOST_RAID}/hf-cache" "${SINGULARITY_TMPDIR}" "${APPTAINER_CACHEDIR}"

# ---- HF token ----
[ -f "${PROJECT_DIR}/.env" ] && source "${PROJECT_DIR}/.env"
export HF_TOKEN="${HF_TOKEN:?HF_TOKEN nao definido no .env}"

# ---- extração: escopo canônico (mesmo do pipeline de perguntas) ----
SEEKERS="${SEEKERS:-Qwen3-8B,Qwen3-4B-Thinking-2507,Qwen3-30B-A3B-Thinking-2507,google-gemma-4-E4B-it,google-gemma-4-31B-it,Nemotron-Cascade-8B}"
ORACLE_PRUNER="${ORACLE_PRUNER:-Qwen3-8B}"
ONLY_RUN_INDEX="${ONLY_RUN_INDEX:-1}"
SAMPLE_INDICES="${SAMPLE_INDICES:-10,20,30,40,50,60,70,80,90,100,110,120,130,140,150}"
UNIFIED_JSONL="${UNIFIED_JSONL:-outputs/belief_states.jsonl}"
MAX_WORKERS="${MAX_WORKERS:-8}"
EXTRA_FLAGS=""
[[ "${FORCE:-0}" == "1" ]]   && EXTRA_FLAGS+=" --force"
[[ "${DRY_RUN:-0}" == "1" ]] && EXTRA_FLAGS+=" --dry-run"

echo "=========================================="
echo "Belief-state extraction (Gemma) — job ${SLURM_JOB_ID:-local} em $(hostname)"
echo "Modelo:    ${MODEL_NAME}  (porta ${VLLM_PORT})"
echo "Unified:   ${UNIFIED_JSONL}   (resume — só conversas novas)"
echo "Seekers:   ${SEEKERS}"
echo "Filtros:   run_index=${ONLY_RUN_INDEX}  samples=${SAMPLE_INDICES}"
echo "=========================================="
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits || true

fuser -k "${VLLM_PORT}/tcp" 2>/dev/null && echo "Porta ${VLLM_PORT} liberada." || echo "Porta ${VLLM_PORT} livre."
sleep 2

# ---- sobe o vLLM em background ----
vllm_args=(
    /usr/bin/python3 -m vllm.entrypoints.openai.api_server
    --model "${MODEL}"
    --served-model-name "${MODEL_NAME}"
    --download-dir /workspace/hf-cache/hub
    --port "${VLLM_PORT}"
    --host 0.0.0.0
    --gpu-memory-utilization "${MODEL_GPU_MEM}"
    --max-num-seqs "${MODEL_MAX_NUM_SEQS}"
    --max-num-batched-tokens 16192
    --tensor-parallel-size "${NUM_GPUS}"
    --max-model-len "${MODEL_MAX_LEN}"
    --dtype bfloat16
    --enable-prefix-caching
    --api-key "${API_KEY}"
)

singularity exec \
    --nv \
    --bind "${HOST_RAID}:/workspace" \
    --bind /dev/shm:/dev/shm \
    --pwd /workspace \
    --env HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}" \
    --env HF_HOME=/workspace/hf-cache \
    --env VLLM_LOGGING_LEVEL="${VLLM_LOGGING_LEVEL}" \
    --env OMP_NUM_THREADS="${OMP_NUM_THREADS}" \
    --env PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF}" \
    "${VLLM_IMAGE}" \
    "${vllm_args[@]}" &
VLLM_PID=$!
echo "vLLM PID: ${VLLM_PID}"

# Garante que o vLLM morre quando o script terminar (sucesso, erro ou cancelamento).
cleanup() {
    echo "Encerrando vLLM (PID ${VLLM_PID})..."
    kill "${VLLM_PID}" 2>/dev/null || true
    wait "${VLLM_PID}" 2>/dev/null || true
}
trap cleanup EXIT

# ---- espera ficar pronto (aborta se o processo morrer ou estourar timeout) ----
echo "Aguardando vLLM (timeout ${VLLM_ENGINE_READY_TIMEOUT_S}s)..."
elapsed=0
until curl -s "http://localhost:${VLLM_PORT}/v1/models" >/dev/null 2>&1; do
    if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
        echo "ERRO: processo vLLM morreu antes de ficar pronto. Veja o log acima." >&2
        exit 1
    fi
    if [ "${elapsed}" -ge "${VLLM_ENGINE_READY_TIMEOUT_S}" ]; then
        echo "ERRO: vLLM nao ficou pronto em ${VLLM_ENGINE_READY_TIMEOUT_S}s." >&2
        exit 1
    fi
    sleep 5; elapsed=$((elapsed + 5))
done
echo "vLLM pronto em http://localhost:${VLLM_PORT}/v1  (apos ${elapsed}s)"

# ---- roda a extração + análise dentro do container (repo deps via pip) ----
EXTRACT_CMD="python3 scripts/reasoning_traces/extract_belief_states.py --all \
    --base-url http://localhost:${VLLM_PORT}/v1 \
    --api-key '${API_KEY}' \
    --model '${MODEL_NAME}' \
    --seekers '${SEEKERS}' \
    --oracle-pruner '${ORACLE_PRUNER}' \
    --only-run-index ${ONLY_RUN_INDEX} \
    --sample-indices '${SAMPLE_INDICES}' \
    --max-workers ${MAX_WORKERS} \
    --unified-jsonl '${UNIFIED_JSONL}'${EXTRA_FLAGS}"

ANALYZE_CMD="python3 scripts/reasoning_traces/analyze_belief_states.py --jsonl '${UNIFIED_JSONL}'"

sg sd22 -c "
    singularity exec \
        --bind ${HOST_RAID}:/workspace \
        --pwd /workspace/projects/info-gainme_dev \
        '${VLLM_IMAGE}' \
        bash -c \"
            pip install --quiet --user -r requirements.txt
            ${EXTRACT_CMD}
            if [ '${DRY_RUN:-0}' != '1' ]; then ${ANALYZE_CMD}; fi
        \"
"

echo "=========================================="
echo "Belief-state extraction concluida — $(date)"
echo "=========================================="
