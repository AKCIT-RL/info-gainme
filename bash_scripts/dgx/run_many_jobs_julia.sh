cd /raid/user_danielpedrozo/projects/info-gainme_dev

JOBS=(
  "configs/full/llama-3.1-8b/|meta-llama/Llama-3.1-8B-Instruct|Llama-3.1-8B-Instruct"
  "configs/full/nemotron-8b/|nvidia/Nemotron-Cascade-8B|Nemotron-Cascade-8B"
  "configs/full/paprika-llama-3.1-8b/|ftajwar/paprika_Meta-Llama-3.1-8B-Instruct|paprika_Meta-Llama-3.1-8B-Instruct"
  "configs/full/gemma-4-31b/|google/gemma-4-31B-it|google/gemma-4-31B-it"
  "configs/full/gemma-4-e4b/|google/gemma-4-E4B-it|google/gemma-4-E4B-it"
)

for j in "${JOBS[@]}"; do
  IFS='|' read -r CFG M1 M1NAME GPUS <<< "$j"
  JOB_NAME="ig-$(echo "$M1NAME" | tr '/' '-')"
  echo ">> sbatch $JOB_NAME  ←  $CFG"
  sbatch \
    --partition=b200n1 \
    --gres=gpu:1 \
    --mem=60G \
    --time=2-00:00:00 \
    --job-name="$JOB_NAME" \
    --output="/raid/user_danielpedrozo/projects/info-gainme_dev/logs/%x-%j.log" \
    --export=ALL,MODE=seeker_only,MODEL1="$M1",MODEL1_NAME="$M1NAME",MODEL2_NAME=Qwen3-8B,VLLM_ENGINE_READY_TIMEOUT_S=3600,CONFIGS_TARGET="$CFG" \
    bash_scripts/dgx/run_full_benchmark.sh
done
