#!/usr/bin/env bash
# Executa download_from_hf.py numa sessão screen com uv run, salvando log.
#
# Usage:
#   bash local/run_download_hf_screen.sh [args...]
#
# Todos os argumentos são repassados para download_from_hf.py, ex:
#   bash local/run_download_hf_screen.sh --num-workers 8
#   bash local/run_download_hf_screen.sh --repo-id akcit-rl/info-gainme --num-workers 8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/download_hf_${TS}.log"
SESSION="download_hf_${TS}"

echo "Starting HF download in screen session: $SESSION"
echo "Log: $LOG"

screen -dmS "$SESSION" bash -c "
  cd '$PROJECT_DIR'
  uv run python scripts/hf/download_from_hf.py $* 2>&1 | tee '$LOG'
  echo 'Done — press any key to close'
  read -r
"

echo ""
echo "Monitor with:"
echo "  tail -f $LOG"
echo "  screen -r $SESSION   # attach to session"
echo "  screen -X -S $SESSION quit   # kill session"
