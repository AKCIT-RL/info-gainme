cd /raid/user_danielpedrozo/projects/info-gainme_dev

JOBS=(
  "configs/full/8b/|Qwen/Qwen3-8B|Qwen3-8B|0,1"
  "configs/full/30b/cot/|Qwen/Qwen3-30B-A3B-Thinking-2507|Qwen3-30B-A3B-Thinking-2507|2,3"
  "configs/full/30b/no_cot/|Qwen/Qwen3-30B-A3B-Instruct-2507|Qwen3-30B-A3B-Instruct-2507|0,1"
  "configs/full/4b/cot/|Qwen/Qwen3-4B-Thinking-2507|Qwen3-4B-Thinking-2507|2,3"
  "configs/full/4b/no_cot/|Qwen/Qwen3-4B-Instruct-2507|Qwen3-4B-Instruct-2507|0,1"
)

for j in "${JOBS[@]}"; do
  IFS='|' read -r CFG M1 M1NAME GPUS <<< "$j"
  SCR="ig-$(echo "$M1NAME" | tr '/' '-')"
  echo ">> screen $SCR  ←  $CFG  (GPUs $GPUS)"
  screen -dmS "$SCR" bash -c "
    MODE=seeker_only \
    MODEL1='$M1' MODEL1_NAME='$M1NAME' MODEL2_NAME=Qwen3-8B \
    FORCE_GPUS='$GPUS' \
    VLLM_ENGINE_READY_TIMEOUT_S=3600 \
    CONFIGS_TARGET='$CFG' \
    srun --partition=b200n1 --gres=gpu:2 --mem=120G --time=2-00:00:00 \
         --output='logs/${SCR}.log' --job-name='$SCR' \
      bash bash_scripts/dgx/run_full_benchmark.sh; exec bash"
done