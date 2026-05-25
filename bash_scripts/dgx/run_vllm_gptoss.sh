#!/bin/bash
# Standalone vLLM server for gpt-oss — designed for srun (sbatch is broken by
# the slurmctld spool I/O error). NO hardcoded CUDA_VISIBLE_DEVICES: the GPU
# list comes from whatever srun --gres allocates (cgroup-isolated). This avoids
# the recurring bug where a hardcoded `CUDA_VISIBLE_DEVICES=4,5` overrode srun's
# allocation and pinned vLLM to busy/nonexistent devices → infinite "Aguardando".
#
# Launch (always in screen — srun blocks, screen survives logout):
#   screen -dmS vllm-gptoss bash -c '
#     cd /raid/user_danielpedrozo/projects/info-gainme_dev
#     srun --partition=b200n1 --gres=gpu:2 --mem=16G --time=15-00:00:00 \
#       bash bash_scripts/dgx/run_vllm_gptoss.sh 2>&1 | tee logs/vllm-gptoss.log
#   '
#
# Overridable env (defaults in parens):
#   VLLM_PORT          server port            (8802)
#   MODEL / MODEL_NAME HF id / served name    (openai/gpt-oss-120b / gpt-oss-120b)
#   MODEL_GPU_MEM      gpu-memory-utilization (0.92)
#   MODEL_MAX_LEN      max-model-len          (62000)
#   MODEL_MAX_NUM_SEQS max-num-seqs           (64)
#   VLLM_PIP_UPGRADE   if "1", pip-install a newer vLLM in-container before
#                      launch (use if the .sif lacks GptOssForCausalLM)  (vazio)
set -uo pipefail

export VLLM_PORT="${VLLM_PORT:-8802}"

# ── gpt-oss config (120b; for 20b override MODEL/MODEL_NAME) ───────
export MODEL="${MODEL:-openai/gpt-oss-120b}"
export MODEL_NAME="${MODEL_NAME:-gpt-oss-120b}"
export MODEL_GPU_MEM="${MODEL_GPU_MEM:-0.92}"
export MODEL_MAX_LEN="${MODEL_MAX_LEN:-62000}"
export MODEL_MAX_NUM_SEQS="${MODEL_MAX_NUM_SEQS:-64}"
# gpt-oss reasoning parser is fixed (CLAUDE.md: *gpt-oss* → openai_gptoss)
export MODEL_REASONING_PARSER="${MODEL_REASONING_PARSER:-openai_gptoss}"

export VLLM_LOGGING_LEVEL=INFO
export OMP_NUM_THREADS=8
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export NCCL_P2P_DISABLE=0
export NCCL_IB_DISABLE=1

# Forçando gpus
echo "GPUs disponíveis pelo SLURM: ${CUDA_VISIBLE_DEVICES}"
# export CUDA_VISIBLE_DEVICES=6,7
# echo "Forçando uso das GPUs: ${CUDA_VISIBLE_DEVICES}"

# ── GPU list comes from srun, NOT hardcoded ───────────────────────
if [ -z "${CUDA_VISIBLE_DEVICES:-}" ]; then
    echo "ERROR: CUDA_VISIBLE_DEVICES not set."
    echo "  Run under srun --gres=gpu:N (it sets CUDA_VISIBLE_DEVICES), or"
    echo "  export it manually to FREE physical GPUs if running without srun."
    exit 1
fi
NUM_GPUS=$(echo "${CUDA_VISIBLE_DEVICES}" | tr ',' '\n' | grep -c .)
export NUM_GPUS

echo "=========================================="
echo "Standalone vLLM gpt-oss (srun-driven GPUs) - $(date)"
echo "Host:                 $(hostname)"
echo "CUDA_VISIBLE_DEVICES: ${CUDA_VISIBLE_DEVICES}  (NUM_GPUS=${NUM_GPUS}, TP=${NUM_GPUS})"
echo "SLURM_JOB_ID:         ${SLURM_JOB_ID:-(none)}"
echo "Model:                ${MODEL_NAME}  (${MODEL})  port ${VLLM_PORT}"
echo "Reasoning parser:     ${MODEL_REASONING_PARSER}"
echo "=========================================="
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits
echo ""

export HF_HOME=/workspace/hf-cache
# shellcheck disable=SC1091
source /raid/user_danielpedrozo/projects/info-gainme_dev/.env
export HF_TOKEN="${HF_TOKEN:?HF_TOKEN não definido no .env}"
export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"
mkdir -p /raid/user_danielpedrozo/projects/info-gainme_dev/logs \
         /raid/user_danielpedrozo/models /raid/user_danielpedrozo/hf-cache

SINGULARITY_IMAGE=/raid/user_danielpedrozo/images/vllm_openai_latest.sif

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
  --enable-prefix-caching \
  --disable-custom-all-reduce \
  --reasoning-parser ${MODEL_REASONING_PARSER}" \
  --api-key "mocha"
# --disable-custom-all-reduce: the custom P2P all-reduce kernel
# (custom_all_reduce.cuh) fails with 'invalid argument' on B200/this vLLM rc
# during warmup → kills a TP worker → "Engine core init failed / cancelled".
# Forcing NCCL all-reduce is the fix (small TP latency cost, but it works).

# Optional: upgrade vLLM in-container if the .sif lacks gpt-oss support
# (GptOssForCausalLM needs vLLM >= 0.10 + MXFP4). Off by default.
PRE_CMD=""
if [ "${VLLM_PIP_UPGRADE:-}" = "1" ]; then
    PRE_CMD="pip install --quiet --user --upgrade 'vllm>=0.10.0' && "
fi

echo "Iniciando vLLM (${MODEL_NAME}, TP=${NUM_GPUS})..."
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
     bash -c "${PRE_CMD}${vllm_cmd}" &

VLLM_PID=$!
echo "PID vLLM (singularity): ${VLLM_PID}"

echo "Aguardando readiness em http://localhost:${VLLM_PORT}/v1/models ..."
while ! curl -s "http://localhost:${VLLM_PORT}/v1/models" > /dev/null; do
    if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
        echo "ERRO: processo vLLM morreu antes de ficar pronto. Veja o log acima"
        echo "      (se for 'GptOssForCausalLM unrecognized' → rode com VLLM_PIP_UPGRADE=1)."
        exit 1
    fi
    echo "  ainda subindo..."
    sleep 5
done

echo "=========================================="
echo "vLLM PRONTO: ${MODEL_NAME} @ http://$(hostname):${VLLM_PORT}/v1"
echo "=========================================="
wait "${VLLM_PID}"
