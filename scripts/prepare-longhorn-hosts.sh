#!/usr/bin/env bash
set -euo pipefail

hosts=("$@")
if [[ ${#hosts[@]} -eq 0 ]]; then
  hosts=(beelink pi)
fi

for host in "${hosts[@]}"; do
  ssh "${host}" \
    'sudo DEBIAN_FRONTEND=noninteractive apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y open-iscsi nfs-common cryptsetup dmsetup
sudo systemctl enable --now iscsid
sudo systemctl disable --now multipathd.service multipathd.socket 2>/dev/null || true'
done
