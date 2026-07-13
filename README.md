# Home Server

This repository is the declarative source of truth for a two-node K3s home
cluster. Flux reconciles `main`; GitHub Actions validates the manifests but does
not deploy them. The former Docker Compose deployment and SWAG edge are retired.

For operating details, see the [cluster architecture](docs/architecture.md) and
the [operator runbook](docs/runbook.md).

## Production topology

```text
Internet -> router -> Traefik host ports -> Gateway API routes -> applications
                         |                          |
                         + MetalLB VIP .240 --------+

GitHub -> Flux -> K3s
                  |-- beelink (.3): server, compute, media acceleration
                  `-- raspberrypi (.2): agent, LAN services, NFS storage
```

- `beelink` (`192.168.1.3`, amd64) is the only K3s server and the main compute
  node.
- `raspberrypi` (`192.168.1.2`, arm64) runs network-facing workloads such as
  Pi-hole, WireGuard, Samba, Syncthing, and Duplicati. It also exports the media,
  downloads, books, Syncthing, and backup trees over NFS.
- Traefik runs as a DaemonSet with host ports 80 and 443. The router can retain
  the Pi as its public forwarding target, while `192.168.1.240` is the MetalLB
  address for the same Gateway inside the LAN.
- cert-manager obtains the `reza.network` wildcard certificate with Cloudflare
  DNS-01. Application and infrastructure secrets are SOPS/age-encrypted in Git.
- Longhorn stores small application databases and configuration with two
  replicas. The Pi NFS exports remain the single source for large shared data.

This is intentionally not a highly available cluster. There is no third K3s
server or independent storage system planned at present. The Beelink control
plane and the Pi NFS server are known single points of failure.

## Workloads

| Area | Workloads | Entry points |
| --- | --- | --- |
| Identity and home | Authentik, Heimdall | `auth.reza.network`, `homepage.reza.network` |
| Personal apps | Actual Budget, MCPHub, Open WebUI with Tika, Speedtest Tracker | `budget.reza.network`, `mcphub.reza.network`, `chat.reza.network`, `speedtest.reza.network` |
| Annotation | Argilla with PostgreSQL, Elasticsearch, Redis, and worker | `argilla.reza.network` |
| Media | Jellyfin, Jellyseerr | `jellyfin.reza.network`, `jellyseerr.reza.network` |
| Downloads | Gluetun, qBittorrent, FlareSolverr, Prowlarr, Radarr, Sonarr | `qbittorrent.reza.network`, `prowlarr.reza.network`, `radarr.reza.network`, `sonarr.reza.network` |
| Books | Calibre-Web, Shelfmark | `library.reza.network`, `shelfmark.reza.network` |
| Network services | Pi-hole, wg-easy, Samba, Syncthing | `pihole.reza.network`, `vpn.reza.network`, SMB on the Pi, `syncthing.reza.network` |
| Operations | Duplicati, Headlamp, Kubernetes event exporter, Cloudflare DDNS | `duplicati.reza.network`, `headlamp.reza.network`, Telegram alerts, background DNS updates |

Headlamp is the read-only Kubernetes dashboard at `headlamp.reza.network`;
Glances is no longer deployed. The former Loggifly function is now a
Kubernetes event exporter that sends warning events to Telegram. Its historical
application name is retained in the manifests.

AnythingLLM and the Gemini Telegram bot are intentionally excluded from the
cluster. Open WebUI remains the supported local LLM interface.

## GitOps workflow

1. Change application or infrastructure manifests.
2. Encrypt any new Secret with SOPS before it enters Git.
3. Render and validate the cluster locally.
4. Push to `main`. The validation workflow checks shell syntax, Kustomize
   rendering, and encrypted-secret metadata.
5. Flux pulls the revision and reconciles it into the cluster.

Useful local checks:

```bash
bash -n scripts/*.sh
kubectl kustomize clusters/home-server >/tmp/home-server.yaml
test -s /tmp/home-server.yaml
```

The former Compose definitions have been removed. New work belongs in the
Kubernetes application and infrastructure manifests.

## Repository layout

```text
apps/                    application workloads, routes, policies, and secrets
clusters/home-server/    Flux reconciliation entry point
infrastructure/          K3s platform, storage, ingress, and host configuration
scripts/                 host preparation, bootstrap, and migration helpers
docs/                    architecture and operations documentation
```

## Access and security

- Most administrative interfaces are restricted to the home LAN and WireGuard
  ranges by an application-side proxy or a Traefik middleware. Headlamp also
  requires an Authentik session.
- Argilla and the explicitly public application routes are reachable through
  the public Gateway. Authentik supplies OIDC where the application supports it.
- Default-deny network policies and explicit egress rules limit namespace
  traffic. The Gluetun pod provides the VPN firewall and kill switch for the
  consolidated download workload.
- Never commit plaintext credentials or an age private identity. See the
  runbook for the locations of the root-only recovery copies.
