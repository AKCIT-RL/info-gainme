cd /raid/user_danielpedrozo/projects/info-gainme_dev

JOBS=(
  "configs/full/8b/|Qwen/Qwen3-8B|Qwen3-8B"
  "configs/full/30b/cot/|Qwen/Qwen3-30B-A3B-Thinking-2507|Qwen3-30B-A3B-Thinking-2507"
  "configs/full/30b/no_cot/|Qwen/Qwen3-30B-A3B-Instruct-2507|Qwen3-30B-A3B-Instruct-2507"
  "configs/full/4b/cot/|Qwen/Qwen3-4B-Thinking-2507|Qwen3-4B-Thinking-2507"
  "configs/full/4b/no_cot/|Qwen/Qwen3-4B-Instruct-2507|Qwen3-4B-Instruct-2507"
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
