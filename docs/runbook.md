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

```bash
sudo k3s kubectl -n flux-system get gitrepositories,kustomizations -o wide
sudo k3s kubectl get helmreleases -A
```

Every source, Kustomization, and HelmRelease should report `READY=True`. Flux
tracks `main` and prunes resources removed from the cluster entry point.

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

The retired Compose definitions are not a deployment path. Do not restart the
old Docker projects to work around a Kubernetes failure; diagnose or roll back
the Git revision through Flux.

## Ingress and TLS

- Public router target: Pi at `192.168.1.2`, TCP ports 80 and 443
- Traefik host ports: TCP 80 and 443 on both cluster nodes
- Traefik MetalLB VIP: `192.168.1.240`
- MetalLB pool: `192.168.1.240-192.168.1.249`
- Pi-hole DHCP range: `192.168.1.10-192.168.1.239`

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

Expected Pi-facing services include DNS on TCP/UDP 53, DHCP on UDP 67, NTP on
UDP 123, SMB on TCP 139/445, Syncthing on TCP/UDP 22000 and UDP 21027, and
WireGuard on UDP 1234. The Pi-hole UI listens internally on port 8181 and is
published through the Gateway rather than directly as the public service.

wg-easy v15 stores its endpoint, client DNS, and AllowedIPs in the persistent
application database; the v14 `WG_*` environment variables are ignored. The
global and per-client DNS value should be `192.168.1.2`. After changing client
DNS or routes, download/import the refreshed client profile because WireGuard
cannot push configuration changes into an already imported profile.

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

Duplicati runs as root so it can read application-owned state. It is pinned to
the Pi and uses a read-only host path for `/home/reza/persistent`; routing this
source through the root-squashed NFS PersistentVolume silently excludes
protected directories. Check the newest Duplicati result for permission
warnings after any storage or identity change.

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
- Cluster: `flux-system/sops-age`

Never print a private identity, put it in shell history, or commit it. Store an
additional recovery copy in a password manager or on encrypted removable media.

## Planned maintenance

The two-node design has deliberate single points of failure:

- Beelink maintenance removes the K3s control plane and most compute workloads.
- Pi maintenance removes DNS/DHCP, public ingress, WireGuard, SMB, Syncthing
  discovery, Duplicati, and all NFS-backed data.

Before rebooting either node, confirm the other node is healthy, check Longhorn
volume health, and expect the services tied to the maintained node to be
unavailable. Afterward, verify node readiness, Longhorn health, Flux readiness,
network listeners, and a representative public route.

AnythingLLM and the Gemini Telegram bot are intentionally absent. Do not restore
their retired Compose projects during maintenance. The `glances` route is
Headlamp, and the `loggifly` workload is the Kubernetes event exporter; these
names are retained only for hostname and migration continuity.
