#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage: migrate-directory-to-pvc.sh <namespace> <pvc> <absolute-source-path> \
  --source-is-read-only-snapshot --target-controllers-are-suspended \
  [source-host] [cluster-host]

The source must be a consistency-safe snapshot mounted read-only. Every
controller that can mount the target, including its Flux ownership chain, must
be suspended. The script refuses a relevant HPA, an active controller/consumer,
or a non-empty PVC. Data is streamed over SSH; the source host directory is
never mounted into Kubernetes.
EOF
  exit 2
}

[[ $# -ge 5 && $# -le 7 ]] || usage

namespace="$1"
pvc="$2"
source_path="$3"
source_snapshot_ack="$4"
target_quiescence_ack="$5"
source_host="${6:-pi}"
cluster_host="${7:-beelink}"

[[ "${source_snapshot_ack}" == "--source-is-read-only-snapshot" ]] || {
  echo "refusing a mutable source: provide a consistency-safe read-only snapshot and pass --source-is-read-only-snapshot" >&2
  exit 2
}
[[ "${target_quiescence_ack}" == "--target-controllers-are-suspended" ]] || {
  echo "refusing an unlocked target: suspend every controller that can mount the PVC, then pass --target-controllers-are-suspended" >&2
  exit 2
}
[[ "${namespace}" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || {
  echo "invalid namespace: ${namespace}" >&2
  exit 2
}
[[ "${pvc}" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || {
  echo "invalid PVC name: ${pvc}" >&2
  exit 2
}
[[ "${source_path}" =~ ^/[A-Za-z0-9._/-]+$ && "${source_path}" != "/" ]] || {
  echo "source path must be a non-root absolute path without whitespace" >&2
  exit 2
}
[[ "${source_host}" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "invalid source SSH host: ${source_host}" >&2
  exit 2
}
[[ "${cluster_host}" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "invalid cluster SSH host: ${cluster_host}" >&2
  exit 2
}

for command in awk grep jq mktemp rm shasum sort ssh; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "required local command is not installed: ${command}" >&2
    exit 1
  }
done

# A deterministic name acts as a migration lock. A stale pod must be inspected
# and removed deliberately rather than silently replaced.
pod="pvc-migrate-${pvc:0:42}"
migration_image="busybox:1.37.0@sha256:9532d8c39891ca2ecde4d30d7710e01fb739c87a8b9299685c63704296b16028"
pod_created=false
copy_pid=""
monitor_pid=""
helper_pod_uid=""
target_pvc_uid=""
target_volume_name=""
quiescence_baseline_captured=false
baseline_consumer_uids=$'\n'
baseline_controller_uids=$'\n'
state_dir="$(mktemp -d)"
monitor_failure="${state_dir}/target-reactivated"
helper_release_marker="${state_dir}/helper-releasing"
helper_release_ack="${state_dir}/helper-release-acknowledged"

cleanup() {
  if [[ -n "${copy_pid}" ]] && kill -0 "${copy_pid}" 2>/dev/null; then
    kill "${copy_pid}" 2>/dev/null || true
    wait "${copy_pid}" 2>/dev/null || true
  fi
  if [[ -n "${monitor_pid}" ]]; then
    kill "${monitor_pid}" 2>/dev/null || true
    wait "${monitor_pid}" 2>/dev/null || true
  fi
  if [[ "${pod_created}" == true ]]; then
    ssh "${cluster_host}" \
      "sudo k3s kubectl -n '${namespace}' delete pod '${pod}' --ignore-not-found --wait=false" \
      >/dev/null 2>&1 || true
  fi
  rm -rf -- "${state_dir}"
}
trap cleanup EXIT

ssh "${source_host}" \
  "set -eu; sudo test -d '${source_path}'; sudo test ! -L '${source_path}'; sudo test -x /usr/bin/busybox; command -v python3 findmnt tar >/dev/null" || {
  echo "source must be a real directory and provide Python, findmnt, tar, and executable /usr/bin/busybox" >&2
  exit 1
}
ssh "${source_host}" \
  "options=\$(findmnt -n -o VFS-OPTIONS --target '${source_path}'); case \",\${options},\" in *,ro,*) exit 0 ;; *) exit 1 ;; esac" || {
  echo "source path is not on a read-only mount: ${source_host}:${source_path}" >&2
  exit 1
}
if ! target_pvc_uid="$(
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' get pvc '${pvc}' -o jsonpath='{.metadata.uid}'"
)" || [[ -z "${target_pvc_uid}" ]]; then
  echo "could not pin the target PVC identity" >&2
  exit 1
fi
if ! target_volume_name="$(
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' get pvc '${pvc}' -o jsonpath='{.spec.volumeName}'"
)"; then
  echo "could not inspect the target PVC binding" >&2
  exit 1
fi

# BusyBox tar does not preserve ACLs or extended attributes and cannot safely
# reproduce device nodes or sockets with this pod's capability set. Refuse such
# sources instead of claiming a complete migration after silently dropping
# metadata.
ssh "${source_host}" "sudo python3 - '${source_path}'" <<'PY'
import array
import errno
import fcntl
import os
import stat
import sys

root = os.path.abspath(sys.argv[1])
problems = []
seen_paths = set()
hard_links = {}

FS_IOC_GETFLAGS = 0x80086601
PRESERVATION_RELEVANT_INODE_FLAGS = (
    0x00000001  # secure deletion
    | 0x00000002  # undelete
    | 0x00000004  # compressed
    | 0x00000008  # synchronous updates
    | 0x00000010  # immutable
    | 0x00000020  # append only
    | 0x00000040  # no-dump
    | 0x00000080  # no-atime
    | 0x00000400  # do not compress
    | 0x00000800  # encrypted
    | 0x00004000  # journal data
    | 0x00008000  # no tail merging
    | 0x00010000  # synchronous directory updates
    | 0x00020000  # top of directory hierarchy
    | 0x00100000  # fs-verity
    | 0x00800000  # no copy-on-write
    | 0x20000000  # inherit project ID
    | 0x40000000  # casefolded directory
)

if os.path.realpath(root) != root:
    problems.append("source path or one of its parents traverses a symbolic link")

root_stat = os.lstat(root)
if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
    problems.append("source root must be a real directory, not a symbolic link")
root_device = root_stat.st_dev

if os.path.lexists(os.path.join(root, "lost+found")):
    problems.append(
        "top-level lost+found is reserved for the target filesystem and cannot be migrated"
    )


def inspect(path: str) -> None:
    if path in seen_paths:
        return
    seen_paths.add(path)
    info = os.lstat(path)
    mode = info.st_mode
    if info.st_dev != root_device:
        problems.append(f"nested filesystem is not supported: {path!r}")
    if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
        problems.append(f"unsupported file type: {path!r}")
    try:
        attrs = os.listxattr(path, follow_symlinks=False)
    except OSError as error:
        problems.append(f"cannot inspect extended attributes for {path!r}: {error}")
        attrs = []
    if attrs:
        problems.append(f"extended attributes/ACLs are not supported: {path!r}")
    if mode & (stat.S_ISUID | stat.S_ISGID):
        problems.append(f"set-user-ID/set-group-ID mode is not supported: {path!r}")
    if stat.S_ISREG(mode) or stat.S_ISDIR(mode):
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            flags = array.array("I", [0])
            try:
                fcntl.ioctl(descriptor, FS_IOC_GETFLAGS, flags, True)
            except OSError as error:
                if error.errno not in (errno.ENOTTY, errno.EOPNOTSUPP, errno.ENOSYS):
                    problems.append(f"cannot inspect inode flags for {path!r}: {error}")
            else:
                relevant_flags = flags[0] & PRESERVATION_RELEVANT_INODE_FLAGS
                if relevant_flags:
                    problems.append(
                        f"preservation-relevant inode flags are not supported: "
                        f"{path!r} (0x{relevant_flags:08x})"
                    )
        finally:
            os.close(descriptor)
    if stat.S_ISLNK(mode) and info.st_nlink != 1:
        problems.append(f"hard-linked symbolic link is not supported: {path!r}")
    if stat.S_ISREG(mode):
        hard_links.setdefault((info.st_dev, info.st_ino), [info.st_nlink, []])[1].append(path)
        if info.st_size > 0 and info.st_blocks * 512 < info.st_size:
            problems.append(f"sparse file allocation is not supported: {path!r}")


for current, directories, files in os.walk(root, followlinks=False):
    inspect(current)
    for name in directories + files:
        path = os.path.join(current, name)
        if path != current:
            inspect(path)

for expected, paths in hard_links.values():
    if expected != len(paths):
        problems.append(
            f"hard link escapes the source tree: {paths[0]!r} "
            f"({len(paths)} of {expected} links present)"
        )


def decode_mount_path(value: str) -> str:
    for escaped, decoded in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        value = value.replace(escaped, decoded)
    return value


with open("/proc/self/mountinfo", encoding="utf-8") as mountinfo:
    for line in mountinfo:
        fields = line.split()
        mount_point = decode_mount_path(fields[4])
        try:
            nested = mount_point != root and os.path.commonpath((root, mount_point)) == root
        except ValueError:
            nested = False
        if nested:
            problems.append(f"nested mount point is not supported: {mount_point!r}")

if problems:
    print("refusing source metadata that cannot be preserved:", file=sys.stderr)
    for problem in problems[:20]:
        print(f"  {problem}", file=sys.stderr)
    if len(problems) > 20:
        print(f"  ... and {len(problems) - 20} more", file=sys.stderr)
    raise SystemExit(1)
PY

# Probe every source tar option before the target is populated.
ssh "${source_host}" \
  "sudo tar --numeric-owner --one-file-system --exclude='./lost+found' -C '${source_path}' -cpf /dev/null --files-from /dev/null"

if ssh "${cluster_host}" \
  "sudo k3s kubectl -n '${namespace}' get pod '${pod}' >/dev/null 2>&1"; then
  echo "migration lock pod already exists: ${namespace}/${pod}" >&2
  exit 1
fi

cluster_inventory() {
  ssh "${cluster_host}" \
    "sudo k3s kubectl get pods,persistentvolumeclaims,replicationcontrollers,deployments.apps,statefulsets.apps,daemonsets.apps,replicasets.apps,jobs.batch,cronjobs.batch,horizontalpodautoscalers.autoscaling,kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io --all-namespaces -o json"
}

pvc_controllers() {
  jq -c --arg namespace "${namespace}" --arg claim "${pvc}" '
      def podspec:
        if .kind == "CronJob" then .spec.jobTemplate.spec.template.spec
        else .spec.template.spec
        end;
      def references($name):
        . as $controller
        | (podspec | any(.volumes[]?; .persistentVolumeClaim.claimName == $name)) or
          (
            .kind == "StatefulSet" and
            any(.spec.volumeClaimTemplates[]?;
              (.metadata.name + "-" + $controller.metadata.name + "-") as $prefix
              | ($name | startswith($prefix)) and
                (($name | ltrimstr($prefix)) | test("^[0-9]+$"))
            )
          );
      def terminal_job:
        any(.status.conditions[]?;
          ((.type == "Complete" or .type == "Failed") and .status == "True"));
      def dormant:
        if (
          .kind == "ReplicationController" or
          .kind == "Deployment" or
          .kind == "StatefulSet" or
          .kind == "ReplicaSet"
        )
        then ((.spec.replicas // 1) == 0)
        elif .kind == "CronJob" then (.spec.suspend == true)
        elif .kind == "Job" then (.spec.suspend == true or terminal_job)
        else false
        end;
      [.items[]
      | select(.metadata.namespace == $namespace)
      | select(
          .kind == "Deployment" or
          .kind == "ReplicationController" or
          .kind == "StatefulSet" or
          .kind == "DaemonSet" or
          .kind == "ReplicaSet" or
          .kind == "Job" or
          .kind == "CronJob"
        )
      | select(references($claim))
      | {
          apiVersion,
          kind,
          metadata: {
            namespace: .metadata.namespace,
            name: .metadata.name,
            uid: .metadata.uid,
            labels: (.metadata.labels // {})
          },
          dormant: dormant
        }]
    '
}

direct_gitops_owners() {
  jq -r '
    def owner($kind; $name_label; $namespace_label):
      select(.metadata.labels[$name_label]? != null)
      | [
          $kind,
          (.metadata.labels[$namespace_label] // .metadata.namespace),
          .metadata.labels[$name_label]
        ]
      | @tsv;
    owner(
      "Kustomization";
      "kustomize.toolkit.fluxcd.io/name";
      "kustomize.toolkit.fluxcd.io/namespace"
    ),
    owner(
      "HelmRelease";
      "helm.toolkit.fluxcd.io/name";
      "helm.toolkit.fluxcd.io/namespace"
    )
  '
}

inventory_gitops_owners() {
  local resource_inventory_id="$1"
  jq -r --arg inventory_id "${resource_inventory_id}" '
    .items[]
    | select(.kind == "Kustomization")
    | select(any(.status.inventory.entries[]?; .id == $inventory_id))
    | ["Kustomization", .metadata.namespace, .metadata.name]
    | @tsv
  '
}

resource_inventory_id() {
  jq -er '
    (.apiVersion |
      if contains("/") then split("/")[0] else "" end
    ) as $group
    | "\(.metadata.namespace)_\(.metadata.name)_\($group)_\(.kind)"
  '
}

gitops_seen=$'\n'
gitops_problems=()

check_gitops_owner() {
  local inventory="$1"
  local kind="$2"
  local owner_namespace="$3"
  local name="$4"
  local key object suspend direct_owners owner_inventory_id inventory_owners

  key="${kind}/${owner_namespace}/${name}"
  if grep -Fqx -- "${key}" <<<"${gitops_seen}"; then
    return 0
  fi
  gitops_seen+="${key}"$'\n'

  if ! object="$(
    jq -c \
      --arg kind "${kind}" \
      --arg namespace "${owner_namespace}" \
      --arg name "${name}" \
      '.items[] | select(
        .kind == $kind and
        .metadata.namespace == $namespace and
        .metadata.name == $name
      )' <<<"${inventory}"
  )"; then
    echo "could not parse GitOps owner inventory while checking ${key}" >&2
    return 1
  fi
  if [[ -z "${object}" ]]; then
    gitops_problems+=("${key} is referenced as an owner but was not found")
    return 0
  fi

  if ! suspend="$(jq -r '.spec.suspend // false' <<<"${object}")"; then
    echo "could not parse suspend state for ${key}" >&2
    return 1
  fi
  if [[ "${suspend}" != "true" ]]; then
    gitops_problems+=("${key} is not suspended")
  fi

  if ! direct_owners="$(direct_gitops_owners <<<"${object}")"; then
    echo "could not parse direct GitOps owners for ${key}" >&2
    return 1
  fi
  while IFS=$'\t' read -r parent_kind parent_namespace parent_name; do
    [[ -n "${parent_kind}" ]] || continue
    if ! check_gitops_owner \
      "${inventory}" "${parent_kind}" "${parent_namespace}" "${parent_name}"; then
      return 1
    fi
  done <<<"${direct_owners}"

  if ! owner_inventory_id="$(resource_inventory_id <<<"${object}")"; then
    echo "could not construct Flux inventory ID for ${key}" >&2
    return 1
  fi
  if ! inventory_owners="$(
    inventory_gitops_owners "${owner_inventory_id}" <<<"${inventory}"
  )"; then
    echo "could not search Flux inventory ownership for ${key}" >&2
    return 1
  fi
  while IFS=$'\t' read -r parent_kind parent_namespace parent_name; do
    [[ -n "${parent_kind}" ]] || continue
    if ! check_gitops_owner \
      "${inventory}" "${parent_kind}" "${parent_namespace}" "${parent_name}"; then
      return 1
    fi
  done <<<"${inventory_owners}"
  return 0
}

ensure_target_quiesced() {
  local inventory controllers consumers hpas controller_json pvc_object consumer_json
  local direct_owners controller_ids managed_ids inventory_owners new_objects
  local controller_rows consumer_rows controller_objects
  local pvc_state helper_object helper_state releasing
  if ! inventory="$(cluster_inventory)"; then
    echo "could not inspect cluster state; refusing to continue without a quiescence proof" >&2
    return 1
  fi
  if ! controller_json="$(pvc_controllers <<<"${inventory}")"; then
    echo "could not identify PVC-owning controllers; refusing to continue" >&2
    return 1
  fi
  if ! pvc_object="$(
    jq -c \
      --arg namespace "${namespace}" \
      --arg claim "${pvc}" '
        .items[]
        | select(
            .kind == "PersistentVolumeClaim" and
            .metadata.namespace == $namespace and
            .metadata.name == $claim
          )
      ' <<<"${inventory}"
  )"; then
    echo "could not parse the target PVC object; refusing to continue" >&2
    return 1
  fi
  if [[ -z "${pvc_object}" ]]; then
    echo "target PVC disappeared during quiescence proof" >&2
    return 1
  fi
  if ! pvc_state="$(
    jq -r \
      --arg uid "${target_pvc_uid}" \
      --arg volume "${target_volume_name}" '
        if .metadata.uid != $uid then "UID changed"
        elif .metadata.deletionTimestamp != null then "deletion is pending"
        elif $volume != "" and (
          .spec.volumeName != $volume or .status.phase != "Bound"
        ) then "bound volume or phase changed"
        elif $volume == "" and (
          .status.phase != "Pending" and .status.phase != "Bound"
        ) then "unexpected phase: \(.status.phase // "Unknown")"
        else "ok"
        end
      ' <<<"${pvc_object}"
  )"; then
    echo "could not validate target PVC identity; refusing to continue" >&2
    return 1
  fi
  if [[ "${pvc_state}" != "ok" ]]; then
    echo "target PVC ${namespace}/${pvc} identity/lifecycle check failed: ${pvc_state}" >&2
    return 1
  fi

  if [[ -n "${helper_pod_uid}" ]]; then
    if ! helper_object="$(
      jq -c \
        --arg namespace "${namespace}" \
        --arg name "${pod}" '
          .items[]
          | select(
              .kind == "Pod" and
              .metadata.namespace == $namespace and
              .metadata.name == $name
            )
        ' <<<"${inventory}"
    )"; then
      echo "could not parse the pinned helper pod; refusing to continue" >&2
      return 1
    fi
    releasing=false
    [[ -e "${helper_release_marker}" ]] && releasing=true
    if [[ -z "${helper_object}" ]]; then
      if [[ "${releasing}" != true ]]; then
        echo "pinned migration helper pod disappeared" >&2
        return 1
      fi
    else
      if ! helper_state="$(
        jq -r \
          --arg uid "${helper_pod_uid}" \
          --arg image "${migration_image}" \
          --arg claim "${pvc}" \
          --arg releasing "${releasing}" '
            if .metadata.uid != $uid then "UID changed"
            elif (.spec.containers | length) != 1 then "container set changed"
            elif ((.spec.initContainers // []) | length) != 0 then "init container injected"
            elif ((.spec.ephemeralContainers // []) | length) != 0
              then "ephemeral container injected"
            elif .spec.containers[0].name != "migrate" then "container name changed"
            elif .spec.containers[0].image != $image then "image changed"
            elif (any(.spec.containers[0].volumeMounts[]?;
              .name == "target" and .mountPath == "/target" and (.readOnly // false) == false
            ) | not) then "target mount changed"
            elif .spec.automountServiceAccountToken != false then "service-account token enabled"
            elif (any(.spec.volumes[]?; .persistentVolumeClaim.claimName == $claim) | not)
              then "target claim changed"
            elif $releasing != "true" and .metadata.deletionTimestamp != null
              then "unexpected deletion"
            elif $releasing != "true" and .status.phase != "Running"
              then "unexpected phase: \(.status.phase // "Unknown")"
            elif $releasing != "true" and (
              any(.status.conditions[]?; .type == "Ready" and .status == "True") | not
            ) then "not Ready"
            else "ok"
            end
          ' <<<"${helper_object}"
      )"; then
        echo "could not validate the pinned helper pod; refusing to continue" >&2
        return 1
      fi
      if [[ "${helper_state}" != "ok" ]]; then
        echo "migration helper identity/spec check failed: ${helper_state}" >&2
        return 1
      fi
    fi
  fi

  if ! controllers="$(
    jq -r '.[] | select(.dormant | not) | "\(.kind)/\(.metadata.name)"' \
      <<<"${controller_json}"
  )"; then
    echo "could not parse controller state; refusing to continue" >&2
    return 1
  fi
  if [[ -n "${controllers}" ]]; then
    echo "refusing PVC ${namespace}/${pvc}; suspend these owning controllers:" >&2
    while IFS= read -r controller; do
      printf '  %s\n' "${controller}" >&2
    done <<<"${controllers}"
    return 1
  fi

  if [[ "${quiescence_baseline_captured}" == true ]]; then
    new_objects=""
    if ! controller_rows="$(
      jq -r '.[] | [.metadata.uid, .kind, .metadata.name] | @tsv' \
        <<<"${controller_json}"
    )"; then
      echo "could not compare the controller baseline; refusing to continue" >&2
      return 1
    fi
    while IFS=$'\t' read -r object_uid object_kind object_name; do
      [[ -n "${object_uid}" ]] || continue
      if ! grep -Fqx -- "${object_uid}" <<<"${baseline_controller_uids}"; then
        new_objects+="${object_kind}/${object_name} (${object_uid})"$'\n'
      fi
    done <<<"${controller_rows}"
    if [[ -n "${new_objects}" ]]; then
      echo "refusing PVC ${namespace}/${pvc}; new PVC controllers appeared after the baseline:" >&2
      printf '  %s\n' "${new_objects%$'\n'}" >&2
      return 1
    fi
  fi

  if ! consumer_json="$(
    jq -c \
      --arg namespace "${namespace}" \
      --arg claim "${pvc}" \
      --arg migration_uid "${helper_pod_uid}" '
        [.items[]
        | select(.kind == "Pod" and .metadata.namespace == $namespace)
        | select($migration_uid == "" or .metadata.uid != $migration_uid)
        | select(any(.spec.volumes[]?; .persistentVolumeClaim.claimName == $claim))
        | {
            uid: .metadata.uid,
            name: .metadata.name,
            phase: (.status.phase // "Unknown")
          }]
      ' <<<"${inventory}"
  )"; then
    echo "could not parse PVC consumers; refusing to continue" >&2
    return 1
  fi
  if ! consumers="$(
    jq -r '
      .[]
      | select(.phase != "Succeeded" and .phase != "Failed")
      | .name
    ' <<<"${consumer_json}"
  )"; then
    echo "could not parse active PVC consumers; refusing to continue" >&2
    return 1
  fi
  if [[ -n "${consumers}" ]]; then
    echo "refusing mounted PVC ${namespace}/${pvc}; active consumer pods:" >&2
    while IFS= read -r consumer; do
      printf '  %s\n' "${consumer}" >&2
    done <<<"${consumers}"
    return 1
  fi
  if [[ "${quiescence_baseline_captured}" == true ]]; then
    new_objects=""
    if ! consumer_rows="$(
      jq -r '.[] | [.uid, .phase, .name] | @tsv' <<<"${consumer_json}"
    )"; then
      echo "could not compare the consumer baseline; refusing to continue" >&2
      return 1
    fi
    while IFS=$'\t' read -r object_uid object_phase object_name; do
      [[ -n "${object_uid}" ]] || continue
      if ! grep -Fqx -- "${object_uid}" <<<"${baseline_consumer_uids}"; then
        new_objects+="Pod/${object_name} phase=${object_phase} (${object_uid})"$'\n'
      fi
    done <<<"${consumer_rows}"
    if [[ -n "${new_objects}" ]]; then
      echo "refusing PVC ${namespace}/${pvc}; new consumer pods appeared after the baseline:" >&2
      printf '  %s\n' "${new_objects%$'\n'}" >&2
      return 1
    fi
  fi

  if ! hpas="$(
    jq -r --arg namespace "${namespace}" --argjson controllers "${controller_json}" '
      .items[]
      | select(
          .kind == "HorizontalPodAutoscaler" and
          .metadata.namespace == $namespace
        ) as $hpa
      | select(
          any($controllers[];
            .kind == $hpa.spec.scaleTargetRef.kind and
            .metadata.name == $hpa.spec.scaleTargetRef.name
          )
        )
      | $hpa
      | "HorizontalPodAutoscaler/\(.metadata.name) -> \(.spec.scaleTargetRef.kind)/\(.spec.scaleTargetRef.name)"
    ' <<<"${inventory}"
  )"; then
    echo "could not parse HPA state; refusing to continue" >&2
    return 1
  fi
  if [[ -n "${hpas}" ]]; then
    echo "refusing PVC ${namespace}/${pvc}; remove these autoscalers before migration:" >&2
    while IFS= read -r hpa; do
      printf '  %s\n' "${hpa}" >&2
    done <<<"${hpas}"
    return 1
  fi

  gitops_seen=$'\n'
  gitops_problems=()
  if ! controller_objects="$(jq -c '.[]' <<<"${controller_json}")"; then
    echo "could not serialize PVC controllers; refusing to continue" >&2
    return 1
  fi
  if ! direct_owners="$(
    {
      printf '%s\n' "${controller_objects}"
      printf '%s\n' "${pvc_object}"
    } |
      direct_gitops_owners |
      sort -u
  )"; then
    echo "could not identify direct GitOps owners; refusing to continue" >&2
    return 1
  fi
  while IFS=$'\t' read -r owner_kind owner_namespace owner_name; do
    [[ -n "${owner_kind}" ]] || continue
    if ! check_gitops_owner \
      "${inventory}" "${owner_kind}" "${owner_namespace}" "${owner_name}"; then
      return 1
    fi
  done <<<"${direct_owners}"

  if ! controller_ids="$(
    jq -r '
      .[]
      | (.apiVersion |
          if contains("/") then split("/")[0] else "" end
        ) as $group
      | "\(.metadata.namespace)_\(.metadata.name)_\($group)_\(.kind)"
    ' <<<"${controller_json}"
  )"; then
    echo "could not construct controller inventory IDs; refusing to continue" >&2
    return 1
  fi
  if ! managed_ids="$(
    printf '%s\n%s_%s__PersistentVolumeClaim\n' \
      "${controller_ids}" "${namespace}" "${pvc}" |
      sort -u
  )"; then
    echo "could not construct the Flux ownership set; refusing to continue" >&2
    return 1
  fi
  while IFS= read -r managed_id; do
    [[ -n "${managed_id}" ]] || continue
    if ! inventory_owners="$(
      inventory_gitops_owners "${managed_id}" <<<"${inventory}"
    )"; then
      echo "could not search Flux inventory ownership; refusing to continue" >&2
      return 1
    fi
    while IFS=$'\t' read -r owner_kind owner_namespace owner_name; do
      [[ -n "${owner_kind}" ]] || continue
      if ! check_gitops_owner \
        "${inventory}" "${owner_kind}" "${owner_namespace}" "${owner_name}"; then
        return 1
      fi
    done <<<"${inventory_owners}"
  done <<<"${managed_ids}"
  if ((${#gitops_problems[@]} > 0)); then
    echo "refusing PVC ${namespace}/${pvc}; suspend the complete GitOps ownership chain:" >&2
    printf '  %s\n' "${gitops_problems[@]}" >&2
    return 1
  fi
  if [[ "${quiescence_baseline_captured}" == false ]]; then
    if ! controller_rows="$(jq -r '.[].metadata.uid' <<<"${controller_json}")"; then
      echo "could not serialize the controller baseline; refusing to continue" >&2
      return 1
    fi
    if ! baseline_controller_uids="$(
      {
        printf '\n'
        printf '%s\n' "${controller_rows}"
      } | sort -u
    )"; then
      echo "could not capture the controller baseline; refusing to continue" >&2
      return 1
    fi
    if ! consumer_rows="$(jq -r '.[].uid' <<<"${consumer_json}")"; then
      echo "could not serialize the consumer baseline; refusing to continue" >&2
      return 1
    fi
    if ! baseline_consumer_uids="$(
      {
        printf '\n'
        printf '%s\n' "${consumer_rows}"
      } | sort -u
    )"; then
      echo "could not capture the consumer baseline; refusing to continue" >&2
      return 1
    fi
    quiescence_baseline_captured=true
  fi
  return 0
}

ensure_target_quiesced || exit 1

render_pod() {
  cat <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${pod}
  namespace: ${namespace}
spec:
  restartPolicy: Never
  terminationGracePeriodSeconds: 1
  automountServiceAccountToken: false
  securityContext:
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: migrate
      image: ${migration_image}
      imagePullPolicy: IfNotPresent
      command: [sh, -ec]
      args:
        - "trap : TERM INT; sleep 2147483647 & wait"
      securityContext:
        runAsUser: 0
        runAsGroup: 0
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: [ALL]
          add: [CHOWN, DAC_OVERRIDE, FOWNER]
      resources:
        requests: {cpu: 25m, memory: 32Mi}
        limits: {cpu: "1", memory: 256Mi}
      volumeMounts:
        - {name: target, mountPath: /target}
        - {name: tmp, mountPath: /tmp}
  volumes:
    - name: target
      persistentVolumeClaim:
        claimName: ${pvc}
    - {name: tmp, emptyDir: {}}
EOF
}

render_pod | ssh "${cluster_host}" \
  "sudo k3s kubectl create -f - >/dev/null"
pod_created=true
if ! helper_pod_uid="$(
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' get pod '${pod}' -o jsonpath='{.metadata.uid}'"
)" || [[ -z "${helper_pod_uid}" ]]; then
  echo "could not pin the migration helper pod identity" >&2
  exit 1
fi
ssh "${cluster_host}" \
  "sudo k3s kubectl -n '${namespace}' wait --for=condition=Ready 'pod/${pod}' --timeout=5m"
if ! bound_volume="$(
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' get pvc '${pvc}' -o jsonpath='{.spec.volumeName}'"
)" || [[ -z "${bound_volume}" ]]; then
  echo "target PVC did not bind after the helper pod became Ready" >&2
  exit 1
fi
if [[ -n "${target_volume_name}" && "${target_volume_name}" != "${bound_volume}" ]]; then
  echo "target PVC binding changed before migration" >&2
  exit 1
fi
target_volume_name="${bound_volume}"

validate_target_lost_found() {
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' exec '${pod}' -- sh -ec '
      set -o pipefail
      if [ -L /target/lost+found ]; then
        echo \"target lost+found must not be a symbolic link\" >&2
        exit 1
      fi
      if [ -e /target/lost+found ] && [ ! -d /target/lost+found ]; then
        echo \"target lost+found must be a directory\" >&2
        exit 1
      fi
      if [ -d /target/lost+found ]; then
        entries=\$(find /target/lost+found -mindepth 1 -print | wc -l) || exit 1
        if [ \"\${entries}\" -ne 0 ]; then
          echo \"target lost+found must be empty\" >&2
          exit 1
        fi
      fi
    '"
}

validate_empty_target() {
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' exec '${pod}' -- sh -ec '
      set -o pipefail
      entries=\$(find /target -mindepth 1 -maxdepth 1 ! -name lost+found -print | wc -l) || exit 1
      [ \"\${entries}\" -eq 0 ]
    '"
}

probe_target_tools() {
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' exec '${pod}' -- sh -ec '
      set -o pipefail
      bb=/bin/busybox
      \"\${bb}\" printf probe >/tmp/probe
      \"\${bb}\" sha256sum /tmp/probe >/dev/null
      # BusyBox 1.37 implements a global sync and ignores GNU coreutils'
      # path-scoped -f form. Exercise the exact operation used below.
      \"\${bb}\" sync
      \"\${bb}\" ln -s probe /tmp/probe-link
      [ \"\$(\"\${bb}\" readlink /tmp/probe-link)\" = probe ]
      \"\${bb}\" chown -h 1234:2345 /tmp/probe-link
      [ \"\$(\"\${bb}\" stat -c %u:%g /tmp/probe-link)\" = 1234:2345 ]
      \"\${bb}\" find /tmp -type f -print0 |
        \"\${bb}\" sort -z |
        \"\${bb}\" xargs -0 -r \"\${bb}\" stat -c %s >/dev/null
      \"\${bb}\" mkdir /tmp/archive /tmp/extracted
      \"\${bb}\" cp /tmp/probe /tmp/archive/probe
      \"\${bb}\" tar -C /tmp/archive -cpf /tmp/probe.tar .
      \"\${bb}\" tar --numeric-owner -C /tmp/extracted -xpf /tmp/probe.tar
      [ \"\$(\"\${bb}\" cat /tmp/extracted/probe)\" = probe ]
      \"\${bb}\" rm -rf /tmp/probe /tmp/probe-link /tmp/probe.tar /tmp/archive /tmp/extracted
    '"
}

source_file_count() {
  ssh "${source_host}" \
    "sudo /usr/bin/busybox sh -es -- '${source_path}' /usr/bin/busybox" <<'SH'
set -o pipefail
root="$1"
bb="$2"
cd "${root}"
"${bb}" find . -xdev -path ./lost+found -prune -o -type f -print0 |
  (
    count=0
    while IFS= read -r -d '' _; do
      count=$((count + 1))
    done
    "${bb}" printf '%s\n' "${count}"
  )
SH
}

target_file_count() {
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' exec -i '${pod}' -- /bin/busybox sh -es -- /target /bin/busybox" <<'SH'
set -o pipefail
root="$1"
bb="$2"
cd "${root}"
"${bb}" find . -xdev -path ./lost+found -prune -o -type f -print0 |
  (
    count=0
    while IFS= read -r -d '' _; do
      count=$((count + 1))
    done
    "${bb}" printf '%s\n' "${count}"
  )
SH
}

# Only aggregate hashes cross into local variables; paths and contents are never
# logged. Both endpoints use BusyBox so unusual file names have identical
# sha256sum escaping semantics.
source_content_digest() {
  ssh "${source_host}" \
    "sudo /usr/bin/busybox sh -es -- '${source_path}' /usr/bin/busybox" <<'SH' |
set -o pipefail
root="$1"
bb="$2"
cd "${root}"
"${bb}" find . -xdev -path ./lost+found -prune -o -type f -print0 |
  "${bb}" sort -z |
  "${bb}" xargs -0 -r "${bb}" sha256sum
SH
    shasum -a 256 | awk '{print $1}'
}

target_content_digest() {
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' exec -i '${pod}' -- /bin/busybox sh -es -- /target /bin/busybox" <<'SH' |
set -o pipefail
root="$1"
bb="$2"
cd "${root}"
"${bb}" find . -xdev -path ./lost+found -prune -o -type f -print0 |
  "${bb}" sort -z |
  "${bb}" xargs -0 -r "${bb}" sha256sum
SH
    shasum -a 256 | awk '{print $1}'
}

source_metadata_digest() {
  ssh "${source_host}" \
    "sudo /usr/bin/busybox sh -es -- '${source_path}' /usr/bin/busybox" <<'SH' |
set -o pipefail
root="$1"
bb="$2"
cd "${root}"
"${bb}" find . -xdev -path ./lost+found -prune -o -print0 |
  "${bb}" sort -z |
  while IFS= read -r -d '' item; do
    metadata="$("${bb}" stat -c '%f|%u|%g' "${item}")"
    links="-"
    if [ ! -L "${item}" ] && [ -f "${item}" ]; then
      links="$("${bb}" stat -c '%h' "${item}")"
    fi
    metadata="${metadata}|${links}"
    target=""
    if [ -L "${item}" ]; then
      target="$("${bb}" readlink "${item}")"
    fi
    "${bb}" printf '%s\0%s\0%s\0' "${item}" "${metadata}" "${target}"
  done
SH
    shasum -a 256 | awk '{print $1}'
}

target_metadata_digest() {
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' exec -i '${pod}' -- /bin/busybox sh -es -- /target /bin/busybox" <<'SH' |
set -o pipefail
root="$1"
bb="$2"
cd "${root}"
"${bb}" find . -xdev -path ./lost+found -prune -o -print0 |
  "${bb}" sort -z |
  while IFS= read -r -d '' item; do
    metadata="$("${bb}" stat -c '%f|%u|%g' "${item}")"
    links="-"
    if [ ! -L "${item}" ] && [ -f "${item}" ]; then
      links="$("${bb}" stat -c '%h' "${item}")"
    fi
    metadata="${metadata}|${links}"
    target=""
    if [ -L "${item}" ]; then
      target="$("${bb}" readlink "${item}")"
    fi
    "${bb}" printf '%s\0%s\0%s\0' "${item}" "${metadata}" "${target}"
  done
SH
    shasum -a 256 | awk '{print $1}'
}

sync_target() {
  # The pinned BusyBox provides global sync(2), not path-scoped syncfs(2).
  # A successful global flush is broader but still establishes the durability
  # barrier required before verification and before the helper releases the PVC.
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' exec '${pod}' -- /bin/busybox sync"
}

# BusyBox tar preserves numeric ownership for files and directories but creates
# symbolic links as root. Restore link ownership explicitly because it affects
# sticky-directory and protected-symlink checks on Linux.
restore_symlink_ownership() {
  ssh "${source_host}" \
    "sudo /usr/bin/busybox sh -es -- '${source_path}' /usr/bin/busybox" <<'SH' |
set -o pipefail
root="$1"
bb="$2"
cd "${root}"
"${bb}" find . -xdev -path ./lost+found -prune -o -type l -print0 |
  while IFS= read -r -d '' item; do
    uid="$("${bb}" stat -c %u "${item}")"
    gid="$("${bb}" stat -c %g "${item}")"
    "${bb}" printf '%s\0%s\0%s\0' "${item}" "${uid}" "${gid}"
  done
SH
    ssh "${cluster_host}" \
      "sudo k3s kubectl -n '${namespace}' exec -i '${pod}' -- /bin/busybox sh -ec '
        set -o pipefail
        bb=/bin/busybox
        cd /target
        while IFS= read -r -d \"\" item; do
          IFS= read -r -d \"\" uid
          IFS= read -r -d \"\" gid
          case \"\${item}\" in ./*) ;; *) exit 1 ;; esac
          case \"\${uid}:\${gid}\" in
            *[!0-9:]*|:*|*:) exit 1 ;;
          esac
          \"\${bb}\" chown -h \"\${uid}:\${gid}\" \"\${item}\"
        done
      '"
}

start_target_monitor() {
  (
    while sleep 2; do
      if ! ensure_target_quiesced; then
        printf 'target quiescence proof failed\n' >"${monitor_failure}"
        exit 1
      fi
      if [[ -e "${helper_release_marker}" ]]; then
        : >"${helper_release_ack}"
      fi
    done
  ) &
  monitor_pid="$!"
}

target_monitor_healthy() {
  if [[ -e "${monitor_failure}" ]]; then
    echo "target quiescence failed during migration; ${namespace}/${pvc} is not verified" >&2
    return 1
  fi
  if [[ -z "${monitor_pid}" ]] || ! kill -0 "${monitor_pid}" 2>/dev/null; then
    echo "target quiescence monitor stopped unexpectedly; refusing verification" >&2
    return 1
  fi
  return 0
}

stop_target_monitor() {
  if ! ensure_target_quiesced; then
    printf 'final target quiescence proof failed\n' >"${monitor_failure}"
  fi
  if ! target_monitor_healthy; then
    return 1
  fi
  kill "${monitor_pid}" 2>/dev/null || true
  wait "${monitor_pid}" 2>/dev/null || true
  monitor_pid=""
  if ! ensure_target_quiesced || [[ -e "${monitor_failure}" ]]; then
    echo "target was not continuously quiescent through verification" >&2
    return 1
  fi
  return 0
}

validate_target_lost_found || exit 1
if ! validate_empty_target; then
  echo "refusing to copy into non-empty PVC ${namespace}/${pvc}" >&2
  exit 1
fi
probe_target_tools || {
  echo "pinned migration image lacks a required verification operation" >&2
  exit 1
}

# Establish a verified before-image. This also exercises every source-side
# post-copy dependency before the PVC can be modified.
if ! source_files_before="$(source_file_count)" ||
   ! source_digest_before="$(source_content_digest)" ||
   ! source_metadata_before="$(source_metadata_digest)"; then
  echo "could not fingerprint the read-only source snapshot" >&2
  exit 1
fi

# Kubernetes has no generic admission lock that prevents an arbitrary custom
# controller from mounting an RWO volume on the same node. The explicit target
# acknowledgement remains required; this fail-closed monitor covers built-ins,
# HPAs, Flux/Helm ownership, and all active consumer pods through verification.
ensure_target_quiesced || exit 1
start_target_monitor

ssh "${source_host}" \
  "sudo tar --numeric-owner --one-file-system --exclude='./lost+found' -C '${source_path}' -cpf - ." |
  ssh "${cluster_host}" \
    "sudo k3s kubectl -n '${namespace}' exec -i '${pod}' -- \
     /bin/busybox tar --numeric-owner -C /target -xpf -" &
copy_pid="$!"
copy_failed=false
while kill -0 "${copy_pid}" 2>/dev/null; do
  if ! target_monitor_healthy; then
    kill "${copy_pid}" 2>/dev/null || true
    break
  fi
  sleep 1
done
if ! wait "${copy_pid}"; then
  copy_failed=true
fi
copy_pid=""
if [[ "${copy_failed}" == true ]]; then
  echo "copy failed; ${namespace}/${pvc} contains a partial stream and must be cleared before retrying" >&2
  exit 1
fi
target_monitor_healthy || exit 1
if ! restore_symlink_ownership; then
  echo "could not restore symbolic-link ownership; ${namespace}/${pvc} is not verified" >&2
  exit 1
fi
target_monitor_healthy || exit 1
if ! sync_target; then
  echo "target filesystem flush failed; ${namespace}/${pvc} is not durable or verified" >&2
  exit 1
fi
target_monitor_healthy || exit 1
validate_target_lost_found || exit 1

if ! target_files="$(target_file_count)"; then
  echo "could not count target files" >&2
  exit 1
fi
target_monitor_healthy || exit 1
if ! target_digest_first="$(target_content_digest)"; then
  echo "could not hash target files" >&2
  exit 1
fi
target_monitor_healthy || exit 1
if ! target_metadata="$(target_metadata_digest)"; then
  echo "could not hash target metadata" >&2
  exit 1
fi
target_monitor_healthy || exit 1
if ! target_digest_final="$(target_content_digest)"; then
  echo "could not recompute the final target hash" >&2
  exit 1
fi
target_monitor_healthy || exit 1

# A genuinely read-only mount cannot change, but recomputing the source at the
# end detects a broken snapshot/mount guarantee and prevents a false success.
if ! source_files_final="$(source_file_count)" ||
   ! source_digest_final="$(source_content_digest)" ||
   ! source_metadata_final="$(source_metadata_digest)"; then
  echo "could not recompute the final source fingerprint" >&2
  exit 1
fi
target_monitor_healthy || exit 1

# Recompute every target dimension as the last mounted read. Content comes last
# so a file write after the metadata pass cannot be accepted on metadata alone.
if ! sync_target; then
  echo "final target filesystem flush failed; ${namespace}/${pvc} is not verified" >&2
  exit 1
fi
target_monitor_healthy || exit 1
if ! target_files_final="$(target_file_count)"; then
  echo "could not recompute the final target file count" >&2
  exit 1
fi
target_monitor_healthy || exit 1
if ! target_metadata_final="$(target_metadata_digest)"; then
  echo "could not recompute the final target metadata" >&2
  exit 1
fi
target_monitor_healthy || exit 1
if ! target_digest_last="$(target_content_digest)"; then
  echo "could not perform the last target content hash" >&2
  exit 1
fi
target_monitor_healthy || exit 1

if [[ "${source_files_before}" != "${source_files_final}" ||
      "${source_digest_before}" != "${source_digest_final}" ||
      "${source_metadata_before}" != "${source_metadata_final}" ]]; then
  echo "source snapshot changed during migration; ${namespace}/${pvc} is not verified" >&2
  exit 1
fi
if [[ "${source_files_before}" != "${target_files}" ||
      "${source_files_before}" != "${target_files_final}" ]]; then
  echo "file-count mismatch: source=${source_files_before}, target=${target_files}, final-target=${target_files_final}" >&2
  exit 1
fi
if [[ "${source_digest_before}" != "${target_digest_first}" ||
      "${source_digest_before}" != "${target_digest_final}" ||
      "${source_digest_before}" != "${target_digest_last}" ]]; then
  echo "SHA-256 tree mismatch; ${namespace}/${pvc} is not verified" >&2
  exit 1
fi
if [[ "${source_metadata_before}" != "${target_metadata}" ||
      "${source_metadata_before}" != "${target_metadata_final}" ]]; then
  echo "metadata tree mismatch; ${namespace}/${pvc} is not verified" >&2
  exit 1
fi
validate_target_lost_found || exit 1
if ! sync_target; then
  echo "final readback metadata flush failed; ${namespace}/${pvc} is not verified" >&2
  exit 1
fi
target_monitor_healthy || exit 1
: >"${helper_release_marker}"
release_acknowledged=false
for _ in {1..30}; do
  target_monitor_healthy || exit 1
  if [[ -e "${helper_release_ack}" ]]; then
    release_acknowledged=true
    break
  fi
  sleep 1
done
if [[ "${release_acknowledged}" != true ]]; then
  echo "quiescence monitor did not acknowledge the helper release phase" >&2
  exit 1
fi
if ! ssh "${cluster_host}" \
  "sudo k3s kubectl -n '${namespace}' delete pod '${pod}' --wait=true --timeout=2m"; then
  echo "migration verified, but the helper pod did not release ${namespace}/${pvc}" >&2
  exit 1
fi
pod_created=false
stop_target_monitor || exit 1

echo "verified ${target_files_final} files plus ownership/mode/link metadata into ${namespace}/${pvc}; helper pod removed"
