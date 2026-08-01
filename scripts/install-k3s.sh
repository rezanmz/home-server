#!/usr/bin/env bash
set -euo pipefail

host="${1:-}"
role="${2:-}"
# renovate: datasource=github-releases depName=k3s-io/k3s versioning=loose
k3s_version="${3:-v1.36.2+k3s1}"
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

if [[ -z "${host}" || -z "${role}" ]]; then
  printf 'usage: %s SSH_ALIAS server|agent [K3S_VERSION]\n' "$0" >&2
  exit 2
fi

if [[ ! "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  printf 'invalid SSH alias: %s\n' "${host}" >&2
  exit 2
fi

case "${role}" in
  server)
    remote_state_check='if sudo -n test -e /var/lib/rancher/k3s || systemctl cat k3s.service >/dev/null 2>&1; then exit 0; fi; exit 1'
    ;;
  agent)
    remote_state_check='if sudo -n test -e /var/lib/rancher/k3s || systemctl cat k3s-agent.service >/dev/null 2>&1; then exit 0; fi; exit 1'
    ;;
  *)
    printf 'role must be server or agent\n' >&2
    exit 2
    ;;
esac

if [[ ! "${k3s_version}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+\+k3s[0-9]+$ ]]; then
  printf 'invalid K3s version: %s\n' "${k3s_version}" >&2
  exit 2
fi

if ! ssh "${ssh_options[@]}" "${host}" sudo -n true; then
  printf 'noninteractive sudo preflight failed on %s\n' "${host}" >&2
  exit 1
fi

if ssh "${ssh_options[@]}" "${host}" "${remote_state_check}"; then
  printf 'refusing to run the fresh-host installer on existing K3s %s %s\n' \
    "${role}" "${host}" >&2
  exit 1
else
  status=$?
  if [[ "${status}" != 1 ]]; then
    printf 'could not establish fresh-host state on %s (ssh status %s)\n' \
      "${host}" "${status}" >&2
    exit 1
  fi
fi

# Pin the installer independently from the K3s release. The installer then
# downloads INSTALL_K3S_VERSION and verifies the release binary against K3s's
# published checksum before installing it.
installer_commit='01b6f04aaa69e8b09303f0393d4b4f1811da23aa'
installer_sha256='46177d4c99440b4c0311b67233823a8e8a2fc09693f6c89af1a7161e152fbfad'
installer_url="https://raw.githubusercontent.com/k3s-io/k3s/${installer_commit}/install.sh"
local_installer="$(mktemp)"

cleanup() {
  rm -f -- "${local_installer}"
}
trap cleanup EXIT

curl --fail --location --proto '=https' --proto-redir '=https' --retry 3 \
  --show-error --silent "${installer_url}" --output "${local_installer}"

if command -v sha256sum >/dev/null 2>&1; then
  actual_sha256="$(sha256sum "${local_installer}" | awk '{print $1}')"
else
  actual_sha256="$(shasum -a 256 "${local_installer}" | awk '{print $1}')"
fi

if [[ "${actual_sha256}" != "${installer_sha256}" ]]; then
  printf 'K3s installer checksum mismatch: expected %s, got %s\n' \
    "${installer_sha256}" "${actual_sha256}" >&2
  exit 1
fi

sh -n "${local_installer}"
ssh "${ssh_options[@]}" "${host}" sudo -n env \
  "INSTALL_K3S_VERSION=${k3s_version}" \
  "INSTALL_K3S_EXEC=${role}" \
  sh - <"${local_installer}"
