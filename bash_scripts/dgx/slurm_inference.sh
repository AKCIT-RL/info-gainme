#!/bin/bash
#SBATCH --partition=h100n2
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=32G
#SBATCH --job-name=eval-positivo
#SBATCH --output=logs/eval-%j.log


# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file..."
    export $(grep -v '^#' .env | xargs)
fi

echo "CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"

MODEL_CACHE_PATH="/raid/user_danielpedrozo/hf-cache/"
IMAGE_DOCKER="/raid/user_danielpedrozo/images/vllm_openai_latest.sif"


if [ "${USER}" == "aluno_daniel" ]; then
    MODEL_CACHE_PATH="/raid/aluno_daniel/cache/vllm_cache_models/"
    IMAGE_DOCKER="/raid/aluno_daniel/images/vllm-openai@sha256_014a95f21c9edf6abe0aea6b07353f96baa4ec291c427bb1176dc7c93a85845c.sif"
    IMAGE_DOCKER="/raid/aluno_daniel/images/vllm-openai_latest.sif"
fi

srun singularity exec \
    --nvccli  \
    --no-home \
    --bind "${MODEL_CACHE_PATH}:/root/" \
    ${IMAGE_DOCKER} \
    bash -c 'export HF_HOME=/root/
             export HOME=/tmp/home_${USER}
             export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
             export JUDGE_PORT=$((RANDOM+10000))
             export JUDGE_API_KEY=positivo-key
             export JUDGE_HOST=localhost

             export DEBUG_LEADERBOARD=0
             #export DEBUG_LEADERBOARD=1

             hf auth login --token ${HF_TOKEN}

             # Clean pip cache and install dependencies
             pip cache purge || true
             pip install --upgrade pip --no-cache-dir
             pip install datasets --user --no-cache-dir
             pip install tenacity --user --no-cache-dir
             pip install --upgrade transformers accelerate --user 
             
             #export SLURM_GPUS_ON_NODE=4
             #export CUDA_VISIBLE_DEVICES=0,1,2,3
             export GPUS=$SLURM_GPUS_ON_NODE

            . fila_inferences.sh
    
             
             echo "Iniciando o servidor utilizando as GPUS ${CUDA_VISIBLE_DEVICES} na porta ${PORT}..."
             nvidia-smi -i ${CUDA_VISIBLE_DEVICES}

            GPU_MEMORY_UTILIZATION=0.95
             if [ ${GPUS} -eq 2 ]; then
                 GPU_MEMORY_UTILIZATION=0.90
             fi
             
             if [ ${GPUS} -eq 4 ]; then
                 GPU_MEMORY_UTILIZATION=0.90
             fi

             vllm serve openai/gpt-oss-120b \
                    --tensor-parallel-size ${GPUS} \
                    --async-scheduling \
                    --gpu-memory-utilization ${GPU_MEMORY_UTILIZATION} \
                    --port ${JUDGE_PORT} \
                    --api-key ${JUDGE_API_KEY} &
            VLLM_PID=$!
            echo "vLLM PID: ${VLLM_PID}"

             while true; do
                    STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${JUDGE_HOST}:${JUDGE_PORT}/health")
                    if [ "${STATUS_CODE}" -eq 200 ]; then
                        echo "VLLM server is up and running on port ${JUDGE_PORT}."
                        break
                    else
                        echo "Waiting for VLLM server to start..."
                        sleep 2
                    fi
                done

            python3 2.judge.py 
            #--no-upload

            echo "Finalizando o servidor VLLM..."
            kill ${VLLM_PID}

            '

exit 0
