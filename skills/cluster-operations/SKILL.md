---
name: cluster-operations
description: Operate Flux, Kubernetes placement, Longhorn participation, agent admission, draining, or planned cluster maintenance. Use for cluster-level lifecycle work, not host-OS configuration or ordinary application changes.
---

# Operate the cluster safely

Use this skill for Kubernetes and Flux operations that affect scheduling,
platform controllers, storage participation, or node lifecycle. It does not
authorize host mutation, a merge, a reconcile, a drain, or any other live
change merely because the requested outcome would benefit from one.

## Read the operating contract

Read the task-relevant sections of:

- [cluster operations and node lifecycle](../../docs/cluster-operations.md);
- [architecture and failure domains](../../docs/architecture.md);
- [incident and recovery runbook](../../docs/runbook.md);
- [service lifecycle manual](../../docs/service-operations.md) when an
  application moves or changes; and
- [JuiceFS operations](../../docs/juicefs-media.md) when a node mounts or caches
  shared media.

Treat placement tables and dated live-deviation notes as leads to verify, not a
substitute for current manifests and read-only live state. Resolve desired
placement from the active workload manifest and current placement from the API.

## Separate the owners

Build an ownership table before proposing a change:

| Plane | Authority and normal path |
| --- | --- |
| Root cluster tree | Git and the root Flux Kustomization; pruning is disabled |
| Flux child | Its own source, path, inventory, dependencies, decryption, health checks, and prune setting |
| Helm platform | HelmRelease plus immutable source and independently rendered chart output |
| K3s packaged component | K3s Addon/host state, not an ordinary root Flux resource |
| Node host | Repository host input applied separately over SSH |
| Router/provider | External state requiring separate authorization |

Do not infer ownership from a filename or label. Follow
`clusters/home-server/kustomization.yaml`, each referenced
`kustomization.yaml`, and each live Flux inventory. Removing a root resource
from Git does not delete it. Removing a child from the non-pruning root can
leave that child continuously reconciling its old path.

## Start with read-only discovery

Establish the repository and live revision before reasoning about drift:

```bash
git status --short --branch
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
kubectl kustomize clusters/home-server >/tmp/home-server.yaml

ssh beelink 'sudo k3s kubectl get nodes -o wide --show-labels'
ssh beelink 'sudo k3s kubectl get pods -A -o wide'
ssh beelink 'sudo k3s kubectl get deploy,statefulset,daemonset,cronjob -A'
ssh beelink 'sudo k3s kubectl get pvc,pv,volumeattachment -A'
ssh beelink 'sudo k3s kubectl -n flux-system get gitrepositories,kustomizations -o wide'
ssh beelink 'sudo k3s kubectl get helmreleases -A'
```

There is no usable local kubeconfig. Live commands go through the Beelink with
`sudo k3s kubectl`.

For each workload, distinguish:

- desired selector or required affinity;
- observed current node;
- image architecture support;
- host network, port, device, or path dependency;
- NFS or other physically remote data dependency;
- attached RWO claims and controllers sharing them; and
- Longhorn replica placement, health, and available target capacity.

Never equate a reschedulable pod with an available service. DNS, DHCP, NFS,
public ingress, WireGuard, SMB, hardware, and the control plane retain physical
failure domains.

## Supported workflows

### Move or repin a workload

1. Inventory every volume, export, device, address, router rule, host port, and
   trust assumption.
2. Prove a current off-site backup and readable application export when
   stateful.
3. Verify every container supports the target architecture.
4. Prepare and test NFS permissions or hardware on the target before moving.
5. Require healthy Longhorn replicas and enough target capacity.
6. Change placement through Git and run the complete validation bundle.
7. After protected merge, prove detach/attach, placement, endpoints, access,
   data reads and writes, and backup coverage at the exact revision.
8. Remove obsolete host or external state only after the new path is proven and
   separately authorized.

Treat controllers sharing an RWO claim as one placement unit. Do not solve a
Multi-Attach risk with an ad hoc live patch.

### Planned maintenance

Before cordon or drain, establish node, Flux, volume, replica, backup, NFS, and
service health. State the expected outage from the physical role. Review a
server-side dry-run drain before a real drain.

Do not weaken Longhorn drain policy, force-delete storage pods, use `--force`,
or add `--delete-emptydir-data` until every exact blocked object and local file
has been classified. A blocked drain is evidence, not an inconvenience.

### Add or permanently remove an agent

Use the complete admission/removal sequence in the cluster manual. For
admission, keep the node tainted or cordoned while host identity, K3s labels,
platform DaemonSets, NFS access, Longhorn requirements, architecture, and
network paths are proven. A node becomes generally schedulable only after those
checks pass.

Use add-before-remove for a storage node. Before permanent removal, migrate
physical services, drain workloads, evacuate Longhorn through supported Node
resources, and prove zero remaining replica, attachment, PV affinity, export,
DNS, or router dependencies. Do not reduce replica counts merely to make an
evacuation possible.

## Hard stops

Stop and report rather than improvise when the task would require:

- replacing or bare-metal restoring the Beelink control plane; the repository
  does not contain a tested consistency-safe off-host restore of the K3s SQLite
  datastore and matching server token;
- a state-aware K3s upgrade; bootstrap, install, and join helpers are
  fresh-host-only and deliberately refuse an existing installation;
- promoting an agent into a casually designed additional server; control-plane
  HA requires a separately designed supported datastore migration;
- treating the disposable Syncthing restore proof as a production disaster
  recovery procedure;
- raw-patching Longhorn Volume, Engine, Replica, or same-commit EngineImage
  metadata;
- describing a previously observed live-only CoreDNS selector as desired state
  without reinspection and a declarative design; or
- draining, deleting, reconciling, or changing external state without explicit
  authority for that mutation.

## Rollback and exact revision proof

Normal rollback is a reviewed Git revert, followed by Flux reconciliation and
service-specific proof. A reverted root addition remains live until explicitly
retired because root pruning is disabled. Git also does not roll back host
files, router rules, provider objects, or application state.

For a deployed change, capture the merged commit and require the Flux source
artifact and relevant root/child `lastAppliedRevision` to contain that exact
commit. `Ready=True` without revision equality is insufficient. Then verify
node readiness, intended placement, controller readiness, volume health,
endpoints, routes, real client access, and any expected physical-service
degradation or recovery.

Report all live, host, application, and provider mutations separately, plus
every check that could not be completed.
