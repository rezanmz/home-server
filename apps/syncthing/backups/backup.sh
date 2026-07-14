#!/bin/sh

set -eu
set -f

SOURCE_ROOT="${SOURCE_ROOT:-/source}"
SYNCTHING_CONFIG_FILE="${SYNCTHING_CONFIG_FILE:-/syncthing-config.xml}"
POLICY_FILE="${POLICY_FILE:-/policy/excluded-folder-ids.txt}"
WORK_DIR="${WORK_DIR:-/work}"
CREDENTIALS_DIR="${CREDENTIALS_DIR:-/credentials}"
RESTIC_HOST="${RESTIC_HOST:-home-server-syncthing-nfs}"
TRUSTED_TAG="${TRUSTED_TAG:-syncthing-nfs}"
CANDIDATE_TAG="${CANDIDATE_TAG:-syncthing-nfs-candidate}"
EXPECTED_REPOSITORY_ID="${EXPECTED_REPOSITORY_ID:-PENDING}"
SOURCE_CANARY_SHA256="${SOURCE_CANARY_SHA256:-}"
ALLOW_REPOSITORY_INIT="${ALLOW_REPOSITORY_INIT:-false}"
MAX_TRUSTED_SNAPSHOT_AGE_SECONDS="${MAX_TRUSTED_SNAPSHOT_AGE_SECONDS:-129600}"
APPROVED_REPOSITORY='s3:https://s3.ca-east-006.backblazeb2.com/rezanmz-home-server-syncthing-backups/syncthing'
EXCLUDE_FILE="${WORK_DIR}/restic-excludes.txt"
FOLDER_MAP="${WORK_DIR}/syncthing-folders.tsv"
BACKUP_OUTPUT="${WORK_DIR}/restic-backup.jsonl"
TAG_OUTPUT="${WORK_DIR}/restic-tag.jsonl"
RESTORE_MOUNT='/restore'
RESTORE_TARGET='/restore/restic-proof'

fail() {
  printf 'syncthing backup: %s\n' "$*" >&2
  exit 1
}

validate_snapshot_id() {
  snapshot_id="$1"
  description="$2"
  case "$snapshot_id" in
    *[!0-9a-f]*|'') fail "${description} is not a valid 64-character hexadecimal ID" ;;
  esac
  [ "${#snapshot_id}" -eq 64 ] || \
    fail "${description} is not a valid 64-character hexadecimal ID"
}

load_credentials() {
  for file in aws-access-key-id aws-secret-access-key repository-password; do
    [ -s "${CREDENTIALS_DIR}/${file}" ] || fail "missing credential file: ${file}"
  done

  AWS_ACCESS_KEY_ID="$(cat "${CREDENTIALS_DIR}/aws-access-key-id")"
  AWS_SECRET_ACCESS_KEY="$(cat "${CREDENTIALS_DIR}/aws-secret-access-key")"
  export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
  RESTIC_PASSWORD_FILE="${CREDENTIALS_DIR}/repository-password"
  export RESTIC_PASSWORD_FILE
}

validate_repository_url() {
  [ "${RESTIC_REPOSITORY:-}" = "$APPROVED_REPOSITORY" ] || \
    fail "repository URL differs from the reviewed bucket and prefix"
}

read_repository_id() {
  repository_id="$(
    restic --retry-lock 2h cat config |
      jq -er '.id | select(type == "string")'
  )" || fail "could not read repository ID"
  validate_snapshot_id "$repository_id" "repository ID"
  printf '%s\n' "$repository_id"
}

verify_repository() {
  validate_repository_url
  case "$EXPECTED_REPOSITORY_ID" in
    *[!0-9a-f]*|'') fail "repository ID is not pinned in the CronJob" ;;
  esac
  [ "${#EXPECTED_REPOSITORY_ID}" -eq 64 ] || \
    fail "repository ID is not pinned in the CronJob"

  actual_repository_id="$(read_repository_id)"
  [ "$actual_repository_id" = "$EXPECTED_REPOSITORY_ID" ] || \
    fail "repository ID does not match the reviewed repository"
}

validate_source_root() {
  [ -d "$SOURCE_ROOT" ] || fail "source root is not mounted: ${SOURCE_ROOT}"
  [ ! -L "$SOURCE_ROOT" ] || fail "source root cannot be a symbolic link"
  [ -r "$SOURCE_ROOT" ] || fail "source root is not readable: ${SOURCE_ROOT}"
  [ -n "$SOURCE_CANARY_SHA256" ] || fail "source canary hash is not configured"

  canary="${SOURCE_ROOT}/.restic-source-canary"
  [ -f "$canary" ] || fail "durable source canary is missing"
  [ ! -L "$canary" ] || fail "durable source canary cannot be a symbolic link"
  actual_canary_sha256="$(sha256sum "$canary" | awk '{print $1}')"
  [ "$actual_canary_sha256" = "$SOURCE_CANARY_SHA256" ] || \
    fail "durable source canary checksum does not match"
}

validate_relative_folder_path() {
  relative="$1"
  folder_id="$2"
  folder_root="${3:-$SOURCE_ROOT}"

  case "$relative" in
    ''|/*|.|..|./*|*/./*|*/.|../*|*/../*|*/..|*//*|*/ )
      fail "Syncthing folder ${folder_id} has an unsafe path"
      ;;
    *'*'*|*'?'*|*'['*|*']'*|*'$'*|*'&'*|*'\'*)
      fail "Syncthing folder ${folder_id} uses unsupported path characters"
      ;;
    ' '*|*' ')
      fail "Syncthing folder ${folder_id} has leading or trailing whitespace"
      ;;
  esac

  current="$folder_root"
  old_ifs="$IFS"
  IFS='/'; set -- $relative; IFS="$old_ifs"
  for component in "$@"; do
    [ -n "$component" ] || fail "Syncthing folder ${folder_id} has an empty path component"
    current="${current}/${component}"
    [ ! -L "$current" ] || fail "Syncthing folder ${folder_id} traverses a symbolic link"
  done

  [ -d "$current" ] || fail "Syncthing folder ${folder_id} is missing from the data mount"
  [ -d "${current}/.stfolder" ] || fail "Syncthing folder ${folder_id} has no real .stfolder directory"
  [ ! -L "${current}/.stfolder" ] || fail "Syncthing folder ${folder_id} has a symlinked marker"
}

build_folder_map() {
  [ -r "$SYNCTHING_CONFIG_FILE" ] || \
    fail "Syncthing configuration is not readable: ${SYNCTHING_CONFIG_FILE}"
  : > "$FOLDER_MAP"
  folder_count=0

  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      *'<folder '*) ;;
      *) continue ;;
    esac

    folder_id="$(printf '%s\n' "$line" | sed -n 's/.*[[:space:]]id="\([^"]*\)".*/\1/p')"
    container_path="$(printf '%s\n' "$line" | sed -n 's/.*[[:space:]]path="\([^"]*\)".*/\1/p')"
    # Syncthing stores an empty folder template under <defaults>. It is not a
    # configured folder and must not enter the backup inventory.
    if [ -z "$folder_id" ] && [ -z "$container_path" ]; then
      continue
    fi
    [ -n "$folder_id" ] || fail "could not parse a Syncthing folder ID"
    [ -n "$container_path" ] || fail "could not parse path for Syncthing folder ${folder_id}"

    case "$folder_id" in
      *[!A-Za-z0-9._-]*) fail "Syncthing folder ID uses unsupported characters" ;;
    esac
    case "$container_path" in
      /data/*) relative="${container_path#/data/}" ;;
      *) fail "Syncthing folder ${folder_id} is outside the protected /data mount" ;;
    esac

    validate_relative_folder_path "$relative" "$folder_id"
    tab="$(printf '\t')"
    if awk -F "$tab" -v id="$folder_id" '$1 == id {found = 1} END {exit !found}' "$FOLDER_MAP"; then
      fail "duplicate Syncthing folder ID: ${folder_id}"
    fi
    if awk -F "$tab" -v path="$relative" '$2 == path {found = 1} END {exit !found}' "$FOLDER_MAP"; then
      fail "multiple Syncthing folder IDs use the same path"
    fi

    printf '%s\t%s\n' "$folder_id" "$relative" >> "$FOLDER_MAP"
    folder_count=$((folder_count + 1))
  done < "$SYNCTHING_CONFIG_FILE"

  [ "$folder_count" -gt 0 ] || fail "Syncthing has no configured folders"

  tab="$(printf '\t')"
  while IFS="$tab" read -r folder_id relative; do
    while IFS="$tab" read -r other_id other_relative; do
      [ "$folder_id" = "$other_id" ] && continue
      case "${other_relative}/" in
        "${relative}/"*) fail "Syncthing folder paths overlap; folder-ID opt-outs are ambiguous" ;;
      esac
    done < "$FOLDER_MAP"
  done < "$FOLDER_MAP"

  printf 'syncthing backup: validated configured folders=%s\n' "$folder_count"
}

build_exclude_file() {
  [ -r "$POLICY_FILE" ] || fail "backup policy is not readable: ${POLICY_FILE}"
  : > "$EXCLUDE_FILE"
  seen_ids="${WORK_DIR}/excluded-folder-ids.seen"
  : > "$seen_ids"
  excluded=0
  tab="$(printf '\t')"

  while IFS= read -r folder_id || [ -n "$folder_id" ]; do
    case "$folder_id" in
      ''|'#'*) continue ;;
      *[!A-Za-z0-9._-]*) fail "excluded Syncthing folder ID is invalid" ;;
    esac

    if grep -Fqx -- "$folder_id" "$seen_ids"; then
      fail "duplicate excluded Syncthing folder ID: ${folder_id}"
    fi
    printf '%s\n' "$folder_id" >> "$seen_ids"

    relative="$(
      awk -F "$tab" -v id="$folder_id" '$1 == id {print $2}' "$FOLDER_MAP"
    )"
    [ -n "$relative" ] || fail "excluded Syncthing folder ID is not configured: ${folder_id}"

    printf '%s/%s\n' "$SOURCE_ROOT" "$relative" >> "$EXCLUDE_FILE"
    excluded=$((excluded + 1))
    printf 'syncthing backup: excluding folder id=%s\n' "$folder_id"
  done < "$POLICY_FILE"

  printf 'syncthing backup: validated policy; excluded folders=%s\n' "$excluded"
}

validate_source_and_policy() {
  validate_source_root
  build_folder_map
  build_exclude_file
}

run_backup() {
  load_credentials
  verify_repository
  validate_source_and_policy

  set +e
  restic --retry-lock 2h backup "$SOURCE_ROOT" \
    --one-file-system \
    --exclude-file "$EXCLUDE_FILE" \
    --host "$RESTIC_HOST" \
    --tag "$CANDIDATE_TAG" \
    --json \
    --quiet > "$BACKUP_OUTPUT"
  backup_status=$?
  set -e
  cat "$BACKUP_OUTPUT"
  if [ "$backup_status" -ne 0 ]; then
    # Exit 3 can leave an incomplete candidate snapshot. Bound those even when
    # every subsequent scan fails, but preserve the original backup failure and
    # never prune data from this best-effort cleanup path.
    if [ "$backup_status" -eq 3 ]; then
      set +e
      restic --retry-lock 10m forget \
        --host "$RESTIC_HOST" \
        --path "$SOURCE_ROOT" \
        --tag "$CANDIDATE_TAG" \
        --group-by host,paths,tags \
        --keep-last 3
      candidate_cleanup_status=$?
      set -e
      if [ "$candidate_cleanup_status" -ne 0 ]; then
        printf 'syncthing backup: warning: failed candidate retention returned status %s\n' \
          "$candidate_cleanup_status" >&2
      fi
    fi
    fail "restic backup failed with exit status ${backup_status}; candidate snapshot was not promoted"
  fi

  candidate_snapshot_id="$(
    jq -r 'select(.message_type == "summary") | .snapshot_id // empty' "$BACKUP_OUTPUT" |
      tail -n 1
  )"
  validate_snapshot_id "$candidate_snapshot_id" "successful backup snapshot ID"

  restic --retry-lock 2h tag \
    --add "$TRUSTED_TAG" \
    --remove "$CANDIDATE_TAG" \
    "$candidate_snapshot_id" \
    --json > "$TAG_OUTPUT"
  cat "$TAG_OUTPUT"

  changed_count="$(
    jq -s '[.[] | select(.message_type == "changed")] | length' "$TAG_OUTPUT"
  )"
  [ "$changed_count" -eq 1 ] || fail "snapshot promotion returned an unexpected result"
  old_snapshot_id="$(
    jq -er 'select(.message_type == "changed") | .old_snapshot_id' "$TAG_OUTPUT"
  )" || fail "snapshot promotion did not report the candidate ID"
  promoted_snapshot_id="$(
    jq -er 'select(.message_type == "changed") | .new_snapshot_id' "$TAG_OUTPUT"
  )" || fail "snapshot promotion did not report the trusted ID"
  validate_snapshot_id "$old_snapshot_id" "promotion candidate snapshot ID"
  validate_snapshot_id "$promoted_snapshot_id" "promoted snapshot ID"
  [ "$old_snapshot_id" = "$candidate_snapshot_id" ] || \
    fail "snapshot promotion changed a different candidate"

  printf 'syncthing backup: trusted snapshot id=%s\n' "$promoted_snapshot_id"

  restic --retry-lock 2h forget \
    --host "$RESTIC_HOST" \
    --path "$SOURCE_ROOT" \
    --tag "$CANDIDATE_TAG" \
    --group-by host,paths,tags \
    --keep-last 3

  restic --retry-lock 2h forget \
    --host "$RESTIC_HOST" \
    --path "$SOURCE_ROOT" \
    --tag "$TRUSTED_TAG" \
    --group-by host,paths,tags \
    --keep-daily 14 \
    --keep-weekly 8 \
    --keep-monthly 12 \
    --keep-yearly 3

  # Prune and structural verification share this CronJob with backup so they
  # cannot overlap it. Never unlock automatically; a stale lock is a condition
  # for an operator to inspect rather than discard blindly.
  if [ "$(date -u +%u)" = 7 ]; then
    restic --retry-lock 2h prune --max-unused 10%
    restic --retry-lock 2h check
  fi

  # Cycle through deterministic quarters without a single large monthly
  # download. A quarterly isolated restore remains the stronger end-to-end
  # recovery proof because the repository changes between these checks.
  if [ "$(date -u +%d)" = 01 ]; then
    month="$(date -u +%m)"
    month="${month#0}"
    subset=$(( (month - 1) % 4 + 1 ))
    restic --retry-lock 2h check --read-data-subset "${subset}/4"
  fi
}

initialize_repository() {
  load_credentials
  validate_repository_url

  probe_output="${WORK_DIR}/repository-probe.json"
  set +e
  restic --retry-lock 2h cat config > "$probe_output"
  status=$?
  set -e

  case "$status" in
    0)
      repository_id="$(jq -er '.id' "$probe_output")" || \
        fail "existing repository returned no ID"
      validate_snapshot_id "$repository_id" "existing repository ID"
      if [ "$EXPECTED_REPOSITORY_ID" != PENDING ]; then
        [ "$repository_id" = "$EXPECTED_REPOSITORY_ID" ] || \
          fail "existing repository ID differs from the pinned ID"
      fi
      printf 'syncthing backup: repository already initialized; repository-id=%s\n' "$repository_id"
      ;;
    10)
      [ "$ALLOW_REPOSITORY_INIT" = true ] || \
        fail "repository is absent and explicit initialization approval is false"
      restic init --repository-version 2
      repository_id="$(read_repository_id)"
      restic check
      printf 'syncthing backup: repository initialized; pin repository-id=%s before enabling schedule\n' "$repository_id"
      ;;
    *)
      fail "repository probe failed with exit status ${status}; refusing to initialize"
      ;;
  esac
}

check_repository_data() {
  load_credentials
  verify_repository
  restic --retry-lock 2h check --read-data
}

check_backup_freshness() {
  load_credentials
  verify_repository

  case "$MAX_TRUSTED_SNAPSHOT_AGE_SECONDS" in
    *[!0-9]*|'') fail "maximum trusted snapshot age is invalid" ;;
  esac
  [ "$MAX_TRUSTED_SNAPSHOT_AGE_SECONDS" -gt 0 ] || \
    fail "maximum trusted snapshot age must be positive"

  snapshot_metadata="$(
    restic --retry-lock 2h snapshots \
      --host "$RESTIC_HOST" \
      --path "$SOURCE_ROOT" \
      --tag "$TRUSTED_TAG" \
      --latest 1 \
      --json
  )" || fail "could not read the latest trusted snapshot"
  latest_snapshot_id="$(
    printf '%s\n' "$snapshot_metadata" | jq -er '.[0].id'
  )" || fail "no trusted Syncthing snapshot exists"
  validate_snapshot_id "$latest_snapshot_id" "latest trusted snapshot ID"
  printf '%s\n' "$snapshot_metadata" |
    jq -e \
      --arg id "$latest_snapshot_id" \
      --arg host "$RESTIC_HOST" \
      --arg path "$SOURCE_ROOT" \
      --arg trusted "$TRUSTED_TAG" \
      --arg candidate "$CANDIDATE_TAG" \
      'length == 1
       and .[0].id == $id
       and .[0].hostname == $host
       and .[0].paths == [$path]
       and ((.[0].tags // []) | index($trusted) != null)
       and ((.[0].tags // []) | index($candidate) == null)' >/dev/null || \
    fail "latest snapshot metadata is not a trusted Syncthing recovery point"

  latest_epoch="$(
    printf '%s\n' "$snapshot_metadata" |
      jq -er '
        .[0].time
        | capture("^(?<base>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\\.[0-9]+)?(?<zone>Z|(?<sign>[+-])(?<hours>[0-9]{2}):(?<minutes>[0-9]{2}))$")
        | (.base + "Z" | fromdateiso8601)
          - (if .zone == "Z" then 0
             else (((.hours | tonumber) * 3600 + (.minutes | tonumber) * 60)
                   * (if .sign == "+" then 1 else -1 end))
             end)
      '
  )" || fail "latest trusted snapshot has an invalid timestamp"
  now_epoch="$(date -u +%s)"
  case "$now_epoch" in
    *[!0-9]*|'') fail "current UTC time is invalid" ;;
  esac
  age_seconds=$((now_epoch - latest_epoch))
  [ "$age_seconds" -ge 0 ] || fail "latest trusted snapshot is in the future"
  [ "$age_seconds" -le "$MAX_TRUSTED_SNAPSHOT_AGE_SECONDS" ] || \
    fail "latest trusted snapshot is stale: age=${age_seconds}s"
  printf 'syncthing backup: freshness check passed; snapshot=%s age=%ss\n' \
    "$latest_snapshot_id" "$age_seconds"
}

run_restore_proof() {
  load_credentials
  verify_repository
  validate_source_and_policy

  restore_snapshot_id="${RESTORE_SNAPSHOT_ID:-}"
  validate_snapshot_id "$restore_snapshot_id" "restore snapshot ID"

  snapshot_metadata="$(
    restic --retry-lock 2h snapshots "$restore_snapshot_id" --json
  )" || fail "could not read restore snapshot metadata"
  printf '%s\n' "$snapshot_metadata" |
    jq -e \
      --arg id "$restore_snapshot_id" \
      --arg host "$RESTIC_HOST" \
      --arg path "$SOURCE_ROOT" \
      --arg trusted "$TRUSTED_TAG" \
      --arg candidate "$CANDIDATE_TAG" \
      'length == 1
       and .[0].id == $id
       and .[0].hostname == $host
       and .[0].paths == [$path]
       and ((.[0].tags // []) | index($trusted) != null)
       and ((.[0].tags // []) | index($candidate) == null)' >/dev/null || \
    fail "restore snapshot is not an exact trusted Syncthing recovery point"

  [ -d "$RESTORE_MOUNT" ] || fail "disposable restore volume is not mounted"
  [ ! -L "$RESTORE_MOUNT" ] || fail "disposable restore mount cannot be a symbolic link"
  [ -w "$RESTORE_MOUNT" ] || fail "disposable restore volume is not writable"
  [ ! -e "$RESTORE_TARGET" ] && [ ! -L "$RESTORE_TARGET" ] || \
    fail "disposable restore target already exists"
  mkdir "$RESTORE_TARGET"

  restic --retry-lock 2h restore "$restore_snapshot_id" --target "$RESTORE_TARGET"

  restored_source="${RESTORE_TARGET}${SOURCE_ROOT}"
  restored_canary="${restored_source}/.restic-source-canary"
  [ -f "$restored_canary" ] || fail "restored source canary is missing"
  [ ! -L "$restored_canary" ] || fail "restored source canary cannot be a symbolic link"
  restored_canary_sha256="$(sha256sum "$restored_canary" | awk '{print $1}')"
  [ "$restored_canary_sha256" = "$SOURCE_CANARY_SHA256" ] || \
    fail "restored source canary checksum does not match"

  tab="$(printf '\t')"
  while IFS="$tab" read -r folder_id relative; do
    restored_folder="${restored_source}/${relative}"
    if grep -Fqx -- "$folder_id" "${WORK_DIR}/excluded-folder-ids.seen"; then
      [ ! -e "$restored_folder" ] && [ ! -L "$restored_folder" ] || \
        fail "excluded Syncthing folder ${folder_id} was restored"
    else
      validate_relative_folder_path "$relative" "$folder_id" "$restored_source"
    fi
  done < "$FOLDER_MAP"

  restored_files="$(find "$restored_source" -type f | wc -l | awk '{print $1}')"
  restored_directories="$(find "$restored_source" -type d | wc -l | awk '{print $1}')"
  [ "$restored_files" -gt 0 ] || fail "restore proof produced no files"
  [ "$restored_directories" -gt 0 ] || fail "restore proof produced no directories"
  printf 'syncthing backup: restore proof passed; snapshot=%s files=%s directories=%s\n' \
    "$restore_snapshot_id" "$restored_files" "$restored_directories"
}

case "${1:-backup}" in
  backup)
    run_backup
    ;;
  init-repository)
    initialize_repository
    ;;
  check-repository-data)
    check_repository_data
    ;;
  check-freshness)
    check_backup_freshness
    ;;
  restore-proof)
    run_restore_proof
    ;;
  validate-policy)
    validate_source_and_policy
    ;;
  *)
    fail "usage: $0 [backup|check-freshness|check-repository-data|init-repository|restore-proof|validate-policy]"
    ;;
esac
