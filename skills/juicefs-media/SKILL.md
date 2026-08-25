---
name: juicefs-media
description: Operate, diagnose, recover, rotate credentials for, resize, or migrate the JuiceFS-backed organized media filesystem. Use for JuiceFS metadata, B2 chunks, FUSE mounts, node caches, or media cutover work.
---

# Operate JuiceFS media storage

JuiceFS is a multi-part data system, not an ordinary PVC. A healthy pod or B2
object listing does not prove the filesystem is recoverable.

## Required reading and authority

Read:

- [JuiceFS media storage operations](../../docs/juicefs-media.md) in full;
- [architecture storage contract](../../docs/architecture.md#storage);
- [runbook storage section](../../docs/runbook.md#storage); and
- [cluster operations](../../docs/cluster-operations.md) for node maintenance.

Separate the owners:

- Git/Flux owns CSI, static PV/PVC binding shape, PostgreSQL workload, Secrets,
  mount policy, NetworkPolicy, metrics, and alerts.
- JuiceFS metadata owns filesystem identity, logical quota, object credentials,
  encryption configuration, and namespace metadata.
- B2 holds authoritative encrypted organized-media chunks and portable metadata
  exports.
- Longhorn protects the PostgreSQL metadata volume.
- Each node owns a persistent but disposable cache and FUSE prerequisites.
- The Pi NFS downloads tree remains a separate local filesystem hidden over the
  JuiceFS `downloads` mountpoint.

Repository editing does not authorize a live `juicefs config`, B2 key change,
cache deletion, metadata restore, host mutation, or data migration.

## Non-negotiable storage contract

- Never edit, rename, restore, or delete JuiceFS chunk objects with the B2 file
  browser. File names and directory structure live in metadata, not object
  names.
- B2 chunks without PostgreSQL metadata or a portable metadata export are not a
  usable filesystem recovery.
- Node cache is not a backup or offline-availability guarantee. It can be
  discarded only after all mounts using it are stopped.
- The JuiceFS root's `downloads` directory is an intentionally empty mountpoint.
  Production consumers hide it with the Pi-local NFS claim. Files must never be
  allowed to accumulate there.
- Database/application state does not belong in JuiceFS; use Longhorn for that
  class.
- Keep category `subPath`, read-only flags, mount propagation, namespace-local
  claims, and the shared filesystem identity intact.
- Do not enable writeback as a workaround for B2 latency or unavailability.

## Read-only health discovery

Inspect without exposing credentials:

```bash
ssh beelink 'sudo k3s kubectl get pv,pvc -A | grep -E "juicefs|NAME"'
ssh beelink 'sudo k3s kubectl -n kube-system get pods -l app.kubernetes.io/name=juicefs-csi-driver -o wide'
ssh beelink 'sudo k3s kubectl -n kube-system get pods -l app.kubernetes.io/name=juicefs-mount -o wide'
ssh beelink 'sudo k3s kubectl -n juicefs-system get pod,pvc,service -o wide'
ssh beelink 'sudo k3s kubectl -n longhorn-system get volumes.longhorn.io | grep juicefs-postgresql'
```

Correlate consumer events and logs with:

- CSI and mount-pod health;
- PostgreSQL readiness and Longhorn replica/backup health;
- portable metadata export freshness;
- B2 request errors and latency;
- logical filesystem capacity;
- per-node cache use, hit ratio, evictions, and object traffic; and
- free space on the independent downloads export.

Never print the Secret, metadata URL with password, RSA key, passphrase, B2 key,
age identity, or mount-pod environment.

## Supported workflows

### Recover a mount

Preserve the first `FailedMount` event and determine whether the fault is CSI,
FUSE, host prerequisite, metadata, credential, B2, or bind-mount related.
Recreate only one affected consumer first. If a shared mount pod must be
recreated, stop writers on that node before deleting that exact pod. Cordon a
single unhealthy node and move consumers when the other path is proven.

Do not restart CSI, PostgreSQL, mount pods, and consumers together.

### Clear a node cache

1. Cordon the exact node.
2. Move or stop every JuiceFS consumer and wait for the shared mount to vanish.
3. Prove no process has the cache path open.
4. Remove only contents beneath the exact cache directory on that node.
5. Restore scheduling and checksum-read a known file.

Clear one node at a time. Expect uncached B2 reads and possible playback cost or
latency. Cache clearing cannot repair metadata.

### Rotate the B2 application key

The key exists in two operational planes. Update both:

1. Create a least-privilege replacement key and keep the old key valid.
2. Update the existing SOPS Secret without exposing plaintext.
3. Merge and reconcile the Secret at the exact revision.
4. Update the credential stored in JuiceFS metadata from one controlled client,
   using secret input that does not appear in the process list.
5. Recreate mount consumers one node at a time.
6. Prove new write, uncached read, delete/trash recovery, and mounts on every
   eligible node.
7. Revoke the old key only after all paths pass and with separate provider
   authorization.

Changing only the Kubernetes Secret leaves current filesystem metadata stale;
changing only metadata leaves future CSI bootstrap stale.

### Restore metadata in a drill

Never overwrite production. Restore the newest Longhorn PostgreSQL backup into
a uniquely named isolated volume/database and mount it read-only with temporary,
non-committed credential copies. Separately load the newest portable metadata
export into another empty isolated database and repeat the read-only checks.

Verify filesystem identity, category inventory, and representative small and
multi-chunk checksums. The portable dump omits object credentials; reapply them
to the disposable metadata before mounting. Delete only exact disposable
resources after recording identifiers and results.

### Change capacity

The usable limit is JuiceFS metadata configuration, not PV capacity or node
cache size. Change it once with `juicefs config`, then update documented format
intent, dashboards, and percentage alerts in Git. Keep bound static PV/PVC
nominal sizes unchanged; changing them can trigger an unsupported FUSE
expansion and does not alter the logical quota. Never shrink below current use.

### Migrate or roll back media

Use the category-scoped, fail-closed procedure and repository migration helper
in the manual. Exclude downloads. Quiesce every writer for final sync, review
dry-run deletions, bound B2 read amplification, verify inventory, ownership,
modes, symlinks, and checksum samples, and preserve a deliberate rollback
source until acceptance is recorded.

Do not partially replay a completed migration, delete checkpoints by hand,
reset a checkpoint while the source changes, or delete source categories merely
because pods are Ready.

## Encryption and recovery hard stops

The original RSA private key and passphrase are required to decrypt existing
chunks; the SOPS age identity is a separate recovery dependency. Never generate
a replacement RSA key for an existing filesystem. Never commit or log recovery
material. Test external recovery copies only in a protected temporary location
and destroy the temporary material after the isolated drill.

Stop when credentials are missing, metadata identity is uncertain, a writer
cannot be quiesced, backup/export freshness is unproven, or a command could
target production instead of a disposable restore.

## Rollback and completion evidence

Git rollback does not revert JuiceFS metadata, B2 credentials, node cache, host
prerequisites, or copied/deleted files. Write a plane-by-plane rollback before
mutation. A migration rollback stops writers, reverses only post-cutover changes
into the proven frozen source, restores old mounts, and validates before writes
resume.

Report exact Git/Flux revision, filesystem and metadata identity, Longhorn
backup and portable-export identifiers, credential planes changed, node/mount
coverage, bounded read/write/checksum results, cache or B2 cost implications,
all live/host/provider actions, and any recovery path not tested.
