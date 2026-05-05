#!/bin/bash
# Executa run_unzip_conversations.sh em background via nohup, salvando log.
#
# Usage:
#   bash dgx/run_unzip_conversations_nohup.sh [args...]
#
# Todos os argumentos são repassados para run_unzip_conversations.sh, ex:
#   bash dgx/run_unzip_conversations_nohup.sh --workers 16
#   bash dgx/run_unzip_conversations_nohup.sh --force

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

TS=$(date +%Y%m%d_%H%M%S)
LOG="$LOG_DIR/unzip-conversations-${TS}.log"

echo "Starting unzip in background..."
echo "Log: $LOG"

nohup bash "$SCRIPT_DIR/run_unzip_conversations.sh" "$@" > "$LOG" 2>&1 &
PID=$!
echo "PID: $PID"
echo ""
echo "Monitor with:"
echo "  tail -f $LOG"
echo "  kill $PID   # to stop"
