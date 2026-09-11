#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 1 ] && [ "$1" = "--check" ]; then
  MODE=check
elif [ "$#" -eq 0 ]; then
  MODE=apply
else
  echo "Usage: $0 [--check]" >&2
  exit 2
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
SETUP_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
OVERLAY_ROOT="$SETUP_DIR/image_build/overlays/stage2/99-klipperpi/files/installed_overlay/rootfs"
REMOTE_HOST=${MENDERPI_HOST-}
[ -n "$REMOTE_HOST" ] || REMOTE_HOST=pi@menderpi.local

[ -d "$OVERLAY_ROOT" ] || {
  echo "Missing installed-file overlay: $OVERLAY_ROOT" >&2
  exit 1
}
command -v rsync >/dev/null 2>&1 || {
  echo "rsync is required" >&2
  exit 1
}

RSYNC_COMMON=(
  --recursive
  --checksum
  --no-owner
  --no-group
  --omit-dir-times
  --exclude .DS_Store
)
RSYNC_REMOTE=(--rsync-path="sudo -n rsync")

changes=$(rsync "${RSYNC_COMMON[@]}" --dry-run --itemize-changes \
  "${RSYNC_REMOTE[@]}" "$OVERLAY_ROOT/" "$REMOTE_HOST:/")

if [ -z "$changes" ]; then
  echo "Installed-file overlay is already current."
  exit 0
fi

if [ "$MODE" = check ]; then
  echo "Installed-file overlay differs from $REMOTE_HOST:" >&2
  printf '%s\n' "$changes" >&2
  exit 1
fi

BACKUP_ROOT="/home/pi/printer_data/backup/installed-overlay-$(date +%Y%m%d-%H%M%S)"
ssh "$REMOTE_HOST" "sudo -n install -d -m 0755 '$BACKUP_ROOT'"
rsync "${RSYNC_COMMON[@]}" --backup --backup-dir="$BACKUP_ROOT" \
  "${RSYNC_REMOTE[@]}" "$OVERLAY_ROOT/" "$REMOTE_HOST:/"

if ! ssh "$REMOTE_HOST" "sudo -n nginx -t"; then
  echo "nginx validation failed; nginx was not reloaded." >&2
  echo "Overlay backup: $REMOTE_HOST:$BACKUP_ROOT" >&2
  exit 1
fi

ssh "$REMOTE_HOST" "sudo -n systemctl reload nginx"
echo "Installed-file overlay deployed and nginx reloaded."
echo "Overlay backup: $REMOTE_HOST:$BACKUP_ROOT"
