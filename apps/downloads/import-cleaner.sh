#!/bin/sh
set -eu

readonly qbittorrent_url="${QBITTORRENT_URL:-http://127.0.0.1:8080}"
readonly sonarr_url="${SONARR_URL:-http://127.0.0.1:8989}"
readonly radarr_url="${RADARR_URL:-http://127.0.0.1:7878}"
readonly lidarr_url="${LIDARR_URL:-http://127.0.0.1:8686}"
readonly check_interval="${CHECK_INTERVAL_SECONDS:-60}"
readonly confirmations_required="${CONFIRMATIONS_REQUIRED:-2}"
readonly deletion_enabled="${DELETE_ENABLED:-false}"
readonly run_once="${RUN_ONCE:-false}"
readonly downloads_path="${DOWNLOADS_PATH:-/media/downloads}"
readonly tv_path="${TV_PATH:-/media/tv}"
readonly movies_path="${MOVIES_PATH:-/media/movies}"
readonly music_path="${MUSIC_PATH:-/media/music}"
readonly sonarr_config_path="${SONARR_CONFIG_PATH:-/arr-config/sonarr}"
readonly radarr_config_path="${RADARR_CONFIG_PATH:-/arr-config/radarr}"
readonly lidarr_config_path="${LIDARR_CONFIG_PATH:-/arr-config/lidarr}"
readonly state_dir="${STATE_PATH:-/state}"
readonly heartbeat="$state_dir/import-cleaner-heartbeat"

log() {
  printf '%s import-cleaner %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

case "$check_interval:$confirmations_required" in
  *[!0-9:]* | *::* | :* | *:)
    log "invalid numeric settings"
    exit 2
    ;;
esac

case "$deletion_enabled:$run_once" in
  true:true | true:false | false:true | false:false) ;;
  *)
    log "DELETE_ENABLED and RUN_ONCE must be true or false"
    exit 2
    ;;
esac

if [ "$confirmations_required" -lt 2 ]; then
  log "CONFIRMATIONS_REQUIRED must be at least two"
  exit 2
fi

require_storage_contract() {
  [ "$(stat -f -c %T "$downloads_path")" = nfs ] &&
    [ "$(stat -f -c %T "$tv_path")" = fuse ] &&
    [ "$(stat -f -c %T "$movies_path")" = fuse ] &&
    [ "$(stat -f -c %T "$music_path")" = fuse ]
}

read_api_key() {
  sed -n 's:.*<ApiKey>\(.*\)</ApiKey>.*:\1:p' "$1/config.xml"
}

sonarr_key="$(read_api_key "$sonarr_config_path")"
radarr_key="$(read_api_key "$radarr_config_path")"
lidarr_key="$(read_api_key "$lidarr_config_path")"

if [ -z "$sonarr_key" ] || [ -z "$radarr_key" ] || [ -z "$lidarr_key" ]; then
  log "one or more Arr API keys are unavailable"
  exit 1
fi

arr_removal_is_disabled() {
  url=$1
  api_version=$2
  api_key=$3

  curl -fsS -H "X-Api-Key: $api_key" \
    "$url/api/$api_version/downloadclient" |
    jq -e '
      any(.[];
        .name=="qBittorrent" and
        .enable==true and
        .removeCompletedDownloads==false)
    ' >/dev/null
}

safe_ownership_policy() {
  preferences="$state_dir/qbittorrent-preferences.json"
  curl -fsS "$qbittorrent_url/api/v2/app/preferences" -o "$preferences" ||
    return 1

  jq -e '
    .max_ratio_act==0 and
    .max_seeding_time_enabled==true and
    .max_seeding_time==1
  ' "$preferences" >/dev/null || return 1

  arr_removal_is_disabled "$sonarr_url" v3 "$sonarr_key" &&
    arr_removal_is_disabled "$radarr_url" v3 "$radarr_key" &&
    arr_removal_is_disabled "$lidarr_url" v1 "$lidarr_key"
}

fetch_history() {
  url=$1
  api_version=$2
  api_key=$3
  destination=$4

  curl -fsS -H "X-Api-Key: $api_key" \
    "$url/api/$api_version/history?page=1&pageSize=10000&sortKey=date&sortDirection=descending" \
    -o "$destination"
}

current_sonarr_files_exist() {
  hash=$1
  episode_ids="$(
    jq -r --arg hash "$hash" '
      .records[] |
      select(
        (.downloadId // "" | ascii_downcase)==($hash | ascii_downcase) and
        .eventType=="downloadFolderImported"
      ) |
      .episodeId
    ' "$state_dir/sonarr-history.json" | sort -nu
  )"
  [ -n "$episode_ids" ] || return 1

  for episode_id in $episode_ids; do
    episode="$(
      curl -fsS -H "X-Api-Key: $sonarr_key" \
        "$sonarr_url/api/v3/episode/$episode_id"
    )" || return 1
    [ "$(printf '%s' "$episode" | jq -r '.hasFile')" = true ] || return 1
    file_id="$(printf '%s' "$episode" | jq -r '.episodeFileId // 0')"
    [ "$file_id" -gt 0 ] || return 1
    episode_file="$(
      curl -fsS -H "X-Api-Key: $sonarr_key" \
        "$sonarr_url/api/v3/episodefile/$file_id"
    )" || return 1
    path="$(printf '%s' "$episode_file" | jq -r '.path // empty')"
    case "$path" in "$tv_path"/*) ;; *) return 1 ;; esac
    [ -f "$path" ] && [ -s "$path" ] || return 1
  done
}

current_radarr_files_exist() {
  hash=$1
  movie_ids="$(
    jq -r --arg hash "$hash" '
      .records[] |
      select(
        (.downloadId // "" | ascii_downcase)==($hash | ascii_downcase) and
        .eventType=="downloadFolderImported"
      ) |
      .movieId
    ' "$state_dir/radarr-history.json" | sort -nu
  )"
  [ -n "$movie_ids" ] || return 1

  for movie_id in $movie_ids; do
    movie="$(
      curl -fsS -H "X-Api-Key: $radarr_key" \
        "$radarr_url/api/v3/movie/$movie_id"
    )" || return 1
    [ "$(printf '%s' "$movie" | jq -r '.hasFile')" = true ] || return 1
    path="$(
      printf '%s' "$movie" |
        jq -r 'if .hasFile then (.path + "/" + .movieFile.relativePath) else "" end'
    )"
    case "$path" in "$movies_path"/*) ;; *) return 1 ;; esac
    [ -f "$path" ] && [ -s "$path" ] || return 1
  done
}

all_lidarr_audio_was_imported() {
  hash=$1
  files="$state_dir/qbittorrent-files-$hash.json"
  curl -fsS --get --data-urlencode "hash=$hash" \
    "$qbittorrent_url/api/v2/torrents/files" -o "$files" || return 1

  jq -e --arg hash "$hash" --slurpfile files "$files" '
    [
      .records[] |
      select(
        (.downloadId // "" | ascii_downcase)==($hash | ascii_downcase) and
        .eventType=="trackFileImported"
      ) |
      .data.droppedPath
    ] as $imported |
    [
      $files[0][] |
      select(.name | test("\\.(mp3|flac|m4a|aac|ogg|opus|wav|ape|alac|wma|mka|dsf|dff|aiff|aif)$"; "i"))
    ] as $audio |
    ($audio | length)>0 and
    all(
      $audio[];
      .progress==1 and
      (.name as $name | any($imported[]; endswith($name)))
    )
  ' "$state_dir/lidarr-history.json" >/dev/null
}

current_lidarr_files_exist() {
  hash=$1
  all_lidarr_audio_was_imported "$hash" || return 1

  track_ids="$(
    jq -r --arg hash "$hash" '
      .records[] |
      select(
        (.downloadId // "" | ascii_downcase)==($hash | ascii_downcase) and
        .eventType=="trackFileImported"
      ) |
      .trackId
    ' "$state_dir/lidarr-history.json" | sort -nu
  )"
  [ -n "$track_ids" ] || return 1

  for track_id in $track_ids; do
    track="$(
      curl -fsS -H "X-Api-Key: $lidarr_key" \
        "$lidarr_url/api/v1/track/$track_id"
    )" || return 1
    [ "$(printf '%s' "$track" | jq -r '.hasFile')" = true ] || return 1
    file_id="$(printf '%s' "$track" | jq -r '.trackFileId // 0')"
    [ "$file_id" -gt 0 ] || return 1
    track_file="$(
      curl -fsS -H "X-Api-Key: $lidarr_key" \
        "$lidarr_url/api/v1/trackfile/$file_id"
    )" || return 1
    path="$(printf '%s' "$track_file" | jq -r '.path // empty')"
    case "$path" in "$music_path"/*) ;; *) return 1 ;; esac
    [ -f "$path" ] && [ -s "$path" ] || return 1
  done
}

unique_download_payload_exists() {
  hash=$1
  row="$(
    jq -r --arg hash "$hash" '
      .[] | select(.hash==$hash) |
      [.content_path, .name, .size] | @tsv
    ' "$state_dir/qbittorrent.json"
  )"
  [ -n "$row" ] || return 1
  content_path="$(printf '%s\n' "$row" | cut -f1)"
  case "$content_path" in "$downloads_path"/*) ;; *) return 1 ;; esac
  references="$(
    jq -r --arg path "$content_path" \
      '[.[] | select(.content_path==$path)] | length' \
      "$state_dir/qbittorrent.json"
  )"
  [ "$references" -eq 1 ] || return 1
  [ -e "$content_path" ] || return 1
}

candidate_is_safe() {
  hash=$1
  category=$2

  unique_download_payload_exists "$hash" || return 1
  case "$category" in
    tv-sonarr) current_sonarr_files_exist "$hash" ;;
    radarr) current_radarr_files_exist "$hash" ;;
    music) current_lidarr_files_exist "$hash" ;;
    *) return 1 ;;
  esac
}

still_stopped_and_complete() {
  hash=$1
  curl -fsS --get --data-urlencode "hashes=$hash" \
    "$qbittorrent_url/api/v2/torrents/info" \
    -o "$state_dir/recheck-$hash.json" || return 1
  jq -e --arg hash "$hash" '
    length==1 and
    .[0].hash==$hash and
    .[0].state=="stoppedUP" and
    .[0].progress==1 and
    .[0].amount_left==0 and
    (.[0].category=="tv-sonarr" or
     .[0].category=="radarr" or
     .[0].category=="music")
  ' "$state_dir/recheck-$hash.json" >/dev/null
}

confirm_or_delete() {
  hash=$1
  category=$2
  name=$3
  size=$4
  marker="$state_dir/confirm-$hash"

  if ! candidate_is_safe "$hash" "$category"; then
    rm -f "$marker"
    return
  fi

  confirmations=0
  if [ -f "$marker" ]; then
    confirmations="$(cat "$marker")"
  fi
  confirmations=$((confirmations + 1))
  printf '%s\n' "$confirmations" > "$marker"

  if [ "$confirmations" -lt "$confirmations_required" ]; then
    log "confirmed pass=$confirmations/$confirmations_required category=$category hash=$hash name=$name"
    return
  fi

  if [ "$deletion_enabled" != true ]; then
    log "dry-run safe category=$category hash=$hash bytes=$size name=$name"
    return
  fi

  still_stopped_and_complete "$hash" || {
    log "recheck rejected category=$category hash=$hash name=$name"
    rm -f "$marker"
    return
  }
  candidate_is_safe "$hash" "$category" || {
    log "second library check rejected category=$category hash=$hash name=$name"
    rm -f "$marker"
    return
  }

  if ! curl -fsS --retry 3 \
    --data-urlencode "hashes=$hash" \
    --data-urlencode 'deleteFiles=true' \
    "$qbittorrent_url/api/v2/torrents/delete" >/dev/null; then
    log "qBittorrent deletion failed category=$category hash=$hash name=$name"
    rm -f "$marker"
    return
  fi
  rm -f "$marker"
  log "deleted verified import category=$category hash=$hash bytes=$size name=$name"
}

run_cycle() {
  # History snapshots are overwritten, while per-torrent API responses use
  # hash-specific names. Remove the latter before every pass so long-running
  # pods cannot accumulate state for torrents that no longer exist.
  rm -f "$state_dir"/qbittorrent-files-*.json "$state_dir"/recheck-*.json

  require_storage_contract || {
    log "storage contract failed; deletion skipped"
    return
  }
  safe_ownership_policy || {
    log "ownership policy failed; Arr removal must be disabled and qBittorrent must use the one-minute stop-only limit"
    return
  }

  curl -fsS "$qbittorrent_url/api/v2/torrents/info" \
    -o "$state_dir/qbittorrent.json" || return
  fetch_history "$sonarr_url" v3 "$sonarr_key" \
    "$state_dir/sonarr-history.json" || return
  fetch_history "$radarr_url" v3 "$radarr_key" \
    "$state_dir/radarr-history.json" || return
  fetch_history "$lidarr_url" v1 "$lidarr_key" \
    "$state_dir/lidarr-history.json" || return

  jq -r '
    .[] |
    select(
      .state=="stoppedUP" and
      .progress==1 and
      .amount_left==0 and
      (.category=="tv-sonarr" or .category=="radarr" or .category=="music")
    ) |
    [.hash, .category, .name, .size] | @tsv
  ' "$state_dir/qbittorrent.json" |
    while IFS="$(printf '\t')" read -r hash category name size; do
      confirm_or_delete "$hash" "$category" "$name" "$size"
    done
}

mkdir -p "$state_dir"
until curl -fsS "$qbittorrent_url/api/v2/app/version" >/dev/null &&
  curl -fsS -H "X-Api-Key: $sonarr_key" "$sonarr_url/ping" >/dev/null &&
  curl -fsS -H "X-Api-Key: $radarr_key" "$radarr_url/ping" >/dev/null &&
  curl -fsS -H "X-Api-Key: $lidarr_key" "$lidarr_url/ping" >/dev/null; do
  sleep 2
done

while true; do
  if ! run_cycle; then
    log "cycle failed; deletion skipped"
  fi
  touch "$heartbeat"
  [ "$run_once" = true ] && break
  sleep "$check_interval"
done
