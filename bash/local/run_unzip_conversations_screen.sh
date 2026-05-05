#!/bin/bash
# Executa run_unzip_conversations.sh numa sessão screen, salvando log.
#
# Usage:
#   bash local/run_unzip_conversations_screen.sh [args...]
#
# Todos os argumentos são repassados para run_unzip_conversations.sh, ex:
#   bash local/run_unzip_conversations_screen.sh --workers 16
#   bash local/run_unzip_conversations_screen.sh --force

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/unzip-conversations-${TS}.log"
SESSION="unzip_conv_${TS}"

echo "Starting unzip in screen session: $SESSION"
echo "Log: $LOG"

screen -dmS "$SESSION" bash -c "
  bash '$SCRIPT_DIR/run_unzip_conversations.sh' $* 2>&1 | tee '$LOG'
  echo 'Done — press any key to close'
  read -r
"

echo ""
echo "Monitor with:"
echo "  tail -f $LOG"
echo "  screen -r $SESSION   # attach to session"
echo "  screen -X -S $SESSION quit   # kill session"
