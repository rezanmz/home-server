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

hosts=("$@")
if [[ ${#hosts[@]} -eq 0 ]]; then
  hosts=(beelink pi)
fi

for host in "${hosts[@]}"; do
  if [[ ! "${host}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    printf 'invalid SSH alias: %s\n' "${host}" >&2
    exit 2
  fi

  ssh "${ssh_options[@]}" "${host}" \
    'set -euo pipefail
sudo -n DEBIAN_FRONTEND=noninteractive apt-get update
sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y open-iscsi nfs-common cryptsetup dmsetup
sudo -n systemctl enable --now iscsid

if ! multipath_maps="$(sudo -n env LC_ALL=C dmsetup ls --target multipath)"; then
  printf "%s\n" "Refusing to stop multipathd: active-map inspection failed." >&2
  exit 1
fi
multipath_maps="$(printf "%s\n" "${multipath_maps}" |
  sed -e "/^[[:space:]]*No devices found[[:space:]]*$/d" \
    -e "/^[[:space:]]*$/d")"
if [[ -n "${multipath_maps}" ]]; then
  printf "%s\n" "Refusing to stop multipathd while active multipath maps exist:" >&2
  printf "%s\n" "${multipath_maps}" >&2
  exit 1
fi
sudo -n systemctl disable --now multipathd.service multipathd.socket 2>/dev/null || true

systemctl is-active --quiet iscsid
for unit in multipathd.service multipathd.socket; do
  enabled_state="$(systemctl is-enabled "${unit}" 2>/dev/null || true)"
  if systemctl is-active --quiet "${unit}"; then
    printf "%s is still active\n" "${unit}" >&2
    exit 1
  fi
  case "${enabled_state}" in
  enabled | enabled-runtime | linked | linked-runtime)
    printf "%s still has unsafe enablement state %s\n" \
      "${unit}" "${enabled_state}" >&2
    exit 1
    ;;
  esac
done'
done
