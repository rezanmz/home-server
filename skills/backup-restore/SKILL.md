---
name: backup-restore
description: Verify, create, read-test, rehearse, or restore home-server backups for Longhorn volumes, Syncthing Restic data, and application-managed state. Use for backup health, recovery-point proof, restore drills, disaster recovery, or a stateful-change backup gate; do not use for ordinary storage moves without a restore component.
---

# Backup verification and restore

A scheduled job, a policy label, a green replica, or an alert that has not fired
is not proof that recoverable data exists. Identify the exact recovery artifact
and prove that it can be read.

## Read the correct recovery contract

Start with:

- [Storage, backups, and restore procedures](../../docs/runbook.md#storage)
- [Backup observability](../../docs/runbook.md#backup-observability)
- [Service storage and recovery classes](../../docs/service-operations.md#storage-and-recovery-class)
- [Stateful change gates](../../docs/service-operations.md#4-add-storage)
- [JuiceFS recovery](../../docs/juicefs-media.md)
- [Longhorn backup desired state](../../infrastructure/longhorn/backups)
- [Syncthing Restic desired state](../../apps/syncthing/backups)

Read the relevant manifests and scripts as well as the manual. Discover the
current schedule, retention, repository, labels, canary, and image pins from
those files; do not copy mutable values from old reports or this skill.

## Authorization and blast radius

- Backup inventory, logs, status, and read-only repository inspection may be
  performed for a review or diagnosis.
- Creating an on-demand backup, unlocking a repository, pruning data, changing
  retention, running a restore, repointing a workload, stopping writers, or
  deleting a restored test volume is a mutation. It must be within the explicit
  request, and the exact target and side effect must be stated immediately
  before execution.
- A request to verify a backup does not authorize a restore into production.
- A request for a restore plan does not authorize stopping workloads or writing
  data.
- Never use production as the first restore test. Prefer an isolated namespace,
  disposable PVC, or other manual-defined rehearsal target.
- Never prune, forget, delete, unlock, or recreate a repository merely to make a
  freshness check pass. Repository locks and identity mismatches are incident
  evidence.

Do not expose SOPS age identities, Restic passwords, B2 credentials, Longhorn
backup-target credentials, application keys, or decrypted Secret values in
commands, logs, diffs, or the final report.

## Identify the data and protection system

Record the exact service, namespace, workload owner, PVC/PV/Longhorn volume or
host path, application data format, and all required encryption keys. Then
classify its actual protection:

- **Longhorn backup:** off-cluster volume backup governed by the Longhorn
  recurring-job and backup-target configuration.
- **Syncthing Restic backup:** file-level encrypted repository with its own
  repository identity, trusted snapshot/canary contract, job, and freshness
  check.
- **Application-managed backup:** database dump or application-native artifact
  whose consistency and restore procedure are application-specific.
- **JuiceFS media:** B2 is the primary authoritative object store, not an
  independent backup. Metadata and client-encryption recovery have separate
  procedures.
- **Replica, retained PV, local snapshot, or cache:** useful recovery material,
  but not an independent backup.
- **Transient NFS data:** assume no backup until a separate mechanism is proved.

Do not infer backup coverage from a similarly named PVC. Prove the exact volume,
selector/label membership, job outcome, remote artifact, and timestamp.

## Preflight

Before creating or restoring anything, establish:

1. The desired-state owner by following the active Kustomization chain.
2. The exact live identity with
   `ssh beelink 'sudo k3s kubectl ...'`; there is no supported local kubeconfig.
3. The consistency boundary: crash-consistent filesystem, stopped application,
   database-native dump, or documented application quiescence.
4. All writers, including CronJobs, maintenance jobs, sidecars, host services,
   and human access.
5. Recovery point objective and the immutable candidate ID, start/completion
   time, size, status, and source volume/repository identity.
6. Required SOPS, application, repository, and client-encryption identities.
   Possession of encrypted data without the matching identities is not
   recoverability.
7. Destination capacity, access mode, storage class, placement, isolation, and
   whether restoring could bind or overwrite a production claim.
8. Rollback for the restore itself. Preserve the current production state until
   restored data has been accepted.

## Verification workflow

### Longhorn

Use the current commands in the runbook and inspect the current Longhorn CRDs
rather than assuming field names from memory. Correlate the intended PVC to its
bound PV and Longhorn volume, then to a completed remote backup. Verify backup
target health and credentials without decrypting them into output.

For an ordinary stateful-change gate, prove at minimum:

- the exact volume is eligible for the configured recurring job;
- a recent backup for that exact volume completed successfully;
- the remote artifact is visible and has the expected source/size/timestamp;
- a read-test or isolated restore appropriate to the planned risk has succeeded.

Do not interpret Longhorn replica health as backup success.

### Syncthing Restic

Read the current CronJob, backup script, freshness script, and their regression
tests before running manual commands:

- [CronJob](../../apps/syncthing/backups/cronjob.yaml)
- [Backup script](../../apps/syncthing/backups/backup.sh)
- [Freshness CronJob](../../apps/syncthing/backups/freshness-cronjob.yaml)
- [Policy tests](../../scripts/ci/test_syncthing_backup_policy.py)

Require the exact repository identity and trusted-snapshot/canary contract. A
partial backup, a snapshot from a different repository, or an untrusted newest
snapshot must not be promoted as recoverable. Do not clear locks automatically.

### Application-managed data

Use the service-specific section of the runbook. Confirm whether a dump is
inside the volume, copied off-volume, or both. A dump on the same failed volume
does not provide independent recovery. Preserve application encryption keys and
version compatibility; an image rollback may not reverse a database migration.

### JuiceFS

Use the distinct procedures in [docs/juicefs-media.md](../../docs/juicefs-media.md)
for mount recovery, metadata restore, client-encryption recovery, and key
rotation. Do not describe the B2 primary data set as its own backup, and do not
rotate or replace an encryption identity during a restore investigation.

## Restore rehearsal

Prefer an isolated restore before production recovery:

1. Create or identify a destination that cannot bind to the production
   workload, route, or Service.
2. Restore by immutable recovery-point ID, not “latest” after selection.
3. Keep production writers and the original data untouched.
4. Mount or attach only to an isolated verification workload.
5. Verify filesystem readability, expected ownership/mode, representative
   files, application/database integrity, and required decryption keys.
6. Record timing, manual steps, tool/image revision, and any drift from the
   runbook.
7. Remove the rehearsal target only if deletion was authorized and its exact
   identity was rechecked immediately beforehand.

## Production restore gate

Before production cutover, require explicit authorization for the exact restore
point and target. Stop and continuously monitor every writer. Preserve the old
PVC/volume or another rollback artifact. Apply desired-state changes through
Git and Flux unless the runbook documents a bounded emergency action.

After cutover, prove the workload at the exact merged revision, endpoints and
routes, application-level data, intended client access, and a new completed
backup. Do not revoke old keys or delete old storage until the restored service
has been accepted and retention cleanup is separately authorized.

## Abort conditions

Stop if:

- the source volume, repository ID, backup ID, or encryption identity is
  ambiguous or mismatched;
- the candidate is partial, stale beyond the accepted objective, failed, or
  unreadable;
- a writer cannot be stopped and monitored;
- the destination could overwrite or bind production unexpectedly;
- the restore requires a missing application or encryption key;
- destination capacity or version compatibility is unproved;
- an isolated read-test fails;
- the only rollback copy would be destroyed.

Preserve logs, IDs, and failed restore state for diagnosis. Do not “repair” a
repository by deleting evidence.

## Required evidence

Report:

- exact service, PVC/PV/volume/path, repository, and recovery-point identities
- backup completion time, size/status, and consistency method
- evidence that the artifact was read-tested or restored in isolation
- required key/credential availability without values
- writer-quiescence evidence for production restores
- before/after workload, volume, endpoint, route, and application checks
- rollback artifact retained and cleanup still pending or separately approved
- every live check that could not be performed

CI can validate desired backup contracts, but it cannot prove that remote data
exists, is decryptable, or restores successfully. Never claim otherwise.
