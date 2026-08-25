# Task brief: design Syncthing disaster recovery

Design and review a production Syncthing disaster-recovery procedure that joins
file data, device identity/configuration, encrypted backup history, application
version, network role, and cutover control. The default outcome is a procedure
and isolated rehearsal plan, not a production restore or peer mutation.

The existing disposable Restic restore proof validates important backup
properties but does not yet establish production disaster recovery.

## Required inputs

- Repository and exact reference revision: [path and commit]
- Disaster scenario and recovery objectives: [Pi loss, NFS corruption, config loss, values]
- Authoritative NFS file-data export, UID/GID/modes, folders, and writers: [inventory]
- Syncthing config/identity PVC, PV, CSI/Longhorn volume, and backup: [identities]
- Current Syncthing immutable image/version and config-schema compatibility: [evidence]
- Device ID and protected cert/key/config/index dependencies: [fingerprints/locations only]
- Restic repository ID, B2 prefix/key identity, password custody, and trusted tag: [redacted facts]
- Exact trusted snapshot ID, source canary, folder policy, check/read-test results: [evidence]
- Replacement NFS host/export and Longhorn/Kubernetes target: [design inputs]
- Peers, folder types, introducers, discovery/relay/NAT, ports, and router state: [inventory]
- Cross-plane recovery-point consistency and acceptable data-loss window: [analysis]
- Isolated rehearsal environment, actual disposable NFSv4.2 export, synthetic
  peer, and no-contact controls: [details]
- Production cutover, fencing, abort, and rollback owner: [details]

Do not include Restic passwords, B2 secrets, Syncthing private keys, GUI/API keys,
device membership dumps, or private file content in this prompt.

## Authorization

Fill every line. Blank or ambiguous means no. The suggested default for live,
host, external, and destructive scopes is no.

- Repository edits: [yes/no; procedure, scripts, tests, backup, SOPS, docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target and draft/ready]
- Merge: [yes/no; exact PR and required checks]
- Read-only cluster/host access: [yes/no; Syncthing, NFS, Longhorn, Restic scope]
- Live cluster mutation: [yes/no; exact disposable/production resources; default no]
- Host mutation: [yes/no; exact NFS/export/filesystem hosts; production default no]
- Application-state mutation: [yes/no; exact Syncthing/UI/API/peer state; default no]
- External/provider mutation: [yes/no; exact B2, router, peer-distribution objects]
- Destructive actions: [yes/no; exact disposable or production data/identity]

Design permission does not authorize restoring into the production export,
starting a duplicate device identity, reconnecting peers, changing router state,
revoking keys, pruning Restic, or deleting old file/config data.

## Manuals, skills, and primary research

Load `home-server-safety`, `network-services`, `backup-restore`,
`storage-recovery`, `application-state`, `secrets-sops`,
`node-host-operations`, `cluster-operations`, `incident-response`,
`high-risk-review`, and `validation`.

Read the current repository [runbook backup and Syncthing sections](../docs/runbook.md),
[architecture](../docs/architecture.md), [cluster operations](../docs/cluster-operations.md),
and [service operations](../docs/service-operations.md). Inspect the active
Syncthing workload, pruning backup child, fail-closed backup script, folder
policy, source canary, Longhorn backup, and current application image.

Research current primary sources at task time:

- [Syncthing configuration and device identity](https://docs.syncthing.net/users/config)
- [Syncthing FAQ, including why sync is not backup](https://docs.syncthing.net/users/faq.html)
- [Restic repository integrity checks](https://restic.readthedocs.io/en/stable/045_working_with_repos.html#checking-integrity-and-consistency)
- [Restic snapshot restoration](https://restic.readthedocs.io/en/stable/050_restore.html)

Record access dates and applicable application/backup versions. Resolve current
upstream behavior against the repository's pinned images and scripts rather than
assuming the latest docs match an older recovery artifact.

## Threat and failure model

Cover at least:

- loss or corruption of the Pi-local NFS file tree;
- loss of the Longhorn config/identity volume independently of file data;
- an intact file snapshot paired with stale folder config or a different device ID;
- restored cert/key creating an active duplicate of the same device identity;
- generating a new identity that peers do not trust or that loses folder membership;
- selecting an untrusted candidate, wrong tag, wrong repository, or wrong prefix;
- source-canary mismatch, substituted/empty NFS root, excluded folders, or path overlap;
- Restic password/key loss, repository corruption, interrupted partial restore,
  stale locks, or concurrent backup/check/prune/restore operations;
- Syncthing version migrating config/index so rollback becomes incompatible;
- restored old files reconnecting and propagating deletes/conflicts to peers;
- permissions, ownership, symlink, marker, root_squash, or filesystem-watch errors;
- global discovery, relays, or automatic router mapping exposing a rehearsal;
- file/config backup timestamps that do not form a coherent recovery point; and
- old and replacement Pi/network listeners operating simultaneously.

Distinguish recovery of file content, configuration, cryptographic identity,
index/cache, peer trust, network service, and backup continuity.

## Design workflow

1. Build a four-part immutable recovery manifest:
   - NFS file data: exact export/path identity, source canary, folder IDs/paths,
     UID/GID/modes, writer inventory, and trusted Restic snapshot ID;
   - Syncthing config/identity: exact PVC/PV/Longhorn backup, device-ID
     fingerprint, config/cert/key/index contents, and timestamp;
   - Backup history: expected Restic repository ID, B2 prefix/key identity,
     password custody, trusted tag, folder policy, and integrity-check evidence;
   - Runtime/network: exact Syncthing image digest/version, schema compatibility,
     node/host-port placement, discovery/relay/NAT policy, router, and peers.
2. Define cross-plane consistency. Restic protects NFS file data; Longhorn
   protects configuration and identity. Neither alone restores production.
   State how a snapshot pair is selected and what configuration/file changes can
   be lost or safely rebuilt.
3. Prove repository identity and choose one exact trusted snapshot, never a
   floating `latest` without the trusted host/path/tag constraints. Require the
   source canary, folder-ID inclusion/exclusion policy, structural check, bounded
   or full data read, and a successful isolated file restore.
4. Define recovery of the Longhorn config/identity volume with the original
   device cert/key. Treat the private key as a secret and the device ID as a
   stable external identity. Do not generate a replacement unless the plan
   explicitly covers re-authorization by every peer as a different device.
5. Pin a Syncthing application version compatible with the restored config and
   index. Determine whether the index can be rebuilt from files and peers, which
   files are essential identity/configuration, and what startup may migrate.
6. Design replacement NFS storage with exact child export, root_squash, UID/GID,
   marker files, capacity, permissions, and the durable source canary. Restore to
   a new empty target; never overlay an interrupted restore on an unclassified
   production tree.
7. Fence the old Syncthing instance, NFS writers, backup jobs, host ports, router
   mapping, discovery, relays, and peers before a future cutover. There must be
   exactly one active instance of the restored device identity.
8. Define real production cutover order: quiesce/fence old writers; restore and
   verify NFS content; restore config/identity; mount exact paths; start the
   compatible application with peer traffic blocked; verify local folders/index;
   enable peers incrementally; inspect conflicts/deletions; restore client access;
   then establish a new trusted backup and freshness baseline.
9. Keep the pruning backup child and Restic repository stable throughout design.
   Never use automatic unlock, no-lock mode, repository reinitialization,
   candidate promotion, forget/prune, or key revocation as recovery shortcuts.
10. Add fail-closed scripts/tests only when repository edits are authorized.
    Reject wrong repository ID, candidate snapshot, canary mismatch, folder
    policy drift, active backup job, non-empty restore target, duplicate device
    identity, unexpected peer egress, incompatible image, or ambiguous NFS path.
11. Run complete validation and security review. Produce a future production
    execution checklist with named authority gates; do not execute it in this
    design task.

## Isolated rehearsal

Restore the exact trusted Restic snapshot into a uniquely named disposable
NFSv4.2 export that reproduces the production child-export boundary,
`root_squash`, UID/GID mapping, mount options, ownership/modes, markers, and
failure behavior. A local directory with NFS-like permissions is only a partial
file test and cannot promote production disaster recovery. Restore a copy of the
matching Longhorn config/identity backup into a separate disposable claim. Use
the pinned Syncthing image and preserve the original device-ID fingerprint.

Block all production peer, discovery, relay, router, LAN host-port, and provider
connectivity before starting the identity clone. Prefer a synthetic peer and
disposable credentials to test protocol behavior. Verify canary, folder IDs and
paths, markers, permissions, file counts/checksums, config schema, device ID,
index/scan and filesystem-watcher behavior, root-squash writes, mount/reconnect
behavior, GUI boundary, and absence of unexpected writes/deletes.

Exercise negative cases: wrong repository ID, wrong password/key, candidate
snapshot, missing/excluded folder, changed canary, partial restore, incompatible
image, duplicate-identity reachability, and active concurrent Restic job.

The existing file-only restore proof may be reused as one test component, but
the rehearsal is incomplete until restored config/identity and application
startup are tested together under network isolation.

## Hard stops and abort gates

Stop for uncertain NFS/PVC/backup identity, absent config-volume backup, missing
device key or Restic password, non-trusted snapshot, failed integrity/read test,
active writer/job, non-empty target, incompatible application version, duplicate
identity exposure, peer traffic that cannot be blocked, or unbounded deletion/
conflict risk.

If an actual isolated NFSv4.2 export with the production security and mount
semantics is unavailable, the file restore may be useful evidence but production
Syncthing disaster recovery remains unsupported.

Do not restore in place, generate a new device key silently, start two copies of
one identity, enable automatic NAT mapping, connect a rehearsal to real peers,
initialize a replacement Restic repository, or call file-only readiness
production disaster recovery.

## Rollback and recovery

- Design/repository: revert procedure/scripts through protected review; leave
  active backup owner and repository unchanged.
- Rehearsal: stop the isolated identity before network changes, preserve logs,
  and remove only exact disposable claims/files/credentials under authority.
- NFS data: retain the original tree and one writer authority. Account for
  post-cutover writes before returning to it.
- Config/identity: retain the original Longhorn volume/backup. Never allow old
  and restored copies of the same device key online together.
- Application version: preserve the pre-cutover immutable image and avoid
  irreversible config migration before the rollback boundary.
- Restic/B2: do not mutate or prune history during restore; preserve repository
  ID, password, canary, and old key until fresh post-cutover proof passes.
- Network/peers: reverse exact host ports/router state and reconnect peers
  incrementally; a Git revert cannot undo peer or application state.
- Future production: if cutover aborts, fence the replacement, restore old
  NFS/config pairing, verify identity and file authority, then resume one side.

## Evidence contract

Return repository/upstream research revisions, failure model, four-part recovery
manifest, exact Restic and Longhorn recovery IDs, key/device fingerprints,
cross-plane RPO analysis, compatible image evidence, isolated file/config/
identity rehearsal, negative gates, production fencing/cutover design, validation
and security findings, measured restore/scan behavior, all actions, and gaps.
Never expose key values or private file content.

## Acceptance criteria

- [ ] NFS file data, Longhorn config/identity, Restic history/canary, and pinned
      Syncthing runtime/network identity are separately and jointly modeled.
- [ ] One exact trusted snapshot and one compatible config-volume recovery point
      form an explicit, evidence-backed recovery set.
- [ ] Device identity is preserved without duplicate online instances.
- [ ] Isolated rehearsal combines an actual production-equivalent NFSv4.2
      export, file restore, config/identity, and application startup while
      blocking real peers and providers.
- [ ] Production fencing, NFS restore, peer reconnection, backup re-baseline,
      abort, and rollback are designed in order.
- [ ] Production execution remains separately authorized and file-only proof is
      not overstated as disaster recovery.
- [ ] The procedure becomes supported only after reviewed rehearsal evidence exists.
