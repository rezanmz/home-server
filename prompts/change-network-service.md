# Task brief: change a physical network service

Change or diagnose `[BLOCKY/KEA/STORK/WIREGUARD/NFS/SAMBA/SYNCTHING]` without
collapsing Kubernetes, host, application, router, and provider ownership into
one operation. Preserve the service's physical failure domain and real-client
recovery path.

## Required inputs

- Service, namespace, active Git owner, and live resource identities: [values]
- Current and desired protocol behavior: [DNS/DHCP/NFS/SMB/WireGuard/Syncthing facts]
- Node, interface, LAN address, host port, and PodCIDR dependencies: [inventory]
- Intended and denied client networks: [LAN/WireGuard/public/node/Pod ranges]
- Host files, exports, sysctls, listeners, and repository helpers: [inventory]
- Application-owned peers, users, shares, folders, identities, or settings: [inventory]
- Router, DHCP, DNS, or external provider objects: [inventory]
- PVC/PV/NFS paths, writers, recovery keys, and backup coverage: [evidence]
- Expected node/service outage and maintenance window: [details]
- Real-client acceptance and rollback signals: [tests]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; service, catalog, policy, host, SOPS paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and required checks]
- Read-only cluster/host access: [yes/no; nodes, listeners, mounts, logs]
- Live cluster/host mutation: [yes/no; rollout, export reload, peer/config scope]
- Application-state mutation: [yes/no; exact peers, users, folders, shares, or settings]
- External/provider mutation: [yes/no; exact router, DHCP, DNS, peer objects]
- Destructive actions: [yes/no; exact lease, peer, export data, identity, credential]

Permission to edit manifests does not authorize host reload, application-state
changes, router work, peer distribution, credential revocation, or data deletion.

## Manuals and skills

Load `home-server-safety`, `network-services`, `node-host-operations`,
`cluster-operations`, `service-catalog`, `network-auth`, `application-state`,
`storage-recovery`, `backup-restore`, `secrets-sops`, `high-risk-review`, and
`validation` as applicable. Read architecture traffic/failure domains, the
runbook DNS/DHCP and Pi-services sections, cluster-operations placement, service
operations, and JuiceFS operations when Samba or media mounts are involved.

## Workflow

1. Record exact Git/Flux revisions and prove the active Kustomization owner,
   including any pruning child such as the Syncthing backup owner. Inventory
   host-installed and application/provider state separately.
2. Establish a read-only baseline from every relevant client: listeners,
   EndpointSlices, pods, NetworkPolicy, mounts, PVC/PV/attachments, logs, DNS
   answers, leases/metrics, NFS exports, WireGuard handshakes/routes, SMB access,
   Syncthing connection/storage, and backup freshness.
3. Apply the service-specific contract:
   - Blocky serves node-address DNS; split-horizon application records are
     catalog-generated, no management route is allowed, and node resolvers stay
     independent of Blocky.
   - Kea remains tied to the Beelink interface and durable lease state. Stork is
     read-only monitoring and cannot become a DHCP availability dependency.
   - WireGuard remains tied to the Pi router target and exact Pi PodCIDR trust
     exception; never broaden it to the cluster PodCIDR.
   - NFS uses exact child exports with root_squash. A new path has no backup
     until independently registered and proven.
   - Samba and Syncthing remain Pi-bound. Syncthing identity/folders are
     application state, automatic router mapping stays disabled, and its backup
     child is validated independently.
4. Trace state and recovery before edits. Distinguish Longhorn configuration,
   Pi-local NFS data, JuiceFS media, transient downloads, and independent
   Syncthing Restic backup. Prove the exact writer and recovery point.
5. Make the smallest change in the authoritative plane. Change generated DNS
   through the descriptor/compiler, host exports through tracked host input,
   and peers/users/folders through supported application state. Do not duplicate
   one setting across planes.
6. Render catalog output and inspect all generated diffs. Run complete validation
   and review host-network, sysctl, capabilities, broad egress, NFS trust, and
   high-risk changes individually.
7. After protected merge, prove the exact Flux owner revision. Apply any host
   file from the exact clean merged revision with its helper, and mutate
   router/provider/application state only under their independent authority.
8. Roll out one failure domain at a time. Never overlap an old and new DHCP
   service or conflicting listener. Preserve one working DNS path and the old
   credential/peer while testing its replacement.
9. Repeat real-client tests from intended and denied networks. Verify state,
   metrics/alerts, mounts, writes where safe, and backup coverage, then remove
   old objects only under exact destructive authority.

## Hard stops

Stop for an ambiguous listener or owner, a second DHCP server, management API
exposure, node DNS dependence on Blocky, broadened WireGuard PodCIDR trust,
broad/overlapping NFS export, disabled root_squash, unknown writer, missing
backup/key, or an application/provider mutation without authority.

Do not revive retired Pi-hole, enable Syncthing automatic NAT mapping, treat
downloads as backed up, claim disposable Syncthing restore proves production
DR, or loosen privileged/high-risk policy merely to restore connectivity.

## Rollback and recovery

- Git/Flux: revert active manifests, descriptor intent, and generated output
  through review; root-prune-disabled objects need explicit cleanup.
- Host: restore the exact saved resolver/export/sysctl/service file and validate
  before reload.
- Application: restore WireGuard peers, Samba users/shares, or Syncthing state
  through supported interfaces and matching backups.
- Storage: retain the prior PVC/NFS path and one writable authority; do not
  delete or reverse-copy without exact writer accounting.
- Router/provider: reverse exact forwards, reservations, DNS records, or keys
  separately.
- Client: preserve prior profiles and leases long enough to prove cutback,
  without running conflicting DHCP services.

## Evidence contract

Return ownership by plane, exact revisions, baseline and final listeners,
client-path tests, state/writer/backup identity, manifest/descriptor/generated
diffs, host installed comparison, application/provider actions, validation and
high-risk results, physical outage observed, old-object disposition, and
plane-specific rollback readiness.

## Acceptance criteria

- [ ] The authoritative plane owns each changed setting exactly once.
- [ ] Physical node, interface, PodCIDR, export, and state boundaries are preserved.
- [ ] Full validation and exact-revision reconciliation pass for repository changes.
- [ ] Intended clients succeed and denied/unexposed paths remain denied.
- [ ] Data and backup semantics are proven rather than inferred from another path.
- [ ] No conflicting DHCP, unsafe NFS, broad WireGuard, or unsupported Syncthing action occurs.
