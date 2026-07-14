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

## Pi network services

Pi-hole, Samba, Syncthing, wg-easy, and Duplicati are Kubernetes workloads in
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
Pi as trusted for those routes, keep sensitive workloads off that node unless
they need its hardware/network role, and never replace the exception with the
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
parameter is `type: snap`; omitting it requests a remote backup, which fails
while no BackupTarget is configured.

Large and shared data remains on NFS exported by the Pi. Check the server and
exports directly when media, downloads, books, Syncthing data, or backups all
fail at once:

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

This set and the age identities are not off-site backups. Duplicati sends its
encrypted repository to Backblaze B2, but restore credentials and the SOPS age
identities still need an independent recovery copy.

Do not assume that job protects the active PVCs. Duplicati mounts only the Pi's
`/home/reza/persistent` tree, while migrated application state lives on
Longhorn. Longhorn's default BackupTarget is the dedicated private
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
Keep Duplicati until the first remote backup and disposable B2 restore test
succeed. Retiring its workload does not authorize deleting the existing B2
repository, retained Longhorn config volume, or `/home/reza/persistent` legacy
tree; preserve those until their remaining recovery value is reviewed.

The Longhorn target does not cover any `nfs-media` PersistentVolume. In
particular, active Syncthing data remains at
`/home/reza/persistent/syncthing/data` and is inside Duplicati's current source,
while `/home/reza/media` is outside the configured Duplicati job as well as
Longhorn. Do not remove Duplicati until the Syncthing/NFS data is deliberately
migrated, covered by a replacement file-level backup, or accepted as an
unprotected/reconstructible data class.

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

Duplicati runs as root so it can read application-owned state. It is pinned to
the Pi and uses a read-only host path for `/home/reza/persistent`; routing this
source through the root-squashed NFS PersistentVolume silently excludes
protected directories. Check the newest Duplicati result for permission
warnings after any storage or identity change. Its pod egress is limited to
Kubernetes DNS and public TCP 443 for Backblaze B2; do not restore unrestricted
egress to support a private destination without adding the exact destination
and port instead.

Never use a Duplicati `repair-update`, purge, compact, or remote delete while
diagnosing an incomplete remote set. Snapshot the local database first, prefer
a remote-only database recreate and verification, and preserve the original
database until a new backup and restore test have succeeded.

As of the 2026-07-14 recovery, Duplicati's local database has been recreated
from B2, its integrity and a remote sample test pass, and a new backup completed
without errors. The scheduler is intentionally paused: the pre-existing
`1W:1D,4W:1W,12M:1M` retention policy automatically removed one old file-list
during the verification backup. Review that policy and the required recovery
points before resuming; then perform a restore test to a disposable path.

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
  discovery, Duplicati, and all NFS-backed data.

Before rebooting either node, confirm the other node is healthy, check Longhorn
volume health, and expect the services tied to the maintained node to be
unavailable. Afterward, verify node readiness, Longhorn health, Flux readiness,
network listeners, and a representative public route.

AnythingLLM and the Gemini Telegram bot are intentionally absent. Headlamp is served at
`headlamp.reza.network`; it requires both LAN/WireGuard access and an Authentik
login. The
`loggifly` workload is the Kubernetes event exporter; these
names are retained only for hostname and migration continuity.
