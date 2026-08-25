# Task brief: perform planned node maintenance

Perform `[MAINTENANCE]` on `[NODE]` with an explicit outage model, safe workload
drain, storage protection, host rollback, and exact recovery proof. Read-only
preflight does not authorize cordon, drain, restart, package change, or reboot.

## Required inputs

- Exact node name, host identity, role, and physical services: [values]
- Maintenance reason, commands/change class, and upstream advisory: [details]
- Window, expected duration, outage budget, and operator contact: [times]
- Current controllers, singleton workloads, PDBs, and local resources: [inventory]
- NFS, DNS, DHCP, ingress, WireGuard, SMB, Syncthing, device roles: [inventory]
- Longhorn node/disks/replicas/attachments and drain policy: [evidence]
- Latest independent backups and required application exports: [identities/read tests]
- Other-node capacity, architecture support, and dependency health: [evidence]
- Host config backup, syntax/preflight checks, and rollback command path: [details]
- Go/no-go, abort, and service-acceptance signals: [criteria]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact policy, host, placement, docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and required checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; preflight and observation scope]
- Live cluster/host mutation: [yes/no; cordon, drain, package, restart, reboot scope]
- Application-state mutation: [yes/no; exact quiesce or settings operations; normally no]
- External/provider mutation: [yes/no; router, DHCP, DNS, alerting objects]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; exact local data or registration; normally no]

Maintenance authority for one node or service does not authorize changes to the
other node, Longhorn policy, provider state, application data, or credentials.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `cluster-operations`, `node-host-operations`,
`network-services`, `storage-recovery`, `backup-restore`, `incident-response`,
`observability`, and `validation`. Read cluster-operations planned maintenance,
architecture failure domains, the runbook planned-maintenance and backup
sections, and JuiceFS operations when mounts or cache are involved.

## Workflow

1. Record exact Git/Flux revisions and establish a clean incident baseline:
   nodes, controllers, pods, recent events, Flux owners, Longhorn, backups,
   network services, NFS, JuiceFS, and observability. Resolve existing degradation
   before attributing it to maintenance.
2. State the physical outage, not merely movable pods. Pi maintenance removes
   its NFS data, public ingress target, WireGuard, SMB, Syncthing, and one DNS
   endpoint. Beelink maintenance removes the control plane, DHCP, and one DNS
   endpoint. List any pinned singleton that will remain unavailable.
3. Prove the other failure domain has capacity, architecture support, healthy
   endpoints, independent name resolution, and needed data access. Verify current
   off-site backups and readable exports for state at risk.
4. Review the current Longhorn drain policy, replica health, attachment state,
   PDBs, emptyDir/local data, DaemonSets, host-network listeners, and shared RWO
   controllers. Define exact blockers and the abort point.
5. Cordon the exact node only with live authority. Run the documented server-side
   dry-run drain and review every object. A blocked drain is evidence to resolve,
   not permission to add force or weaken policy.
6. Drain only within the approved scope. Do not discard emptyDir data or force
   unmanaged pods until every exact file and owner is classified and explicitly
   authorized.
7. Apply host maintenance through the supported host path. For tracked config,
   use the exact clean merged revision and repository helper. Validate syntax and
   save the approved rollback copy before reload/restart. Package or reboot work
   must preserve OS-specific policy and avoid unreviewed automatic reboot.
8. After the node returns, prove host identity, time, listeners, mounts, K3s
   Ready state, labels/taints, platform DaemonSets, Longhorn health, NFS/JuiceFS,
   and physical services before uncordoning.
9. Uncordon deliberately and watch rescheduling, attachments, endpoints, and
   alerts. Verify real DNS/DHCP/NFS/WireGuard/SMB/Syncthing or application paths
   relevant to the node.
10. Confirm Flux remains at the expected exact revision, remove temporary
    silences, and compare the final baseline with pre-maintenance state.

## Hard stops

Stop for a failed backup/read test, last healthy replica, unexplained node or
Flux degradation, insufficient other-node capacity, unknown local data, a dry-run
drain blocker, unsupported package/K3s procedure, or ambiguous rollback.
Do not weaken Longhorn drain policy, use force, bulk-delete pods, clear JuiceFS
cache under a live mount, broaden NFS trust, or run fresh-install K3s helpers as
an upgrade.

Beelink replacement/datastore recovery and production Syncthing disaster
recovery remain unsupported; a maintenance window does not make them routine.

## Rollback and recovery

- Scheduling: keep the node cordoned on failed return; move back only workloads
  whose data and dependencies are proven.
- Host: restore the exact saved config/package state through its supported
  syntax and service path.
- K3s: do not attempt a fresh reinstall over existing state; stop at the
  unsupported recovery boundary.
- Storage: halt on degraded replicas or attachments and use supported Longhorn
  recovery with current backups.
- Network/physical: restore exact listeners, exports, router/DNS ownership, and
  peer behavior without running conflicting DHCP services.
- Git/provider/application: reverse each separately; maintenance rollback is not
  accomplished by a Git revert alone.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return pre/post revisions and health baseline, outage statement, backup/read
tests, target capacity, dry-run and actual drain results, host change and backup,
restart/reboot observations, node/platform/storage recovery, physical-service
and client tests, alert/silence status, all mutations, and unresolved deviations.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] Expected physical and workload outages are explicit and accepted.
- [ ] Backups, other-node capacity, replicas, and dry-run drain pass before work.
- [ ] Host/K3s work follows a supported procedure with a concrete rollback.
- [ ] Node, storage, mounts, listeners, workloads, and client paths recover.
- [ ] Temporary controls are removed and final state matches the expected revision.
- [ ] No safety policy is weakened to force maintenance through.
