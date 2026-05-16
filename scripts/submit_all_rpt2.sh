#!/usr/bin/env bash
# Submit all configs/full/ jobs with runs_per_target=2 (already edited in YAMLs).
#
# Strategy:
#   - 1 GPU per job (--gres=gpu:1)
#   - MODE=seeker_only — only the seeker is brought up locally, oracle/pruner
#     come from external endpoints in configs/servers.yaml (Qwen3-8B).
#   - 12 jobs distributed across b200n1 / h100n2 (daniel) / h100n3 (julia).
#
# Run this on h2 (daniel). Jobs targeted at h3 are submitted via the `asjulia`
# alias (only defined in h2's ~/.bashrc; we wrap with `bash -ic`).
#
# Usage:
#   bash scripts/submit_all_rpt2.sh                 # submit everything
#   bash scripts/submit_all_rpt2.sh --dry-run       # print only
#   bash scripts/submit_all_rpt2.sh --only 4b-cot   # filter by tag

set -euo pipefail

DRY_RUN=0
ONLY=""
VIA_SRUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --via-srun) VIA_SRUN=1; shift ;;
    --only) ONLY="$2"; shift 2 ;;
    --only=*) ONLY="${1#--only=}"; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Common pieces
EXPORT_BASE="ALL,MODE=seeker_only,MODEL2_NAME=Qwen3-8B"
# srun mode: same KVs but as `env` assignments (no ALL, space-separated)
ENV_BASE="MODE=seeker_only MODEL2_NAME=Qwen3-8B"
SCRIPT="bash_scripts/dgx/run_full_benchmark.sh"
PROJECT_DIR="/raid/user_danielpedrozo/projects/info-gainme_dev"
SRUN_OPTS="--gres=gpu:1 --mem=60G --time=2-00:00:00"

# JOB SPEC: tag|partition|owner|MODEL1_KV|extra_env|CONFIGS_TARGET
#   owner = "daniel" (run locally) or "julia" (wrap via asjulia)
declare -a JOBS=(
  # ── b200n1 (largest VRAM — heavy MoE / 30B models) ─────────────
  "30b-cot|b200n1|daniel|MODEL1=Qwen/Qwen3-30B-A3B-Thinking-2507,MODEL1_NAME=Qwen3-30B-A3B-Thinking-2507|VLLM_ENGINE_READY_TIMEOUT_S=3600|configs/full/30b/cot/"
  "30b-no-cot|b200n1|daniel|MODEL1=Qwen/Qwen3-30B-A3B-Instruct-2507,MODEL1_NAME=Qwen3-30B-A3B-Instruct-2507|VLLM_ENGINE_READY_TIMEOUT_S=3600|configs/full/30b/no_cot/"
  "gemma-4-31b|b200n1|daniel|MODEL1=google/gemma-4-31B-it,MODEL1_NAME=google/gemma-4-31B-it|VLLM_ENGINE_READY_TIMEOUT_S=3600|configs/full/gemma-4-31b/"

  # ── h100n2 (daniel) ────────────────────────────────────────────
  "4b-cot|h100n2|daniel|MODEL1=Qwen/Qwen3-4B-Thinking-2507,MODEL1_NAME=Qwen3-4B-Thinking-2507||configs/full/4b/cot/"
  "4b-no-cot|h100n2|daniel|MODEL1=Qwen/Qwen3-4B-Instruct-2507,MODEL1_NAME=Qwen3-4B-Instruct-2507||configs/full/4b/no_cot/"
  "8b|h100n2|daniel|MODEL1=Qwen/Qwen3-8B,MODEL1_NAME=Qwen3-8B||configs/full/8b/"
  "nemotron-8b|h100n2|daniel|MODEL1=nvidia/Nemotron-Cascade-8B,MODEL1_NAME=Nemotron-Cascade-8B||configs/full/nemotron-8b/"

  # ── h100n3 (julia, via asjulia) ────────────────────────────────
  "0.6b|h100n3|julia|MODEL1=Qwen/Qwen3-0.6B,MODEL1_NAME=Qwen3-0.6B||configs/full/0.6b/"
  "gemma-4-e2b|h100n3|julia|MODEL1=google/gemma-4-E2B-it,MODEL1_NAME=google/gemma-4-E2B-it||configs/full/gemma-4-e2b/"
  "gemma-4-e4b|h100n3|julia|MODEL1=google/gemma-4-E4B-it,MODEL1_NAME=google/gemma-4-E4B-it||configs/full/gemma-4-e4b/"
  "llama-3.1-8b|h100n3|julia|MODEL1=meta-llama/Llama-3.1-8B-Instruct,MODEL1_NAME=Llama-3.1-8B-Instruct||configs/full/llama-3.1-8b/no_cot/"
  "paprika-llama-3.1-8b|h100n3|julia|MODEL1=ftajwar/paprika_Meta-Llama-3.1-8B-Instruct,MODEL1_NAME=paprika_Meta-Llama-3.1-8B-Instruct||configs/full/paprika-llama-3.1-8b/no_cot/"
)

ONLY_PADDED=""
if [[ -n "$ONLY" ]]; then
  ONLY_PADDED=",$(echo "$ONLY" | tr -d ' '),"
fi
keep_tag() {
  [[ -z "$ONLY_PADDED" ]] && return 0
  [[ "$ONLY_PADDED" == *",$1,"* ]]
}

build_sbatch() {
  local partition="$1"
  local model_kv="$2"
  local extra_env="$3"
  local target="$4"
  local export_str="${EXPORT_BASE},${model_kv}"
  if [[ -n "$extra_env" ]]; then
    export_str="${export_str},${extra_env}"
  fi
  export_str="${export_str},CONFIGS_TARGET=${target}"
  echo "sbatch --partition=${partition} --gres=gpu:1 --export=${export_str} ${SCRIPT}"
}

# srun mode: builds the inner shell command (no surrounding quotes).
# Caller wraps it per-owner. The inner has NO single/double quotes and
# NO $ so it can be embedded in either '...' (daniel) or \"...\" (julia).
# sbatch is currently broken (slurmctld spool I/O error); srun bypasses it.
build_srun_inner() {
  local partition="$1"
  local model_kv="$2"
  local extra_env="$3"
  local target="$4"
  local tag="$5"
  local kv_env="${model_kv//,/ }"   # commas → spaces for `env`
  local env_str="${ENV_BASE} ${kv_env}"
  if [[ -n "$extra_env" ]]; then
    env_str="${env_str} ${extra_env//,/ }"
  fi
  env_str="${env_str} CONFIGS_TARGET=${target}"
  echo "cd ${PROJECT_DIR} && env ${env_str} srun --partition=${partition} ${SRUN_OPTS} bash ${SCRIPT} 2>&1 | tee logs/srun-${tag}.out"
}

submitted=0
for entry in "${JOBS[@]}"; do
  IFS='|' read -r tag partition owner model_kv extra_env target <<< "$entry"

  if ! keep_tag "$tag"; then
    continue
  fi

  echo "── [$tag] partition=$partition owner=$owner ──"

  if [[ $VIA_SRUN -eq 1 ]]; then
    inner=$(build_srun_inner "$partition" "$model_kv" "$extra_env" "$target" "$tag")
    if [[ "$owner" == "julia" ]]; then
      # screen runs on h3 under julia. Inner goes in bash -c "..." (double
      # quotes), the whole thing in asjulia "...", all in bash -ic '...'.
      cmd="bash -ic 'asjulia \"screen -dmS srun-${tag} bash -c \\\"${inner}\\\"\"'"
    else
      # daniel: run screen locally; inner safely single-quoted.
      cmd="screen -dmS srun-${tag} bash -c '${inner}'"
    fi
  else
    sb=$(build_sbatch "$partition" "$model_kv" "$extra_env" "$target")
    if [[ "$owner" == "julia" ]]; then
      cmd="bash -ic 'asjulia \"cd ${PROJECT_DIR}; ${sb}\"'"
    else
      cmd="$sb"
    fi
  fi

  echo "$cmd"
  if [[ $DRY_RUN -eq 0 ]]; then
    eval "$cmd"
    submitted=$((submitted + 1))
  fi
  echo
done

if [[ $DRY_RUN -eq 1 ]]; then
  echo "(dry-run — nothing submitted)"
else
  echo "Submitted $submitted job(s)."
  if [[ $VIA_SRUN -eq 1 ]]; then
    echo "srun mode: each job runs in a detached screen 'srun-<tag>'."
    echo "  list screens: screen -ls"
    echo "  attach:       screen -r srun-<tag>"
    echo "  tail log:     tail -f logs/srun-<tag>.out"
  fi
  echo "Check daniel: squeue -u \$USER"
  echo "Check julia: bash -ic 'asjulia \"squeue -u user_juliadollis\"'  (or alias: sqj)"
fi
