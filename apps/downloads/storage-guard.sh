#!/bin/sh
set -eu

readonly downloads_path="${DOWNLOADS_PATH:-/media/downloads}"
readonly qbittorrent_url="${QBITTORRENT_URL:-http://127.0.0.1:8080}"
readonly check_interval="${CHECK_INTERVAL_SECONDS:-60}"
readonly min_free_bytes="${MIN_FREE_BYTES:-107374182400}"
readonly min_free_percent="${MIN_FREE_PERCENT:-10}"
readonly resume_free_bytes="${RESUME_FREE_BYTES:-214748364800}"
readonly resume_free_percent="${RESUME_FREE_PERCENT:-20}"
readonly guard_tag="${GUARD_TAG:-storage-guard-paused}"
readonly cleaner_ready="${IMPORT_CLEANER_READY_PATH:-/import-cleaner-state/import-cleaner-ready}"
readonly verify_delay="${VERIFY_DELAY_SECONDS:-2}"
readonly run_once="${RUN_ONCE:-false}"
readonly state_dir="${STATE_PATH:-/tmp}"
readonly heartbeat="$state_dir/guard-heartbeat"
readonly inventory="$state_dir/qbittorrent-inventory.json"
readonly resume_inventory="$state_dir/qbittorrent-resume-inventory.json"
readonly resume_deferred_marker="$state_dir/resume-deferred"

log() {
  printf '%s storage-guard %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

case "$check_interval:$min_free_bytes:$min_free_percent:$resume_free_bytes:$resume_free_percent:$verify_delay" in
  *[!0-9:]* | *::* | :* | *:)
    log "received invalid numeric settings"
    exit 2
    ;;
esac

case "$run_once" in
  true | false) ;;
  *)
    log "RUN_ONCE must be true or false"
    exit 2
    ;;
esac

if [ "$min_free_bytes" -ge "$resume_free_bytes" ] || \
   [ "$min_free_percent" -ge "$resume_free_percent" ]; then
  log "resume thresholds must be greater than pause thresholds"
  exit 2
fi

case "$guard_tag" in
  "" | *,*)
    log "GUARD_TAG must be one non-empty qBittorrent tag"
    exit 2
    ;;
esac

mkdir -p "$state_dir"

require_download_storage() {
  filesystem_type="$(stat -f -c %T "$downloads_path")"
  if [ "$filesystem_type" != nfs ]; then
    log "refusing $downloads_path: expected nfs, got $filesystem_type"
    return 1
  fi
}

fetch_inventory() {
  destination=$1
  if ! curl -fsS --retry 3 "$qbittorrent_url/api/v2/torrents/info" \
    -o "$destination"; then
    log "qBittorrent inventory fetch failed"
    return 1
  fi
  jq -e 'type=="array"' "$destination" >/dev/null
}

active_incomplete_hashes() {
  jq -r '
    .[] |
    select(
      .progress < 1 and
      .amount_left > 0 and
      (
        .state=="allocating" or
        .state=="checkingDL" or
        .state=="checkingResumeData" or
        .state=="downloading" or
        .state=="forcedDL" or
        .state=="forcedMetaDL" or
        .state=="metaDL" or
        .state=="moving" or
        .state=="queuedDL" or
        .state=="stalledDL"
      )
    ) |
    .hash
  ' "$1" | paste -sd '|' -
}

guard_stopped_hashes() {
  jq -r --arg tag "$guard_tag" '
    def tags:
      (.tags // "" | split(",") | map(gsub("^[[:space:]]+|[[:space:]]+$"; "")));
    .[] |
    select(
      .progress < 1 and
      .amount_left > 0 and
      .state=="stoppedDL" and
      (tags | index($tag)) != null
    ) |
    .hash
  ' "$1" | paste -sd '|' -
}

resumed_guard_hashes() {
  jq -r --arg tag "$guard_tag" '
    def tags:
      (.tags // "" | split(",") | map(gsub("^[[:space:]]+|[[:space:]]+$"; "")));
    .[] |
    select(
      .progress < 1 and
      .amount_left > 0 and
      (tags | index($tag)) != null and
      (
        .state=="allocating" or
        .state=="checkingDL" or
        .state=="checkingResumeData" or
        .state=="downloading" or
        .state=="forcedDL" or
        .state=="forcedMetaDL" or
        .state=="metaDL" or
        .state=="moving" or
        .state=="queuedDL" or
        .state=="stalledDL"
      )
    ) |
    .hash
  ' "$1" | paste -sd '|' -
}

hash_count() {
  if [ -z "$1" ]; then
    printf '0\n'
  else
    printf '%s\n' "$1" | awk -F '|' '{print NF}'
  fi
}

pause_active_downloads() {
  hashes="$(active_incomplete_hashes "$inventory")"
  [ -n "$hashes" ] || return 0

  # Establish ownership before stopping anything. If tagging fails, preserve
  # the current qBittorrent state rather than creating another manual-resume
  # burden that the guard cannot distinguish from a user decision.
  if ! curl -fsS --retry 3 \
    --data-urlencode "hashes=$hashes" \
    --data-urlencode "tags=$guard_tag" \
    "$qbittorrent_url/api/v2/torrents/addTags" >/dev/null; then
    log "could not tag active downloads; no torrents were stopped"
    return 1
  fi
  if ! curl -fsS --retry 3 --data-urlencode "hashes=$hashes" \
    "$qbittorrent_url/api/v2/torrents/stop" >/dev/null; then
    log "could not stop tagged active downloads"
    return 1
  fi

  log "paused guard-owned active downloads count=$(hash_count "$hashes")"
}

cleaner_is_ready() {
  find "$cleaner_ready" -mmin -3 -print -quit 2>/dev/null | grep -q .
}

resume_guard_downloads() {
  hashes="$(guard_stopped_hashes "$inventory")"
  if [ -z "$hashes" ]; then
    rm -f "$resume_deferred_marker"
    return 0
  fi

  if ! cleaner_is_ready; then
    if [ ! -e "$resume_deferred_marker" ]; then
      log "automatic resume deferred: import cleaner has no fresh successful storage check"
      : > "$resume_deferred_marker"
    fi
    return 0
  fi
  rm -f "$resume_deferred_marker"

  if ! curl -fsS --retry 3 --data-urlencode "hashes=$hashes" \
    "$qbittorrent_url/api/v2/torrents/start" >/dev/null; then
    log "could not resume guard-owned downloads"
    return 1
  fi

  [ "$verify_delay" -eq 0 ] || sleep "$verify_delay"
  fetch_inventory "$resume_inventory" || return 1
  resumed="$(resumed_guard_hashes "$resume_inventory")"
  if [ -z "$resumed" ]; then
    log "qBittorrent accepted resume request but no guarded torrent became active; ownership tags retained"
    return 0
  fi
  if ! curl -fsS --retry 3 \
    --data-urlencode "hashes=$resumed" \
    --data-urlencode "tags=$guard_tag" \
    "$qbittorrent_url/api/v2/torrents/removeTags" >/dev/null; then
    log "resumed torrents but could not remove guard ownership tags"
    return 1
  fi

  log "resumed guard-owned downloads count=$(hash_count "$resumed")"
}

run_cycle() {
  require_download_storage || return 1
  fetch_inventory "$inventory" || return 1

  space="$(stat -f -c '%b %a %S' "$downloads_path")" || {
    log "download storage capacity check failed"
    return 1
  }
  # Intentional field splitting of stat's three numeric values.
  # shellcheck disable=SC2086
  set -- $space
  if [ "$#" -ne 3 ]; then
    log "download storage returned an invalid capacity result"
    return 1
  fi
  total_bytes=$(($1 * $3))
  free_bytes=$(($2 * $3))
  [ "$total_bytes" -gt 0 ] || {
    log "download storage reported zero total bytes"
    return 1
  }
  free_percent=$((free_bytes * 100 / total_bytes))

  if [ "$free_bytes" -lt "$min_free_bytes" ] || \
     [ "$free_percent" -lt "$min_free_percent" ]; then
    pause_active_downloads
  elif [ "$free_bytes" -ge "$resume_free_bytes" ] && \
       [ "$free_percent" -ge "$resume_free_percent" ]; then
    resume_guard_downloads
  fi
}

until curl -fsS "$qbittorrent_url/api/v2/app/version" >/dev/null; do
  sleep 2
done

while true; do
  if ! run_cycle; then
    log "cycle failed; qBittorrent state left unchanged where possible"
  fi
  touch "$heartbeat"
  [ "$run_once" = true ] && break
  sleep "$check_interval"
done
