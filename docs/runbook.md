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

## Pi network services

Pi-hole, Samba, Syncthing, wg-easy, and Duplicati are Kubernetes workloads in
the `network-services` namespace. They are pinned to the Pi when they require
its address or data.

```bash
sudo k3s kubectl -n network-services get deployments,pods,pvc -o wide
sudo k3s kubectl -n network-services logs deployment/pihole --tail=100
sudo k3s kubectl -n network-services logs deployment/wg-easy --tail=100
```

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
The FTL listener must be `127.0.0.1:8181`; the colocated proxy listens on 18181,
accepts only the cluster pod network, and should return 403 to a direct LAN
request.

Syncthing must have automatic NAT traversal disabled (`natenabled=false`) so it
cannot ask the router to expose port 22000 through UPnP or NAT-PMP. LAN
discovery, global discovery, relays, and connections over WireGuard remain
enabled. Verify the persistent setting from the running pod after replacing its
configuration:

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
legacy `/home/reza/persistent` tree, while migrated application state lives on
Longhorn. As of 2026-07-14, Longhorn's default BackupTarget has an empty URL and
is unavailable, with no Backup or BackupVolume objects. Check the gap directly:

```bash
sudo k3s kubectl -n longhorn-system get backuptargets.longhorn.io \
  -o custom-columns=NAME:.metadata.name,AVAILABLE:.status.available,URL:.spec.backupTargetURL
sudo k3s kubectl -n longhorn-system get backups.longhorn.io,backupvolumes.longhorn.io
```

Choose the remote target, credential scope, encryption, retention, and restore
test before enabling it. A second Longhorn replica or a snapshot on either
cluster node is not an off-site backup.

The security-remediation rollback set is root-only at:

```text
/srv/home-server-backups/remediation-prechange-20260714T004819Z/
```

It includes a consistency-safe K3s server-state archive, cluster inventory,
pre-restore PVC archives, quarantined Open WebUI extensions, Syncthing state,
and the age-key rotation rollback material. The Pi also has root-only/current
PVC recovery archives under `/home/reza/security-recovery-current/`. These are
rollback aids on the same two machines, not independent backups.

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
