#!/bin/sh
set -eu

readonly downloads_path=/media/downloads
readonly qbittorrent_url=http://127.0.0.1:8080
readonly check_interval="${CHECK_INTERVAL_SECONDS:-60}"
readonly min_free_bytes="${MIN_FREE_BYTES:-214748364800}"
readonly min_free_percent="${MIN_FREE_PERCENT:-20}"
readonly pause_marker=/tmp/downloads-paused-by-storage-guard
readonly heartbeat=/tmp/guard-heartbeat

case "$check_interval:$min_free_bytes:$min_free_percent" in
  *[!0-9:]* | *::* | :* | *:)
    echo "storage guard received invalid numeric settings" >&2
    exit 2
    ;;
esac

filesystem_type="$(stat -f -c %T "$downloads_path")"
if [ "$filesystem_type" != nfs ]; then
  echo "storage guard refuses $downloads_path: expected nfs, got $filesystem_type" >&2
  exit 1
fi

until curl -fsS "$qbittorrent_url/api/v2/app/version" >/dev/null; do
  sleep 2
done

while true; do
  set -- $(stat -f -c '%b %a %S' "$downloads_path")
  total_bytes=$(($1 * $3))
  free_bytes=$(($2 * $3))
  free_percent=$((free_bytes * 100 / total_bytes))

  if [ "$free_bytes" -lt "$min_free_bytes" ] || \
     [ "$free_percent" -lt "$min_free_percent" ]; then
    curl -fsS --retry 3 --data-urlencode 'hashes=all' \
      "$qbittorrent_url/api/v2/torrents/stop" >/dev/null
    if [ ! -e "$pause_marker" ]; then
      printf '%s storage guard stopped every torrent: free_bytes=%s free_percent=%s threshold_bytes=%s threshold_percent=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$free_bytes" "$free_percent" \
        "$min_free_bytes" "$min_free_percent"
      : > "$pause_marker"
    fi
  elif [ -e "$pause_marker" ]; then
    printf '%s download storage recovered: free_bytes=%s free_percent=%s; torrents remain stopped for manual review\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$free_bytes" "$free_percent"
    rm -f "$pause_marker"
  fi

  touch "$heartbeat"
  sleep "$check_interval"
done
