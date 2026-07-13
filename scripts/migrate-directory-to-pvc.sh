#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 || $# -gt 5 ]]; then
  echo "usage: $0 <namespace> <pvc> <absolute-source-path> [source-host] [cluster-host]" >&2
  exit 2
fi

namespace="$1"
pvc="$2"
source_path="$3"
source_host="${4:-pi}"
cluster_host="${5:-beelink}"

[[ "${namespace}" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || {
  echo "invalid namespace: ${namespace}" >&2
  exit 2
}
[[ "${pvc}" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || {
  echo "invalid PVC name: ${pvc}" >&2
  exit 2
}
[[ "${source_path}" =~ ^/[A-Za-z0-9._/-]+$ ]] || {
  echo "source path must be an absolute path without whitespace: ${source_path}" >&2
  exit 2
}

pod="pvc-migrate-${pvc:0:35}-$(date +%s)"

cleanup() {
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' delete pod '${pod}' --ignore-not-found --wait=false" \
    >/dev/null 2>&1 || true
}
trap cleanup EXIT

ssh "${source_host}" "sudo test -d '${source_path}'"
ssh "${cluster_host}" "sudo k3s kubectl -n '${namespace}' get pvc '${pvc}' >/dev/null"

render_pod() {
  cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${pod}
  namespace: ${namespace}
spec:
  restartPolicy: Never
  nodeSelector:
    kubernetes.io/hostname: beelink
  containers:
    - name: migrate
      image: alpine:3.22
      command: [sh, -c, "trap : TERM INT; sleep infinity & wait"]
      securityContext:
        runAsUser: 0
        runAsGroup: 0
      volumeMounts:
        - name: target
          mountPath: /data
  volumes:
    - name: target
      persistentVolumeClaim:
        claimName: ${pvc}
EOF
}

render_pod | ssh "${cluster_host}" "sudo k3s kubectl apply -f - >/dev/null"
ssh "${cluster_host}" \
  "sudo k3s kubectl -n '${namespace}' wait --for=condition=Ready 'pod/${pod}' --timeout=5m"

target_entries="$(ssh "${cluster_host}" \
  "sudo k3s kubectl -n '${namespace}' exec '${pod}' -- sh -c 'find /data -mindepth 1 -maxdepth 1 ! -name lost+found | wc -l'")"
if [[ "${target_entries}" != "0" ]]; then
  echo "refusing to copy into non-empty PVC ${namespace}/${pvc}" >&2
  exit 1
fi

ssh "${source_host}" "sudo tar --numeric-owner -C '${source_path}' -cpf - ." |
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' exec -i '${pod}' -- tar -C /data -xpf -"

source_files="$(ssh "${source_host}" \
  "sudo find '${source_path}' -xdev -type f | wc -l")"
target_files="$(ssh "${cluster_host}" \
  "sudo k3s kubectl -n '${namespace}' exec '${pod}' -- find /data -xdev -type f | wc -l")"

if [[ "${source_files}" != "${target_files}" ]]; then
  echo "file-count mismatch: source=${source_files}, target=${target_files}" >&2
  exit 1
fi

echo "copied ${source_files} files to ${namespace}/${pvc}"
