#!/usr/bin/env bash
set -euo pipefail

server_host="${1:-beelink}"
agent_host="${2:-pi}"
k3s_version="${K3S_VERSION:-v1.36.2+k3s1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="${repo_root}/infrastructure/k3s/agent-pi-config.yaml"
sshd_config="${repo_root}/infrastructure/hosts/raspberrypi/sshd-hardening.conf"
apt_periodic_config="${repo_root}/infrastructure/hosts/raspberrypi/20auto-upgrades"
unattended_upgrades_config="${repo_root}/infrastructure/hosts/raspberrypi/52-home-server-unattended-upgrades"

scp "${config}" "${agent_host}:/tmp/home-server-k3s-agent.yaml"
scp "${sshd_config}" "${agent_host}:/tmp/home-server-sshd-hardening.conf"
scp "${apt_periodic_config}" "${agent_host}:/tmp/home-server-20auto-upgrades"
scp "${unattended_upgrades_config}" \
  "${agent_host}:/tmp/home-server-52-unattended-upgrades"
ssh "${agent_host}" sudo install -D -m 0600 \
  /tmp/home-server-k3s-agent.yaml /etc/rancher/k3s/config.yaml
ssh "${agent_host}" sudo install -m 0644 \
  /tmp/home-server-sshd-hardening.conf \
  /etc/ssh/sshd_config.d/00-home-server-hardening.conf
ssh "${agent_host}" sudo sshd -t
ssh "${agent_host}" sudo systemctl reload ssh

# Disable both timers before touching APT policy. If this script fails, they
# stay disabled rather than falling back to Debian's broader defaults after a
# reboot. Let an already-running APT job finish instead of interrupting dpkg.
ssh "${agent_host}" sudo systemctl disable --now \
  apt-daily.timer apt-daily-upgrade.timer
ssh "${agent_host}" sudo bash -s <<'REMOTE_WAIT_FOR_APT'
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
ssh "${agent_host}" sudo install -m 0644 \
  /tmp/home-server-20auto-upgrades /etc/apt/apt.conf.d/20auto-upgrades
ssh "${agent_host}" sudo install -m 0644 \
  /tmp/home-server-52-unattended-upgrades \
  /etc/apt/apt.conf.d/52-home-server-unattended-upgrades

# Install the updater without upgrading the rest of the host. The repository
# policy is deliberately narrower than Debian's default: security origin only,
# with no unattended reboot or dependency removal.
ssh "${agent_host}" sudo env DEBIAN_FRONTEND=noninteractive \
  apt-get -o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 update
ssh "${agent_host}" sudo env DEBIAN_FRONTEND=noninteractive \
  apt-get -o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 install -y \
  --no-install-recommends unattended-upgrades

# Fail closed if a distro default or later local fragment broadens eligibility.
# The dry run exercises unattended-upgrades' own parser and resolver without
# changing installed packages.
ssh "${agent_host}" sudo bash -s <<'REMOTE_UNATTENDED_UPGRADES'
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

ssh "${agent_host}" rm -f \
  /tmp/home-server-k3s-agent.yaml \
  /tmp/home-server-sshd-hardening.conf \
  /tmp/home-server-20auto-upgrades \
  /tmp/home-server-52-unattended-upgrades

# A legacy minute-by-minute watchdog treated filtered public TCP/53 as a Pi
# network failure and could restart NetworkManager or reload a Wi-Fi driver on
# this Ethernet DNS/DHCP/NFS node. Preserve its files for forensics, but never
# let it run under K3s.
ssh "${agent_host}" \
  "if systemctl list-unit-files network-watchdog.timer >/dev/null 2>&1; then sudo systemctl disable --now network-watchdog.timer; fi"

# The join token never appears in process arguments or the repository.
ssh "${server_host}" sudo cat /var/lib/rancher/k3s/server/node-token \
  | ssh "${agent_host}" sudo install -D -m 0600 /dev/stdin /etc/rancher/k3s/node-token

ssh "${agent_host}" \
  "curl -sfL https://get.k3s.io | sudo INSTALL_K3S_VERSION='${k3s_version}' INSTALL_K3S_EXEC=agent sh -"

ssh "${server_host}" sudo k3s kubectl wait \
  --for=condition=Ready node/raspberrypi --timeout=180s
ssh "${server_host}" sudo k3s kubectl cordon raspberrypi
