# Home cluster runbook

## Access and first checks

The Kubernetes API is not exposed publicly. Administer the cluster through the
Beelink:

```bash
ssh beelink
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl get pods -A
```

The server kubeconfig is root-only at `/etc/rancher/k3s/k3s.yaml`. Healthy
production state means both nodes are `Ready`, all expected application pods
are `Running` or successfully `Completed`, and no workload controller is short
of its desired ready replicas.

Useful controller checks:

```bash
sudo k3s kubectl get deployments,statefulsets -A
sudo k3s kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
sudo k3s kubectl get events -A --sort-by=.lastTimestamp | tail -n 50
```

## GitOps reconciliation

Changes reach production through a pull request. Direct pushes to `main` are
blocked, and the required `Validate cluster configuration / validate` check
must pass before merge. The workflow is intentionally GitHub-hosted and has
read-only repository permissions; neither cluster node should be registered as
a GitHub Actions runner.

```bash
sudo k3s kubectl -n flux-system get gitrepositories,ocirepositories,kustomizations -o wide
sudo k3s kubectl get helmreleases -A
```

Every source, Kustomization, and HelmRelease should report `READY=True`. The
root Kustomization intentionally has `prune: false`: removing a manifest or
temporarily losing the decryption key must not delete live workloads, Secrets,
or PVCs. Before an intentional retirement, review the rendered diff and delete
resources explicitly, one workload at a time. Never delete the root
`flux-system` Kustomization as a recovery step.

Before changing storage, create an application-level export or snapshot and
verify that it can be read. Longhorn uses `reclaimPolicy: Retain`, but that
only protects a volume after PVC deletion; it is not a database backup.

To request immediate reconciliation after a push:

```bash
stamp=$(date +%s)
sudo k3s kubectl -n flux-system annotate gitrepository flux-system \
  reconcile.fluxcd.io/requestedAt="$stamp" --overwrite
sudo k3s kubectl -n flux-system annotate kustomization flux-system \
  reconcile.fluxcd.io/requestedAt="$stamp" --overwrite
```

If reconciliation fails, inspect the Kustomization and relevant HelmRelease
before changing live objects:

```bash
sudo k3s kubectl -n flux-system describe kustomization flux-system
sudo k3s kubectl -n flux-system logs deployment/source-controller --tail=100
sudo k3s kubectl -n flux-system logs deployment/kustomize-controller --tail=100
```

Docker Compose is not a deployment path for this cluster. Do not restart old
Docker projects to work around a Kubernetes failure; diagnose or roll back the
Git revision through Flux.

During a deliberate recovery, suspend the root Kustomization before making
temporary live changes. Keep it suspended until the corresponding protected
revision is merged, verify the GitRepository artifact points at that revision,
then resume and reconcile. Do not leave production permanently dependent on
uncommitted live drift.

## Ingress and TLS

- Public router target: Pi at `192.168.1.2`, TCP ports 80 and 443
- Traefik host ports: TCP 80 and 443 on both cluster nodes
- Traefik MetalLB VIP: `192.168.1.240`
- MetalLB pool: `192.168.1.240-192.168.1.249`
- Pi-hole DHCP range: `192.168.1.10-192.168.1.239`

Pi-hole's local overrides point HTTP hostnames at the Traefik VIP (`.240`),
not at an application node. Kubernetes Services then follow pods as they move
between nodes. Pi-specific protocols such as DNS/DHCP, SMB, NFS, and the
WireGuard UDP endpoint continue to use the Pi address (`.2`).

Check the edge and certificate objects:

```bash
sudo k3s kubectl -n traefik get daemonsets,pods,services -o wide
sudo k3s kubectl -n traefik get gateway home
sudo k3s kubectl -n traefik get certificate reza-network
sudo k3s kubectl get clusterissuer letsencrypt-production
sudo k3s kubectl get httproutes -A
```

Test the public path, the Pi host-port path, and the MetalLB path separately:

```bash
curl -fsS https://homepage.reza.network/ >/dev/null
curl -fsS --resolve homepage.reza.network:443:192.168.1.2 \
  https://homepage.reza.network/ >/dev/null
curl -fsS --resolve homepage.reza.network:443:192.168.1.240 \
  https://homepage.reza.network/ >/dev/null
```

The `letsencrypt-production` ClusterIssuer uses Cloudflare DNS-01. The wildcard
certificate is stored as `traefik/reza-network-tls` and renews automatically.
An HTTP 403 from an administrative hostname can be correct when the request
does not originate from an allowed LAN or WireGuard range.
Administrative allow-lists intentionally exclude the K3s node addresses `.2`
and `.3`: cross-node pod-to-hostPort traffic can be SNATed to the peer node and
must not inherit LAN trust. A request issued directly from either node should
therefore receive 403, while the same request from an ordinary LAN client via
the `.240` VIP should succeed. The high-risk policy rejects any Traefik
IP allow-list range that contains either node address.

### Home Assistant recovery gate

Home Assistant uses its built-in authentication and is internet-accessible at
`homeassistant.reza.network`. Every administrator must use a unique password and
enable TOTP MFA from the Home Assistant profile security page. Its init container
serves a deny-only proxy unless the PVC contains a regular
`/config/.owner-onboarded` file. After restoring or replacing that PVC, validate
an active owner through a loopback-only port-forward before recreating the marker
and restarting the Deployment. Never create the marker merely to clear an HTTP
503; a genuinely empty instance would otherwise expose first-owner creation to
the public internet.

### Audiobookshelf recovery and OIDC bootstrap

Audiobookshelf is internet-accessible at `audiobooks.reza.network` and uses its
native Authentik OIDC flow for browsers and the official mobile app. Its local
root account is a recovery path; the generated password is stored only in the
SOPS-encrypted `media/audiobookshelf-secrets` Secret. Do not disable local auth
without replacing and testing that recovery path.

The lifecycle bootstrap writes `/config/.gitops-bootstrap-complete` only after
the root account, OIDC settings, and initial libraries are configured. The
marker includes a one-way hash of the OIDC client secret: ordinary restarts do
not need the recovery login, while a secret rotation reconciles the application
settings before writing a new marker. The pod cannot become Ready on an empty
PVC before that hook succeeds. If the hook fails, inspect the previous
container log and verify the Authentik OIDC provider/application and discovery
document, encrypted secrets, NFS mounts, and root credential; do not bypass the
hook or create the marker manually to clear the outage.

Longhorn and its B2 target protect `/config` and `/metadata`. The writable
`/home/reza/media/audiobooks` and `/home/reza/media/podcasts` NFS directories,
including downloaded podcast episodes, are not included in Longhorn backups.
Neither is the read-only Calibre source; all three remain part of the
reconstructible media data class.

## Pi network services

Pi-hole, Samba, Syncthing, and wg-easy are Kubernetes workloads in
the `network-services` namespace. They are pinned to the Pi when they require
its address or data.

```bash
sudo k3s kubectl -n network-services get deployments,pods,pvc -o wide
sudo k3s kubectl -n network-services logs deployment/pihole --tail=100
sudo k3s kubectl -n network-services logs deployment/wg-easy --tail=100
```

The legacy `network-watchdog.timer` must remain disabled and inactive. It used
a public TCP/53 probe to decide whether to restart NetworkManager and reload a
Wi-Fi driver, which can disconnect the Ethernet K3s/NFS/DNS node during an
unrelated upstream failure. Its files are retained for forensics only:

```bash
systemctl is-enabled network-watchdog.timer  # expected: disabled
systemctl is-active network-watchdog.timer   # expected: inactive
```

### Pi unattended security updates

The Pi refreshes package metadata daily and applies packages only from the
Debian Security archive. Ordinary Debian point updates remain a planned
maintenance task. Repository-owned fragments `20auto-upgrades` and
`52-home-server-unattended-upgrades` replace Debian's broader default origin
list and explicitly disable automatic reboots and automatic dependency or
kernel cleanup. `scripts/join-k3s-agent.sh` installs the policy, verifies its
effective apt configuration, performs a non-installing resolver dry run, and
only then enables the apt timers.

Audit the effective policy after changing apt sources or configuration:

```bash
ssh pi 'sudo apt-config dump | grep -E "^(APT::Periodic::(Update-Package-Lists|Unattended-Upgrade)|Unattended-Upgrade::(Origins-Pattern|Allowed-Origins|Automatic-Reboot))"'
ssh pi 'sudo unattended-upgrade --dry-run --debug'
ssh pi 'systemctl is-enabled unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer'
```

The effective output must contain exactly one list entry under
`Unattended-Upgrade::Origins-Pattern`: Debian's
`${distro_codename}-security` suite with the `Debian-Security` label. It must
not contain the base `${distro_codename}` archive or any legacy
`Allowed-Origins` list entries. The dry run may identify and download eligible
packages into APT's cache, but it must not install them. A pending reboot or
non-security upgrade is handled only during a maintenance window after storage
and cluster health checks.

From a LAN machine, verify DNS and the host-level listeners:

```bash
dig @192.168.1.2 github.com
ssh pi 'sudo ss -lntup'
```

Keep `127.0.1.1 raspberrypi` in the Pi's `/etc/hosts`. Administrative commands
must be able to resolve the local hostname while Pi-hole is stopped or being
replaced; relying on the DNS workload for `sudo` can otherwise break recovery.

Expected Pi-facing services include DNS on TCP/UDP 53, DHCP on UDP 67, NTP on
UDP 123, SMB on TCP 139/445, Syncthing on TCP/UDP 22000 and UDP 21027, and
WireGuard on UDP 1234. The Pi-hole UI listens internally on port 8181 and is
published through the Gateway rather than directly as the public service.
The FTL listener must be `127.0.0.1:8181`; the colocated proxy listens with TLS
on 18181 and requires Traefik's cert-manager-managed backend client certificate.
The HTTPRoute reaches it through `TraefikService/pihole-mtls` and
`ServersTransport/pihole-mtls`. A direct request without that certificate must
return HTTP 400 (or fail its TLS handshake), even with a forged
`X-Forwarded-For`; the Gateway route must return 200 from an allowed source.
All three `pihole-mtls-*` Certificates must remain Ready. This backend identity
is separate from the public wildcard certificate. The server leaf is loaded
through nginx's one-minute certificate cache so normal Secret renewal does not
need a restart. The private CA intentionally keeps the same key for its ten-year
lifetime; rotate it only as a staged maintenance operation that reissues both
leaf certificates and rolls the Pi-hole pod after proving the new trust chain.

Syncthing must have automatic NAT traversal disabled (`natenabled=false`) so it
cannot ask the router to expose port 22000 through UPnP or NAT-PMP. LAN
discovery, global discovery, relays, and connections over WireGuard remain
enabled. Verify the persistent setting from the running pod after replacing its
configuration:

Its GUI remains HTTPS on loopback and is reached through the TLS listener on
port 18384. That listener requires the dedicated `syncthing-mtls-client`
certificate from Traefik and must return 400 (or fail TLS) to a direct request,
including from another pod. The `syncthing-mtls-ca`, `-server`, and `-client`
Certificates must all remain Ready; only the CA public certificate may be
projected into nginx.

```bash
pod=$(sudo k3s kubectl -n network-services get pod \
  -l app.kubernetes.io/name=syncthing -o jsonpath='{.items[0].metadata.name}')
sudo k3s kubectl -n network-services exec "$pod" -c syncthing -- \
  syncthing cli --home=/config config options natenabled get
```

wg-easy v15 stores its endpoint, client DNS, and AllowedIPs in the persistent
application database; the v14 `WG_*` environment variables are ignored. The
global and per-client DNS value should be `192.168.1.2`. After changing client
DNS or routes, download/import the refreshed client profile because WireGuard
cannot push configuration changes into an already imported profile.

The Pi kubelet allowlists only `net.ipv4.ip_forward` and
`net.ipv4.conf.all.src_valid_mark` as pod-scoped unsafe sysctls. wg-easy
declares those settings directly and needs only `NET_ADMIN` plus `NET_RAW`; it
must not regain a privileged init container, `SYS_MODULE`, or a `/lib/modules`
host mount. A `SysctlForbidden` pod status means the deployed Pi K3s config no
longer matches `infrastructure/k3s/agent-pi-config.yaml`.

wg-easy also masquerades VPN clients when forwarding them to the cluster. As a
result, Traefik and the application-side access proxies see `10.42.1.0/24`, the
Pi node's fixed pod CIDR, instead of `10.8.0.0/24`. The administrative route
allow-lists intentionally contain exactly that Pi CIDR. Treat every pod on the
Pi as trusted for those routes. Keeping unrelated sensitive workloads off that
node is currently an operator preference, not an enforced invariant: the Pi is
untainted and floating workloads can schedule there. Pin or taint explicitly if
placement is a security requirement, and never replace the exception with the
cluster-wide `10.42.0.0/16`. The CI high-risk baseline should fail if a new
pod-CIDR exception is added without review.

## Storage

Longhorn stores small application state with two replicas across the two nodes:

```bash
sudo k3s kubectl get storageclass
sudo k3s kubectl get pvc -A
sudo k3s kubectl -n longhorn-system get nodes.longhorn.io
sudo k3s kubectl -n longhorn-system get volumes.longhorn.io
```

Every attached Longhorn volume should be `healthy`. A degraded volume means one
of the two nodes or replicas needs attention; do not delete its PVC as a repair
step.

Kubernetes CSI snapshots require all three layers: the snapshot CRDs, the
common `kube-system/snapshot-controller`, and Longhorn's CSI snapshotter
sidecars. Verify them together; green Longhorn sidecars alone are insufficient:

```bash
sudo k3s kubectl get crd | grep 'snapshot.storage.k8s.io'
sudo k3s kubectl -n kube-system get deployment,pods -l \
  app.kubernetes.io/name=snapshot-controller
sudo k3s kubectl -n longhorn-system logs deployment/csi-snapshotter \
  --since=10m | grep -i 'the server could not find the requested resource'
```

The last command should produce no output. CSI snapshots remain local Longhorn
state and do not replace an authenticated off-cluster BackupTarget. Use the
`longhorn-snapshot` VolumeSnapshotClass. Longhorn 1.12's exact local snapshot
parameter is `type: snap`; omitting it requests a remote backup instead of the
intended local snapshot and therefore consumes the configured B2 target.

Large and shared data remains on NFS exported by the Pi. Check the server and
exports directly when multiple NFS-backed workloads or the Syncthing file-level
backup fail at once:

```bash
ssh pi 'systemctl is-active nfs-server && sudo exportfs -v'
sudo k3s kubectl get pv | grep nfs-media
```

The Pi is the authoritative source for these trees. There is no independent NAS
or third storage node, so a Pi outage is expected to interrupt every NFS-backed
workload. Do not treat Longhorn replicas as copies of the NFS data.

The local pre-migration recovery set is on the Beelink:

```text
/srv/home-server-backups/pre-k3s-20260712/
├── persistent/
├── postgres/
└── SHA256SUMS
```

This set and the age identities are not off-site backups. Restore credentials,
the Restic repository password, and the SOPS age identities still need an
independent recovery copy.

Longhorn's default BackupTarget is the dedicated private
`rezanmz-home-server-longhorn-backups` Backblaze B2 bucket in `ca-east-006`.
Its S3 credential exists only as the SOPS-encrypted
`longhorn-system/longhorn-backblaze-b2` Secret. Check the target and backup
inventory directly:

```bash
sudo k3s kubectl -n longhorn-system get backuptargets.longhorn.io \
  -o custom-columns=NAME:.metadata.name,AVAILABLE:.status.available,URL:.spec.backupTargetURL,CREDENTIAL:.spec.credentialSecret
sudo k3s kubectl -n longhorn-system get recurringjobs.longhorn.io
sudo k3s kubectl -n longhorn-system get backups.longhorn.io,backupvolumes.longhorn.io
```

The target must report `AVAILABLE=true`. `b2-nightly` runs at 06:17 UTC, retains
14 logical backups per volume, processes one volume at a time, and requests a
full backup after every seven completed incremental backups. Normal backup jobs
skip unchanged data, so that full interval is count-based rather than a strict
weekly calendar. Longhorn may temporarily attach an otherwise detached volume
at backup time. A second Longhorn replica or a local snapshot on either node is
not an off-site backup.

The B2 bucket must stay private with default SSE-B2 encryption enabled. Do not
enable Object Lock or add a bucket lifecycle expiry rule: Longhorn must control
logical backup deletion. Backblaze's `Keep all versions` setting can retain
hidden historical versions after a logical delete, so monitor physical bucket
growth separately from Longhorn's retention count. The every-seven-backups full
refresh can also replace block objects and create additional hidden versions.

Review the bucket's billed size and hidden/noncurrent version count in the
Backblaze console at least monthly and after any large restore or retention
cleanup. Treat unexplained continued growth after Longhorn reaches steady-state
retention as an incident. Do not add an automated B2 lifecycle rule as a quick
cost fix; first verify a noncurrent-version-only policy with both Longhorn and
Backblaze support because deleting current backupstore objects can invalidate
the backup index.

Longhorn backups are crash-consistent per volume. They do not coordinate writes
between an application and its PostgreSQL, Redis, or Elasticsearch PVC, or
between multiple PVCs. Periodic native database exports and application-level
restore tests remain desirable even after the block-level restore proof passes.

### Syncthing file-level backups

The Longhorn target does not cover any `nfs-media` PersistentVolume. Media is
accepted as reconstructible. Active Syncthing data is protected separately by
Restic in the private `rezanmz-home-server-syncthing-backups` bucket. Never put
Restic objects in the Longhorn or historical Duplicati bucket.

The B2 bucket must stay private with SSE-B2 enabled and Object Lock disabled.
It currently uses `Keep all versions`: hidden object versions are useful
forensic material but are not a coherent or tested point-in-time rollback of a
multi-object Restic repository. Monitor their unbounded billable growth. If a
bounded rule is introduced later, it may expire only hidden prior versions and
must never expire current objects based on upload age.

Restic 0.19.1's normal S3 operations use object listing, reads, writes, and
name-only deletes that create hide markers. A future least-privilege key should
be restricted to bucket `rezanmz-home-server-syncthing-backups`, name prefix
`syncthing/` including the trailing slash, and begin with only `listFiles`,
`readFiles`, and `writeFiles`. Prove initialization, two changed backups, lock
cleanup, forget/prune, full check, and restore with that exact key. Add
`listBuckets` plus `listAllBucketNames` only if B2's bucket probe requires them,
and add `deleteFiles` only if a name-only cleanup is proven to fail without it.
Do not grant bucket creation/deletion, lifecycle changes, sharing, logging,
notifications, replication, or Object Lock administration.

The rollout key is bucket-scoped but was created with broader capabilities and
no name-prefix restriction. Rotation to the proven reduced key is a worthwhile
hardening task; until then, compromise of the backup pod can use Backblaze's
native API to destroy historical versions. Treat unexpected backup-pod
execution, key use, or object-count drops as an incident. Restic separately
encrypts every repository object with the password in the SOPS Secret. Preserve
that password offline; Backblaze cannot recover it.

`network-services/syncthing-backup` runs at 07:43 UTC. It retains 14 daily,
8 weekly, 12 monthly, and 3 yearly snapshots, prunes on Sunday, performs a
structural check after pruning, and reads one deterministic quarter of the
repository on the first day of each month. The entire `/source` mount is backed
up, so new folders are protected without a manifest change. The stable host,
source path, and tag in the CronJob are part of Restic's snapshot grouping and
must not be changed casually. The initial 2026-07-14 backup processed 21 files
and 18 directories (5.27 MiB), the full encrypted-data check passed, and the
same trusted snapshot restored successfully into an isolated volume.
At 12:13 UTC, `syncthing-backup-freshness` checks the same pinned repository
from the Beelink and fails when no exact trusted snapshot is newer than 36
hours. It mounts the credential but no Syncthing data or configuration. Its
failed Job emits a Warning event consumed by the existing event-alert pipeline.

Inspect the schedule and the newest jobs directly:

```bash
sudo k3s kubectl -n network-services get cronjob syncthing-backup
sudo k3s kubectl -n network-services get cronjob syncthing-backup-freshness
sudo k3s kubectl -n network-services get jobs \
  -l app.kubernetes.io/name=syncthing-backup \
  --sort-by=.metadata.creationTimestamp
sudo k3s kubectl -n network-services logs \
  -l app.kubernetes.io/name=syncthing-backup \
  --all-containers --tail=200 --prefix
```

Any nonzero Restic result, including exit 3 for an incomplete live-file scan,
is a failed backup. Do not suppress it. Do not add `--no-lock`, and never run an
automatic `restic unlock`; first prove no backup, check, prune, or restore pod is
alive.

The repository is initialized exactly once after the SOPS Secret reconciles.
Generate the Job locally before applying it so the normal backup command cannot
race the command override:

```bash
set -euo pipefail
name="syncthing-backup-init-$(date -u +%Y%m%d%H%M%S)"
sudo k3s kubectl -n network-services create job "$name" \
  --from=cronjob/syncthing-backup --dry-run=client -o json |
  jq '
    .spec.template.spec.containers[0].command[-1] = "init-repository"
    | (.spec.template.spec.containers[0].env[]
        | select(.name == "ALLOW_REPOSITORY_INIT").value) = "true"
  ' |
  sudo k3s kubectl apply -f -
sudo k3s kubectl -n network-services wait \
  --for=condition=complete "job/$name" --timeout=15m
sudo k3s kubectl -n network-services logs "job/$name"
```

Initialization is idempotent only when the existing repository password is
correct. Exit 10 permits creation only in the explicitly modified one-shot Job;
authorization, network, and wrong-password failures refuse to create a second
repository. Copy the 64-character `repository-id` from the successful log into
`EXPECTED_REPOSITORY_ID` in the CronJob and reconcile it while `suspend: true`.
Every backup and integrity check compares the live ID with that pinned value,
preventing a bucket-prefix typo from silently starting a second history.

To start an on-demand run from the exact scheduled template:

```bash
set -euo pipefail
test "$(sudo k3s kubectl -n network-services get jobs \
  -l app.kubernetes.io/name=syncthing-backup -o json | \
  jq '[.items[] | select((.status.active // 0) > 0)] | length')" -eq 0
name="syncthing-backup-manual-$(date -u +%Y%m%d%H%M%S)"
sudo k3s kubectl -n network-services create job "$name" \
  --from=cronjob/syncthing-backup
sudo k3s kubectl -n network-services wait \
  --for=condition=complete "job/$name" --timeout=12h
sudo k3s kubectl -n network-services logs "job/$name"
```

The CronJob's `Forbid` policy does not serialize independently created Jobs.
Run manual backup, check, prune, and restore work away from 07:43 UTC and only
after the active-job check above returns zero.

Run a complete encrypted-data check before retiring another backup path and at
least quarterly:

```bash
set -euo pipefail
test "$(sudo k3s kubectl -n network-services get jobs \
  -l app.kubernetes.io/name=syncthing-backup -o json | \
  jq '[.items[] | select((.status.active // 0) > 0)] | length')" -eq 0
name="syncthing-backup-full-check-$(date -u +%Y%m%d%H%M%S)"
sudo k3s kubectl -n network-services create job "$name" \
  --from=cronjob/syncthing-backup --dry-run=client -o json |
  jq '.spec.template.spec.containers[0].command[-1] = "check-repository-data"' |
  sudo k3s kubectl apply -f -
sudo k3s kubectl -n network-services wait \
  --for=condition=complete "job/$name" --timeout=12h
sudo k3s kubectl -n network-services logs "job/$name"
```

A successful `restic check --read-data` is necessary but not a restore proof.
Copy the full 64-character trusted snapshot ID from a successful backup log;
never use an unpromoted candidate. The following procedure creates a disposable
Longhorn PVC, derives a Job from the reviewed CronJob, mounts that PVC only at
`/restore`, and invokes the script's fail-closed `restore-proof` mode. Increase
`restore_size` above the snapshot's restored size when the data grows.

```bash
set -euo pipefail
snapshot_id=REPLACE_WITH_64_CHARACTER_TRUSTED_SNAPSHOT_ID
restore_size=1Gi
case "$snapshot_id" in
  *[!0-9a-f]*|'') printf 'invalid snapshot ID\n' >&2; exit 1 ;;
esac
test "${#snapshot_id}" -eq 64
test "$(sudo k3s kubectl -n network-services get jobs \
  -l app.kubernetes.io/name=syncthing-backup -o json | \
  jq '[.items[] | select((.status.active // 0) > 0)] | length')" -eq 0

stamp=$(date -u +%Y%m%d%H%M%S)
pvc="syncthing-restore-proof-$stamp"
job="syncthing-restore-proof-$stamp"
sudo k3s kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $pvc
  namespace: network-services
  labels:
    app.kubernetes.io/name: syncthing-backup
    app.kubernetes.io/component: restore-proof
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: $restore_size
EOF

sudo k3s kubectl -n network-services create job "$job" \
  --from=cronjob/syncthing-backup --dry-run=client -o json |
  jq --arg snapshot "$snapshot_id" --arg pvc "$pvc" '
    .spec.template.spec.containers[0].command[-1] = "restore-proof"
    | .spec.template.spec.containers[0].env += [
        {"name": "RESTORE_SNAPSHOT_ID", "value": $snapshot}
      ]
    | .spec.template.spec.containers[0].volumeMounts += [
        {"name": "restore", "mountPath": "/restore"}
      ]
    | .spec.template.spec.volumes += [
        {"name": "restore", "persistentVolumeClaim": {"claimName": $pvc}}
      ]
  ' |
  sudo k3s kubectl apply -f -
sudo k3s kubectl -n network-services wait \
  --for=condition=complete "job/$job" --timeout=12h
sudo k3s kubectl -n network-services logs "job/$job"
```

The proof rejects a snapshot unless its exact ID, host
`home-server-syncthing-nfs`, path `/source`, and trusted tag all match. It then
checks the restored canary, requires every included configured folder and its
real `.stfolder`, requires every opted-out folder to be absent, and reports
only aggregate file/directory counts. Delete the disposable objects only after
the log says `restore proof passed`; retain them for diagnosis after a failure:

```bash
set -euo pipefail
pv_json=$(sudo k3s kubectl -n network-services get pvc "$pvc" -o json |
  jq -e 'select(.status.phase == "Bound" and (.spec.volumeName | length > 0))')
pv=$(jq -r '.spec.volumeName' <<<"$pv_json")
pvc_uid=$(jq -r '.metadata.uid' <<<"$pv_json")
volume_handle=$(sudo k3s kubectl get pv "$pv" -o json |
  jq -er --arg pvc "$pvc" --arg pvc_uid "$pvc_uid" '
    select(.spec.claimRef.namespace == "network-services"
           and .spec.claimRef.name == $pvc
           and .spec.claimRef.uid == $pvc_uid
           and .spec.storageClassName == "longhorn"
           and .spec.csi.driver == "driver.longhorn.io")
    | .spec.csi.volumeHandle
    | select(type == "string" and length > 0)
  ')

# The default Longhorn StorageClass is Retain. Change only this proven
# disposable PV before deleting its claim so the restored data is not orphaned.
sudo k3s kubectl patch pv "$pv" --type=merge \
  -p '{"spec":{"persistentVolumeReclaimPolicy":"Delete"}}'
sudo k3s kubectl -n network-services delete job "$job" --wait=true
sudo k3s kubectl -n network-services delete pvc "$pvc" --wait=true

for _ in $(seq 1 120); do
  if ! sudo k3s kubectl get pv "$pv" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if sudo k3s kubectl get pv "$pv" >/dev/null 2>&1; then
  printf 'disposable PV still exists: %s\n' "$pv" >&2
  exit 1
fi
for _ in $(seq 1 120); do
  if ! sudo k3s kubectl -n longhorn-system get volume.longhorn.io \
    "$volume_handle" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if sudo k3s kubectl -n longhorn-system get volume.longhorn.io \
  "$volume_handle" >/dev/null 2>&1; then
  printf 'disposable Longhorn volume still exists: %s\n' "$volume_handle" >&2
  exit 1
fi
```

After initial backup, full-data check, and isolated restore all pass, the
CronJob may be unsuspended. Repeat both the full-data check and isolated restore
at least quarterly.

Every Syncthing folder is included unless its stable folder ID appears in
`apps/syncthing/backups/excluded-folder-ids.txt`. The policy intentionally
starts empty.

The storage-identity canary is the regular file
`/home/reza/persistent/syncthing/data/.restic-source-canary` on the Pi. It is
owned by UID/GID 1000, mode `0444`, and its expected SHA-256 is
`6665ae1d8e206b61b16d6a199c5bb76a292e5ed4906337fb0dbcdaad5415d840`.
Do not remove or casually edit it: every backup refuses an empty, wrong, or
substituted NFS root when the checksum differs. To recreate it after a deliberate
storage rebuild, first prove the path is the intended Syncthing export, then run:

```bash
printf 'home-server-syncthing-source-canary-v1\n' |
  ssh pi 'sudo tee /home/reza/persistent/syncthing/data/.restic-source-canary >/dev/null'
ssh pi 'sudo chown 1000:1000 /home/reza/persistent/syncthing/data/.restic-source-canary &&
  sudo chmod 0444 /home/reza/persistent/syncthing/data/.restic-source-canary &&
  sha256sum /home/reza/persistent/syncthing/data/.restic-source-canary'
```

If the intentional content ever changes, update `SOURCE_CANARY_SHA256` in the
CronJob in the same reviewed change and complete a fresh backup/check/restore
proof before accepting the new identity.

To review the live folder IDs and paths without dumping secret-bearing
`config.xml` or device membership:

```bash
pod=$(sudo k3s kubectl -n network-services get pod \
  -l app.kubernetes.io/name=syncthing -o jsonpath='{.items[0].metadata.name}')
for id in $(sudo k3s kubectl -n network-services exec "$pod" -c syncthing -- \
  syncthing cli --home=/config config folders list); do
  printf 'id=%s label=' "$id"
  sudo k3s kubectl -n network-services exec "$pod" -c syncthing -- \
    syncthing cli --home=/config config folders "$id" label get
  printf 'id=%s path=' "$id"
  sudo k3s kubectl -n network-services exec "$pod" -c syncthing -- \
    syncthing cli --home=/config config folders "$id" path get
done
```

Add only the exact folder ID, for example `mbjfk-vepmo`; keep labels and paths in
comments if useful for review. The preflight resolves that ID through the live
config, so a path rename remains excluded. It rejects unknown or duplicate IDs,
folders outside `/data`, path overlap, symlinks, and directories without a real
`.stfolder`. Removing an ID includes the folder again at the next successful
backup. A policy or storage-identity error fails the entire job instead of
silently backing up or omitting the wrong folder.

Restic gives each new snapshot a candidate tag first. Exit 0 is required before
the exact snapshot is promoted to the trusted `syncthing-nfs` tag; incomplete
exit-3 snapshots remain candidates and are never selected by trusted retention
or the restore procedure. A best-effort failure-path rule and every later
successful run retain only the newest three candidate snapshots without
pruning repository data. Always select the trusted tag and record the exact
snapshot ID used for a restore.

The `flux-system/syncthing-backups` child owns the credential, data-backup and
freshness CronJobs, policy ConfigMap, and NetworkPolicy with pruning enabled.
For a planned rollback, first commit `suspend: true` on both CronJobs and wait
for reconciliation, delete any running backup Jobs, then remove the child
resources in a second commit while leaving the child Kustomization present so
it can prune them. Only after the inventory is empty should the child manifest
be removed from the parent. The root reconciler has pruning disabled, so
explicitly delete the now-empty child object afterward.

For an immediate stop, suspend the child before touching its resources:

```bash
sudo k3s kubectl -n flux-system patch kustomization syncthing-backups \
  --type=merge -p '{"spec":{"suspend":true}}'
sudo k3s kubectl -n network-services patch cronjob syncthing-backup \
  --type=merge -p '{"spec":{"suspend":true}}'
sudo k3s kubectl -n network-services patch cronjob syncthing-backup-freshness \
  --type=merge -p '{"spec":{"suspend":true}}'
sudo k3s kubectl -n network-services delete job \
  -l app.kubernetes.io/name=syncthing-backup --wait=true
sudo k3s kubectl -n network-services delete cronjob \
  syncthing-backup syncthing-backup-freshness \
  --ignore-not-found
sudo k3s kubectl -n network-services delete secret \
  syncthing-backup-credentials --ignore-not-found
```

This does not delete the remote Restic repository. Commit the matching desired
state before resuming the child, or Flux will recreate the backup plane.

Duplicati was retired after the Restic backup, full-data check, and isolated
restore proof passed. Its Deployment, Services, HTTPRoute, NetworkPolicy,
access-proxy ConfigMap, and live Secret are absent. This retirement does not
authorize deleting the existing `rezanmz-homeserver-backup` B2 repository, AES
passphrase, SOPS settings key, retained `duplicati-config` PVC,
or `/home/reza/persistent` legacy tree. The unused `duplicati-backups` NFS
PV/PVC and dedicated writable export were removed, but their empty underlying
directory remains on the Pi. The old repository is native Duplicati B2 format
at the bucket root and must not be compacted, purged, repaired with deletion,
or reused by Restic.

The Longhorn HelmRelease owns the BackupTarget and detached-volume values through
Longhorn's supported chart configuration; `longhorn-manager` then owns the
singleton custom resources. The `longhorn-backups` child is the stable prunable
owner for only the credential and recurring job. This split avoids Flux
server-side-apply conflicts with Longhorn-managed fields.

For a planned Git rollback, keep the child Kustomization and remove its Secret
and RecurringJob resources so its next successful reconcile prunes them. In the
same change, explicitly set `defaultBackupStore.backupTarget` and
`defaultBackupStore.backupTargetCredentialSecret` to empty strings and
`defaultSettings.allowRecurringJobWhileVolumeDetached` to `"false"` in the
Longhorn HelmRelease. Do not merely omit those Helm values: Longhorn preserves
an existing value when the corresponding default-resource key is absent. Verify
the recurring job and Secret are gone and the default BackupTarget is blank
before removing the child itself.

Because the root Flux Kustomization intentionally has pruning disabled, removing
the child manifest from Git does not delete the live child object. After the
rollback commit has reconciled and the owned resources are absent, remove it
explicitly:

```bash
sudo k3s kubectl -n flux-system delete kustomization longhorn-backups
```

For an emergency stop before a Git change is ready, suspend both the root and
backup Kustomizations first so they cannot immediately restore the desired
state:

```bash
sudo k3s kubectl -n flux-system patch kustomization flux-system \
  --type=merge -p '{"spec":{"suspend":true}}'
sudo k3s kubectl -n flux-system patch kustomization longhorn-backups \
  --type=merge -p '{"spec":{"suspend":true}}'
sudo k3s kubectl -n longhorn-system delete recurringjob b2-nightly \
  --ignore-not-found
sudo k3s kubectl -n longhorn-system patch backuptarget default \
  --type=merge -p '{"spec":{"backupTargetURL":"","credentialSecret":""}}'
sudo k3s kubectl -n longhorn-system patch setting \
  allow-recurring-job-while-volume-detached --type=merge -p '{"value":"false"}'
sudo k3s kubectl -n longhorn-system delete secret longhorn-backblaze-b2 \
  --ignore-not-found
```

The emergency stop deliberately creates GitOps drift. Commit the matching
rollback before resuming the root Kustomization and then `longhorn-backups`;
otherwise Flux and Longhorn restore the target, credential, and schedule.

The security-remediation rollback set is root-only at:

```text
/srv/home-server-backups/remediation-prechange-20260714T004819Z/
```

It includes a consistency-safe K3s server-state archive, cluster inventory,
pre-restore PVC archives, quarantined Open WebUI extensions, Syncthing state,
and the age-key rotation rollback material. The Pi also has root-only/current
PVC recovery archives under `/home/reza/security-recovery-current/`. These are
rollback aids on the same two machines, not independent backups.

Never stage Open WebUI user-import CSV files under
`/app/backend/data/static`: that directory is served without application
authentication. Keep recovery imports outside the static tree with mode 0600
and verify the former URL returns 404 after cleanup.

### Retired Duplicati recovery artifacts

`apps/duplicati/kustomization.yaml` reconciles only `storage.yaml`. The retired
workload manifests and SOPS-encrypted settings key remain unreferenced recovery
artifacts in that directory; do not re-add them as an ordinary rollback. The
live `duplicati-config` Longhorn PVC remains deliberately present and unmounted.
The obsolete `duplicati-backups` NFS PVC/PV and writable export must remain
absent. Confirm that state with:

```bash
sudo k3s kubectl -n network-services get pvc duplicati-config
sudo k3s kubectl -n network-services get pvc duplicati-backups --ignore-not-found
sudo k3s kubectl get pv duplicati-backups-network-services --ignore-not-found
sudo k3s kubectl -n network-services get \
  deployment/duplicati service/duplicati service/duplicati-access \
  httproute/duplicati networkpolicy/duplicati \
  configmap/duplicati-access-proxy secret/duplicati-secrets \
  --ignore-not-found
```

The second, third, and final commands should return no rows. As of the
2026-07-14 recovery, Duplicati's local database had been recreated from B2, its
integrity and a remote sample test passed, and a new backup completed without
errors. Its scheduler was paused; the pre-existing `1W:1D,4W:1W,12M:1M`
retention policy removed one old file-list during that verification backup.

After the final pod shutdown, Longhorn snapshot
`duplicati-final-snap-20260714t163445z` and backup
`duplicati-final-backup-20260714t163445z` completed for the detached
`duplicati-config` volume. They carry only the `purpose=duplicati-retirement`
label, so the recurring job's normal retention does not own this archival point.
Do not delete that Backup CR: deletion can remove the corresponding remote
backup object.

Never use Duplicati `repair-update`, purge, compact, or remote delete while
diagnosing the retained set. Snapshot the config volume/database first, prefer
a remote-only database recreate and read-only verification, and preserve the
original. Any temporary recovery pod would again need root-level read access to
the historical source because the NFS export is root-squashed; give it the
smallest exact mounts and network egress, keep the source read-only, do not
publish a route, and delete it after a disposable restore test.

For a one-time directory-to-PVC migration, stop every writer and take a
consistency-safe source snapshot before acknowledging quiescence:

```bash
scripts/migrate-directory-to-pvc.sh NAMESPACE PVC /absolute/snapshot/path \
  --source-is-read-only-snapshot --target-controllers-are-suspended pi beelink
```

Mount the consistency-safe source snapshot read-only; a stopped application on a
writable directory is not sufficient. Scale built-in PVC-owning controllers to
zero, suspend Jobs/CronJobs and their complete Flux Kustomization/HelmRelease
ownership chain, and remove any matching HPA before acknowledging the target.
The helper checks Flux status inventories as well as labels, monitors controller
and consumer state throughout the copy and verification, and fails closed if any
cluster query or JSON proof fails. It refuses a mounted or non-empty PVC, an
invalid/non-empty `lost+found`, mutable or unsupported source metadata, nested
mounts, sparse files, and hard links that leave the snapshot.

The helper streams the snapshot over SSH without creating a Kubernetes
`hostPath`, restores symbolic-link ownership explicitly, recomputes source and
target fingerprints, and verifies file contents, ownership, modes, hard-link
counts, and symlink targets. On success it waits for the helper pod to release
the PVC before returning zero. A failed copy can still leave a partial target;
inspect and clear it deliberately rather than rerunning blindly. Kubernetes RWO
does not prevent a custom controller from mounting on the same node, so the
operator acknowledgement is still required for controllers the helper cannot
enumerate.

## Media VPN checks

The consolidated downloads pod shares Gluetun's network namespace. A healthy
pod has all containers ready, a ProtonVPN public address, and qBittorrent's
listening port matched to Gluetun's forwarded port.

```bash
sudo k3s kubectl -n media get pod -l app.kubernetes.io/name=media-vpn
sudo k3s kubectl -n media logs deployment/downloads -c gluetun --tail=100
sudo k3s kubectl -n media logs deployment/downloads -c qbittorrent --tail=100
```

If Gluetun is unhealthy, keep the download clients stopped or unready until its
tunnel and firewall are healthy. Do not bypass the sidecar with an ordinary
pod-level egress route.

## Secrets and recovery identities

Only SOPS ciphertext belongs in Git. The age public recipient is in the SOPS
configuration. Root-only recovery identities are stored at:

- Beelink: `/root/.config/sops/age/keys.txt`
- Pi: `/root/.config/sops/age/home-server.txt`
- Operator workstation: `~/.config/sops/age/keys.txt` (mode `0600`)
- Cluster: `flux-system/sops-age`

Never print a private identity, put it in shell history, or commit it. Store an
additional recovery copy in a password manager or on encrypted removable media.

Rotating the age recipient protects future access to the current ciphertext;
it does not revoke application credentials present in old Git history or other
copies. Rotate provider tokens, passwords, API keys, and OIDC credentials at
their issuing systems, then re-encrypt the updated Kubernetes Secrets. Preserve
application encryption keys such as Speedtest Tracker's `APP_KEY` until the
matching database has been successfully decrypted and migrated: substituting a
new key can make existing encrypted fields unrecoverable.

The remaining coordinated rotation set includes Cloudflare API tokens,
Telegram and ProtonVPN credentials, Authentik/OIDC client secrets, and
application passwords or API keys. Rotate one integration at a time, update its
SOPS Secret, reconcile, and prove the dependent workload before revoking the
old value.

The legacy Speedtest Tracker database must not replace the current PVC until a
trusted copy of its matching `APP_KEY` is recovered and proven. The database is
healthy, but encrypted fields cannot be validated from a hash or a newly
generated key. Keep the legacy source read-only and preserve the current PVC
until that prerequisite is satisfied.

## Planned maintenance

The two-node design has deliberate single points of failure:

- Beelink maintenance removes the K3s control plane and most compute workloads.
- Pi maintenance removes DNS/DHCP, public ingress, WireGuard, SMB, Syncthing
  discovery, scheduled Syncthing backups, and all NFS-backed data.

Before rebooting either node, confirm the other node is healthy, check Longhorn
volume health, and expect the services tied to the maintained node to be
unavailable. Afterward, verify node readiness, Longhorn health, Flux readiness,
network listeners, and a representative public route.

AnythingLLM and the Gemini Telegram bot are intentionally absent. Headlamp is served at
`headlamp.reza.network`; it requires both LAN/WireGuard access and an Authentik
login. The
`loggifly` workload is the Kubernetes event exporter; these
names are retained only for hostname and migration continuity.
