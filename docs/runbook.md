# Home cluster runbook

## Access

The K3s API is intentionally not exposed to the internet. Administer it through
the Beelink:

```bash
ssh beelink
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl get pods -A
```

The server kubeconfig is root-only at `/etc/rancher/k3s/k3s.yaml`. The Pi is an
agent and its production Compose stack remains separately managed by Docker.

## GitOps health

```bash
sudo k3s kubectl -n flux-system get gitrepositories,kustomizations
sudo k3s kubectl get helmreleases -A
```

Healthy state means every source, Kustomization, and HelmRelease reports
`READY=True`. Flux tracks `main` at `clusters/home-server` and prunes resources
removed from that path.

To request an immediate reconciliation after a push:

```bash
stamp=$(date +%s)
sudo k3s kubectl -n flux-system annotate gitrepository flux-system \
  reconcile.fluxcd.io/requestedAt="$stamp" --overwrite
sudo k3s kubectl -n flux-system annotate kustomization flux-system \
  reconcile.fluxcd.io/requestedAt="$stamp" --overwrite
```

## Node scheduling

The Pi is cordoned while it runs the legacy Compose stack:

```bash
sudo k3s kubectl get nodes
```

Longhorn system DaemonSets and existing replicas still run there. Do not leave
the Pi uncordoned until its Docker workload has been reduced enough for the
Kubernetes scheduler to make safe placement decisions. When a new two-replica
volume is created during migration, uncordon only long enough for Longhorn to
build its Pi replica, verify the volume is healthy, then cordon it again:

```bash
sudo k3s kubectl uncordon raspberrypi
sudo k3s kubectl -n longhorn-system get volumes.longhorn.io
sudo k3s kubectl cordon raspberrypi
```

## Storage

The default `longhorn` StorageClass uses two replicas, `Retain` reclaim policy,
and `WaitForFirstConsumer`. It is for small application state only.

```bash
sudo k3s kubectl get storageclass
sudo k3s kubectl -n longhorn-system get nodes.longhorn.io
sudo k3s kubectl -n longhorn-system get volumes.longhorn.io
```

Media, downloads, books, Syncthing shared data, and backup repositories stay on
the Pi until independent NAS/NFS storage is available.

The pre-migration rollback set is on the Beelink at:

```text
/srv/home-server-backups/pre-k3s-20260712/
├── persistent/
├── postgres/
└── SHA256SUMS
```

This is not off-site backup. Copy it to independent storage before retiring any
Pi service.

## Networking and TLS

- Pi-hole DHCP range: `192.168.1.10-192.168.1.239`
- MetalLB pool: `192.168.1.240-192.168.1.249`
- Traefik Gateway VIP: `192.168.1.240`
- Current public router target: Pi/SWAG at `192.168.1.2`

Test the Kubernetes edge without changing DNS or the router:

```bash
curl --resolve homepage.reza.network:443:192.168.1.240 \
  https://homepage.reza.network/
```

The `letsencrypt-production` ClusterIssuer uses Cloudflare DNS-01. The wildcard
certificate is stored as `traefik/reza-network-tls` and renews automatically.

```bash
sudo k3s kubectl get clusterissuer letsencrypt-production
sudo k3s kubectl -n traefik get certificate reza-network
sudo k3s kubectl -n traefik get gateway home
sudo k3s kubectl -n apps get httproutes
```

## Secrets

Only SOPS ciphertext belongs in Git. The age public recipient is in
`.sops.yaml`. Root-only recovery identities are stored at:

- Beelink: `/root/.config/sops/age/keys.txt`
- Pi: `/root/.config/sops/age/home-server.txt`
- Cluster: `flux-system/sops-age`

The copies on the two cluster nodes are not an off-site recovery strategy. Back
up the identity to a secure password manager or encrypted removable medium.
Never print the identity, put it in shell history, or commit it.

## Heimdall canary

`apps/heimdall` is a data-restored Kubernetes canary on the Beelink. Its public
hostname still reaches Pi/SWAG; the K3s copy is tested through the `.240` VIP.
Before cutover, re-run a final SQLite online backup, sync any changes since the
canary copy, validate the route, and keep the Pi container available for quick
rollback.

## Remaining dependencies

- Add a third wired SSD-backed node before converting the K3s datastore to
  embedded-etcd HA.
- Add independent NAS/NFS storage before moving large/shared datasets.
- Reserve and forward router ports 80/443 to `192.168.1.240` only after service
  route parity is complete.
- Move DHCP/WireGuard to the router and SMB to the NAS where possible.
