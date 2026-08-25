# Task brief: change application storage

Change storage for `[SERVICE]` only after proving data authority, exact object
identity, backup readability, writer quiescence, and migration/rollback behavior.

## Required inputs

- Service, namespace, controller, and active manifests: [values]
- Current mounts and data authority: [container paths, volumeMounts, subPaths]
- Current identity chain: [PVC UID, PV UID/reclaim policy, CSI handle/volume or NFS path]
- Current storage class/access mode/capacity and actual usage: [values]
- Target class/access mode/capacity/location: [values]
- Operation: [resize/migrate/rename/reclassify/retire/mount change]
- Writers, consistency group, and quiesce method: [inventory]
- Application export, independent backup, and content read test: [evidence]
- Backup coverage after the change: [mechanism and restore procedure]
- Downtime, copy/verify method, and point of no return: [details]

## Authorization

Fill every line with exact identities. Blank or ambiguous means no.

- Repository edits: [yes/no; PVC/controller/catalog/backup paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; volume/mount/backup inspection]
- Live cluster/host mutation: [yes/no; quiesce/copy/attach/resize scope]
- Application-state mutation: [yes/no; exact quiesce/export/migration operations]
- External/provider mutation: [yes/no; object-store/NFS/backup objects]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; exact old PVC/PV/volume/path/data]

Permission to edit a PVC manifest does not authorize changing or deleting the
bound live volume, NFS path, object-store data, or application database.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `service-lifecycle`, `service-catalog`,
`configuration-ownership`, `storage-recovery`, `backup-restore`, and `validation`;
load `secrets-sops` when encryption keys are involved and `juicefs-media` for any
JuiceFS operation. Read architecture storage classes, service-operations
stateful-change and exact-identity guidance, the service recovery runbook,
cluster-operations for node/Longhorn behavior, and the JuiceFS manual when needed.

## Workflow

1. Prove the active controller and actual mounts. Trace each data path through
   volume/claim/template to exact live PVC/PV/CSI/NFS/object-store identity. Verify
   reclaim policy, attachments, owner, and every writer.
2. Classify data correctly: small application/database state normally uses
   Longhorn RWO; organized media can use JuiceFS RWX; active downloads may use
   transient Pi NFS; Syncthing has its dedicated protected pattern. Do not place a
   database in JuiceFS merely because it is shared. A new NFS path has no automatic
   backup.
3. Verify authoritative-copy and backup semantics. JuiceFS B2 data is a primary
   copy, not an independent backup. A Longhorn replica, snapshot, retained PV, or
   local copy is not an independent off-site recovery point.
4. Produce a readable application export and exact-volume independent backup.
   For multi-PVC applications, quiesce or use a documented consistency strategy.
5. Plan target provisioning, copy, checksum/application verification, cutover,
   rollback, and old-data retention before mutation. Treat a PVC rename as a new
   volume; do not force immutable fields.
6. Change manifests, catalog data/protection intent, and backup registration
   together. Independently verify catalog claims against actual mounts/classes;
   a compiler pass does not prove storage truth.
7. Run complete validation. If authorized, quiesce writers, repeat writer
   inventory, execute the minimum migration, and verify mounts, permissions,
   capacity, application reads/writes, state integrity, backup inclusion, and
   exact merged revision.
8. Retain old storage until the new path and recovery proof pass. Destroy exact
   old objects only with destructive authorization after checking identity again.

## Hard stops

Stop for ambiguous storage identity, active/unknown writer, shared NFS/object
path, missing application export or off-site backup/read test, unsupported shrink,
forced immutable-field change, database-on-JuiceFS shortcut, unplanned multi-PVC
consistency, missing encryption key, false catalog classification, or destructive
scope that names a label/path but not exact live objects.

## Rollback and recovery

Define the cutback point, old mount/PVC/volume retention, reverse-copy safety,
application binary/schema compatibility, and exact export/backup restore. Account
for writes after cutover; do not reconnect two writable authorities. Root pruning
will not clean old objects automatically.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return before/after mount and identity chains, writer inventory, authority and
backup classification, export/backup/read-test proof, migration/copy verification,
manifest/descriptor/generated diffs, validation results, live mutations, retained
old objects, and exact functional/backup acceptance without exposing secrets.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] After an authorized cutover, the target is the single intended data
      authority with correct mount/access semantics; otherwise the cutover remains
      an explicit unexecuted phase.
- [ ] Application export and independent backup were read-tested before mutation.
- [ ] Writers and multi-volume consistency were controlled through cutover.
- [ ] Catalog protection claims match real mounts and backup objects.
- [ ] Full validation and, if authorized, exact-revision read/write/recovery checks pass.
- [ ] Old data remains retained or is destroyed only by exact explicit authority.
