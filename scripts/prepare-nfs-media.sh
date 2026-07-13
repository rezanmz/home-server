#!/usr/bin/env bash
set -euo pipefail

host="${1:-pi}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exports="${repo_root}/infrastructure/hosts/raspberrypi/home-server.exports"

scp "${exports}" "${host}:/tmp/home-server.exports"
ssh "${host}" \
  'set -eu
sudo DEBIAN_FRONTEND=noninteractive apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nfs-kernel-server
sudo install -d -m 0755 /etc/exports.d
sudo install -m 0644 /tmp/home-server.exports /etc/exports.d/home-server.exports
rm -f /tmp/home-server.exports
sudo exportfs -ra
sudo systemctl enable --now nfs-server'
