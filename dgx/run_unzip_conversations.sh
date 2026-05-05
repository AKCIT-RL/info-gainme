#!/usr/bin/env bash
# Unzip all conversations.zip files under outputs/models/.
#
# Extracts each zip into its parent directory (conversations/ subdir).
# Skips if conversations/ already exists and is non-empty.
# Parallel with WORKERS (default 8).
#
# Usage:
#   bash dgx/run_unzip_conversations.sh [outputs_dir] [--workers N] [--force]
#
# Options:
#   outputs_dir   Base dir to search (default: outputs/)
#   --workers N   Parallel unzip jobs (default: 8)
#   --force       Re-extract even if conversations/ already exists

set -uo pipefail

OUTPUTS_DIR="outputs"
WORKERS=8
FORCE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --workers) WORKERS="$2"; shift 2 ;;
        --force)   FORCE=1; shift ;;
        *)         OUTPUTS_DIR="$1"; shift ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [[ "$OUTPUTS_DIR" == /* ]]; then
    OUTPUTS_PATH="$OUTPUTS_DIR"
else
    OUTPUTS_PATH="$PROJECT_DIR/$OUTPUTS_DIR"
fi

echo "=================================================="
echo "Unzip conversations.zip — $(date)"
echo "Dir:     $OUTPUTS_PATH"
echo "Workers: $WORKERS"
echo "Force:   $FORCE"
echo "=================================================="

# Collect zip files into a temp file (mapfile not available on macOS bash 3.2)
ZIPLIST=$(mktemp)
find "$OUTPUTS_PATH" -name "conversations.zip" | sort > "$ZIPLIST"
TOTAL=$(wc -l < "$ZIPLIST" | tr -d ' ')

if [[ "$TOTAL" -eq 0 ]]; then
    echo "No conversations.zip found under $OUTPUTS_PATH"
    rm -f "$ZIPLIST"
    exit 0
fi

echo "Found $TOTAL zip(s)"
echo ""

# Write per-zip worker script to a temp file (export -f not reliable on macOS)
WORKER=$(mktemp)
cat > "$WORKER" << 'WORKER_EOF'
#!/usr/bin/env bash
zip="$1"
force="$2"
dir="$(dirname "$zip")"
conv_dir="$dir/conversations"

if [[ "$force" -eq 0 ]] && [[ -d "$conv_dir" ]] && [[ -n "$(ls -A "$conv_dir" 2>/dev/null)" ]]; then
    echo "SKIP  $zip"
    exit 0
fi

if unzip -q -o "$zip" -d "$dir" 2>/dev/null; then
    echo "OK    $zip"
    exit 0
else
    echo "FAIL  $zip" >&2
    exit 1
fi
WORKER_EOF
chmod +x "$WORKER"

# Run in parallel via xargs
RESULTS=$(cat "$ZIPLIST" | xargs -P "$WORKERS" -I{} bash "$WORKER" {} "$FORCE" 2>&1)

DONE=0
SKIPPED=0
FAILED=0

while IFS= read -r line; do
    case "$line" in
        OK*)   ((DONE++))    ;;
        SKIP*) ((SKIPPED++)) ;;
        FAIL*) ((FAILED++))  ;;
    esac
done <<< "$RESULTS"

# Print individual lines
echo "$RESULTS"
echo ""

rm -f "$ZIPLIST" "$WORKER"

echo "=================================================="
echo "Done:    $DONE"
echo "Skipped: $SKIPPED (conversations/ already present)"
echo "Failed:  $FAILED"
echo "Total:   $TOTAL"
echo "Finished: $(date)"
echo "=================================================="

[[ $FAILED -eq 0 ]]
