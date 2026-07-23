# JuiceFS media storage operations

This manual covers the shared `media` JuiceFS Community Edition filesystem.
It is the recovery and change-control reference for the B2-backed organized
media library; it is not an application-specific configuration guide.

## Storage contract

| Data | Authority | Runtime behavior |
| --- | --- | --- |
| `movies`, `tv`, `music`, `books`, `audiobooks`, `podcasts` | JuiceFS chunks in the private `rezanmz-home-server-juicefs-media` B2 bucket | Read and successful writes are cached independently under `/var/lib/juicefs-cache` on each node |
| `downloads` and incomplete/seeding torrents | `/home/reza/media/downloads` on the Pi | Mounted over `/media/downloads`; never copied into B2 merely because a torrent is seeding |
| JuiceFS metadata | PostgreSQL on the `juicefs-postgresql` Longhorn PVC | Two Longhorn replicas plus the normal nightly Longhorn B2 backup |
| Portable metadata exports | The bucket's JuiceFS-managed `meta/` objects | Written automatically by a mounted client every hour |
| Node cache | `/var/lib/juicefs-cache` on each node | Persistent but disposable; not authoritative and not backed up |

The filesystem has a 2,048 GiB hard capacity and seven-day JuiceFS trash
retention. Compression and writeback are disabled. Client-side
`aes256gcm-rsa` encryption protects file contents before B2 receives them;
Backblaze's SSE-B2 remains a second, server-side layer. File names and other
metadata live in PostgreSQL and its metadata exports, not as normal B2 object
names. B2 contains implementation chunks and must never be edited, renamed, or
restored with the Backblaze file browser.
The bucket remains private with SSE-B2 enabled and Object Lock disabled. Its
lifecycle keeps current objects and deletes hidden/previous object versions one
day after they are superseded; it never age-expires current JuiceFS chunks.

The three namespace-local `media-library-juicefs` claims deliberately refer to
the same filesystem. `volumeHandle` remains unique per PV, while the shared
credential and filesystem name allow the CSI driver to share one mount pod per
node. Consumers use category `subPath` mounts and retain the established
application paths.

Production consumers mount the JuiceFS claim with
`mountPropagation: HostToContainer` so CSI mount recovery can propagate a
replacement FUSE mount into an existing container. The downloads stack mounts
the Pi-local `media-downloads` NFS claim over `/media/downloads`; this nested
mount is the boundary that prevents torrent writes and seeding reads from
reaching B2. qBittorrent receives the parent JuiceFS mount read-only. Radarr,
Sonarr, and Lidarr receive it read-write because imports copy into the cloud
library. All read-only consumers retain read-only mounts.
The JuiceFS root contains an intentionally empty `downloads` directory solely
as the nested mountpoint. It must never hold files: in every production
consumer, the Pi-local NFS claim hides it before the application starts.

Every eligible node must expose `/dev/fuse` and apply
`infrastructure/hosts/common/99-home-server-juicefs.conf`. Run
`scripts/prepare-juicefs-hosts.sh` after provisioning or replacing a node. The
inotify limit is a host prerequisite: K3s containers share the root user's
quota, and an exhausted quota prevents the CSI driver from loading its watched
configuration before it can serve any mount.
On hosts that enforce Ubuntu's `fusermount3` AppArmor profile, the same script
installs the narrow rule in
`infrastructure/hosts/common/juicefs-fusermount3`. It permits FUSE mounts only
under the `/jfs` path used inside JuiceFS mount pods and reloads the profile.

## Rollout state

The migration is intentionally staged:

1. Install CSI, metadata PostgreSQL, credentials, empty static claims, metrics,
   and alerts without moving a production consumer.
2. Prove encrypted B2 reads/writes and cross-node cache behavior with disposable
   test pods.
3. Copy the six organized categories in the background, excluding downloads.
4. Quiesce writers, run a reviewed final incremental sync, and switch mounts.
5. Freeze the original NFS library read-only for 48 hours.
6. Delete only verified source categories and narrow the NFS export to
   downloads.

During the initial migration, qBittorrent is deliberately paused and the Pi
kubelet uses a temporary 5% image-filesystem eviction threshold. The Pi's
organized library and K3s image store share one root filesystem, so the normal
15% threshold would otherwise evict Blocky and Longhorn while approximately
60 GiB remains free. Do not resume torrents until the verified source library
has been reclaimed. Remove the temporary kubelet arguments immediately after
free space is back above 15%.

The current production stage must be recorded in the pull request and operator
handoff. Never infer that the presence of a JuiceFS PVC means the applications
have already cut over.

## Routine health checks

Start with Kubernetes and Longhorn state:

```bash
ssh beelink 'sudo k3s kubectl get nodes,pv,pvc -A | grep -E "juicefs|NAME"'
ssh beelink 'sudo k3s kubectl -n kube-system get pods -l app.kubernetes.io/name=juicefs-csi-driver -o wide'
ssh beelink 'sudo k3s kubectl -n kube-system get pods -l app.kubernetes.io/name=juicefs-mount -o wide'
ssh beelink 'sudo k3s kubectl -n juicefs-system get pod,pvc,service -o wide'
ssh beelink 'sudo k3s kubectl -n longhorn-system get volumes.longhorn.io | grep juicefs-postgresql'
```

Then check the Grafana Media Storage dashboard. The important independent
signals are:

- CSI path health and mount-error counter growth;
- `pg_up` and the health of the two Longhorn metadata replicas;
- age of `last_successful_backup`, which proves a client completed the hourly
  portable metadata export;
- B2 request errors and latency;
- filesystem logical usage against the 2 TiB ceiling;
- per-node cache bytes, hit ratio, evictions, and B2 GET/PUT traffic;
- free space in the Pi-local downloads directory.

Inspect a mount without exposing credentials:

```bash
pod="$(ssh beelink 'sudo k3s kubectl -n kube-system get pod -l app.kubernetes.io/name=juicefs-mount -o jsonpath={.items[0].metadata.name}')"
ssh beelink "sudo k3s kubectl -n kube-system exec ${pod} -- sh -c 'juicefs status \"\${metaurl}\"'"
ssh beelink "sudo k3s kubectl -n kube-system exec ${pod} -- sh -c 'juicefs stats -l 1 -c 1 \"\$(findmnt -rn -t fuse.juicefs -o TARGET | head -n 1)\"'"
```

Do not print the Secret, the PostgreSQL URL with its password, the RSA key, or
mount-pod environment variables into tickets or chat logs.

## Mount failure and recovery

1. Check the consuming Pod's events, then the node CSI pod and matching mount
   pod logs. A `FailedMount` event identifies whether the fault is credential,
   PostgreSQL, B2, FUSE, or bind-mount related.
2. Confirm PostgreSQL is ready and B2 request errors are not rising. Do not
   restart every layer simultaneously; retain the first useful failure signal.
3. For one stuck consumer, recreate only that application Pod. CSI automatic
   mount recovery normally reconnects it to the existing shared mount pod.
4. If the shared mount pod is unhealthy, stop writers on that node before
   deleting that exact mount pod. The CSI node service will recreate it.
5. If one node alone is unhealthy, cordon it and reschedule consumers to the
   other node. Do not enable writeback as a workaround for B2 latency or
   unavailability.

New imports intentionally fail when PostgreSQL or B2 is unavailable. Existing
fully cached files may remain readable, but cache residency is not an offline
availability guarantee.

## Cache clearing

Cache is safe to discard, but never remove cache files underneath a live mount.

1. Cordon the target node.
2. Move or stop every JuiceFS consumer on it and wait for its shared mount pod
   to disappear.
3. Confirm no process has `/var/lib/juicefs-cache` open.
4. Remove only the contents beneath that exact path on the target node.
5. Uncordon the node and checksum-read a known file after the mount returns.

Clearing cache causes B2 reads and can increase playback latency and egress. Do
one node at a time. Never treat a cache clear as a way to repair metadata.

## Bucket key rotation

Create a new key scoped only to the media bucket with list, read, write, and
delete operations. Keep the old key valid until all mounts use the new key.

1. Update the existing SOPS Secret fields; never add a plaintext Secret or put
   a key in a command argument.
2. Commit, merge, and reconcile the Secret.
3. Use `juicefs config` from one controlled mount pod to update the filesystem's
   stored object credential. Supply the key via environment or standard input,
   not the process list.
4. Recreate consumers one node at a time so CSI recreates each mount pod.
5. Prove a new write, an uncached read, and a delete/trash recovery.
6. Revoke the old B2 key only after both nodes pass.

Changing only the Kubernetes Secret does not rewrite the credential already
stored in JuiceFS metadata. Changing only JuiceFS metadata leaves future CSI
mounts with stale bootstrap credentials. Both steps are required.

## Client-encryption recovery

The SOPS Secret contains an AES-encrypted RSA private key and its passphrase.
The age identity that decrypts SOPS is a separate root recovery dependency.
Before deleting the NFS source, keep an independently encrypted/password-manager
copy of all three:

- RSA private key;
- RSA passphrase;
- SOPS age identity and this recovery manual.

Never rotate the RSA key by generating a replacement for an existing volume.
The original key is required to decrypt existing chunks. Test the external copy
by decrypting it into a temporary memory-backed directory, using it to load a
metadata export into a disposable database, reading a test file, and then
destroying the temporary material.

## Metadata restoration drill

There are two independent recovery sources: the Longhorn PostgreSQL backup and
JuiceFS's portable `meta/dump-*.json.gz` exports in the media bucket.

For a drill, never overwrite production:

1. Restore the newest `juicefs-postgresql` Longhorn backup into a uniquely
   named temporary volume and database.
2. Create a temporary, namespace-isolated Secret that contains copies of the
   existing B2 and RSA credentials. Do not commit or log its plaintext.
3. Point a disposable JuiceFS client at the restored database and mount
   read-only.
4. Check the filesystem UUID, category counts, and checksums of representative
   small and multi-chunk files.
5. Separately test portable recovery by loading the latest `meta/` export into
   another empty temporary PostgreSQL database with the original encrypted RSA
   key, then mount it read-only and repeat the checks.
6. Record the backup identifiers, export timestamp, file checksums, and result;
   delete only the exact disposable resources.

The portable dump intentionally omits object-store secrets. Reapply the B2
configuration with `juicefs config` after loading it. A successful B2 object
listing is not a metadata restore test.

## Capacity change

The 2 TiB limit is a JuiceFS logical quota, not the size of either cache. To
raise it:

1. Review expected B2 cost and the alert thresholds.
2. Run `juicefs config META_URL --capacity NEW_GIB` once from a controlled
   client using secret environment injection.
3. Update `format-options`, all static PV/PVC display capacities, dashboard
   constants, and 75/85/95 percent alert expressions in the same Git change.
   `format-options` documents bootstrap intent but does not change an already
   formatted volume by itself.
4. Reconcile and verify `juicefs status` reports the new limit.

Shrinking below current usage is forbidden. Category quotas are not enabled.

## Migration and rollback controls

Initial and final copy operations include only `movies`, `tv`, `music`,
`books`, `audiobooks`, and `podcasts`. Every command is category-scoped,
resumable, and byte-checks new objects. `downloads` is always excluded.

The initial background copy runs directly on the Pi host instead of as a Pod.
This is intentional: a migration Pod is itself eligible for eviction on the
source disk it must read. Install the exact JuiceFS 1.4.0 binary copied from the
digest-pinned CSI mount image, verify its checksum, stage `metaurl`,
`meta-password`, and `rsa-passphrase` as root-owned mode-0600 files under the
tmpfs path `/run/juicefs-media-migration`, then run:

```bash
sudo systemd-run --unit=juicefs-media-migration \
  --property=CPUWeight=20 --property=IOWeight=20 --property=MemoryMax=3G \
  /usr/local/sbin/run-juicefs-media-migration.sh
sudo journalctl -fu juicefs-media-migration
```

`scripts/run-juicefs-media-migration.sh` accepts only the six organized
categories, defaults to four transfer threads and 158 Mbps (60% of the measured
encrypted B2 upload rate), preserves directories, permissions, and symlinks,
and checks every new or changed file. It never accepts `downloads`, never
deletes from the source, keeps resumable checkpoints in the root-only runtime
directory, and refuses credentials supplied in command arguments. A failed or
interrupted category is resumed by running the same script with that category
name. Remove the runtime credential directory after the copy finishes.

Before cutover, compare source and destination file counts, logical bytes,
ownership, directory modes, symlinks, and a checksum sample per category.
Normalize only inconsistent library ownership to UID/GID 1000 and directories
to mode 0775. Do not mass-rewrite valid file modes.

For final cutover:

1. Pause automatic grabs and Flux reconciliation for the affected bundles.
2. Scale every library writer and reader down.
3. Run a dry-run destination-delete sync separately for each category and
   review every proposed removal.
4. Run final incremental sync, then repeat counts, bytes, permission, and
   changed-file checks.
5. Reconcile the PVC switch and validate each application before resuming
   downloads.

During the 48-hour rollback window, the old NFS categories stay frozen and
read-only. To roll back, stop all writers, reverse-sync only changes made after
cutover into the frozen tree, restore the old PVC references, and validate
before resuming. Never delete the NFS source merely because pods reached Ready.

After the window, record a final verification report, delete only the six old
category directories, retain `/home/reza/media/downloads`, and narrow the Pi
NFS export to that directory. Removing obsolete PV/PVCs is a separate,
identity-checked cleanup.

## Security boundaries

- CSI and FUSE require privileged kube-system workloads, host paths, broad CSI
  RBAC, and access to volume Secrets. Those upstream privileges are recorded in
  the reviewed high-risk baseline and are not inherited by media applications.
- PostgreSQL accepts port 5432 only from kube-system mount/CSI pods. Prometheus
  alone can reach exporter port 9187. The `juicefs-system` namespace otherwise
  default-denies ingress and egress.
- The CSI dashboard is disabled and has no HTTP route. Use Grafana and
  `kubectl` through SSH.
- The B2 key is bucket-scoped. The Longhorn and Syncthing buckets and keys are
  not valid JuiceFS recovery material.
- B2 is the authoritative media payload store, not a second media backup.
  Metadata plus the RSA key are required to interpret it.
