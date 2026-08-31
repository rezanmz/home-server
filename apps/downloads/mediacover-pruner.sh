#!/bin/sh
# Prune Lidarr's MediaCover image cache on a rolling age window.
#
# MediaCover is a regenerable artwork cache: Lidarr re-downloads images on
# demand when they are missing. Without pruning it grows unbounded and fills
# the volume (incident 2026-08: 4.4GB cache filled the 5Gi lidarr-config PVC
# and crash-looped lidarr). This pruner deletes cached images older than
# MEDIACOVER_AGE_DAYS so the cache stays bounded around recent activity.

set -eu

readonly mediacover_path="${MEDIACOVER_PATH:-/config/MediaCover}"
readonly prune_interval="${PRUNE_INTERVAL_SECONDS:-86400}"
readonly age_days="${MEDIACOVER_AGE_DAYS:-30}"
readonly state_dir="${STATE_PATH:-/tmp}"

log() {
  printf '%s mediacover-pruner %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

case "$prune_interval:$age_days" in
  *[!0-9:]* | *::* | :* | *:)
    log "received invalid numeric settings"
    exit 2
    ;;
esac

if [ ! -d "$mediacover_path" ]; then
  log "MediaCover path $mediacover_path does not exist yet; waiting for lidarr"
fi

while :; do
  if [ -d "$mediacover_path" ]; then
    before=$(du -sh "$mediacover_path" 2>/dev/null | cut -f1)
    # Delete cached artwork older than the retention window, then remove
    # artist/album directories left empty. Files still referenced by lidarr
    # are re-downloaded automatically when the UI or API needs them.
    find "$mediacover_path" -type f -mtime "+$age_days" -delete 2>/dev/null || true
    find "$mediacover_path" -mindepth 1 -type d -empty -delete 2>/dev/null || true
    after=$(du -sh "$mediacover_path" 2>/dev/null | cut -f1)
    log "pruned MediaCover (age > ${age_days}d): before=${before:-?} after=${after:-?}"
  fi
  touch "$state_dir/pruner-heartbeat"
  sleep "$prune_interval"
done
