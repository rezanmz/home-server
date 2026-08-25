# Task brief: verify backups

Verify that `[SERVICE/DATASET]` has the expected independent, current, readable
recovery point. Do not treat a replica, snapshot, retained PV, or primary object
store as an independent backup.

## Required inputs

- Service/dataset and recovery objective: [what must be recoverable]
- Authoritative data stores and exact identities: [PVC/volume/NFS/remote paths]
- Declared catalog protection and backup jobs/targets: [paths/objects]
- Required freshness/retention: [policy, not guessed]
- Expected backup class: [Longhorn remote/application export/Restic/other]
- Encryption/key recovery dependencies: [redacted locations]
- Required proof level: [metadata/content read/disposable restore]
- Restore target and cleanup plan: [if restore is in scope]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; backup registration/docs fixes]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Read-only cluster/host access: [yes/no; backup/volume/job inspection]
- Live cluster/host mutation: [yes/no; create backup/restore/test workload]
- Application-state mutation: [yes/no; exact restore login/read/write scope]
- External/provider mutation: [yes/no; B2/backup repository operations]
- Destructive actions: [yes/no; exact disposable restore cleanup only]

Read-only verification does not authorize triggering a backup, mounting a restore,
changing retention, deleting snapshots/backups, or downloading secret material.

## Manuals and skills

Load `home-server-safety`, `backup-restore`, `storage-recovery`,
`service-lifecycle`, `service-catalog`, and `secrets-sops` for recovery
identities; load `juicefs-media` when relevant and `validation` for any repository
correction. Read architecture storage/backup boundaries, service-operations
stateful gates, the exact service
restore procedure in the runbook, cluster-operations for Longhorn, and the
JuiceFS manual when relevant.

## Workflow

1. Trace the service's actual volumeMounts to exact authoritative storage. Compare
   manifests and live objects with the descriptor; do not accept catalog
   `protection` as proof of real inclusion.
2. Identify the independent recovery mechanism for every authoritative store.
   Note explicitly that Longhorn replicas/snapshots/retained PVs are not off-site
   backups, JuiceFS object data is its primary copy, and ordinary Pi NFS paths are
   unprotected unless a specific backup covers them.
3. Inspect schedule/job/controller status, target health, credentials only by
   metadata, exact source volume/path, latest successful completion, size, and
   retention. Distinguish “job ran” from “this dataset was included.”
4. Perform a non-secret content read test supported by the backup mechanism. For
   an application export, parse or inspect representative content. For an
   encrypted backup, prove the existing recovery identity can read it without
   disclosing key or data.
5. If a disposable restore is explicitly authorized, restore to an isolated
   target with no production writers/routes, verify login plus representative
   read and safe write, then clean up only exact disposable objects covered by
   destructive authorization. Do not reuse its cleanup procedure for production.
6. Record gaps as failures. If repository correction is authorized, update backup
   registration/catalog intent and run complete validation; do not claim coverage
   until a new qualifying backup and read test exist.

## Hard stops

Stop for ambiguous source identity, unhealthy target, missing recovery key,
latest status not successful, suspiciously empty/partial content, schedule without
dataset inclusion, shared production restore target, unknown writer, absent live/
provider authority for a restore, or any request to delete old recovery points
without an explicit retention/destructive decision.

## Rollback and recovery

Verification should be read-only unless the matrix says otherwise. For a test
restore, define isolation, cleanup identities, and how to preserve evidence on
failure. For repository changes, retain prior schedule/target configuration and
avoid deleting existing backups until replacement coverage is proven.

## Evidence contract

Return an authority-to-backup matrix with exact non-secret identities, declared
versus actual inclusion, last qualifying completion, target/retention health,
content-read or restore-test result, key dependency, gaps, authorized mutations,
and cleanup status. Do not report filenames or content when sensitive.

## Acceptance criteria

- [ ] Every authoritative dataset maps to an independent recovery mechanism or an
      explicit uncovered-risk finding.
- [ ] The newest qualifying backup meets declared freshness and completed successfully.
- [ ] Dataset inclusion and readable content are proven, not inferred from schedule status.
- [ ] Restore prerequisites, including encryption identities, are available and protected.
- [ ] Any test restore is isolated, verified, and cleaned up only within authority.
