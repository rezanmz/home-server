#!/usr/bin/env bash
set -euo pipefail

server_host="${1:-beelink}"
agent_host="${2:-pi}"
k3s_version="${K3S_VERSION:-v1.36.2+k3s1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="${repo_root}/infrastructure/k3s/agent-pi-config.yaml"
installer="${repo_root}/scripts/install-k3s.sh"
token_installer="${repo_root}/scripts/install-k3s-agent-token.sh"
sshd_config="${repo_root}/infrastructure/hosts/raspberrypi/sshd-hardening.conf"
apt_periodic_config="${repo_root}/infrastructure/hosts/raspberrypi/20auto-upgrades"
unattended_upgrades_config="${repo_root}/infrastructure/hosts/raspberrypi/52-home-server-unattended-upgrades"
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

for host in "${server_host}" "${agent_host}"; do
  if [[ ! "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    printf 'invalid SSH alias: %s\n' "${host}" >&2
    exit 2
  fi
done

run_agent() {
  ssh "${ssh_options[@]}" "${agent_host}" "$@"
}

run_server() {
  ssh "${ssh_options[@]}" "${server_host}" "$@"
}

if run_agent \
  'if sudo -n test -e /etc/rancher/k3s/config.yaml || \
    sudo -n test -e /var/lib/rancher/k3s || \
    systemctl cat k3s-agent.service >/dev/null 2>&1; then \
      exit 0; \
    fi; \
    exit 1'; then
  printf '%s\n' \
    'Refusing to run the fresh-agent join helper on an existing K3s agent.' >&2
  exit 1
else
  status=$?
  if [[ "${status}" != 1 ]]; then
    printf 'could not establish fresh-agent state on %s (ssh status %s)\n' \
      "${agent_host}" "${status}" >&2
    exit 1
  fi
fi

if [[ "$(run_agent id -un)" != reza ]] || ! run_agent sudo -n true ||
  ! run_server sudo -n true; then
  printf '%s\n' \
    'Refusing host mutation: expected key-authenticated reza with noninteractive sudo.' >&2
  exit 1
fi

ssh_connection="$(run_agent 'printf "%s\n" "$SSH_CONNECTION"')"
read -r client_address client_port server_address server_port extra \
  <<<"${ssh_connection}"
if [[ ! "${client_address}" =~ ^[0-9A-Fa-f:.]+$ ]] ||
  [[ ! "${server_address}" =~ ^[0-9A-Fa-f:.]+$ ]] ||
  [[ ! "${client_port}" =~ ^[0-9]+$ ]] ||
  [[ ! "${server_port}" =~ ^[0-9]+$ ]] || [[ -n "${extra:-}" ]]; then
  printf 'refusing unexpected SSH connection context: %s\n' \
    "${ssh_connection}" >&2
  exit 1
fi

remote_staging="$(run_agent mktemp -d /tmp/home-server-k3s-agent.XXXXXX)"
if [[ ! "${remote_staging}" =~ ^/tmp/home-server-k3s-agent\.[A-Za-z0-9]+$ ]]; then
  printf 'refusing unexpected remote staging path: %s\n' \
    "${remote_staging}" >&2
  exit 1
fi

cleanup_staging() {
  run_agent rm -rf -- "${remote_staging}" >/dev/null 2>&1 || true
}
trap cleanup_staging EXIT

scp "${ssh_options[@]}" "${config}" \
  "${agent_host}:${remote_staging}/k3s-agent.yaml"
scp "${ssh_options[@]}" "${sshd_config}" \
  "${agent_host}:${remote_staging}/sshd-hardening.conf"
scp "${ssh_options[@]}" "${apt_periodic_config}" \
  "${agent_host}:${remote_staging}/20auto-upgrades"
scp "${ssh_options[@]}" "${unattended_upgrades_config}" \
  "${agent_host}:${remote_staging}/52-home-server-unattended-upgrades"

run_agent sudo -n bash -s -- "${remote_staging}" "${client_address}" \
  "${server_address}" "${server_port}" <<'REMOTE_INSTALL_CONFIG'
set -euo pipefail

staging="$1"
client_address="$2"
server_address="$3"
server_port="$4"
sshd_target=/etc/ssh/sshd_config.d/00-home-server-hardening.conf
apt_periodic_target=/etc/apt/apt.conf.d/20auto-upgrades
unattended_target=/etc/apt/apt.conf.d/52-home-server-unattended-upgrades
sshd_candidate=''
sshd_backup=''
sshd_had_target=false
sshd_replacement_active=false

cleanup_candidate() {
  status=$?
  if [[ "$sshd_replacement_active" == true ]]; then
    sshd_replacement_active=false
    printf '%s\n' 'SSH change did not complete; restoring the previous drop-in.' >&2
    if ! restore_sshd; then
      printf '%s\n' \
        'CRITICAL: failed to restore and reload the prior SSH configuration.' >&2
      status=1
    fi
  fi
  if [[ -n "$sshd_candidate" ]]; then
    if ! rm -f -- "$sshd_candidate"; then
      status=1
    fi
  fi
  trap - EXIT HUP INT TERM
  exit "$status"
}
trap cleanup_candidate EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

assert_absent_or_identical() {
  local desired target
  desired="$1"
  target="$2"
  if [[ ! -e "$target" ]]; then
    return 0
  fi
  if [[ ! -f "$target" || -L "$target" ]]; then
    printf 'Refusing non-regular or symlinked managed file: %s\n' "$target" >&2
    return 1
  fi
  if ! cmp -s "$desired" "$target"; then
    printf 'Refusing unexplained live drift in managed file: %s\n' "$target" >&2
    return 1
  fi
}

assert_absent_or_identical "$staging/sshd-hardening.conf" "$sshd_target"
assert_absent_or_identical "$staging/20auto-upgrades" "$apt_periodic_target"
assert_absent_or_identical \
  "$staging/52-home-server-unattended-upgrades" "$unattended_target"

if [[ -e "$sshd_target" ]]; then
  if [[ ! -f "$sshd_target" || -L "$sshd_target" ]]; then
    printf '%s\n' 'Refusing to replace a non-regular or symlinked SSH drop-in.' >&2
    exit 1
  fi
  sshd_backup="$(mktemp \
    "/root/home-server-sshd.before-$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")"
  cp --archive -- "$sshd_target" "$sshd_backup"
  sshd_had_target=true
  printf 'Saved previous SSH drop-in as %s\n' "$sshd_backup" >&2
fi

restore_sshd() {
  if [[ "$sshd_had_target" == true ]]; then
    cp --archive -- "$sshd_backup" "$sshd_target" || return 1
  else
    rm -f -- "$sshd_target" || return 1
  fi
  sshd -t || return 1
  systemctl reload ssh || return 1
}

sshd_candidate="$(mktemp /etc/ssh/sshd_config.d/.home-server-hardening.XXXXXX)"
install -m 0644 "$staging/sshd-hardening.conf" "$sshd_candidate"
mv -f -- "$sshd_candidate" "$sshd_target"
sshd_candidate=''
sshd_replacement_active=true

host_context="$(hostname -f 2>/dev/null || hostname)"
effective_sshd="$(sshd -T -C \
  "user=reza,host=${host_context},addr=${client_address},laddr=${server_address},lport=${server_port}")"
grep -Fqx 'passwordauthentication no' <<<"$effective_sshd"
grep -Fqx 'kbdinteractiveauthentication no' <<<"$effective_sshd"
grep -Fqx 'permitrootlogin no' <<<"$effective_sshd"
grep -Fqx 'pubkeyauthentication yes' <<<"$effective_sshd"
grep -Fqx 'allowusers reza' <<<"$effective_sshd"

if ! sshd -t; then
  printf '%s\n' 'Rejected SSH configuration.' >&2
  exit 1
fi
if ! systemctl reload ssh; then
  printf '%s\n' 'SSH reload failed.' >&2
  exit 1
fi
sshd_replacement_active=false
REMOTE_INSTALL_CONFIG

# This must be a new public-key-authenticated connection, not an existing SSH
# multiplexed session, so it proves the reloaded policy still admits reza.
run_agent 'set -euo pipefail
test "$(id -un)" = reza
sudo -n true
sudo -n sshd -T | grep -qx "passwordauthentication no"
sudo -n sshd -T | grep -qx "kbdinteractiveauthentication no"
sudo -n sshd -T | grep -qx "permitrootlogin no"
sudo -n sshd -T | grep -qx "pubkeyauthentication yes"
sudo -n sshd -T | grep -qx "allowusers reza"'

# Disable both timers before touching APT policy. If this script fails, they
# stay disabled rather than falling back to Debian's broader defaults after a
# reboot. Let an already-running APT job finish instead of interrupting dpkg.
run_agent sudo -n systemctl disable --now \
  apt-daily.timer apt-daily-upgrade.timer
run_agent sudo -n bash -s <<'REMOTE_WAIT_FOR_APT'
set -euo pipefail

deadline=$((SECONDS + 600))
while systemctl is-active --quiet apt-daily.service || \
  systemctl is-active --quiet apt-daily-upgrade.service; do
  if (( SECONDS >= deadline )); then
    printf '%s\n' 'Timed out waiting for the active APT job to finish.' >&2
    exit 1
  fi
  sleep 2
done
REMOTE_WAIT_FOR_APT

# Install the security-only policy before the package so a package post-install
# action can never observe Debian's broader default origin list.
run_agent sudo -n install -m 0644 \
  "${remote_staging}/20auto-upgrades" /etc/apt/apt.conf.d/20auto-upgrades
run_agent sudo -n install -m 0644 \
  "${remote_staging}/52-home-server-unattended-upgrades" \
  /etc/apt/apt.conf.d/52-home-server-unattended-upgrades

# Install the updater without upgrading the rest of the host. The repository
# policy is deliberately narrower than Debian's default: security origin only,
# with no unattended reboot or dependency removal.
run_agent sudo -n env DEBIAN_FRONTEND=noninteractive \
  apt-get -o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 update
run_agent sudo -n env DEBIAN_FRONTEND=noninteractive \
  apt-get -o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 install -y \
  --no-install-recommends unattended-upgrades

# Fail closed if a distro default or later local fragment broadens eligibility.
# The dry run exercises unattended-upgrades' own parser and resolver without
# changing installed packages.
run_agent sudo -n bash -s <<'REMOTE_UNATTENDED_UPGRADES'
set -euo pipefail

expected_origin='origin=Debian,codename=${distro_codename}-security,label=Debian-Security'
effective_config="$(apt-config dump)"
mapfile -t configured_origins < <(
  sed -n 's/^Unattended-Upgrade::Origins-Pattern:: "\(.*\)";$/\1/p' \
    <<<"${effective_config}"
)
mapfile -t legacy_origins < <(
  sed -n 's/^Unattended-Upgrade::Allowed-Origins:: "\(.*\)";$/\1/p' \
    <<<"${effective_config}"
)

if (( ${#configured_origins[@]} != 1 )) ||
  [[ "${configured_origins[0]:-}" != "${expected_origin}" ]] ||
  (( ${#legacy_origins[@]} != 0 )); then
  printf '%s\n' 'Refusing to enable unattended upgrades: effective origins are not security-only.' >&2
  grep -E '^Unattended-Upgrade::(Origins-Pattern|Allowed-Origins)' \
    <<<"${effective_config}" >&2 || true
  exit 1
fi

grep -Fqx 'APT::Periodic::Update-Package-Lists "1";' <<<"${effective_config}"
grep -Fqx 'APT::Periodic::Unattended-Upgrade "1";' <<<"${effective_config}"
grep -Fqx 'Unattended-Upgrade::Automatic-Reboot "false";' <<<"${effective_config}"
grep -Fqx 'Unattended-Upgrade::Remove-New-Unused-Dependencies "false";' \
  <<<"${effective_config}"
grep -Fqx 'Unattended-Upgrade::Remove-Unused-Dependencies "false";' \
  <<<"${effective_config}"
grep -Fqx 'Unattended-Upgrade::Remove-Unused-Kernel-Packages "false";' \
  <<<"${effective_config}"
unattended-upgrade --dry-run
systemctl enable --now unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer
REMOTE_UNATTENDED_UPGRADES

# A legacy minute-by-minute watchdog treated filtered public TCP/53 as a Pi
# network failure and could restart NetworkManager or reload a Wi-Fi driver on
# this Ethernet DNS/DHCP/NFS node. Preserve its files for forensics, but never
# let it run under K3s.
run_agent \
  "if systemctl list-unit-files network-watchdog.timer >/dev/null 2>&1; then sudo -n systemctl disable --now network-watchdog.timer; fi"

# A one-hour agent bootstrap token is validated and atomically installed. The
# receiver preserves any old token file if creation or transfer fails.
"${token_installer}" "${server_host}" "${agent_host}" raspberrypi

run_agent sudo -n install -D -m 0600 \
  "${remote_staging}/k3s-agent.yaml" /etc/rancher/k3s/config.yaml

"${installer}" "${agent_host}" agent "${k3s_version}"

run_server sudo -n k3s kubectl wait \
  --for=condition=Ready node/raspberrypi --timeout=180s
run_server sudo -n k3s kubectl cordon raspberrypi
