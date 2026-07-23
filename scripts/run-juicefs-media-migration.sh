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
categories=(podcasts audiobooks books music movies tv)

usage() {
  cat <<'EOF'
Usage: run-juicefs-media-migration.sh [--dry-run] [--reset-checkpoint] [CATEGORY ...]

Categories: podcasts audiobooks books music movies tv

Required root-only files under /run/juicefs-media-migration:
  metaurl          PostgreSQL metadata URL (without a password)
  meta-password    PostgreSQL password
  rsa-passphrase   JuiceFS encrypted RSA-key passphrase

The source is never deleted. Downloads are not an accepted category.
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
if ((threads < 1 || threads > 16 || bwlimit < 1)); then
  printf '%s\n' 'Refusing unsafe thread count or bandwidth limit.' >&2
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
  --check-new
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

for category in "${categories[@]}"; do
  source="${source_root}/${category}"
  if [[ ! -d "${source}" || -L "${source}" ]]; then
    printf 'Category source is missing or unsafe: %s\n' "${source}" >&2
    exit 1
  fi

  printf 'Starting category %s at %s\n' "${category}" "$(date --iso-8601=seconds)"
  "${juicefs_bin}" sync "${sync_args[@]}" \
    "${source}/" "jfs://media/${category}/"
  printf 'Completed category %s at %s\n' "${category}" "$(date --iso-8601=seconds)"
done

printf 'JuiceFS media migration completed at %s\n' "$(date --iso-8601=seconds)"
