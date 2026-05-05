#!/usr/bin/env bash
# Executa download_from_hf.py em background via nohup, salvando log.
#
# Usage:
#   bash local/run_download_hf_nohup.sh [args...]
#
# Todos os argumentos são repassados para download_from_hf.py, ex:
#   bash local/run_download_hf_nohup.sh --num-workers 8
#   bash local/run_download_hf_nohup.sh --repo-id akcit-rl/info-gainme --num-workers 8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/download_hf_${TS}.log"

# Use .venv python if available, else fall back to python3
PYTHON="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python3"
fi

echo "Starting HF download in background..."
echo "Python: $PYTHON"
echo "Log: $LOG"

nohup "$PYTHON" "$PROJECT_DIR/scripts/hf/download_from_hf.py" "$@" > "$LOG" 2>&1 &
PID=$!
echo "PID: $PID"
echo ""
echo "Monitor with:"
echo "  tail -f $LOG"
echo "  kill $PID   # to stop"
