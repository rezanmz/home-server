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

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_config="${repo_root}/infrastructure/hosts/common/99-home-server-juicefs.conf"
hosts=("$@")
if [[ ${#hosts[@]} -eq 0 ]]; then
  hosts=(beelink pi)
fi

for host in "${hosts[@]}"; do
  if [[ ! "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    printf 'invalid SSH alias: %s\n' "${host}" >&2
    exit 2
  fi

  remote_config="/tmp/99-home-server-juicefs.conf"
  scp "${ssh_options[@]}" "${source_config}" "${host}:${remote_config}"
  ssh "${ssh_options[@]}" "${host}" \
    'set -euo pipefail
test -c /dev/fuse
sudo -n install -m 0644 \
  /tmp/99-home-server-juicefs.conf \
  /etc/sysctl.d/99-home-server-juicefs.conf
sudo -n sysctl --load /etc/sysctl.d/99-home-server-juicefs.conf >/dev/null
test "$(sudo -n sysctl -n fs.inotify.max_user_instances)" = 1024
rm /tmp/99-home-server-juicefs.conf
printf "%s\n" "JuiceFS host prerequisites verified."'
done
