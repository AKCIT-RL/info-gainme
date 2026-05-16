#!/bin/bash
# Standalone vLLM server — runs directly on the node, NO SLURM.
# GPUs are pinned by this script (CUDA_VISIBLE_DEVICES below), so the
# scheduler is not involved. Use when sbatch/srun are unavailable
# (e.g. slurmctld spool I/O error) and the target GPUs are physically
# free and on a partition SLURM won't schedule onto (e.g. DRAINED h3).
#
# Usage (always inside screen so it survives logout):
#   screen -dmS vllm-8b bash bash_scripts/dgx/run_vllm_no_slurm.sh
#   tail -f logs/vllm-no-slurm-Qwen3-8B.log
#   curl -s http://localhost:8800/v1/models | head
#
# Stop:  screen -r vllm-8b  then Ctrl-C   (or: fuser -k 8800/tcp)

set -uo pipefail

# ── server port (node-internal) ───────────────────────────────────
export VLLM_PORT=8800

# ── GPUs to use (THIS replaces SLURM allocation) ──────────────────
export CUDA_VISIBLE_DEVICES=4,5
export NUM_GPUS=2

# ── model config ──────────────────────────────────────────────────
export MODEL="Qwen/Qwen3-8B"
export MODEL_NAME="Qwen3-8B"
export MODEL_GPU_MEM=0.95
export MODEL_REASONING_PARSER="qwen3"
export MODEL_MAX_LEN=32000
export MODEL_MAX_NUM_SEQS=128

# Alternative (uncomment + comment the block above):
# export MODEL="Qwen/Qwen3-30B-A3B-Thinking-2507"
# export MODEL_NAME="Qwen3-30B-A3B-Thinking-2507"
# export MODEL_GPU_MEM=0.9
# export MODEL_REASONING_PARSER=""
# export MODEL_MAX_LEN=140000
# export MODEL_MAX_NUM_SEQS=128

# ── vLLM / runtime env ────────────────────────────────────────────
export VLLM_LOGGING_LEVEL=INFO
export OMP_NUM_THREADS=8
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export NCCL_P2P_DISABLE=0
export NCCL_IB_DISABLE=1

PROJECT_DIR="/raid/user_danielpedrozo/projects/info-gainme_dev"
SINGULARITY_IMAGE="/raid/user_danielpedrozo/images/vllm_openai_latest.sif"

# HF cache lives in /workspace (bind-mounted) to dodge /raid perm issues
export HF_HOME=/workspace/hf-cache
# shellcheck disable=SC1091
source "${PROJECT_DIR}/.env"
export HF_TOKEN="${HF_TOKEN:?HF_TOKEN não definido no .env}"
export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"

mkdir -p "${PROJECT_DIR}/logs" /raid/user_danielpedrozo/models /raid/user_danielpedrozo/hf-cache

# ── manual log redirect (no #SBATCH --output without SLURM) ───────
LOG="${PROJECT_DIR}/logs/vllm-no-slurm-${MODEL_NAME//\//_}.log"
exec > >(tee -a "${LOG}") 2>&1

echo "=========================================="
echo "Standalone vLLM (NO SLURM) - $(date)"
echo "Host: $(hostname)"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}  NUM_GPUS=${NUM_GPUS}"
echo "Model: ${MODEL_NAME}  port: ${VLLM_PORT}  TP=${NUM_GPUS}"
echo "Log: ${LOG}"
echo "=========================================="
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits
echo ""

# free the port if a stale process holds it
echo "Checando porta ${VLLM_PORT}..."
fuser -k ${VLLM_PORT}/tcp 2>/dev/null && echo "  processo anterior encerrado." || echo "  porta livre."
sleep 2

vllm_cmd="/usr/bin/python3 -m vllm.entrypoints.openai.api_server \
  --model ${MODEL} \
  --served-model-name ${MODEL_NAME} \
  --download-dir /workspace/hf-cache/hub \
  --port ${VLLM_PORT} \
  --host 0.0.0.0 \
  --gpu-memory-utilization ${MODEL_GPU_MEM} \
  --max-num-seqs ${MODEL_MAX_NUM_SEQS} \
  --max-num-batched-tokens 16384 \
  --tensor-parallel-size ${NUM_GPUS} \
  --max-model-len ${MODEL_MAX_LEN} \
  --enable-prefix-caching"

if [ -n "${MODEL_REASONING_PARSER}" ]; then
    vllm_cmd="${vllm_cmd} --reasoning-parser ${MODEL_REASONING_PARSER}"
fi

echo "Iniciando vLLM..."
singularity exec \
     --nv \
     --bind /raid/user_danielpedrozo:/workspace \
     --bind /dev/shm:/dev/shm \
     --pwd /workspace \
     --env CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES} \
     --env HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN} \
     --env HF_TOKEN=${HF_TOKEN} \
     --env VLLM_LOGGING_LEVEL=${VLLM_LOGGING_LEVEL} \
     --env OMP_NUM_THREADS=${OMP_NUM_THREADS} \
     --env PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF} \
     --env NCCL_P2P_DISABLE=${NCCL_P2P_DISABLE} \
     --env NCCL_IB_DISABLE=${NCCL_IB_DISABLE} \
     "${SINGULARITY_IMAGE}" \
     bash -c "${vllm_cmd}" &

VLLM_PID=$!
echo "PID vLLM (singularity): ${VLLM_PID}"

# die cleanly if vLLM exits before becoming ready
echo "Aguardando readiness em http://localhost:${VLLM_PORT}/v1/models ..."
while ! curl -s "http://localhost:${VLLM_PORT}/v1/models" > /dev/null; do
    if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
        echo "ERRO: processo vLLM morreu antes de ficar pronto. Veja ${LOG}."
        exit 1
    fi
    echo "  ainda subindo..."
    sleep 5
done

echo "=========================================="
echo "vLLM PRONTO: ${MODEL_NAME} @ http://$(hostname):${VLLM_PORT}/v1"
echo "=========================================="
wait "${VLLM_PID}"
