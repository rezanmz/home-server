#!/usr/bin/env bash
set -euo pipefail

server_host="${1:-beelink}"
agent_host="${2:-pi}"
k3s_version="${K3S_VERSION:-v1.36.2+k3s1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="${repo_root}/infrastructure/k3s/agent-pi-config.yaml"

scp "${config}" "${agent_host}:/tmp/home-server-k3s-agent.yaml"
ssh "${agent_host}" sudo install -D -m 0600 \
  /tmp/home-server-k3s-agent.yaml /etc/rancher/k3s/config.yaml
ssh "${agent_host}" rm -f /tmp/home-server-k3s-agent.yaml

# The join token never appears in process arguments or the repository.
ssh "${server_host}" sudo cat /var/lib/rancher/k3s/server/node-token \
  | ssh "${agent_host}" sudo install -D -m 0600 /dev/stdin /etc/rancher/k3s/node-token

ssh "${agent_host}" \
  "curl -sfL https://get.k3s.io | sudo INSTALL_K3S_VERSION='${k3s_version}' INSTALL_K3S_EXEC=agent sh -"

ssh "${server_host}" sudo k3s kubectl wait \
  --for=condition=Ready node/raspberrypi --timeout=180s
ssh "${server_host}" sudo k3s kubectl cordon raspberrypi
