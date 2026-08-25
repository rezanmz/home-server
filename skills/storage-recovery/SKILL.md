---
name: storage-recovery
description: Plan or perform home-server PVC, Longhorn, NFS, JuiceFS, or directory-to-PVC storage changes and recovery. Use for volume moves, storage-class or database-layout changes, NFS export changes, data migrations, and failed-storage recovery; do not use for ordinary stateless manifest edits or backup verification alone.
---

# Storage recovery and migration

Protect data first. A storage change is not complete when Kubernetes accepts a
manifest; it is complete only when the exact data set, writers, recovery point,
and live consumer have been proved.

## Read the authoritative procedure

Read the sections that match the operation before proposing commands:

- [Service storage and migration gates](../../docs/service-operations.md#4-add-storage)
- [Service modification](../../docs/service-operations.md#modify-a-service)
- [Service retirement](../../docs/service-operations.md#retire-or-remove-a-service)
- [Cluster storage placement](../../docs/cluster-operations.md#storage-placement-and-impact)
- [Home-cluster storage runbook](../../docs/runbook.md#storage)
- [JuiceFS media operations](../../docs/juicefs-media.md)
- [Directory-to-PVC helper](../../scripts/migrate-directory-to-pvc.sh)
- [JuiceFS migration helper](../../scripts/run-juicefs-media-migration.sh)
- [NFS export helper](../../scripts/prepare-nfs-media.sh)

The manuals are authoritative when a helper, comment, or this skill disagrees.
Stop and report the drift rather than choosing the less restrictive instruction.

## Authorization boundary

Read-only Git and live inspection are not authorization to mutate storage.

- A request to plan, diagnose, or review permits inspection only.
- A request to edit the repository permits the scoped desired-state edit and
  local validation. It does not permit a live migration, controller suspension,
  snapshot creation/deletion, host export change, PVC/PV deletion, bucket
  mutation, or remote data copy.
- Immediately before a live or host-side operation, state the exact node,
  namespace, controller, PVC/PV or filesystem path, source, destination, and
  expected side effect. Proceed only when that operation is within the user's
  request. Ask for explicit authorization if it is not.
- Never improvise destructive cleanup. Do not delete a PVC, PV, Longhorn
  volume, snapshot, backup, source directory, JuiceFS object, NFS data, or a
  partially copied target merely because it appears unused.
- Do not use `kubectl apply`, `edit`, or `set image` as the normal path. Git and
  Flux own desired state. Exceptional live mitigation must be explicitly
  authorized, recorded, and reconciled back to Git.

Root Flux pruning is disabled. Removing a manifest does not remove its live
object; deletion and retention are separate reviewed decisions.

## Establish exact identities

Before changing anything, record:

1. The active Git resource chain, following each `kustomization.yaml` from
   [the cluster root](../../clusters/home-server/kustomization.yaml). Do not
   infer activity from a file merely existing.
2. Namespace, workload kind/name, controller owner, ServiceAccount, PVC name,
   bound PV, storage class, Longhorn volume where applicable, access mode,
   requested and actual capacity, node placement, and every mount path.
3. The source and destination identities independently. Refuse a migration if
   either side is inferred from a similar name, a shell glob, or an unresolved
   variable.
4. Every writer: application pods, CronJobs, maintenance jobs, sidecars,
   operators, host services, and human access paths. Scaling one Deployment is
   not proof that all writers are stopped.
5. The data contract: database versus files, ownership/mode/xattrs, symlinks,
   hard links, sparse files, nested mounts, filesystem boundaries, expected
   file count/size, and the application's consistency requirements.
6. The rollback point and who retains it. A Longhorn replica, retained PV, or
   local snapshot is not an independent backup.

Use `ssh beelink 'sudo k3s kubectl ...'` for cluster inspection. There is no
supported local kubeconfig. Use the Pi SSH alias only for documented Pi-hosted
filesystems and services.

## Preflight gate

Do not start a stateful mutation until all of the following are true:

- The relevant application and storage manuals have been read.
- The intended service downtime and consistency model are explicit.
- A recent independent backup is completed and identified by immutable backup
  or snapshot ID and timestamp, and a read-test appropriate to the change has
  succeeded. Backup eligibility or a healthy replica is not enough.
- Recovery credentials and encryption identities are available without being
  printed, copied into Git, or passed on a command line.
- Capacity headroom exists at the destination and on any temporary staging
  filesystem.
- The exact writer-quiescence proof and continuous-monitoring method are
  defined.
- Rollback preserves the old data until the new consumer has passed functional
  and data-integrity checks.

A genuinely new, empty claim has no recovery point yet and is not a mutation of
existing data. Prove that the name and backing volume are new and empty, protect
any import source independently, and define the post-initialization gate. The
service is not complete until the exact new volume has a completed independent
backup and an appropriate isolated read/restore test. This exception never
applies to adoption, rename, migration, recovery, or an apparently empty volume
whose provenance is uncertain.

If an independent backup does not exist for the data class, say so plainly and
stop unless the user explicitly accepts a documented, bounded risk. Do not call
B2-backed JuiceFS an independent backup: B2 is the authoritative media copy.
Do not claim transient NFS download data is backed up unless a separate backup
has been proved.

## Choose the procedure

### Declarative PVC, storage-class, or database-layout change

Treat this as a migration, not an in-place YAML edit. Define the old and new
objects, copy or application migration, writer freeze, cutover, verification,
rollback, and final retention decision. Keep the old recovery point until the
new workload has run successfully and the operator accepts cleanup.

Render from the active cluster tree and run the complete validation sequence in
[the validation workflow](../../.github/workflows/validate-cluster.yml). For a
cataloged service, update its colocated catalog descriptor and regenerate the
catalog; never hand-edit generated integrations.

### NFS export change

Read [prepare-nfs-media.sh](../../scripts/prepare-nfs-media.sh) in full and use
its guarded path. Inspect the live export file and calculate its exact SHA256.
Pass that value through `EXPECTED_LIVE_EXPORTS_SHA256`; never omit, fabricate,
or weaken the guard to overwrite an existing file. Preserve the helper's
backup, atomic replacement, reload validation, and rollback behavior.

An NFS export update changes a live host and may interrupt clients. Confirm
that side effect immediately before running the helper. Afterward, prove both
server export state and client mount/read behavior. If the live hash changed
since preflight, stop and re-review the new state.

### Directory-to-PVC migration

Read [migrate-directory-to-pvc.sh](../../scripts/migrate-directory-to-pvc.sh)
and the corresponding runbook procedure in full. Use the helper rather than
reimplementing its stream, fingerprints, metadata checks, or quiescence monitor.

The acknowledgements accepted by the helper are factual assertions, not bypass
flags:

- the source must be a consistency-safe, read-only snapshot;
- all target controllers and other writers must remain suspended for the full
  copy and verification window;
- namespace, PVC, source host, and source path must be exact;
- the target must meet the helper's emptiness and metadata constraints.

The helper deliberately leaves a partial stream on copy failure. A failed target
is unverified. Do not retry over it or clear it automatically. Inspect it,
preserve failure evidence, choose an explicit cleanup/recreate plan, and obtain
authorization for any deletion before retrying.

### JuiceFS media migration or recovery

Follow [docs/juicefs-media.md](../../docs/juicefs-media.md) for the selected
mode: mount recovery, cache clearing, key rotation, metadata restore, capacity,
or migration. Do not reuse a migration procedure for encryption or metadata
recovery.

For [run-juicefs-media-migration.sh](../../scripts/run-juicefs-media-migration.sh):

- run it only in the documented host context;
- keep credential files root-owned and mode `0600` under `/run`;
- never put credentials in arguments, logs, environment dumps, or Git;
- use the script's dry-run and category boundaries before a real copy;
- treat `--delete-dst` and checkpoint reset as destructive, separately
  authorized operations;
- preserve the source; the helper does not authorize source deletion;
- require its systemd network accounting and metrics. Abort if accounting,
  metrics, or the remote-read budget guard fails.

## Abort conditions

Stop without attempting a workaround if:

- an identity, ownership chain, source mount, or destination binding is
  ambiguous;
- a source expected to be read-only changes;
- any writer reappears or continuous quiescence proof fails;
- the backup cannot be identified and read-tested;
- encryption or repository identity does not match the documented value;
- the destination is nonempty unexpectedly, loses capacity, or violates the
  helper's supported metadata contract;
- copy, fingerprint, count, content, or metadata verification differs;
- NFS live-state hash differs from the reviewed value;
- JuiceFS accounting or metrics disappear;
- rollback would require destroying the only known-good copy.

Do not turn an abort into success by skipping a guard, editing a helper inline,
or declaring a partial target usable.

## Required verification evidence

Report evidence, not conclusions:

- Git revision and rendered object identities
- before/after PVC, PV, storage class, capacity, mount, and node state
- immutable backup/recovery-point identity and read-test result
- how writers were stopped and continuously monitored
- source and destination fingerprints/counts/metadata checks
- workload rollout and pod readiness at the exact merged revision
- application-level read and write checks from the intended client path
- backup inclusion and a new completed backup after cutover when applicable
- retained rollback artifact and the separately approved cleanup decision

If live verification was not authorized or reachable, say exactly which checks
remain; do not claim the migration or recovery complete.
