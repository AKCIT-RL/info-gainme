#!/bin/bash
#SBATCH --job-name=vllm-info-gainme
#SBATCH --partition=h100n3
#SBATCH --gres=gpu:4
#SBATCH --mem=16G
#SBATCH --time=15-00:00:00
#SBATCH --output=/raid/user_danielpedrozo/projects/info-gainme_dev/logs/%x-%j.log
#
# vLLM gemma-4-31B-it com thinking. CORREÇÃO de 2 bugs da versão antiga:
#   1) JSON de --default-chat-template-kwargs era corrompido (aspas comidas)
#      por montar string + `bash -c "$vllm_cmd"`.
#   2) --reasoning-parser caía em linha nova (trailing newline na string) →
#      "command not found", parser nunca aplicado.
# Solução: comando vLLM como ARRAY passado direto pro `singularity exec`
# (sem bash -c), então JSON e flags condicionais passam intactos.
# Bônus: kill -0 liveness (não vira zumbi se o vLLM morrer no init).

export VLLM_PORT=8226

# ── modelo ────────────────────────────────────────────────────────
export MODEL="google/gemma-4-31B-it"
export MODEL_NAME="gemma-4-31B-it"
export MODEL_GPU_MEM=0.92
export MODEL_REASONING_PARSER="gemma4"
export MODEL_MAX_LEN=102000
export MODEL_MAX_NUM_SEQS=128

export VLLM_LOGGING_LEVEL=INFO
export OMP_NUM_THREADS=8
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export NCCL_P2P_DISABLE=0
export NCCL_IB_DISABLE=1

# ── GPUs: self-pin (SLURM accounting furada no nó) ────────────────
echo "GPUs disponíveis pelo SLURM: ${CUDA_VISIBLE_DEVICES:-(none)}"
export CUDA_VISIBLE_DEVICES=6,7
echo "Forçando uso das GPUs: ${CUDA_VISIBLE_DEVICES}"
export NUM_GPUS=$(echo "${CUDA_VISIBLE_DEVICES}" | tr ',' '\n' | grep -c .)
echo "NUM_GPUS: ${NUM_GPUS}"

export HF_HOME=/workspace/hf-cache
# shellcheck disable=SC1091
source /raid/user_danielpedrozo/projects/info-gainme_dev/.env
export HF_TOKEN="${HF_TOKEN:?HF_TOKEN não definido no .env}"
export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"

mkdir -p /raid/user_danielpedrozo/projects/info-gainme_dev/logs \
         /raid/user_danielpedrozo/models /raid/user_danielpedrozo/hf-cache
[ -n "${APPTAINER_CACHEDIR:-}" ] && mkdir -p "${APPTAINER_CACHEDIR}"
[ -n "${APPTAINER_TMPDIR:-}" ]   && mkdir -p "${APPTAINER_TMPDIR}"

# Auto-log: o script redireciona sua própria saída pro arquivo. Assim o
# lançamento é trivial (screen -dmS vllm-gemma bash <script>) — sem
# `| tee`, sem `bash -c`, sem aspas aninhadas frágeis no SSH.
LOG_FILE="${LOG_FILE:-/raid/user_danielpedrozo/projects/info-gainme_dev/logs/vllm-gemma.log}"
if [ -z "${__LOG_REDIRECTED__:-}" ]; then
    export __LOG_REDIRECTED__=1
    exec > >(tee -a "${LOG_FILE}") 2>&1
fi

SINGULARITY_IMAGE=/raid/user_danielpedrozo/images/vllm_openai_latest.sif

echo "=========================================="
echo "vLLM ${MODEL_NAME} @ $(hostname):${VLLM_PORT}  GPUs=${CUDA_VISIBLE_DEVICES} TP=${NUM_GPUS}"
echo "=========================================="
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits
echo ""

echo "Checando porta ${VLLM_PORT}..."
fuser -k ${VLLM_PORT}/tcp 2>/dev/null && echo "  processo anterior encerrado." || echo "  porta livre."
sleep 2

# ── comando vLLM como ARRAY (quoting/JSON sobrevivem; sem bash -c) ─
VLLM_ARGS=(
  -m vllm.entrypoints.openai.api_server
  --model "${MODEL}"
  --served-model-name "${MODEL_NAME}"
  --download-dir /workspace/hf-cache/hub
  --port "${VLLM_PORT}"
  --host 0.0.0.0
  --gpu-memory-utilization "${MODEL_GPU_MEM}"
  --max-num-seqs "${MODEL_MAX_NUM_SEQS}"
  --max-num-batched-tokens 32000
  --tensor-parallel-size "${NUM_GPUS}"
  --max-model-len "${MODEL_MAX_LEN}"
  --enable-prefix-caching
  --enable-auto-tool-choice
  --tool-call-parser gemma4
  --chat-template /vllm-workspace/examples/tool_chat_template_gemma4.jinja
  --default-chat-template-kwargs '{"enable_thinking": true}'
)
# --reasoning-parser só se setado (na MESMA invocação, não em linha nova)
if [ -n "${MODEL_REASONING_PARSER}" ]; then
  VLLM_ARGS+=( --reasoning-parser "${MODEL_REASONING_PARSER}" )
fi

echo "Iniciando vLLM (${MODEL_NAME}, TP=${NUM_GPUS})..."
echo "args: ${VLLM_ARGS[*]}"
singularity exec \
     --nv \
     --bind /raid/user_danielpedrozo:/workspace \
     --bind /dev/shm:/dev/shm \
     --pwd /workspace \
     --env CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES}" \
     --env HUGGING_FACE_HUB_TOKEN="${HUGGING_FACE_HUB_TOKEN}" \
     --env HF_TOKEN="${HF_TOKEN}" \
     --env VLLM_LOGGING_LEVEL="${VLLM_LOGGING_LEVEL}" \
     --env OMP_NUM_THREADS="${OMP_NUM_THREADS}" \
     --env PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF}" \
     --env NCCL_P2P_DISABLE="${NCCL_P2P_DISABLE}" \
     --env NCCL_IB_DISABLE="${NCCL_IB_DISABLE}" \
     "${SINGULARITY_IMAGE}" \
     /usr/bin/python3 "${VLLM_ARGS[@]}" &

VLLM_PID=$!
echo "PID vLLM (singularity): ${VLLM_PID}"

echo "Aguardando readiness em http://localhost:${VLLM_PORT}/v1/models ..."
while ! curl -s "http://localhost:${VLLM_PORT}/v1/models" > /dev/null; do
    if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
        echo "ERRO: processo vLLM morreu antes de ficar pronto. Veja o log acima"
        echo "      (erro de argumento, OOM, ou arch). NÃO vira zumbi."
        exit 1
    fi
    echo "  ainda subindo..."
    sleep 5
done

echo "=========================================="
echo "vLLM PRONTO: ${MODEL_NAME} @ http://$(hostname):${VLLM_PORT}/v1"
echo "=========================================="
wait "${VLLM_PID}"
