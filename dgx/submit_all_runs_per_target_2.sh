#!/bin/bash
# Ressubmete TODOS os benchmarks com RUNS_PER_TARGET=2 em MODE=seeker_only.
# Uma chamada de sbatch por seeker (cobre todas as combinações domínio × FO/IO/PO).
# Como o benchmark_runner é resumível por (target_id, run_index), run01 já feito
# será pulado; só o run02 será preenchido.
#
# Modos por tipo:
#   - local-seeker (run_full_benchmark.sh + MODE=seeker_only):
#       sobe APENAS o seeker localmente (com TP nos GPUs alocados),
#       oracle/pruner (Qwen3-8B) é resolvido via configs/servers.yaml.
#       Pré-requisito: Qwen3-8B precisa estar rodando em http://10.100.0.113:8800
#
#   - external-seeker (run_external_seeker_benchmark.sh):
#       sobe APENAS o oracle/pruner Qwen3-8B local; seeker (235b, gemma-4-31b)
#       já está externo via servers.yaml. Necessário porque esses seekers são
#       grandes demais pra subir local mesmo com TP.
#
# DRY-RUN por padrão (mostra o que vai submeter). Para executar:
#   APPLY=1 bash dgx/submit_all_runs_per_target_2.sh
#
# Filtros:
#   USER_FILTER=daniel|julia|external APPLY=1 bash ...
#   SEEKER_FILTER=phi4 APPLY=1 bash ...

set -uo pipefail

APPLY="${APPLY:-0}"
USER_FILTER="${USER_FILTER:-all}"
SEEKER_FILTER="${SEEKER_FILTER:-}"

# Formato: USER|TYPE|SEEKER_NAME|HF_PATH|CONFIGS_TARGET|PARTITION|GRES|EXTRAS
#   TYPE   local | external
#   GRES   gpu:1 (TP=1) ou gpu:2 (TP=2 — necessário pros 30B+)
JOBS=(
  # --- Daniel (h100n2) — seeker local (TP=1, exceto onde indicado) ---
  "daniel|local|Qwen3-0.6B|Qwen/Qwen3-0.6B|configs/full/0.6b/|h100n2|gpu:1|"
  "daniel|local|Qwen3-4B-Thinking-2507|Qwen/Qwen3-4B-Thinking-2507|configs/full/4b/cot/|h100n2|gpu:1|"
  "daniel|local|Qwen3-4B-Instruct-2507|Qwen/Qwen3-4B-Instruct-2507|configs/full/4b/no_cot/|h100n2|gpu:1|"
  "daniel|local|Qwen3-8B|Qwen/Qwen3-8B|configs/full/8b/|h100n2|gpu:1|"
  "daniel|local|Nemotron-Cascade-8B|nvidia/Nemotron-Cascade-8B|configs/full/nemotron-8b/|h100n2|gpu:1|"
  "daniel|local|google/gemma-4-E2B-it|google/gemma-4-E2B-it|configs/full/gemma-4-e2b/|h100n2|gpu:1|"
  "daniel|local|google/gemma-4-E4B-it|google/gemma-4-E4B-it|configs/full/gemma-4-e4b/|h100n2|gpu:1|"
  "daniel|local|Llama-3.1-8B-Instruct|meta-llama/Llama-3.1-8B-Instruct|configs/full/llama-3.1-8b/no_cot/|h100n2|gpu:1|"
  "daniel|local|paprika_Meta-Llama-3.1-8B-Instruct|ftajwar/paprika_Meta-Llama-3.1-8B-Instruct|configs/full/paprika-llama-3.1-8b/no_cot/|h100n2|gpu:1|"
  "daniel|local|Phi-4-mini-instruct|microsoft/Phi-4-mini-instruct|configs/full/phi4-mini/no_cot/|h100n2|gpu:1|"
  "daniel|local|Phi-4-mini-reasoning|microsoft/Phi-4-mini-reasoning|configs/full/phi4-mini/cot/|h100n2|gpu:1|"
  "daniel|local|Phi-4-reasoning|microsoft/Phi-4-reasoning|configs/full/phi4/cot/|h100n2|gpu:1|"
  "daniel|local|phi-4|microsoft/phi-4|configs/full/phi4/no_cot/|h100n2|gpu:1|"

  # --- Daniel (b200n1) — 30B precisa de TP=2 ---
  "daniel|local|Qwen3-30B-A3B-Thinking-2507|Qwen/Qwen3-30B-A3B-Thinking-2507|configs/full/30b/cot/|b200n1|gpu:2|VLLM_ENGINE_READY_TIMEOUT_S=3600"
  "daniel|local|Qwen3-30B-A3B-Instruct-2507|Qwen/Qwen3-30B-A3B-Instruct-2507|configs/full/30b/no_cot/|b200n1|gpu:2|VLLM_ENGINE_READY_TIMEOUT_S=3600"

  # --- External seeker (seeker já está rodando externamente, sobe oracle/pruner local) ---
  "external|external|Qwen/Qwen3-235B-A22B-Instruct-2507-FP8|-|configs/full/235b/no_cot/|h100n2|gpu:1|"
  "external|external|google/gemma-4-31B-it|-|configs/full/gemma-4-31b/|h100n2|gpu:1|"

  # --- Julia (h100n3) — descomente pra espelhar/acelerar ---
  # "julia|local|Qwen3-8B|Qwen/Qwen3-8B|configs/full/8b/|h100n3|gpu:1|"
  # "julia|local|Qwen3-30B-A3B-Thinking-2507|Qwen/Qwen3-30B-A3B-Thinking-2507|configs/full/30b/cot/|h100n3|gpu:2|VLLM_ENGINE_READY_TIMEOUT_S=3600"
)

submit_one() {
    local user="$1" type="$2" seeker="$3" hf="$4" target="$5" partition="$6" gres="$7" extras="$8"
    local script export_str

    if [ "${type}" = "external" ]; then
        # run_external_seeker_benchmark.sh: sobe Qwen3-8B local, seeker via servers.yaml
        script="dgx/run_external_seeker_benchmark.sh"
        export_str="ALL,RUNS_PER_TARGET=2,CONFIGS_TARGET=${target},MODEL1=Qwen/Qwen3-8B,MODEL1_NAME=Qwen3-8B"
    else
        # run_full_benchmark.sh com MODE=seeker_only: sobe seeker local, oracle via servers.yaml
        script="dgx/run_full_benchmark.sh"
        export_str="ALL,RUNS_PER_TARGET=2,CONFIGS_TARGET=${target},MODE=seeker_only,MODEL1=${hf},MODEL1_NAME=${seeker},MODEL2_NAME=Qwen3-8B"
    fi

    [ -n "${extras}" ] && export_str="${export_str},${extras}"

    local cmd="sbatch --partition=${partition} --gres=${gres} --export=${export_str} ${script}"

    if [ "${user}" = "julia" ]; then
        cmd="bash -ic 'asjulia \"cd /raid/user_danielpedrozo/projects/info-gainme_dev; ${cmd}\"'"
    fi

    echo "[${user}/${type}] ${seeker} → ${target}"
    echo "  ${cmd}"
    if [ "${APPLY}" = "1" ]; then
        eval "${cmd}"
    fi
    echo
}

count=0
for line in "${JOBS[@]}"; do
    IFS='|' read -r user type seeker hf target partition gres extras <<< "${line}"
    if [ "${USER_FILTER}" != "all" ] && [ "${user}" != "${USER_FILTER}" ]; then
        continue
    fi
    if [ -n "${SEEKER_FILTER}" ] && [[ "${seeker}" != *"${SEEKER_FILTER}"* ]]; then
        continue
    fi
    submit_one "${user}" "${type}" "${seeker}" "${hf}" "${target}" "${partition}" "${gres}" "${extras}"
    count=$((count + 1))
done

echo "=========================================="
if [ "${APPLY}" = "1" ]; then
    echo "✓ ${count} jobs SUBMITTED"
else
    echo "DRY-RUN: ${count} jobs printed. Set APPLY=1 to actually submit."
fi
echo "=========================================="
