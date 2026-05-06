#!/bin/bash
# Sync outputs/ entre nodes DGX — bidirecional seguro com --update.
#
# Cobre 2 conjuntos:
#   1. outputs/models/ recursivo (runs.csv, summary.json, conversations/...)
#   2. arquivos de análise no root: seeker_traces.jsonl, question_classifications.jsonl,
#      unified_experiments.csv, reasoning_traces_analysis.json, model_summary.csv
#
# Em ambas as direções, rsync só transfere arquivos cujo mtime do source é
# MAIS NOVO que o destination. Isso protege:
#   - Pull: arquivos que h2 tem com versão mais nova não são sobrescritos.
#   - Push: arquivos que b200/h3 estão escrevendo (mais novos) não são
#           sobrescritos com versões velhas que h2 tenha.
# Resultado: pull + push deixa todos os nodes com a versão mais recente de
# cada arquivo, sem destruição mesmo durante benchmarks ativos.
#
# Usage:
#   bash dgx/sync_outputs.sh [h3|b200|all]          # pull from remote(s)
#   bash dgx/sync_outputs.sh push [h3|b200|all]     # push from h2 to remote(s)
#
# Nodes:
#   h3   — dgx-H100-03  10.100.0.113
#   b200 — dgx-B200-1   10.100.0.121

set -uo pipefail

PROJECT=/raid/user_danielpedrozo/projects/info-gainme_dev
DEST="$PROJECT/outputs/models/"
OUTPUTS_ROOT="$PROJECT/outputs/"
LOGS="$PROJECT/logs"
mkdir -p "$LOGS"

# Arquivos de análise no nível raiz de outputs/. Cada um é opcional — rsync
# silenciosamente pula os que não existem do lado source.
ANALYSIS_FILES=(
    "seeker_traces.jsonl"
    "question_classifications.jsonl"
    "unified_experiments.csv"
    "reasoning_traces_analysis.json"
    "model_summary.csv"
)

IP_H3=10.100.0.113
IP_B200=10.100.0.121

# Parse args: optional "push" keyword, then target
MODE="pull"
if [ "${1:-}" = "push" ]; then
    MODE="push"
    shift
fi

TARGET="${1:-all}"
TARGET="${TARGET#--}"   # strip leading -- (--all → all, etc.)
TS=$(date +%Y%m%d_%H%M%S)

sync_node() {
    local name="$1"
    local ip="$2"
    local logfile="$LOGS/sync_${MODE}_${name}_${TS}.log"

    if [ "$MODE" = "push" ]; then
        echo "==> Pushing h2 → $name ($ip)  (--update: only newer files overwrite)"
        echo "    Log: $logfile"
        echo "    Started: $(date)"
        rsync -rlv --omit-dir-times --update \
            "$DEST" \
            "${ip}:${DEST}" \
            >> "$logfile" 2>&1
    else
        echo "==> Pulling $name ($ip) → h2  (--update: only newer files overwrite)"
        echo "    Log: $logfile"
        echo "    Started: $(date)"
        rsync -rlv --omit-dir-times --update \
            "${ip}:${DEST}" \
            "$DEST" \
            >> "$logfile" 2>&1
    fi

    # Sync de arquivos de análise no root de outputs/ (JSONL + CSVs agregados).
    # Mesma direção, mesma flag --update. Faz cada arquivo separado pra não
    # falhar caso algum não exista no source — `--ignore-missing-args` cobre isso.
    {
        echo ""
        echo "--- analysis files ($MODE) ---"
        for f in "${ANALYSIS_FILES[@]}"; do
            if [ "$MODE" = "push" ]; then
                rsync -lv --update --ignore-missing-args \
                    "${OUTPUTS_ROOT}${f}" \
                    "${ip}:${OUTPUTS_ROOT}${f}" 2>&1 || true
            else
                rsync -lv --update --ignore-missing-args \
                    "${ip}:${OUTPUTS_ROOT}${f}" \
                    "${OUTPUTS_ROOT}${f}" 2>&1 || true
            fi
        done
    } >> "$logfile" 2>&1

    local rc=$?
    local transferred
    transferred=$(grep -c '^s_' "$logfile" 2>/dev/null) || transferred=0

    if [ $rc -eq 0 ] || [ $rc -eq 23 ]; then
        echo "    Done: $(date) — ~${transferred} paths transferred (exit $rc)"
    else
        echo "    FAILED (exit $rc) — check $logfile"
    fi
    return 0
}

case "$TARGET" in
    h3)
        sync_node h3 "$IP_H3"
        ;;
    b200)
        sync_node b200 "$IP_B200"
        ;;
    all)
        sync_node h3 "$IP_H3"
        sync_node b200 "$IP_B200"
        ;;
    *)
        echo "Usage: $0 [push] [h3|b200|all]"
        exit 1
        ;;
esac
