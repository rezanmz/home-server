# Task brief: move or repin a workload

Move `[WORKLOAD]` from `[CURRENT PLACEMENT]` to `[TARGET PLACEMENT]` while
preserving architecture support, state attachment, physical dependencies,
network reachability, and recovery. A schedulable pod is not necessarily an
available service.

## Required inputs

- Service/workload, namespace, controller, and active manifest owner: [identities]
- Current and target node/placement policy: [facts and desired rule]
- Reason for the move and acceptable downtime: [details]
- Container images and target architecture support: [verified evidence]
- PVCs, access modes, RWO-sharing controllers, and writer inventory: [list]
- Longhorn replicas, attachments, target capacity, and current backup: [evidence]
- NFS exports, JuiceFS mounts, host paths, devices, GPU, interfaces, and ports: [inventory]
- DNS, ingress, WireGuard, router, or node-address dependencies: [inventory]
- Catalog placement/protection declarations: [current and target intent]
- Canary, success signal, maintenance window, and cutback trigger: [details]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; workload, catalog, policy, host, docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and required checks]
- Read-only cluster/host access: [yes/no; nodes, storage, mounts, listeners]
- Live cluster/host mutation: [yes/no; rollout, cordon, attach, migration scope]
- Application-state mutation: [yes/no; exact UI/API storage, path, or identity changes]
- External/provider mutation: [yes/no; router, DNS, DHCP, peer objects]
- Destructive actions: [yes/no; exact old path, volume, or host resource]

A placement edit does not authorize host preparation, data copy, live patching,
provider changes, or deletion of the old data path.

## Manuals and skills

Load `home-server-safety`, `cluster-operations`, `service-lifecycle`,
`storage-recovery`, `backup-restore`, `service-catalog`, `network-services`,
`high-risk-review`, and `validation`; add `juicefs-media` for organized media.
Read cluster-operations placement/storage matrices, architecture failure
domains, service-operations stateful workflow, the affected runbook, and
configuration ownership when the move changes application-managed state.

## Workflow

1. Traverse active Kustomizations and Flux inventory to identify the exact
   controller and owner. Record desired placement, current observed node, exact
   revision, and any existing drift before changing anything.
2. Inventory all containers, init containers, sidecars, architectures, PVCs,
   mounts, RWO-sharing controllers, devices, host paths, interfaces, host ports,
   NFS exports, JuiceFS paths, LAN trusts, router rules, and external endpoints.
3. State the physical failure-domain change. DNS, DHCP, NFS, public ingress,
   WireGuard, SMB, Syncthing, hardware, and the control plane do not become
   portable because their pod specification can schedule elsewhere.
4. For stateful work, prove the exact independent off-site backup and readable
   application export. Require healthy Longhorn replicas, no conflicting
   attachment, and enough target-node storage before cutover.
5. Prepare host and NFS prerequisites through the separate host workflow and
   authority. Verify target architecture and a harmless dependency path before
   moving the production controller.
6. Change placement declaratively and update the colocated catalog descriptor
   when placement intent changes. Keep all controllers sharing one RWO claim in
   the same placement unit. Do not use an ad hoc nodeSelector patch.
7. Render generated intent, inspect diffs, and run the complete validation
   bundle. Review any new host-network, device, capability, affinity, egress, or
   high-risk finding rather than refreshing a baseline blindly.
8. After protected merge, prove the Flux source and exact owner applied the
   merged revision. Observe orderly detach/attach and rollout; stop on
   Multi-Attach, mount, replica, or architecture errors.
9. Verify intended node, endpoints, route conditions, client access, dependency
   reachability, representative data reads/writes, physical-service behavior,
   logs, and backup inclusion.
10. Retain old host/provider/data prerequisites until the new path passes. Remove
    them only under separate exact authority.

## Hard stops

Stop for an unsupported target architecture, missing device or export,
unhealthy/last Longhorn replica, unknown writer, stale backup, RWO controllers
that would split, ambiguous Flux owner, physical service that cannot move, or
an application/data migration without rollback. Do not force detach, delete
pods repeatedly, patch Longhorn internals, broaden NFS trust, or loosen placement
solely to make the scheduler succeed.

Do not describe moving the Beelink control plane or production Syncthing
disaster recovery as an ordinary workload move.

## Rollback and recovery

- Git/Flux: preserve the exact prior placement and immutable images; revert
  through review and account for root-prune-disabled leftovers.
- Workload: define a cutback signal and ensure the prior node remains admissible
  until acceptance.
- Storage: keep one writable authority, preserve the old volume/export, and
  account for writes after cutover before reversing.
- Host/network: restore exact host files, NFS permissions, listener ownership,
  and router/DNS objects separately.
- Application/provider: reverse UI or provider changes through their supported
  interfaces; a Git revert cannot do so.

## Evidence contract

Return active owner and exact revisions, before/after placement, architecture
proof, physical-dependency map, storage identity and writer inventory,
backup/read test, host preparation, manifest/descriptor/generated diffs,
complete validation, detach/attach and rollout observations, real-client and
read/write checks, external actions, retained old state, and cutback readiness.

## Acceptance criteria

- [ ] Target architecture, capacity, host, network, and physical dependencies pass.
- [ ] Every shared RWO controller moves as one unit with current recovery evidence.
- [ ] Desired placement and catalog intent agree and full validation passes.
- [ ] Exact merged revision, target placement, access, and data behavior are proven.
- [ ] Old prerequisites remain until accepted or are removed only with authority.
- [ ] No unsupported control-plane or Syncthing recovery procedure is implied.
