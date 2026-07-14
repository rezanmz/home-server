#!/usr/bin/env bash
set -euo pipefail

host="${1:-pi}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exports="${repo_root}/infrastructure/hosts/raspberrypi/home-server.exports"
expected_live_sha256="${EXPECTED_LIVE_EXPORTS_SHA256:-}"
remote_expected_live_sha256="${expected_live_sha256:--}"
ssh_options=(
  -o BatchMode=yes
  -o ConnectionAttempts=1
  -o ConnectTimeout=10
  -o ControlMaster=no
  -o ControlPath=none
  -o KbdInteractiveAuthentication=no
  -o PasswordAuthentication=no
  -o PreferredAuthentications=publickey
  -o StrictHostKeyChecking=yes
)

if [[ ! "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  printf 'invalid SSH alias: %s\n' "${host}" >&2
  exit 2
fi
if [[ -n "${expected_live_sha256}" ]] &&
  [[ ! "${expected_live_sha256}" =~ ^[0-9a-f]{64}$ ]]; then
  printf '%s\n' 'EXPECTED_LIVE_EXPORTS_SHA256 must be 64 lowercase hex characters.' >&2
  exit 2
fi

remote_temporary="$(ssh "${ssh_options[@]}" "${host}" \
  mktemp /tmp/home-server-exports.XXXXXX)"
if [[ ! "${remote_temporary}" =~ ^/tmp/home-server-exports\.[A-Za-z0-9]+$ ]]; then
  printf 'refusing unexpected remote temporary path: %s\n' \
    "${remote_temporary}" >&2
  exit 1
fi

cleanup() {
  ssh "${ssh_options[@]}" "${host}" \
    rm -f -- "${remote_temporary}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

scp "${ssh_options[@]}" "${exports}" \
  "${host}:${remote_temporary}"
ssh "${ssh_options[@]}" "${host}" bash -s -- \
  "${remote_expected_live_sha256}" "${remote_temporary}" <<'REMOTE'
set -euo pipefail

expected_live_sha256="$1"
temporary="$2"
if [[ "$expected_live_sha256" == - ]]; then
  expected_live_sha256=''
fi
target=/etc/exports.d/home-server.exports
staged=''
had_target=false
backup=''
replacement_active=false

cleanup_remote() {
  status=$?
  if [[ "$replacement_active" == true ]]; then
    replacement_active=false
    printf '%s\n' 'New exports did not reload; restoring the previous file.' >&2
    if [[ "$had_target" == true ]]; then
      if ! sudo -n cp --archive -- "$backup" "$target"; then
        printf '%s\n' 'CRITICAL: failed to restore the previous export file.' >&2
        status=1
      fi
    elif ! sudo -n rm -f -- "$target"; then
      printf '%s\n' 'CRITICAL: failed to remove the rejected export file.' >&2
      status=1
    fi
    if ! sudo -n exportfs -ra; then
      printf '%s\n' \
        'CRITICAL: previous export state was restored but its reload failed.' >&2
      status=1
    fi
  fi
  if ! rm -f -- "$temporary"; then
    status=1
  fi
  if [[ -n "$staged" ]]; then
    if ! sudo -n rm -f -- "$staged"; then
      status=1
    fi
  fi
  trap - EXIT HUP INT TERM
  exit "$status"
}
trap cleanup_remote EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if sudo -n test -e "$target"; then
  if ! sudo -n test -f "$target" || sudo -n test -L "$target"; then
    printf '%s\n' 'Refusing to replace a non-regular or symlinked export file.' >&2
    exit 1
  fi
  if [[ ! "$expected_live_sha256" =~ ^[0-9a-f]{64}$ ]]; then
    printf '%s\n' \
      'Refusing to replace existing exports without EXPECTED_LIVE_EXPORTS_SHA256.' >&2
    exit 1
  fi
  actual_live_sha256="$(sudo -n sha256sum "$target" | awk '{print $1}')"
  if [[ "$actual_live_sha256" != "$expected_live_sha256" ]]; then
    printf 'Refusing live export drift: expected %s, got %s\n' \
      "$expected_live_sha256" "$actual_live_sha256" >&2
    exit 1
  fi
  backup="$(sudo -n mktemp \
    "/root/home-server.exports.before-$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")"
  sudo -n cp --archive -- "$target" "$backup"
  had_target=true
  printf 'Saved previous exports as %s\n' "$backup" >&2
elif [[ -n "$expected_live_sha256" ]]; then
  printf '%s\n' 'Refusing expected export replacement: live file is absent.' >&2
  exit 1
fi

sudo -n DEBIAN_FRONTEND=noninteractive apt-get update
sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y nfs-kernel-server
sudo -n install -d -m 0755 /etc/exports.d
sudo -n systemctl enable --now nfs-server

staged="$(sudo -n mktemp /etc/exports.d/.home-server.exports.XXXXXX)"
sudo -n install -m 0644 "$temporary" "$staged"
sudo -n cmp -s "$temporary" "$staged"
sudo -n mv -f -- "$staged" "$target"
staged=''

replacement_active=true
sudo -n exportfs -ra
replacement_active=false
REMOTE
