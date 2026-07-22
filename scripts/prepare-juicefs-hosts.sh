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
source_apparmor="${repo_root}/infrastructure/hosts/common/juicefs-fusermount3"
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
  remote_apparmor="/tmp/juicefs-fusermount3"
  scp "${ssh_options[@]}" "${source_config}" "${host}:${remote_config}"
  scp "${ssh_options[@]}" "${source_apparmor}" "${host}:${remote_apparmor}"
  ssh "${ssh_options[@]}" "${host}" \
    'set -euo pipefail
test -c /dev/fuse
sudo -n install -m 0644 \
  /tmp/99-home-server-juicefs.conf \
  /etc/sysctl.d/99-home-server-juicefs.conf
sudo -n sysctl --load /etc/sysctl.d/99-home-server-juicefs.conf >/dev/null
test "$(sudo -n sysctl -n fs.inotify.max_user_instances)" = 1024
if [[ -f /etc/apparmor.d/fusermount3 ]] && sudo -n test -x /usr/sbin/apparmor_parser; then
  sudo -n install -m 0644 \
    /tmp/juicefs-fusermount3 \
    /etc/apparmor.d/local/fusermount3
  sudo -n /usr/sbin/apparmor_parser -r /etc/apparmor.d/fusermount3
fi
rm /tmp/99-home-server-juicefs.conf /tmp/juicefs-fusermount3
printf "%s\n" "JuiceFS host prerequisites verified."'
done
