#!/usr/bin/env bash
set -euo pipefail

host="${1:-beelink}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
netplan="${repo_root}/infrastructure/hosts/beelink/netplan.yaml"
sshd_config="${repo_root}/infrastructure/hosts/beelink/sshd-hardening.conf"

scp "${netplan}" "${host}:/tmp/home-server-netplan.yaml"
scp "${sshd_config}" "${host}:/tmp/home-server-sshd-hardening.conf"

ssh "${host}" sudo install -m 0600 \
  /tmp/home-server-netplan.yaml /etc/netplan/00-installer-config.yaml
ssh "${host}" sudo install -m 0644 \
  /tmp/home-server-sshd-hardening.conf \
  /etc/ssh/sshd_config.d/00-home-server-hardening.conf
ssh "${host}" rm -f \
  /tmp/home-server-netplan.yaml /tmp/home-server-sshd-hardening.conf

# Remove installer/editor leftovers. The Netplan swap file may contain the old
# Wi-Fi credential, and the superseded SSH drop-in would be misleading.
ssh "${host}" sudo rm -f \
  /etc/netplan/.00-installer-config.yaml.swp \
  /etc/ssh/sshd_config.d/60-home-server-hardening.conf

ssh "${host}" sudo netplan generate
ssh "${host}" sudo sshd -t
ssh "${host}" sudo timedatectl set-timezone America/Toronto
ssh "${host}" sudo netplan apply
ssh "${host}" sudo systemctl reload ssh
