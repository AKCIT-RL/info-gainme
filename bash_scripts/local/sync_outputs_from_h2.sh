#!/usr/bin/env bash
# Sync outputs/ from h100n2 (10.100.0.112) to local laptop.
#
# Strategy:
#   - Pulls everything EXCEPT loose `conversations/` dirs (use the zips).
#   - `--update` so we never overwrite a newer local file.
#   - No `--delete` so locally-only files are preserved.
#   - After rsync, unzips any new `conversations.zip` with overwrite.
#
# Usage:
#   bash scripts/sync_outputs_from_h2.sh                # do it
#   bash scripts/sync_outputs_from_h2.sh --dry-run      # preview
#   bash scripts/sync_outputs_from_h2.sh --no-unzip     # skip the unzip step
set -euo pipefail

REMOTE_USER="user_danielpedrozo"
REMOTE_HOST="10.100.0.112"
REMOTE_PATH="/raid/user_danielpedrozo/projects/info-gainme_dev/outputs/"

# Resolve project root from this script's location: scripts/ -> project root -> outputs/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_PATH="$(cd "$SCRIPT_DIR/.." && pwd)/outputs"

DRY_RUN=0
DO_UNZIP=1
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-unzip) DO_UNZIP=0 ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

RSYNC_OPTS=(
  -av
  --update
  --progress
  --exclude='conversations/'
  --exclude='.git/'
  --exclude='*.bak'
  --exclude='logs/'
)
[[ $DRY_RUN -eq 1 ]] && RSYNC_OPTS+=(--dry-run)

echo "==> rsync from ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}"
echo "             -> ${LOCAL_PATH}/"
[[ $DRY_RUN -eq 1 ]] && echo "    (DRY RUN — nothing will be written)"
mkdir -p "$LOCAL_PATH"
rsync "${RSYNC_OPTS[@]}" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}" \
  "${LOCAL_PATH}/"

if [[ $DRY_RUN -eq 1 || $DO_UNZIP -eq 0 ]]; then
  echo "==> skipping unzip (dry-run or --no-unzip)"
  exit 0
fi

STAMP="$LOCAL_PATH/.last_sync_h2"
echo "==> unzipping new conversations.zip (newer than $(stat -f '%Sm' "$STAMP" 2>/dev/null || echo 'never'))"

if [[ -f "$STAMP" ]]; then
  FIND_NEWER=(-newer "$STAMP")
else
  FIND_NEWER=()
fi

count=0
while IFS= read -r -d '' zip; do
  exp="$(dirname "$zip")"
  unzip -oq "$zip" -d "$exp"
  count=$((count + 1))
  printf '.'
done < <(find "$LOCAL_PATH/models" -type f -name 'conversations.zip' "${FIND_NEWER[@]}" -print0 2>/dev/null)
echo
echo "==> unzipped $count archive(s)"

touch "$STAMP"
echo "Done."
