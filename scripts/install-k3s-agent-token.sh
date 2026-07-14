#!/usr/bin/env bash
set -euo pipefail

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

receive_token() {
  local target directory temporary line_count
  target="${K3S_AGENT_TOKEN_TARGET:-/etc/rancher/k3s/node-token}"
  directory="$(dirname "${target}")"

  if [[ ! -d "${directory}" ]]; then
    install -d -m 0700 "${directory}"
  fi
  temporary="$(mktemp "${directory}/.node-token.XXXXXX")"
  receive_temporary="${temporary}"

  cleanup_receive() {
    status=$?
    if [[ -n "${receive_temporary:-}" ]] &&
      ! rm -f -- "${receive_temporary}"; then
      status=1
    fi
    trap - EXIT HUP INT TERM
    exit "${status}"
  }
  trap cleanup_receive EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM

  cat >"${temporary}"
  line_count="$(awk 'END {print NR}' "${temporary}")"
  if [[ "${line_count}" != 1 ]] ||
    ! LC_ALL=C grep -Eq \
      '^K10[0-9a-f]{64}::[a-z0-9]{6}\.[a-z0-9]{16}$' "${temporary}"; then
    printf 'refusing invalid or incomplete K3s bootstrap token\n' >&2
    exit 1
  fi

  chmod 0600 "${temporary}"
  if ((EUID == 0)); then
    chown root:root "${temporary}"
  elif [[ "${target}" == /etc/rancher/k3s/node-token ]]; then
    printf 'receiver must run as root for the production token path\n' >&2
    exit 1
  fi
  mv -f -- "${temporary}" "${target}"
  receive_temporary=''
  trap - EXIT HUP INT TERM
}

if [[ "${1:-}" == --receive ]]; then
  receive_token
  exit 0
fi

server_host="${1:-}"
agent_host="${2:-}"
node_name="${3:-}"

for host in "${server_host}" "${agent_host}"; do
  if [[ ! "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    printf 'invalid SSH alias: %s\n' "${host}" >&2
    exit 2
  fi
done
if [[ ! "${node_name}" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
  printf 'invalid node name: %s\n' "${node_name}" >&2
  exit 2
fi

script_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
description="join-${node_name}-$(date -u +%Y%m%dT%H%M%SZ)"
remote_helper="$(
  ssh "${ssh_options[@]}" "${agent_host}" \
    mktemp /tmp/home-server-k3s-token.XXXXXX
)"
if [[ ! "${remote_helper}" =~ ^/tmp/home-server-k3s-token\.[A-Za-z0-9]+$ ]]; then
  printf 'refusing unexpected remote helper path: %s\n' "${remote_helper}" >&2
  exit 1
fi

cleanup() {
  ssh "${ssh_options[@]}" "${agent_host}" \
    rm -f -- "${remote_helper}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

scp "${ssh_options[@]}" "${script_path}" \
  "${agent_host}:${remote_helper}"

printf 'Creating one-hour bootstrap token with description %s\n' \
  "${description}" >&2
ssh "${ssh_options[@]}" "${server_host}" sudo -n k3s token create \
  --ttl 1h --description "${description}" |
  ssh "${ssh_options[@]}" "${agent_host}" sudo -n bash \
    "${remote_helper}" --receive

printf 'Installed bootstrap token; delete server-side token %s after admission.\n' \
  "${description}" >&2
