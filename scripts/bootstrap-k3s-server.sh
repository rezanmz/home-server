#!/usr/bin/env bash
set -euo pipefail

host="${1:-beelink}"
# renovate: datasource=github-releases depName=k3s-io/k3s versioning=loose
k3s_version="${K3S_VERSION:-v1.36.2+k3s1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="${repo_root}/infrastructure/k3s/server-config.yaml"
installer="${repo_root}/scripts/install-k3s.sh"
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

run_host() {
  ssh "${ssh_options[@]}" "${host}" "$@"
}

if ! run_host sudo -n true; then
  printf 'noninteractive sudo preflight failed on %s\n' "${host}" >&2
  exit 1
fi

if run_host \
  'if sudo -n test -e /etc/rancher/k3s/config.yaml || \
    sudo -n test -e /var/lib/rancher/k3s || \
    systemctl cat k3s.service >/dev/null 2>&1; then \
      exit 0; \
    fi; \
    exit 1'; then
  printf '%s\n' \
    'Refusing to run the fresh-server bootstrap helper on an existing K3s server.' >&2
  exit 1
else
  status=$?
  if [[ "${status}" != 1 ]]; then
    printf 'could not establish fresh-server state on %s (ssh status %s)\n' \
      "${host}" "${status}" >&2
    exit 1
  fi
fi

remote_config="$(run_host mktemp /tmp/home-server-k3s-server.XXXXXX)"
if [[ ! "${remote_config}" =~ ^/tmp/home-server-k3s-server\.[A-Za-z0-9]+$ ]]; then
  printf 'refusing unexpected remote config path: %s\n' "${remote_config}" >&2
  exit 1
fi

cleanup() {
  run_host rm -f -- "${remote_config}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

scp "${ssh_options[@]}" "${config}" "${host}:${remote_config}"
run_host sudo -n install -D -m 0600 \
  "${remote_config}" /etc/rancher/k3s/config.yaml
"${installer}" "${host}" server "${k3s_version}"

run_host sudo -n k3s kubectl wait \
  --for=condition=Ready node/beelink --timeout=180s
