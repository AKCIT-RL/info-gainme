#!/bin/bash
# Roda extract_belief_states.py — extrai o "belief state" que o Seeker mantém
# dentro do raciocínio (<think>) a cada turno e pontua contra o conjunto ativo
# verdadeiro (Omega_t) do Pruner. Suporta a tese de que o CoT funciona como
# scaffold de belief-tracking (ganho concentrado nos modos IO/PO).
#
# Usa um extrator LLM (Gemma-4-31B-IT por default), o mesmo modelo usado para
# extrair as perguntas candidatas no pipeline de reasoning traces.
#
# Lançamento típico (cria screen automaticamente):
#   bash bash_scripts/dgx/run_extract_belief_states_screen.sh
#
# Foreground (sem screen):
#   FOREGROUND=1 bash bash_scripts/dgx/run_extract_belief_states_screen.sh
#
# Acompanhar:
#   screen -r belief-states ; tail -f logs/belief-states-latest.log
#
# Variáveis de ambiente (com defaults):
#   BASE_URL   endpoint do extrator (…/v1)   (default: http://10.100.0.122:8041/v1 — dgx-B200-2)
#   MODEL      served-model-name do extrator (default: google/gemma-4-31B-it)
#   API_KEY                                   (default: EMPTY)
#   MAX_WORKERS   conversas em paralelo       (default: 8)
#   MAX_TURNS     limita turnos por conversa  (default: vazio = todos)
#   ONLY_RUN_INDEX  filtra run_index (ex.: 1) (default: vazio = todos)
#   SAMPLE_INDICES  posições 0-based no csv ('+' vira ',')   (default: vazio = todas)
#   SEEKERS         whitelist de seekers ('+' vira ',') — só com --all
#   UNIFIED_JSONL   saída (default: outputs/belief_states.jsonl)
#   FORCE / DRY_RUN  "1" para re-extrair / só listar
#
# Argumento posicional opcional:
#   $1   runs.csv específico. Se omitido, processa todos os CoT via --all.

umask 002
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

PROJECT_DIR="/raid/user_danielpedrozo/projects/info-gainme_dev"
SINGULARITY_IMAGE="/raid/user_danielpedrozo/images/vllm_openai_latest.sif"
export SINGULARITY_TMPDIR="${SINGULARITY_TMPDIR:-/raid/user_danielpedrozo/tmp/singularity-${USER}}"
export APPTAINER_TMPDIR="${APPTAINER_TMPDIR:-${SINGULARITY_TMPDIR}}"
mkdir -p "${SINGULARITY_TMPDIR}"

if [ -z "${STY:-}" ] && [ "${FOREGROUND:-0}" != "1" ]; then
    mkdir -p "${PROJECT_DIR}/logs"
    echo "Iniciando screen 'belief-states' (run=${RUN_TS})..."
    screen -dmS belief-states bash -c "RUN_TS='${RUN_TS}' BASE_URL='${BASE_URL:-}' MODEL='${MODEL:-}' API_KEY='${API_KEY:-}' MAX_WORKERS='${MAX_WORKERS:-}' MAX_TURNS='${MAX_TURNS:-}' ONLY_RUN_INDEX='${ONLY_RUN_INDEX:-}' SAMPLE_INDICES='${SAMPLE_INDICES:-}' SEEKERS='${SEEKERS:-}' UNIFIED_JSONL='${UNIFIED_JSONL:-}' FORCE='${FORCE:-}' DRY_RUN='${DRY_RUN:-}' bash '${BASH_SOURCE[0]}' ${1:-}; exec bash"
    echo "  screen -r belief-states"
    echo "  tail -f ${PROJECT_DIR}/logs/belief-states-latest.log"
    exit 0
fi

RUNS_PATH="${1:-}"
MAX_WORKERS="${MAX_WORKERS:-8}"
BASE_URL="${BASE_URL:-http://10.100.0.122:8041/v1}"
MODEL="${MODEL:-google/gemma-4-31B-it}"
API_KEY="${API_KEY:-EMPTY}"

EXTRA_FLAGS=""
[[ "${FORCE}" == "1" ]]          && EXTRA_FLAGS+=" --force"
[[ "${DRY_RUN}" == "1" ]]        && EXTRA_FLAGS+=" --dry-run"
[[ -n "${MAX_TURNS:-}" ]]        && EXTRA_FLAGS+=" --max-turns ${MAX_TURNS}"
[[ -n "${ONLY_RUN_INDEX:-}" ]]   && EXTRA_FLAGS+=" --only-run-index ${ONLY_RUN_INDEX}"
SAMPLE_INDICES="${SAMPLE_INDICES//+/,}"
[[ -n "${SAMPLE_INDICES:-}" ]]   && EXTRA_FLAGS+=" --sample-indices ${SAMPLE_INDICES}"
SEEKERS="${SEEKERS//+/,}"
[[ -n "${SEEKERS:-}" ]]          && EXTRA_FLAGS+=" --seekers ${SEEKERS}"
[[ -n "${UNIFIED_JSONL:-}" ]]    && EXTRA_FLAGS+=" --unified-jsonl ${UNIFIED_JSONL}"

mkdir -p "${PROJECT_DIR}/logs"
LOG_FILE="${LOG_FILE:-${PROJECT_DIR}/logs/belief-states-${RUN_TS}.log}"
ln -sfn "${LOG_FILE}" "${PROJECT_DIR}/logs/belief-states-latest.log"
if [ -z "${__LOG_REDIRECTED__:-}" ]; then
    export __LOG_REDIRECTED__=1
    exec > >(tee -a "${LOG_FILE}") 2>&1
fi

echo "=========================================="
echo "Belief-State Extraction — RUN ${RUN_TS}"
echo "Endpoint:    ${BASE_URL}"
echo "Extractor:   ${MODEL}"
echo "Max workers: ${MAX_WORKERS}"
echo "Flags:       ${EXTRA_FLAGS:-(default: resume on)}"
echo "Log:         ${LOG_FILE}"
echo "Started:     $(date)"
if [ -n "${RUNS_PATH}" ]; then
    echo "CSV:         ${RUNS_PATH}"
    TARGET="'${RUNS_PATH}'"
else
    echo "Mode:        --all (todos os CoT runs.csv sob outputs/)"
    TARGET="--all"
fi
echo "=========================================="

CMD="python3 scripts/reasoning_traces/extract_belief_states.py \
    ${TARGET} \
    --model '${MODEL}' \
    --base-url '${BASE_URL}' \
    --api-key '${API_KEY}' \
    --max-workers ${MAX_WORKERS}${EXTRA_FLAGS}"

sg sd22 -c "
    singularity exec \
        --bind /raid/user_danielpedrozo:/workspace \
        --pwd /workspace/projects/info-gainme_dev \
        '${SINGULARITY_IMAGE}' \
        bash -c \"
            pip install --quiet --user -r requirements.txt
            ${CMD}
        \"
"

echo "=========================================="
echo "Extração RUN ${RUN_TS} finalizada — $(date)"
echo "=========================================="
