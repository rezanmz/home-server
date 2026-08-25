# Task brief: add an agent node

Add a fresh K3s agent to the home-server cluster without weakening host identity,
storage, scheduling, or physical-service boundaries. This brief is not a
Beelink replacement, control-plane expansion, or existing-node recovery plan.

## Required inputs

- Repository and base revision: [path and exact branch/commit]
- Proposed unique node name, role, architecture, and operating system: [values]
- Hardware, system disk, intended Longhorn disk, and capacity: [inventory]
- LAN address, DHCP reservation, routes, and required node-to-node ports: [facts]
- Physical-console access and expected Ed25519 host-key fingerprint: [evidence]
- Existing K3s unit/data-directory state: [absent, with read-only proof]
- Repository host config and fresh-agent helper to use: [paths]
- Workloads, devices, NFS exports, or network roles intended for this node: [list]
- JuiceFS/FUSE/cache and other host prerequisites: [list]
- Bootstrap-token handling and expiry/revocation plan: [non-secret procedure]
- Admission checks, maintenance window, and rollback owner: [details]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact host, K3s, placement, docs, and policy paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target and draft/ready]
- Merge: [yes/no; exact PR and required checks]
- Read-only cluster/host access: [yes/no; existing nodes and candidate host]
- Live cluster/host mutation: [yes/no; exact install, join, label, taint, storage operations]
- Application-state mutation: [yes/no; exact service/device objects; normally no]
- External/provider mutation: [yes/no; DHCP, router, DNS, inventory objects]
- Destructive actions: [yes/no; exact candidate-host data or stale registration]

Repository permission does not authorize first contact with the host, K3s
installation, token creation, uncordoning, Longhorn admission, or provider work.

## Manuals and skills

Load `home-server-safety`, `cluster-operations`, `node-host-operations`,
`network-services`, `storage-recovery`, `backup-restore`, `secrets-sops`,
`high-risk-review`, and `validation`. Read the cluster-operations node-admission
procedure, architecture failure domains, the runbook access/storage sections,
and the JuiceFS manual when the node will mount or cache media. Manuals and the
repository helper's fail-closed behavior are authoritative.

## Workflow

1. Prove this is a new agent, not a Beelink replacement, server promotion,
   existing K3s repair, or same-name shortcut. Record exact Git state and inspect
   the candidate locally before any SSH or copy operation.
2. From an authenticated physical console, obtain the candidate's Ed25519
   fingerprint. Compare it character for character from the workstation before
   trusting SSH. Do not accept an unauthenticated key scan.
3. Preflight unique hostname and machine identity, time, architecture, OS,
   disks, mounts, firewall, LAN address, routes, name resolution, and required
   bidirectional K3s traffic. Prove there is no existing K3s service or data
   directory and no legacy data tree that the install could overwrite.
4. Inventory every workload and physical role proposed for the node. Verify
   immutable image architecture support, device and host-path availability, NFS
   export permissions, UID/GID behavior, JuiceFS prerequisites, and target
   Longhorn capacity before scheduling any application.
5. Add a host-specific repository config with an explicit agent role and a
   temporary admission taint. Keep labels minimal and factual. Run complete
   validation and review any privileged, host-network, sysctl, storage, or
   high-risk baseline change.
6. After protected merge, operate only from the exact clean merged revision.
   Use the repository's fresh-host-only helper and pinned installer path. Handle
   the one-time join token without committing, logging, or leaving it behind.
7. Follow the manual's admission sequence: after initial Ready/identity proof,
   cordon the node, remove only the bootstrap taint, and leave it cordoned while
   proving platform DaemonSets, CNI, node DNS independence, metrics, host policy,
   NFS access, JuiceFS prerequisites, and the complete Longhorn condition gate.
8. Confirm the Longhorn node and intended disk are discovered but correctly
   unschedulable while the Kubernetes node is cordoned. Prove required packages,
   mount propagation, kernel-module policy, capacity, MetalLB membership, and
   architecture-safe image pulls without lowering replica policy or moving
   production data.
9. Uncordon only after every admission condition passes. Then require the
   Longhorn node/disk to become schedulable, watch actual scheduling and all
   volumes for a reconciliation cycle, and run a controlled representative
   canary before moving material production workloads or replicas.
10. Revoke the short-lived bootstrap token and complete separately authorized
    DHCP/router/inventory changes. Prove Flux and relevant owners are at the
    exact merged revision and report any workload not tested on the node.

## Hard stops

Stop for a fingerprint mismatch, reused or ambiguous host identity, existing
K3s state, unknown system disk, legacy data at risk, unsupported architecture,
missing NFS/host prerequisites, unhealthy Longhorn, absent backup, or a token
that cannot be handled safely. Do not disable SSH verification, pipe a mutable
remote installer to a shell, reuse the Pi-specific helper generically, or remove
the admission taint early.

Do not use this procedure to replace the Beelink, restore its SQLite datastore,
join a second server, design control-plane HA, or upgrade an existing node.
Those operations are not established by the repository.

## Rollback and recovery

- Git/Flux: revert proposed host or placement intent through protected review;
  root-prune-disabled objects require explicit retirement.
- Candidate host: keep it cordoned, remove only the fresh agent installation
  using the documented helper path, and restore exact pre-install host state.
- Cluster identity: remove the exact node registration only after workloads,
  attachments, replicas, and physical dependencies are absent.
- Storage: evacuate only through supported Longhorn resources; never delete a
  disk or replica as rollback.
- Network/provider: reverse the exact DHCP, router, or inventory objects under
  separate authority.
- Secrets: revoke the exact bootstrap token without exposing it.

Define the abort point before installation. If identity, storage, or admission
proof fails, leave the candidate unschedulable and preserve evidence.

## Evidence contract

Return base and merged revisions, candidate fingerprint verification, fresh-host
proof, hardware/network inventory, repository and installed config comparison,
helper and token lifecycle results, node labels/taints, platform-pod readiness,
architecture checks, NFS/JuiceFS tests, Longhorn node/disk/replica evidence,
canary result, external actions, validation results, and rollback status.

## Acceptance criteria

- [ ] The host is authenticated, uniquely named, and proven fresh before install.
- [ ] The node joins only as an agent through the repository-pinned path.
- [ ] Admission taint/cordon prevents ordinary scheduling until every gate passes.
- [ ] Platform, network, storage, architecture, and recovery checks are complete.
- [ ] Flux and live intent match the exact merged revision where applicable.
- [ ] Token and external objects are handled only within explicit authority.
- [ ] No unsupported Beelink replacement, K3s upgrade, or server promotion occurs.
