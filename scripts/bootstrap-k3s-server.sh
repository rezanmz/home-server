#!/usr/bin/env bash
set -euo pipefail

host="${1:-beelink}"
k3s_version="${K3S_VERSION:-v1.36.2+k3s1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="${repo_root}/infrastructure/k3s/server-config.yaml"

scp "${config}" "${host}:/tmp/home-server-k3s-server.yaml"
ssh "${host}" sudo install -D -m 0600 \
  /tmp/home-server-k3s-server.yaml /etc/rancher/k3s/config.yaml
ssh "${host}" rm -f /tmp/home-server-k3s-server.yaml
ssh "${host}" \
  "curl -sfL https://get.k3s.io | sudo INSTALL_K3S_VERSION='${k3s_version}' INSTALL_K3S_EXEC=server sh -"

ssh "${host}" sudo k3s kubectl wait --for=condition=Ready node/beelink --timeout=180s
