#!/usr/bin/env bash
set -Eeuo pipefail

# Copy the organized Pi media library into the already-formatted JuiceFS
# volume. Credentials are staged in a root-only tmpfs directory by the
# operator; this script never accepts them as command-line arguments.

source_root="${JUICEFS_MIGRATION_SOURCE:-/home/reza/media}"
runtime_dir="${JUICEFS_MIGRATION_RUNTIME:-/run/juicefs-media-migration}"
juicefs_bin="${JUICEFS_BIN:-/usr/local/bin/juicefs}"
threads="${JUICEFS_MIGRATION_THREADS:-4}"
bwlimit="${JUICEFS_MIGRATION_BWLIMIT:-158}"
metrics="${JUICEFS_MIGRATION_METRICS:-127.0.0.1:9568}"
max_ingress_base_bytes="${JUICEFS_MIGRATION_MAX_INGRESS_BASE_BYTES:-67108864}"
categories=(podcasts audiobooks books music movies tv)
active_sync_pid=''
migration_unit=''

stop_active_sync() {
  if [[ -n "${active_sync_pid}" ]] && kill -0 "${active_sync_pid}" 2>/dev/null; then
    kill -TERM "${active_sync_pid}" 2>/dev/null || true
    wait "${active_sync_pid}" 2>/dev/null || true
  fi
}

trap 'stop_active_sync; exit 130' INT
trap 'stop_active_sync; exit 143' TERM

usage() {
  cat <<'EOF'
Usage: run-juicefs-media-migration.sh [--dry-run] [--reset-checkpoint] [CATEGORY ...]

Categories: podcasts audiobooks books music movies tv

Required root-only files under /run/juicefs-media-migration:
  metaurl          PostgreSQL metadata URL (without a password)
  meta-password    PostgreSQL password
  rsa-passphrase   JuiceFS encrypted RSA-key passphrase

The source is never deleted. Downloads are not an accepted category.
The migration must run in an IPAccounting-enabled systemd service. It stops if
inbound traffic exceeds 64 MiB plus a conservative allowance for upload ACKs.
Use --reset-checkpoint only after stopping source writers when a prior run
recorded stale size or modification-time data.
EOF
}

if [[ "${EUID}" -ne 0 ]]; then
  printf '%s\n' 'Run this migration as root.' >&2
  exit 1
fi

dry_run=false
reset_checkpoint=false
requested=()
while (($#)); do
  case "$1" in
    --dry-run)
      dry_run=true
      ;;
    --reset-checkpoint)
      reset_checkpoint=true
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    --*)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      requested+=("$1")
      ;;
  esac
  shift
done

if ((${#requested[@]})); then
  categories=("${requested[@]}")
fi

case "${threads}" in
  '' | *[!0-9]*) printf '%s\n' 'Thread count must be a positive integer.' >&2; exit 2 ;;
esac
case "${bwlimit}" in
  '' | *[!0-9]*) printf '%s\n' 'Bandwidth limit must be a positive integer.' >&2; exit 2 ;;
esac
case "${max_ingress_base_bytes}" in
  '' | *[!0-9]*) printf '%s\n' 'Base ingress budget must be a positive integer.' >&2; exit 2 ;;
esac
if ((threads < 1 || threads > 16 || bwlimit < 1 || max_ingress_base_bytes < 1)); then
  printf '%s\n' 'Refusing unsafe thread count or bandwidth limit.' >&2
  exit 2
fi
if [[ ! "${metrics}" =~ ^127\.0\.0\.1:[0-9]{2,5}$ ]]; then
  printf 'Migration metrics must listen only on IPv4 loopback: %s\n' "${metrics}" >&2
  exit 2
fi

migration_unit="$(basename "$(cut -d: -f3 /proc/self/cgroup)")"
if [[ "${migration_unit}" != *.service ]] ||
  [[ "$(systemctl show "${migration_unit}" --property=IPAccounting --value 2>/dev/null)" != yes ]]; then
  printf '%s\n' 'Run the migration in a systemd service with IPAccounting=yes.' >&2
  exit 2
fi

allowed=' podcasts audiobooks books music movies tv '
for category in "${categories[@]}"; do
  if [[ "${allowed}" != *" ${category} "* ]]; then
    printf 'Refusing unknown category: %s\n' "${category}" >&2
    exit 2
  fi
done

if [[ ! -x "${juicefs_bin}" ]]; then
  printf 'JuiceFS binary is not executable: %s\n' "${juicefs_bin}" >&2
  exit 1
fi
if [[ ! -d "${source_root}" || -L "${source_root}" ]]; then
  printf 'Source root is not a real directory: %s\n' "${source_root}" >&2
  exit 1
fi
if [[ ! -d "${runtime_dir}" || -L "${runtime_dir}" ]]; then
  printf 'Runtime directory is missing or unsafe: %s\n' "${runtime_dir}" >&2
  exit 1
fi

for secret_file in metaurl meta-password rsa-passphrase; do
  path="${runtime_dir}/${secret_file}"
  if [[ ! -f "${path}" || -L "${path}" ]]; then
    printf 'Required credential file is missing or unsafe: %s\n' "${path}" >&2
    exit 1
  fi
  mode="$(stat -c '%a' "${path}")"
  owner="$(stat -c '%u:%g' "${path}")"
  if [[ "${mode}" != 600 || "${owner}" != 0:0 ]]; then
    printf 'Credential file must be root:root mode 0600: %s\n' "${path}" >&2
    exit 1
  fi
done

export media
export META_PASSWORD
export JFS_RSA_PASSPHRASE
media="$(<"${runtime_dir}/metaurl")"
META_PASSWORD="$(<"${runtime_dir}/meta-password")"
JFS_RSA_PASSPHRASE="$(<"${runtime_dir}/rsa-passphrase")"
if [[ "${media}" != postgres://juicefs@juicefs-postgresql.juicefs-system.svc.cluster.local:5432/juicefs* ]] &&
  [[ "${media}" != postgres://juicefs@10.*:5432/juicefs* ]]; then
  printf '%s\n' 'Refusing unexpected JuiceFS metadata endpoint.' >&2
  exit 1
fi
if [[ -z "${META_PASSWORD}" || -z "${JFS_RSA_PASSPHRASE}" ]]; then
  printf '%s\n' 'A required credential is empty.' >&2
  exit 1
fi

checkpoint_home="${runtime_dir}/home"
install -d -o root -g root -m 0700 "${checkpoint_home}"
export HOME="${checkpoint_home}"

sync_args=(
  --threads="${threads}"
  --bwlimit="${bwlimit}"
  --enable-checkpoint
  --checkpoint-interval=30s
  --dirs
  --perms
  --links
  --update
  --check-change
  --max-failure=0
  --metrics="${metrics}"
)
if [[ "${dry_run}" == true ]]; then
  sync_args+=(--dry)
fi
if [[ "${reset_checkpoint}" == true ]]; then
  sync_args+=(--checkpoint-force-reset)
fi

printf 'JuiceFS media migration starting: categories=%s threads=%s bwlimit=%sMbps dry_run=%s reset_checkpoint=%s\n' \
  "${categories[*]}" "${threads}" "${bwlimit}" "${dry_run}" "${reset_checkpoint}"

run_guarded_sync() {
  local source="$1"
  local destination="$2"
  local metrics_url="http://${metrics}/metrics"
  local metrics_body copied_bytes ingress_bytes ingress_delta allowed_ingress
  local metrics_failures=0
  local peak_ingress_bytes=0
  local initial_ingress_bytes
  local started_at="${SECONDS}"
  local rc=0

  initial_ingress_bytes="$(systemctl show "${migration_unit}" --property=IPIngressBytes --value)"
  if [[ ! "${initial_ingress_bytes}" =~ ^[0-9]+$ ]]; then
    printf '%s\n' 'ABORTING: systemd did not provide an initial IP ingress counter.' >&2
    return 71
  fi

  "${juicefs_bin}" sync "${sync_args[@]}" "${source}" "${destination}" &
  active_sync_pid=$!

  while kill -0 "${active_sync_pid}" 2>/dev/null; do
    if metrics_body="$(curl --silent --show-error --max-time 2 "${metrics_url}" 2>/dev/null)"; then
      metrics_failures=0
      copied_bytes="$({
        printf '%s\n' "${metrics_body}"
      } | awk '
        /^juicefs_sync_copied_bytes\{/ { total += $NF }
        END { printf "%.0f", total + 0 }
      ')"
      ingress_bytes="$(systemctl show "${migration_unit}" --property=IPIngressBytes --value)"
      if [[ ! "${ingress_bytes}" =~ ^[0-9]+$ ]]; then
        printf '%s\n' 'ABORTING: systemd stopped reporting IP ingress.' >&2
        kill -TERM "${active_sync_pid}" 2>/dev/null || true
        wait "${active_sync_pid}" 2>/dev/null || true
        active_sync_pid=''
        return 71
      fi
      ingress_delta=$((ingress_bytes - initial_ingress_bytes))
      if ((ingress_delta > peak_ingress_bytes)); then
        peak_ingress_bytes="${ingress_delta}"
      fi
      # The cgroup counter includes TCP ACKs and small PostgreSQL responses.
      # Five percent of copied bytes is deliberately more than healthy upload
      # traffic needs, but tiny compared with the 128x encrypted-read failure.
      allowed_ingress=$((max_ingress_base_bytes + copied_bytes / 20))
      if ((ingress_delta > allowed_ingress)); then
        printf 'ABORTING: inbound migration traffic reached %s bytes; dynamic budget is %s bytes.\n' \
          "${ingress_delta}" "${allowed_ingress}" >&2
        kill -TERM "${active_sync_pid}" 2>/dev/null || true
        wait "${active_sync_pid}" 2>/dev/null || true
        active_sync_pid=''
        return 70
      fi
    else
      metrics_failures=$((metrics_failures + 1))
      if ((SECONDS - started_at >= 30 && metrics_failures >= 5)); then
        printf '%s\n' 'ABORTING: the JuiceFS egress guard cannot read its metrics endpoint.' >&2
        kill -TERM "${active_sync_pid}" 2>/dev/null || true
        wait "${active_sync_pid}" 2>/dev/null || true
        active_sync_pid=''
        return 71
      fi
    fi
    sleep 2
  done

  if wait "${active_sync_pid}"; then
    rc=0
  else
    rc=$?
  fi
  active_sync_pid=''
  printf 'Egress guard: peak inbound traffic=%s bytes; fixed budget=%s bytes plus 5%% of copied bytes.\n' \
    "${peak_ingress_bytes}" "${max_ingress_base_bytes}"
  return "${rc}"
}

for category in "${categories[@]}"; do
  source="${source_root}/${category}"
  if [[ ! -d "${source}" || -L "${source}" ]]; then
    printf 'Category source is missing or unsafe: %s\n' "${source}" >&2
    exit 1
  fi

  printf 'Starting category %s at %s\n' "${category}" "$(date --iso-8601=seconds)"
  run_guarded_sync "${source}/" "jfs://media/${category}/"
  printf 'Completed category %s at %s\n' "${category}" "$(date --iso-8601=seconds)"
done

printf 'JuiceFS media migration completed at %s\n' "$(date --iso-8601=seconds)"
