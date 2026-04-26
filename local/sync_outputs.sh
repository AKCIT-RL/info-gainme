#!/bin/bash
# Puxa os outputs analíticos da H100-02 (10.100.0.112) para o repo local.
#
# Por padrão roda dentro de um screen (chamado "sync") e gera log timestamped.
# Sincroniza só os arquivos pequenos de análise (JSONL/CSV/JSON agregados).
# Pra puxar a árvore inteira de outputs/models/ (conversations, seeker.json,
# oracle.json, ...) passe --with-models — pode ser dezenas de GB.
#
# Uso:
#   bash local/sync_outputs.sh                # screen "sync" + log timestamped
#   bash local/sync_outputs.sh --with-models  # + árvore completa de modelos
#   bash local/sync_outputs.sh --dry-run      # mostra o que seria copiado
#   HOST=user_X@1.2.3.4 bash local/sync_outputs.sh    # outro host
#   FOREGROUND=1 bash local/sync_outputs.sh   # roda no terminal atual (sem screen)
#
# Acompanhar:
#   screen -r sync
#   tail -f logs/sync-latest.out

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-user_danielpedrozo@10.100.0.112}"
REMOTE_DIR="${REMOTE_DIR:-/raid/user_danielpedrozo/projects/info-gainme_dev}"
RUN_TS="${RUN_TS:-$(date +%Y%m%d-%H%M%S)}"

WITH_MODELS=0
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --with-models) WITH_MODELS=1 ;;
        --dry-run)     DRY_RUN=1 ;;
        -h|--help)
            sed -n '2,/^set -e/p' "$0" | sed 's/^# \{0,1\}//' | head -n -1
            exit 0
            ;;
        *) echo "flag desconhecida: $arg" >&2; exit 1 ;;
    esac
done

# Auto-screen: se não estamos num screen e FOREGROUND não foi pedido, lança um.
# screen seta $STY automaticamente, então o re-entry no script segue direto.
if [ -z "${STY:-}" ] && [ "${FOREGROUND:-0}" != "1" ]; then
    mkdir -p "${PROJECT_DIR}/logs"
    LOG_FILE="${PROJECT_DIR}/logs/sync-${RUN_TS}.out"
    ln -sfn "${LOG_FILE}" "${PROJECT_DIR}/logs/sync-latest.out"
    echo "Iniciando screen 'sync' (run=${RUN_TS})..."
    screen -dmS sync bash -c "RUN_TS='${RUN_TS}' bash '${BASH_SOURCE[0]}' $* 2>&1 | tee '${LOG_FILE}'; exec bash"
    echo "  screen -r sync"
    echo "  tail -f ${PROJECT_DIR}/logs/sync-latest.out"
    exit 0
fi

RSYNC_OPTS=(-av --update --partial)
[ "$DRY_RUN" -eq 1 ] && RSYNC_OPTS+=(--dry-run)

mkdir -p "${PROJECT_DIR}/outputs"

echo "===================================="
echo "Sync outputs from $HOST — RUN ${RUN_TS}"
echo "Remote:  ${REMOTE_DIR}/outputs/"
echo "Local:   ${PROJECT_DIR}/outputs/"
[ "$DRY_RUN" -eq 1 ] && echo "Mode:    DRY RUN"
echo "Started: $(date)"
echo "===================================="

# 1) Arquivos analíticos pequenos (top-level de outputs/)
echo
echo "--- Arquivos analíticos (top-level) ---"
rsync "${RSYNC_OPTS[@]}" \
    --include='*.jsonl' \
    --include='*.csv' \
    --include='*.json' \
    --exclude='*' \
    "${HOST}:${REMOTE_DIR}/outputs/" \
    "${PROJECT_DIR}/outputs/"

# 2) Resultados específicos de pipelines (subdirs com agregados)
for sub in question_classification reasoning_traces; do
    echo
    echo "--- outputs/$sub/ ---"
    rsync "${RSYNC_OPTS[@]}" \
        --include='*/' \
        --include='*.json' \
        --include='*.csv' \
        --include='*.jsonl' \
        --exclude='*' \
        "${HOST}:${REMOTE_DIR}/outputs/${sub}/" \
        "${PROJECT_DIR}/outputs/${sub}/" 2>/dev/null || echo "  (não existe no remoto)"
done

# 3) Árvore completa de modelos — opcional (pesado)
if [ "$WITH_MODELS" -eq 1 ]; then
    echo
    echo "--- outputs/models/ (CONVERSAS COMPLETAS — pode demorar) ---"
    rsync "${RSYNC_OPTS[@]}" \
        --exclude='*.lock' \
        "${HOST}:${REMOTE_DIR}/outputs/models/" \
        "${PROJECT_DIR}/outputs/models/"
fi

echo
echo "===================================="
echo "Sync RUN ${RUN_TS} completo — $(date)"
echo "Arquivos no outputs/ (top-level):"
ls -la "${PROJECT_DIR}/outputs/" | grep -E "\.jsonl$|\.csv$|\.json$" | head -20
echo "===================================="
