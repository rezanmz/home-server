# Task brief: remove an agent node

Permanently remove `[NODE]` from the cluster only after all application,
Longhorn, NFS, network, and physical-service dependencies have moved or been
explicitly retired. This brief must never be used for the Beelink server.

## Required inputs

- Repository and exact base revision: [path and commit]
- Exact agent node name, machine identity, address, and physical owner: [values]
- Reason, removal date, maintenance window, and disposition of the hardware: [details]
- Workloads, selectors, affinities, host ports, devices, and local paths: [inventory]
- RWO claims and controllers that must move together: [inventory]
- Longhorn node, disks, replicas, attachments, capacity, and backup state: [evidence]
- NFS exports, DNS, WireGuard, SMB, Syncthing, ingress, and router roles: [inventory]
- Host configs, DHCP reservations, monitoring, credentials, and provider objects: [inventory]
- Replacement node or target failure domain and tested capacity: [details]
- Data retention, backups/read tests, and abort criteria: [evidence]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; placement, host, storage, catalog, docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target and state]
- Merge: [yes/no; exact PR and required checks]
- Read-only cluster/host access: [yes/no; exact node and dependent systems]
- Live cluster/host mutation: [yes/no; cordon, drain, evacuation, uninstall, metadata scope]
- Application-state mutation: [yes/no; exact peer, folder, share, or service identity]
- External/provider mutation: [yes/no; router, DHCP, DNS, peer, inventory objects]
- Destructive actions: [yes/no; exact node registration, host data, volumes, credentials]

Drain or hardware-removal intent does not imply permission to delete PVCs,
replicas, NFS trees, backups, Secrets, peers, or provider records.

## Manuals and skills

Load `home-server-safety`, `cluster-operations`, `node-host-operations`,
`network-services`, `storage-recovery`, `backup-restore`, `retained-artifacts`,
`high-risk-review`, and `validation`. Read cluster-operations permanent-agent
removal and replacement, architecture failure domains, service-operations
stateful gates, the runbook, and JuiceFS operations when the node has mounted
media. Use add-before-remove whenever replacement capacity is required.

## Workflow

1. Prove `[NODE]` is an agent and not the Beelink server. Record exact desired
   state, Flux owners, live node UID, host identity, and any unexplained drift.
2. Build a complete dependency matrix from controllers, pods, affinity,
   EndpointSlices, PVC/PV/VolumeAttachment, Longhorn nodes/replicas, NFS exports,
   host listeners, router rules, credentials, monitoring, and application state.
   A pod inventory alone is insufficient.
3. If replacing capacity, fully admit the uniquely named replacement first.
   Verify architectures, target resources, NFS access, JuiceFS prerequisites,
   Longhorn capacity, and a representative workload before moving production.
4. Migrate or retire physical services before draining. For the Pi role this
   includes NFS data, DNS endpoint, ingress target, WireGuard, SMB, Syncthing
   identity/data/backup, and router state. A production Syncthing recovery path
   is not established by the disposable restore proof.
5. For every stateful workload, prove a current independent backup and readable
   export where applicable. Move controllers that share an RWO claim as one
   placement unit, then verify detach/attach, data reads/writes, and backup
   coverage at the new placement.
6. Cordon the exact node. Run the documented server-side dry-run drain and
   classify every blocker. Do not weaken Longhorn drain policy, force deletion,
   or discard local files to make the output disappear.
7. Perform the reviewed drain only after blockers are resolved. Confirm no
   ordinary or singleton workload, attachment, local-path dependency, or
   physical network role remains unintentionally tied to the node.
8. Evacuate Longhorn through supported node/disk resources. Prove zero replicas,
   attachments, volume affinity, or recovery dependency remains before removing
   Longhorn participation. Do not lower replica counts to manufacture success.
9. With explicit host/live authority, uninstall the agent and remove the exact
   Kubernetes registration metadata in the documented order. Preserve evidence
   needed to distinguish a future replacement from a stale same-name join.
10. Remove or update repository host config, placement, NFS client permission,
    DHCP reservation, monitoring, and external objects as separate reviewed
    changes. Run complete validation and prove the exact merged revision.
11. Destroy or repurpose host disks and credentials only under exact destructive
    authority after a repeated writer/identity check.

## Hard stops

Stop if the target is the Beelink, owner identity is ambiguous, a writer or
attachment remains, the node holds a last healthy Longhorn replica, replacement
capacity is unproven, NFS or physical services have no migration, or recovery
evidence is missing. Do not use force drain, broad deletion, replica-count
reduction, raw Longhorn object patches, or a label selector as destruction scope.

Do not infer production Syncthing recovery, Beelink restoration, K3s server
migration, or datastore recovery from the agent-removal procedure.

## Rollback and recovery

- Placement: retain prior selectors and a controlled cutback plan until moved
  workloads pass real operations and backup checks.
- Node scheduling: if drain fails safely, keep the node cordoned, stop, and
  restore workloads only after the blocker is understood.
- Longhorn: halt evacuation on degraded health; do not delete replicas. Re-admit
  the disk/node only through supported resources if removal has not completed.
- Host/K3s: uninstall is a late boundary; after it, recovery is fresh admission
  with a unique identity, not an assumed same-name rollback.
- Physical services: preserve old NFS, DNS, WireGuard, SMB, Syncthing, and
  router state until the replacement path is accepted, but never run conflicting
  DHCP or listener ownership.
- Git/provider/data: use reviewed Git reversals and exact external/data recovery;
  neither plane automatically restores the other.

## Evidence contract

Return the exact node identity, base/merged/Flux revisions, full dependency
matrix, backup/read-test evidence, replacement admission, dry-run and real drain
results, workload placement and functional checks, Longhorn zero-dependency
proof, host uninstall/registration status, physical-service migrations,
repository/provider/destructive actions, validation, and retained rollback state.

## Acceptance criteria

- [ ] The target is proven to be an agent and every dependency is inventoried.
- [ ] Replacement capacity and all physical-service migrations pass before removal.
- [ ] Stateful moves have current independent recovery and functional proof.
- [ ] Drain and Longhorn evacuation complete without weakened safeguards.
- [ ] No workload, attachment, replica, export, route, or credential depends on the node.
- [ ] Host, Git, cluster, provider, and data cleanup stay within separate authority.
- [ ] Beelink/control-plane and unsupported Syncthing recovery are excluded.
