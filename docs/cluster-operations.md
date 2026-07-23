# Cluster operations and node lifecycle manual

This manual is for the operator maintaining the cluster itself. After reading
it, you should be able to explain where each workload may run, determine which
physical node a service still depends on, add a K3s agent safely, move a pinned
workload, and remove or replace an agent without abandoning Longhorn replicas.

Use the [service lifecycle manual](service-operations.md) for application
manifests and the [runbook](runbook.md) for incident recovery and backup restore
procedures.

## Configuration ownership

The repository is the source of truth, but not every layer is reconciled by
Flux.

| Layer | Source and application method | Important consequence |
| --- | --- | --- |
| Applications and most platform objects | Flux builds the protected `main` branch | Direct overlapping edits are corrected by Flux; root orphan deletion is disabled |
| Separately owned backup/snapshot children | Flux child Kustomizations | Pruning and dependencies are defined per child |
| K3s server and agent configuration | Repository bootstrap inputs copied to `/etc/rancher/k3s/config.yaml` by scripts | A Git merge does not update a running host automatically |
| Pi NFS and host security configuration | Repository inputs applied by SSH helper scripts | Desired and live host files must be verified separately |
| CoreDNS, Metrics Server, and other K3s-packaged components | K3s Addon manifests on the Beelink | They are not ordinary Flux resources |
| Router and Cloudflare | External systems | Kubernetes cannot reconcile or roll them back; Kea reservations are Git-managed |

When a host-level file changes, the pull request must say how and when it will
be applied. After application, compare the installed file with the repository
copy and verify the affected service.

## Current cluster configuration

| Setting | Current value |
| --- | --- |
| K3s | `v1.36.2+k3s1` |
| Control plane | One Beelink server using the K3s SQLite datastore |
| Agent | One Raspberry Pi |
| Pod network | Flannel `host-gw`; Beelink `10.42.0.0/24`, Pi `10.42.1.0/24` |
| Service network | K3s default `10.43.0.0/16` |
| Secrets at rest | K3s secrets encryption enabled; SOPS/age for Git resources |
| API authentication | Authentik OIDC configured for Headlamp; API reachable only through the LAN/server |
| Disabled K3s packages | Bundled Traefik, ServiceLB, and local-storage |
| Ingress | Flux-managed Traefik DaemonSet on host ports 80/443 plus MetalLB VIP `192.168.1.240` |
| DNS | Blocky on the Pi host network at `192.168.1.2:53` |
| DHCP | Kea on the Beelink host network and `enp1s0`, pool `192.168.1.10-192.168.1.239` |
| Shared organized media | JuiceFS with authoritative encrypted payloads in Backblaze B2 and persistent node caches |
| Active downloads | Pi NFS at `192.168.1.2`, exported only from `/home/reza/media/downloads` |
| Application block storage | Longhorn V1 engine, two replicas, one default disk per labeled node |
| Longhorn node/upgrade safety | Storage scheduling disabled on cordoned nodes; automatic engine upgrades disabled |
| Off-site storage | Separate Backblaze B2 buckets for Longhorn backups, Syncthing backups, and authoritative JuiceFS media |

The two nodes are schedulable workers as well as their special roles:

| Node | Address and architecture | Fixed role | Labels |
| --- | --- | --- | --- |
| `beelink` | `192.168.1.3`, amd64 | Sole K3s server, SQLite datastore, main compute, AMD GPU | amd64, NVMe, AMD GPU, Longhorn default disk |
| `raspberrypi` | `192.168.1.2`, arm64 | K3s agent, NFS server, LAN/broadcast protocols, router-forwarded WireGuard | arm64, NVMe, Longhorn default disk |

Both are currently untainted. A Beelink outage removes DHCP and the Kubernetes
control plane. A Pi outage removes DNS, NFS, WireGuard, SMB, and the physical
data behind every NFS volume. The design is not highly available even when a
pod can be rescheduled.

## Networking assumptions

- Both nodes are wired and on the same LAN. Flannel `host-gw` relies on direct
  routing between nodes; do not add an agent behind NAT or on an isolated VLAN
  without redesigning the CNI path.
- Agents must reach the Beelink on TCP 6443. Nodes must reach one another on
  TCP 10250 for metrics/Kubelet access. Pod and Service CIDRs must not be
  blocked internally. MetalLB speakers also require bidirectional node-to-node
  TCP and UDP 7946 for memberlist gossip. Do not expose these interfaces to the
  Internet.
- Ports 80 and 443 must be free on every eligible node because Traefik creates
  one host-port pod per node.
- MetalLB speakers run on every node and advertise the L2 VIP range
  `192.168.1.240-192.168.1.249`.
- The router forwards public TCP 80/443 and WireGuard UDP 1234 to the Pi.
- Kea's DHCP range ends at `.239`; node addresses and the MetalLB range are
  statically assigned outside it.
- Administrative allow-lists deliberately do not trust `.2` or `.3`. Do not
  add a new node address merely because it belongs to the cluster.
- wg-easy masquerades clients to the Pi pod CIDR, so the exact
  `10.42.1.0/24` range is a reviewed administrative exception. Rebuilding or
  replacing the Pi can change its PodCIDR and requires an explicit allow-list
  review.

## Placement vocabulary

The manuals use four placement terms:

- **Pinned:** a hostname selector requires a particular node. The pod remains
  Pending if that node is unavailable.
- **Floating:** no hostname selector or hard affinity. The scheduler may choose
  either compatible node; this does not create a second replica.
- **Every node:** a DaemonSet or system component intentionally runs once on
  each eligible node.
- **Physically dependent:** the pod can move, but its data or external network
  endpoint still lives on one machine.

Always inspect desired placement, current placement, and storage dependency
separately:

```bash
ssh beelink 'sudo k3s kubectl get nodes -o wide --show-labels'
ssh beelink 'sudo k3s kubectl get pods -A -o wide'
ssh beelink 'sudo k3s kubectl get deploy,statefulset,daemonset,cronjob -A -o wide'
ssh beelink 'sudo k3s kubectl get pvc,pv -A'
```

The pod's current `NODE` is an observation. A `nodeSelector`, required affinity,
host path, NFS endpoint, device mount, or host port is the durable constraint.

## Application placement matrix

### Pinned to the Beelink

| Workload | Why it is pinned | Physical dependencies |
| --- | --- | --- |
| `media/jellyfin` | AMD hardware transcoding and LAN discovery | `/dev/dri`, host network, Longhorn config, and read-only JuiceFS library |
| `media/audiobookshelf` | Public workload must not inherit the Pi pod CIDR's private-route trust | Longhorn config/metadata, writable JuiceFS audiobooks/podcasts, read-only JuiceFS books, and Authentik OIDC |
| `media/navidrome` | Keeps music scanning and streaming on the main compute node | Longhorn application state and read-only JuiceFS music |
| `apps/home-assistant` | Keeps third-party integration code and selected LAN egress off the Pi's trusted NFS host | Longhorn configuration; approved LAN integrations require protocol-scoped network policy |
| `network-services/kea-dhcp4` | ISC's official image is amd64-only and DHCP must use a real LAN interface | Beelink host network, `enp1s0`, Longhorn lease database |
| `network-services/stork-server`, `stork-postgresql` | The audited Stork images are currently built for amd64 and monitor the Beelink-hosted Kea service | Authentik OIDC, Longhorn database, and the Kea Stork agent at `10.42.0.1:8080` |
| `network-services/syncthing-backup-freshness` | Checks B2 from the node that is not the data source | B2 only; no Syncthing data PVC |
| K3s server processes | Single-server design | Beelink host filesystem and SQLite datastore |

The downloads Deployment is one pod containing Gluetun, qBittorrent,
FlareSolverr, Prowlarr, Radarr, Sonarr, Shelfmark, and their access proxies.
They share Gluetun's network namespace and must be treated as one upgrade unit.

### Pinned to the Raspberry Pi

| Workload | Why it is pinned | Physical dependencies |
| --- | --- | --- |
| `network-services/blocky` | Preserves the established resolver address `192.168.1.2` | Pi host network and reproducible Longhorn list cache |
| `network-services/samba` | SMB/NetBIOS LAN broadcast behavior | Host network and writable JuiceFS library |
| `network-services/syncthing` | LAN discovery and stable direct-sync ports | Host network, Longhorn config, Pi-local NFS data |
| `network-services/wg-easy` | Router forwards UDP 1234 to the Pi; exact unsafe sysctls are allowed only there | Host port 1234 and Longhorn config |
| `network-services/syncthing-backup` | Reads NFS locally and must share the Pi attachment of Syncthing's Longhorn RWO config claim | Read-only NFS data plus `config.xml` from `syncthing-config` |
| NFS server | Host systemd service, not a pod | Pi filesystem |

The Pi is more trusted than an ordinary pod source because VPN traffic is
masqueraded to its pod CIDR. General floating workloads are nevertheless
allowed to land there. NetworkPolicies reduce the exposure, but a future
hardening project may taint the Pi and add tolerations only to required
workloads.

### Floating applications

These controllers have no hostname selector. Each is a singleton unless stated
otherwise and may run on either node if its image architecture and resources
allow it.

| Namespace | Workloads | Storage or external dependency |
| --- | --- | --- |
| `media` | Downloads/Arr stack and Calibre-Web | Downloads softly prefers a non-control-plane worker. Calibre-Web follows it through required pod affinity because both mount the `calibre-web-ingest` RWO claim. Neither names a physical node. Pi-hosted NFS downloads and JuiceFS remain reachable from either node. |
| `apps` | Actual Budget, Homepage, Jellyseerr, Speedtest Tracker | Longhorn for stateful workloads; Homepage is stateless |
| `apps` | Argilla server/worker, PostgreSQL, Elasticsearch, Redis | Separate Longhorn PVCs; application is multi-component, not transactionally backed up as one unit |
| `apps` | Authentik server/worker and PostgreSQL StatefulSet | Longhorn |
| `apps` | MCPHub and PostgreSQL/pgvector StatefulSet; Hermes Agent; internal LlamaCloud MCP | Longhorn for state; LlamaCloud is stateless and reads the Syncthing vault over NFS |
| `apps` | Open WebUI and Tika | Open WebUI uses Longhorn; Tika is stateless; Authentik OIDC dependency |
| `apps` | Cloudflare DDNS | Stateless; Cloudflare API dependency |
| `monitoring` | Headlamp | Stateless; Kubernetes API and Authentik dependencies |
| `monitoring` | Loggifly/event-exporter | Stateless; Kubernetes API and Telegram dependency |
| `monitoring` | Grafana, Prometheus, Alertmanager, Prometheus Operator, kube-state-metrics | Floating multi-architecture workloads; Longhorn observability PVCs; Authentik and Telegram dependencies |
| `traefik` | Shared error-pages Deployment | Stateless |

Prowlarr, Radarr, Sonarr, and Lidarr directories contain their PVCs, routes, Services,
and proxy resources, but their containers live in the downloads Deployment.
Shelfmark's container also lives there while its route and related resources
are grouped with the Calibre-Web module.

### Platform placement

| Component | Placement behavior |
| --- | --- |
| Traefik | DaemonSet on every node, host ports 80/443 |
| Prometheus node exporter | Privileged host-observer DaemonSet in `kube-system` on every node |
| MetalLB speaker | Host-network DaemonSet on every Linux node |
| MetalLB controller | Floating singleton |
| Longhorn manager and CSI plugin | DaemonSets on every eligible Kubernetes node |
| Longhorn engine images and instance managers | Dynamically managed on Longhorn nodes |
| Longhorn driver deployer | Floating singleton that manages CSI deployment |
| Longhorn CSI sidecars | Two floating replicas each, normally spread across nodes |
| Longhorn UI | Two floating replicas, normally spread across nodes |
| Longhorn `b2-nightly` recurring job | No hostname pin; Longhorn runs per-volume backup work where the relevant volume engine can run |
| Snapshot controller | Two replicas with required hostname anti-affinity; one per node in this cluster |
| cert-manager controller, cainjector, webhook | Floating singletons |
| Flux controllers | Floating singletons |
| Metrics Server | K3s-packaged floating singleton |
| CoreDNS | K3s-packaged singleton; see the live-drift section below |
| K3s API server, scheduler, controller manager, SQLite | Beelink host processes |

A new eligible node automatically receives the Traefik, MetalLB speaker,
Longhorn manager/CSI, and applicable Longhorn engine-image DaemonSet pods.

## Storage placement and impact

Longhorn-backed application state uses RWO volumes with two replicas by
default, one on each existing node. The workload frontend attaches to the node
running the consuming pod. A floating RWO workload can relocate after
detach/reattach; it cannot mount the same volume concurrently from both nodes.

The production storage paths are:

| Storage | Access | Typical consumers |
| --- | --- | --- |
| JuiceFS `media` volume | RWX; permissions and pod mounts constrain writers | Organized movies, TV, music, books, audiobooks, and podcasts |
| Pi `/home/reza/media/downloads` NFS export | Read/write from whichever node runs download automation | qBittorrent, Arr importers, Soularr/slskd, Homepage, and the storage exporter |
| Pi `/home/reza/persistent/syncthing/data` NFS export | Read/write | Syncthing and its read-only backup mount |

Each JuiceFS consumer uses its namespace-local `media-library-juicefs` claim.
All claims address the same encrypted filesystem and use one consistent mount
configuration so the CSI driver can share a mount pod per node. Consumers set
`mountPropagation: HostToContainer` for automatic mount recovery. Category
`subPath` mounts and `readOnly` flags enforce each application's expected view.
The physical cache at `/var/lib/juicefs-cache` is persistent but disposable;
never treat it as another media copy.

The retained `/home/reza/persistent` legacy tree is intentionally not exported.
Do not add a parent export around the Syncthing path: overlapping parent and
child NFS exports with different access modes can cause NFSv4 clients to apply
the parent's read-only policy to the child.

During a migration rollback window, the broader `/home/reza/media` export and
old NFS claims may remain present but frozen. Retire them only after the
cross-node, application, playback, and metadata-restore acceptance checks pass.
The production steady state exports the exact downloads directory, never its
parent; all organized categories are authoritative in JuiceFS/B2.

Removing one of the two current storage nodes makes every two-replica Longhorn
volume degraded. For permanent node removal, add and prepare a replacement
storage node first, then wait for replica evacuation. Reducing replica counts
to force removal is a separate risk decision and requires verified off-site
backups.

## Add an agent node

The current architecture supports adding **agents**. Do not casually add a
second server: two control-plane members do not provide an embedded-etcd quorum,
and the current server uses SQLite. A control-plane HA project requires a
supported datastore migration and normally three server members.

The existing `join-k3s-agent.sh` helper is Pi-specific. It installs Pi SSH/APT
policy, uses the Pi's unsafe-sysctl configuration, waits for the hard-coded
`raspberrypi` node, and ends by cordoning it. Do not run it against a generic
new host.

### 1. Preflight the host

- The documented generic-agent path supports Debian with systemd and apt. A
  different OS needs a reviewed equivalent for K3s and every Longhorn host
  dependency; do not run the apt helper and hope it is portable.
- Assign a unique hostname and a stable/reserved wired LAN address outside the
  Kea DHCP pool (`192.168.1.10-192.168.1.239`), the MetalLB range
  (`192.168.1.240-192.168.1.249`), every administrative allow-list CIDR, and
  every existing infrastructure reservation. The current `192.168.1.32/27`
  admin range is not a valid node-address pool even though adding an address
  there would require no visible `/32` rule.
- Confirm amd64 or arm64 support and adequate CPU, memory, and SSD capacity.
- Confirm TCP 6443 to the Beelink, bidirectional TCP 10250, bidirectional TCP
  and UDP 7946 between every MetalLB speaker node, pod/service CIDR
  reachability, Internet registry access, and NTP.
- Ensure host ports 80 and 443 are free.
- Decide whether the node will hold Longhorn replicas.
- Verify every workload that may float there has a compatible multi-architecture
  image.
- If it will mount Pi NFS, add its address only to each exact required export,
  use `ro` unless that node contains an intended writer, and test the export
  before scheduling consumers. Do not grant a new node blanket access to the
  legacy or Syncthing trees.
- Add the exact node address to `K3S_NODE_ADDRESSES` in
  `scripts/ci/check-high-risk-policy.py` and extend its guardrail tests before
  deployment. This prevents a future broad allow-list from silently trusting
  peer-node SNAT. Do not add the node address to administrative HTTP
  allow-lists.

Before the first SSH/SCP operation, obtain the new host's Ed25519 fingerprint
from its physical console or another authenticated out-of-band channel:

```bash
# Run on the new host's local console.
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub

# Run on the workstation; compare the SHA256 fingerprint character for
# character with the console result before accepting it.
ssh-keyscan -t ed25519 NEW_LAN_IP 2>/dev/null | ssh-keygen -lf -
ssh -o ControlMaster=no -o ControlPath=none \
  -o StrictHostKeyChecking=ask NEW_SSH_ALIAS true
ssh -o BatchMode=yes -o ControlMaster=no -o ControlPath=none \
  -o KbdInteractiveAuthentication=no -o PasswordAuthentication=no \
  -o PreferredAuthentications=publickey -o StrictHostKeyChecking=yes \
  NEW_SSH_ALIAS true
```

Stop on any mismatch. Never use `StrictHostKeyChecking=no` or blindly append
`ssh-keyscan` output. No join token may be sent until the final strict check
succeeds.

Before **any mutating SSH or SCP command**, create the host-specific SSH and
unattended-security-update configuration under
`infrastructure/hosts/NEW_NODE/`, the agent K3s config described below, all
required NFS/export and guardrail changes, and the placement documentation in
one reviewed change. Use the Pi host files and the fail-closed APT block in
`scripts/join-k3s-agent.sh` as the Debian reference, but do not copy the Pi's
K3s unsafe-sysctl configuration. Run the complete validation in
[the service manual](service-operations.md#8-validate-before-the-pull-request),
merge through the protected PR/CI path, then operate from that exact clean
`main` revision:

```bash
set -euo pipefail
git fetch origin main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain)"
```

Physical-console inspection and the read-only fingerprint comparison above may
happen before merge; applying host policy, exports, K3s configuration, or a
token may not.

Host-baseline application is intentionally node-specific: SSH account names,
APT origins, and OS behavior are host policy, so there is no generic helper
that is safe to aim at an arbitrary machine. The same PR must add a reviewed,
idempotent `scripts/prepare-NEW_NODE-host.sh` for the supported Debian host.
Use the implementation in `join-k3s-agent.sh` as the reference and require that
new helper to:

- use strict SSH host-key checking and a unique remote staging directory;
- refuse a managed SSH/APT target that is a symlink, non-regular file, or
  differs from the last reviewed/expected content; resolve adoption or drift
  explicitly in the pull request instead of adding a generic force flag;
- install the reviewed SSH drop-in as
  `/etc/ssh/sshd_config.d/00-home-server-hardening.conf`, preserve the prior
  file, verify both `sshd -t` and the connection-context effective policy, and
  restore it if syntax, effective-policy, or reload validation fails;
- prove the reloaded policy with a new key-only, non-multiplexed connection and
  noninteractive sudo before continuing; do not mistake an existing
  `ControlPersist` session for a successful login;
- disable both APT timers and wait for active APT jobs before changing policy;
- install the reviewed `20auto-upgrades` and
  `52-home-server-unattended-upgrades` fragments, clearing distro defaults so
  exactly the Debian Security origin remains eligible;
- prove automatic reboot and dependency/kernel cleanup are disabled;
- run `unattended-upgrade --dry-run` before enabling the service and timers;
  and
- fail closed: an APT-policy error leaves the timers disabled, while any SSH
  validation/reload error restores the previous valid configuration. Retain a
  physical-console recovery path for a failure after reload.

Do not replace this reviewed host-specific step with ad-hoc copy commands. Run
the merged helper, inspect its diff/output, then verify the installed baseline:

```bash
set -euo pipefail
ssh -o BatchMode=yes -o ControlMaster=no -o ControlPath=none \
  -o KbdInteractiveAuthentication=no -o PasswordAuthentication=no \
  -o PreferredAuthentications=publickey -o StrictHostKeyChecking=yes \
  NEW_SSH_ALIAS 'set -euo pipefail
    sudo -n true
    if sudo -n test -e /etc/rancher/k3s/config.yaml ||
      sudo -n test -e /var/lib/rancher/k3s ||
      systemctl cat k3s-agent.service >/dev/null 2>&1; then
      printf "%s\n" "Refusing existing or partially installed K3s host." >&2
      exit 1
    fi'
scripts/prepare-NEW_NODE-host.sh NEW_SSH_ALIAS
ssh -o StrictHostKeyChecking=yes NEW_SSH_ALIAS \
  'sudo cat /etc/ssh/sshd_config.d/00-home-server-hardening.conf' |
  diff -u infrastructure/hosts/NEW_NODE/sshd-hardening.conf -
ssh -o StrictHostKeyChecking=yes NEW_SSH_ALIAS \
  'sudo cat /etc/apt/apt.conf.d/20auto-upgrades' |
  diff -u infrastructure/hosts/NEW_NODE/20auto-upgrades -
ssh -o StrictHostKeyChecking=yes NEW_SSH_ALIAS \
  'sudo cat /etc/apt/apt.conf.d/52-home-server-unattended-upgrades' |
  diff -u infrastructure/hosts/NEW_NODE/52-home-server-unattended-upgrades -

ssh -o StrictHostKeyChecking=yes NEW_SSH_ALIAS 'set -euo pipefail
  . /etc/os-release
  test "$ID" = debian
  sudo sshd -t
  sudo sshd -T | grep -qx "passwordauthentication no"
  sudo sshd -T | grep -qx "kbdinteractiveauthentication no"
  sudo sshd -T | grep -qx "permitrootlogin no"
  systemctl is-enabled --quiet unattended-upgrades.service
  systemctl is-enabled --quiet apt-daily.timer
  systemctl is-enabled --quiet apt-daily-upgrade.timer
  sudo unattended-upgrade --dry-run'
```

If the node will store Longhorn replicas, mount or identify the filesystem that
backs the configured `/var/lib/longhorn` data path **before** applying the
default-disk label. The current nodes intentionally use their SSD-backed root
filesystems; a separate persistent mount is also valid. The output must name
the intended persistent SSD and show sufficient free space, including after a
reboot when a separate mount is used:

```bash
ssh -o StrictHostKeyChecking=yes NEW_SSH_ALIAS 'set -euo pipefail
  sudo install -d -m 0755 /var/lib/longhorn
  findmnt -T /var/lib/longhorn -o TARGET,SOURCE,FSTYPE,OPTIONS,SIZE,AVAIL
  df -h /var/lib/longhorn
  lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS'
```

Do not accept an accidental boot/SD-card filesystem or an unmounted directory
on `/` when a separate data disk was intended.

Install Longhorn's V1 prerequisites before joining:

```bash
scripts/prepare-longhorn-hosts.sh NEW_SSH_ALIAS
ssh -o StrictHostKeyChecking=yes NEW_SSH_ALIAS 'set -euo pipefail
  systemctl is-active --quiet iscsid
  sudo sh -c "command -v mount.nfs4 cryptsetup dmsetup >/dev/null"
  for unit in multipathd.service multipathd.socket; do
    enabled_state="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
    if systemctl is-active --quiet "$unit"; then
      printf "%s is still active\n" "$unit" >&2
      exit 1
    fi
    case "$enabled_state" in
    enabled|enabled-runtime|linked|linked-runtime)
      printf "%s still has unsafe enablement state %s\n" \
        "$unit" "$enabled_state" >&2
      exit 1
      ;;
    esac
  done'
```

The helper installs `open-iscsi`, `nfs-common`, `cryptsetup`, and `dmsetup`,
starts `iscsid`, and disables multipath only after proving that no active
multipath map exists. It refuses to continue if map inspection fails or finds
an active map. Missing multipath units are benign, but the explicit post-check
above remains authoritative. If the node will never be a Longhorn storage
node, still verify the CSI/mount requirements for any Longhorn-backed workload
it may run.

For every image used by a floating workload, verify the pinned reference is a
multi-architecture index containing both current cluster architectures. This
requires `skopeo` and `jq` on the operator workstation and deliberately fails
for a single-platform digest:

```bash
set -euo pipefail
command -v skopeo jq >/dev/null
image='REGISTRY/REPOSITORY:TAG@sha256:DIGEST'
for arch in amd64 arm64; do
  skopeo inspect --raw "docker://${image}" |
    jq -e --arg arch "$arch" \
      'any(.manifests[]?;
        .platform.os == "linux" and .platform.architecture == $arch)' \
      >/dev/null
done
```

### 2. Add a host-specific K3s config

Create a reviewed agent configuration under the K3s infrastructure module. Do
not copy the Pi-only unsafe sysctls. A safe initial shape is:

```yaml
server: https://192.168.1.3:6443
token-file: /etc/rancher/k3s/node-token
node-name: NEW_NODE
node-ip: NEW_LAN_IP
node-label:
  - homelab.rezan.dev/cpu-arch=CPU_ARCH
  - homelab.rezan.dev/storage=STORAGE_TYPE
  # Include only after the /var/lib/longhorn filesystem proof above.
  - node.longhorn.io/create-default-disk=true
node-taint:
  - homelab.rezan.dev/bootstrap=true:NoSchedule
```

Replace `CPU_ARCH` with `amd64` or `arm64` and set `STORAGE_TYPE` to truthful
inventory metadata such as `nvme`; no current workload or Longhorn policy uses
that label for scheduling. Do not copy a hardware label the node does not
satisfy. Omit the Longhorn default-disk label when the disk must not store
replicas or its backing filesystem has not been proven.
The temporary taint prevents ordinary workloads from landing before host,
storage, and architecture validation. K3s registration-time labels and taints
should be recorded in the host config; later changes use `kubectl` and should
also be reflected in the intended policy.

### 3. Install the exact cluster K3s version

Copy the config and token without printing the token or placing it in process
arguments:

```bash
set -euo pipefail
ssh_options=(
  -o BatchMode=yes
  -o ControlMaster=no
  -o ControlPath=none
  -o KbdInteractiveAuthentication=no
  -o PasswordAuthentication=no
  -o PreferredAuthentications=publickey
  -o StrictHostKeyChecking=yes
)
ssh "${ssh_options[@]}" NEW_SSH_ALIAS 'set -euo pipefail
  sudo -n true
  if sudo -n test -e /etc/rancher/k3s/config.yaml ||
    sudo -n test -e /var/lib/rancher/k3s ||
    systemctl cat k3s-agent.service >/dev/null 2>&1; then
    printf "%s\n" "Refusing existing or partially installed K3s host." >&2
    exit 1
  fi'
remote_config="$(ssh "${ssh_options[@]}" NEW_SSH_ALIAS \
  mktemp /tmp/home-server-k3s-config.XXXXXX)"
if [[ ! "$remote_config" =~ ^/tmp/home-server-k3s-config\.[A-Za-z0-9]+$ ]]; then
  printf 'Refusing unexpected remote config path: %s\n' "$remote_config" >&2
  exit 1
fi
cleanup_remote_config() {
  ssh "${ssh_options[@]}" NEW_SSH_ALIAS \
    rm -f -- "$remote_config" >/dev/null 2>&1 || true
}
trap cleanup_remote_config EXIT

scp "${ssh_options[@]}" \
  infrastructure/k3s/agent-NEW_NODE-config.yaml \
  "NEW_SSH_ALIAS:${remote_config}"
ssh "${ssh_options[@]}" NEW_SSH_ALIAS sudo -n install -D -m 0600 \
  "$remote_config" /etc/rancher/k3s/config.yaml

scripts/install-k3s-agent-token.sh beelink NEW_SSH_ALIAS NEW_NODE

scripts/install-k3s.sh NEW_SSH_ALIAS agent 'v1.36.2+k3s1'
```

When the cluster version changes, update this example and use the exact version
already running on the server. The helper downloads the installer from a pinned
upstream K3s commit, verifies its reviewed SHA-256, and then asks that installer
for the exact release. Do not replace it with the mutable `get.k3s.io | sh`
pattern or let an installer default pick a newer K3s release. Updating the K3s
version or installer commit/checksum is its own reviewed supply-chain change;
the checksum proves identity, while release provenance/signature verification
remains a separate hardening option. The bootstrap, join, and installer helpers
are fresh-host-only: they refuse an existing K3s unit or data directory rather
than acting as an implicit upgrade/recovery tool. Plan upgrades and recovery as
separate, state-aware procedures.

The join credential above is a secure-format, one-hour agent bootstrap token,
not the full-administrator K3s server token. Record its description. If the
admission is abandoned, the host becomes untrusted, or the fingerprint changes,
delete the matching token ID immediately with `sudo k3s token delete TOKEN_ID`
on the Beelink. After the node reaches Ready, list tokens with
`sudo k3s token list`, delete that exact ID, and leave the expired token file
root-only on the agent; it is no longer a valid join credential. If the server
token is ever exposed instead, follow K3s's supported server-token rotation and
preserve the old token with backups that require it.

### 4. Admit platform pods before application workloads

```bash
ssh beelink 'sudo k3s kubectl wait --for=condition=Ready node/NEW_NODE --timeout=3m'
ssh beelink 'sudo k3s kubectl get node NEW_NODE -o wide --show-labels'
ssh beelink 'sudo k3s kubectl describe node NEW_NODE'
```

First verify K3s reports Ready with the intended internal IP, architecture,
labels, and only the bootstrap taint. Then cordon the node, remove the custom
taint, and leave it cordoned. Kubernetes DaemonSets tolerate the standard
unschedulable state, while ordinary application pods remain excluded:

```bash
ssh beelink 'sudo k3s kubectl cordon NEW_NODE'
ssh beelink 'sudo k3s kubectl taint node NEW_NODE \
  homelab.rezan.dev/bootstrap=true:NoSchedule-'
ssh beelink 'test "$(sudo k3s kubectl -n longhorn-system get setting \
  disable-scheduling-on-cordoned-node -o jsonpath="{.value}")" = true'
```

Now verify:

- the Longhorn Node CR and intended disk are discovered when storage was
  enabled; Longhorn correctly disables scheduling while the Kubernetes node is
  cordoned;
- Traefik, MetalLB speaker, Longhorn manager/CSI, and engine-image DaemonSets
  have healthy pods as applicable;
- Pi NFS mounts work from the new IP when needed;
- host ports 80/443 and routes are healthy; and
- no image fails with an architecture mismatch, digest mismatch, or pull error.

Useful checks while the node remains cordoned:

```bash
ssh beelink 'sudo k3s kubectl -n longhorn-system get node.longhorn.io NEW_NODE -o yaml'
ssh beelink 'sudo k3s kubectl get pods -A -o wide --field-selector spec.nodeName=NEW_NODE'
ssh beelink 'sudo k3s kubectl -n metallb-system get pods \
  -l app.kubernetes.io/component=speaker -o wide'
ssh beelink 'sudo k3s kubectl -n metallb-system logs \
  -l app.kubernetes.io/component=speaker \
  --all-containers=true --prefix --since=10m'
ssh beelink 'sudo k3s kubectl -n longhorn-system \
  get node.longhorn.io NEW_NODE -o json' |
  jq -e '
    ["Ready", "RequiredPackages", "Multipathd",
     "NFSClientInstalled", "MountPropagation"] as $required |
    [.status.conditions[] | select(.status == "True") | .type] as $true |
    all($required[];
      . as $condition | ($true | index($condition)) != null)'
```

The five required conditions above must all be true before uncordon. Also
inspect `KernelModulesLoaded`. A false result is acceptable only when its
reason is `KernelModulesNotLoaded`, its complete message is exactly
`Kernel modules [dm_crypt] are not loaded`, and the cluster has no encrypted
Longhorn Volume. Prove that narrow exception explicitly:

```bash
ssh -o StrictHostKeyChecking=yes beelink \
  'sudo k3s kubectl -n longhorn-system get node.longhorn.io NEW_NODE -o json' |
  jq -e '
    .status.conditions[] | select(.type == "KernelModulesLoaded") |
    (.status == "True") or
    (
      .status == "False" and
      .reason == "KernelModulesNotLoaded" and
      .message == "Kernel modules [dm_crypt] are not loaded"
    )'
ssh -o StrictHostKeyChecking=yes beelink \
  'sudo k3s kubectl -n longhorn-system get volumes.longhorn.io -o json' |
  jq -e '[.items[] | select(.spec.encrypted == true)] | length == 0'
```

Missing `iscsi_tcp`, any additional module, an inspection error, or any
encrypted volume blocks uncordon. In those cases load and persist every
required module and require the condition to become true. `Schedulable` is
expected to be false while cordoned. The new MetalLB speaker must be Ready, its
host must listen on TCP and UDP 7946, and the speaker logs must show no
memberlist join/timeout error before VIP behavior is accepted.

Finally make the node schedulable:

```bash
ssh beelink 'sudo k3s kubectl uncordon NEW_NODE'
```

Watch actual scheduling and all Longhorn volumes for at least one
reconciliation cycle. When it is a storage node, require the Longhorn node and
disk to become Ready/allow scheduling and its `Schedulable` condition to become
true after uncordon before expecting replicas there. Update the
architecture/placement documentation in the same change that introduces a
permanent node role.

## Move or repin a workload

1. Identify every volume, NFS path, device, host port, router rule, DNS entry,
   and allow-list assumption.
2. Prove a current backup and application export when stateful.
3. Verify the target architecture supports every container in the pod.
4. For NFS, permit and test the target node address first.
5. For Longhorn, require healthy replicas and enough space on all participating
   and target storage nodes.
6. Change the selector through Git and pass the full validation/high-risk
   review.
7. Reconcile, watch detach/reattach, and test the service from its real client
   path.
8. Remove obsolete host, router, or allow-list state only after the new path is
   proven.

Treat controllers that share one Longhorn RWO claim as a single placement unit.
In particular, move Calibre-Web and downloads together because they share
`calibre-web-ingest`; move Syncthing and `syncthing-backup` together unless the
backup design stops mounting `syncthing-config`. Moving only one side can cause
a cross-node Multi-Attach failure even when both mounts are read-only.

Do not use a live `kubectl patch` as a permanent placement change. A hostname
pin should represent a physical requirement; prefer no pin for genuinely
portable workloads.

## Planned maintenance on a node

For a short reboot, follow the runbook's health checks and accept that pinned
singletons will be unavailable. Before draining:

```bash
ssh beelink 'sudo k3s kubectl get nodes'
ssh beelink 'sudo k3s kubectl -n longhorn-system get volumes.longhorn.io'
ssh beelink 'sudo k3s kubectl -n longhorn-system get setting node-drain-policy'
```

The current Longhorn drain policy is `block-if-contains-last-replica`. Do not
weaken it merely to make a drain finish. A blocked drain is evidence that the
remaining data placement is unsafe.

For the Pi, explicitly expect loss of DNS, NFS, public ingress target,
WireGuard, SMB, Syncthing, and Pi-pinned pods. For the Beelink, expect loss of
DHCP, the API/control plane, and most compute. The other node being Ready does
not remove those physical dependencies.

## Permanently remove an agent

Do not use this procedure for the Beelink server. Do not permanently remove one
of the current two Longhorn nodes until a replacement storage node has enough
space and is ready to receive replicas.

### 1. Remove application dependencies first

- Move or retire every hostname-pinned workload through Git.
- If removing the Pi, migrate NFS, DNS, SMB, Syncthing, WireGuard, router
  forwards, static PV endpoints, and the trusted Pi PodCIDR design first.
- If removing the Beelink, migrate Kea DHCP before taking down its physical
  `enp1s0` listener; a replacement must be proven on the same broadcast domain.
- Remove the node address from Pi NFS exports only after no mount uses it.
- Confirm Longhorn's B2 target and recent backups are complete.
- Require every attached volume to be `healthy`, with its requested replica
  count present and no failed replica. An intentionally detached archival
  volume can report robustness `unknown`; for it, require the expected number
  of stopped replicas on distinct storage nodes, non-empty `healthyAt`, empty
  `failedAt`, no attachment, and an exact completed off-site backup. The retained
  Duplicati archive is the current exception that needs this detached-volume
  test rather than the impossible blanket `healthy` test.

### 2. Cordon and drain

```bash
ssh beelink 'sudo k3s kubectl cordon NODE'
ssh beelink 'sudo k3s kubectl get pods -A \
  --field-selector spec.nodeName=NODE -o wide'
ssh beelink 'sudo k3s kubectl drain NODE \
  --ignore-daemonsets \
  --grace-period=-1 \
  --dry-run=server \
  --timeout=300s'
ssh beelink 'sudo k3s kubectl drain NODE \
  --ignore-daemonsets \
  --grace-period=-1 \
  --timeout=300s'
```

The first drain is a server-side dry run; review its output before the real
evictions. The default real command intentionally stops for unmanaged pods and
`emptyDir` data. If it stops, identify each pod and owner. Add
`--delete-emptydir-data` only after proving those exact local files are
disposable. Repair or explicitly handle an unmanaged pod; do not add `--force`
to the generic procedure. Never force-delete storage components or change the
Longhorn drain policy to conceal the cause.

### 3. Evacuate Longhorn

Disable Longhorn scheduling and request replica eviction using its supported
Node resource:

```bash
ssh beelink 'sudo k3s kubectl -n longhorn-system patch node.longhorn.io NODE \
  --type=merge \
  -p '\''{"spec":{"allowScheduling":false,"evictionRequested":true}}'\'''
```

Wait until every disk reports zero scheduled replicas and backing images:

```bash
ssh beelink 'sudo k3s kubectl -n longhorn-system \
  get node.longhorn.io NODE -o json | jq '\''
    .status.diskStatus | to_entries[] |
    {
      disk: .key,
      scheduledReplicas: (.value.scheduledReplica | length),
      scheduledBackingImages: (.value.scheduledBackingImage | length)
    }'\'''
```

Also require every attached volume to remain healthy, every deliberately
detached volume to retain its expected non-failed replicas, and no volume or
VolumeAttachment to target the departing node. If eviction cannot reach zero,
add capacity or resolve anti-affinity/volume health; do not delete the Node CR
with replicas still present.

### 4. Uninstall and remove metadata

After workload drain and storage evacuation:

```bash
ssh NODE_SSH_ALIAS sudo /usr/local/bin/k3s-agent-uninstall.sh
ssh beelink 'sudo k3s kubectl delete node NODE'
ssh beelink 'sudo k3s kubectl -n longhorn-system delete node.longhorn.io NODE'
```

The uninstall script deletes local K3s state but does not delete external
Longhorn or NFS data. Deleting the Kubernetes Node is also important before a
same-name rejoin so K3s can remove the old node-password registration state.

Finally remove the host config, NFS permission, DHCP reservation, monitoring,
and placement documentation in a reviewed change. Verify no PV node affinity,
Longhorn replica, DaemonSet pod, DNS entry, or router rule still refers to it.

## Replace a node

Prefer a new unique node name and use add-before-remove. This lets Longhorn
build replacement replicas while the old node is still available.

Reusing a name requires the full removal sequence first. Longhorn recognizes
that the replacement disk is different; old disk metadata must be evacuated
and removed before registering the replacement disk. Never point a new node at
an old `/var/lib/longhorn` directory and assume the replica directories are
valid members of the current cluster.

Replacing the Pi is a storage/network migration, not an ordinary agent swap.
Preserve its NFS data, ownership, exports, `192.168.1.2` Blocky DNS endpoint,
Syncthing identity, WireGuard configuration, router target, and
PodCIDR-dependent access rules.

Replacing the Beelink is a control-plane recovery or migration, not an agent
operation. It is **not currently runbook-supported**: the repository has no
tested consistency-safe, checksummed, off-host backup and restore procedure for
the SQLite datastore plus server token. The existing dated archive is local to
the Beelink and does not protect against its disk loss. Do not run the agent
removal procedure against it or claim a routine replacement is possible until
that recovery gap is closed and restore-tested. Kea DHCP and its lease volume
must also move to a proven amd64 host on the same LAN before the old `enp1s0`
listener stops.

## Current live deviations requiring follow-up

These were verified on 2026-07-14. They are not reasons to panic, but they must
not be forgotten.

### 1. Longhorn volume EngineImage metadata is still tag-only

Longhorn's manager, desired default engine setting, and new EngineImage are
digest-qualified. All 26 pre-existing V1 volumes still select the legacy
`longhorn-engine:v1.12.0` EngineImage without the digest. Both EngineImages are
currently pulled as the same reviewed binary digest, so this is metadata and
future-repull exposure—not evidence that foreign code is running.

Do **not** try to normalize these references with a manual or automatic engine
upgrade. Longhorn's official same-commit migration warning says an upgrade from
one image reference to another image built from the identical Git commit can
become stuck. Keep
`concurrentAutomaticEngineUpgradePerNodeLimit: "0"`; do not raw-patch Volume,
Engine, or Replica CRs; and do not delete the legacy EngineImage or DaemonSet
while its reference count is nonzero.

The safe plan is to leave the metadata tracked until a genuinely newer,
supported Longhorn engine release is adopted. At that point, follow the normal
supported engine-upgrade process after proving backups and volume health, and
verify all old references reach zero as an outcome of that real version
upgrade. A same-version disposable-volume experiment or upstream confirmation
would be required before attempting any earlier normalization.

Useful read-only checks:

```bash
ssh beelink 'sudo k3s kubectl -n longhorn-system get engineimages.longhorn.io \
  -o custom-columns=NAME:.metadata.name,IMAGE:.spec.image,STATE:.status.state,REFS:.status.refCount'
ssh beelink 'sudo k3s kubectl -n longhorn-system get volumes.longhorn.io -o json \
  | jq -r ".items[] | [.metadata.name,.spec.image,.status.currentImage,.status.state,.status.robustness] | @tsv"'
```

### 2. CoreDNS has an undocumented live hostname selector

The K3s-packaged CoreDNS source manifest selects only Linux nodes. The live
Deployment additionally selects `kubernetes.io/hostname=beelink`, and no Git or
host configuration records that change. It is a singleton and therefore cannot
move to the Pi in its current state.

Decide explicitly between:

- removing the live-only hostname field and returning to the packaged K3s
  placement; or
- defining and maintaining a reproducible K3s Addon customization with a
  documented reason.

Do not simply describe the live pin as desired state. Before changing it,
capture the Deployment, confirm the CoreDNS image supports arm64, verify the Pi
can run it, and prepare DNS tests from both nodes and an ordinary LAN client.

## Remaining resilience and hardening options

Control-plane recovery is the highest-priority gap. The remaining items are
listed here so accepted risk does not turn into forgotten risk:

- Design, automate, checksum, encrypt, copy off-host, and bare-metal
  restore-test a consistency-safe backup of the single-server K3s SQLite
  datastore **and** the matching server token. Until then, Beelink disk loss is
  a control-plane rebuild, not a documented restore. Keep every historical
  server token alongside backups that were encrypted with it.
- Rotate the K3s server token through the supported K3s procedure so the Pi no
  longer holds the current full-administrator token. Reinstall a temporary
  bootstrap token on the Pi as needed, restart every required component, and
  preserve the old token for old recovery artifacts before revocation.
- Write and rehearse a state-aware K3s patch/minor-upgrade procedure. The
  repository's bootstrap/join/install helpers now deliberately refuse existing
  nodes; they are not an upgrade mechanism.
- Observe and record the first clock-triggered Longhorn and Syncthing runs
  after deployment, then add an external dead-man monitor independent of this
  cluster and its Telegram exporter. Also add an automated per-volume Longhorn
  freshness/coverage check; a reachable BackupTarget alone does not prove that
  every volume is current.
- Add recurring native database/application exports for multi-PVC or
  write-heavy services such as Argilla, and restore-test them with the matching
  block backups. Write and rehearse a production Syncthing disaster-recovery
  procedure in addition to its existing disposable restore proof.
- Resolve the live-only CoreDNS hostname selector described above and add a
  bounded, redacted K3s API audit policy with rotation and off-node shipping so
  future direct patches or deletes are attributable. Kubernetes Events do not
  provide that audit trail.
- Define and enforce a repository-owned unattended-security-update policy for
  the Ubuntu Beelink, including allowed origins, no automatic reboot/cleanup,
  verification, and maintenance-window handling. The Pi policy is already
  explicit; the Beelink policy is not.
- Rotate the Syncthing B2 key to the proven `syncthing/` prefix and minimum
  list/read/write capabilities, and use a separate read-only freshness key.
  Use an FQDN-aware proxy/CNI policy if backup-pod HTTPS egress must be limited
  to Backblaze rather than arbitrary public TCP 443.
- Put an explicit retention expiry on the detached `duplicati-config` PVC, old
  Duplicati B2 repository, encrypted settings/recovery material, historical
  manifests, and the empty Pi directory. Verify recovery requirements before
  deleting the batch and revoke the obsolete credential afterward.
- Monitor Backblaze hidden-version growth and cost monthly; bucket-level
  “keep all versions” can retain physical objects after logical backup pruning.
- Review Traefik's cluster-wide Secret read RBAC and Jellyfin's direct LAN 8096
  path, which bypasses Gateway/Authentik and relies on Jellyfin authentication.
- Keep an independent password-manager or encrypted-offline copy of the Restic
  password, SOPS age identity, K3s recovery tokens, and recovery instructions.
- Add automated regression coverage for the Syncthing restore-proof path and
  continue quarterly isolated Syncthing plus application/database restores.
- Decide whether to taint the Pi and tolerate only physically required
  workloads, reducing the trust implied by its pod-CIDR exception.
- Add a third-server control-plane design only as an intentional three-member
  HA migration; two server nodes do not provide the desired embedded-etcd
  failure tolerance.
- Periodically restore JuiceFS metadata into an isolated PostgreSQL instance
  and mount the media filesystem from that restored metadata. B2 chunks alone
  are not a usable recovery path.

## Related material

- [Cluster architecture](architecture.md)
- [Service lifecycle manual](service-operations.md)
- [Incident and recovery runbook](runbook.md)
- [K3s requirements](https://docs.k3s.io/installation/requirements)
- [K3s agent configuration](https://docs.k3s.io/cli/agent)
- [K3s secure, agent, and expiring bootstrap tokens](https://docs.k3s.io/cli/token)
- [K3s uninstallation and same-name rejoin warning](https://docs.k3s.io/installation/uninstall)
- [Longhorn graceful node removal](https://longhorn.io/docs/1.12.0/nodes-and-volumes/nodes/graceful-node-removal/)
- [Longhorn engine upgrades](https://longhorn.io/docs/1.12.0/deploy/upgrade/upgrade-engine/)
- [Longhorn identical-commit EngineImage warning](https://longhorn.io/kb/how-to-migrate-longhorn-chart-installed-in-old-rancher-ui-to-the-chart-in-new-rancher-ui/)
- [Flux pruning and inventory](https://fluxcd.io/flux/components/kustomize/kustomizations/)
