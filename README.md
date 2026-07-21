# Home Server

This repository is the declarative source of truth for a two-node K3s home
cluster. Flux reconciles `main`; GitHub Actions validates the manifests but does
not deploy them. The former Docker Compose deployment and SWAG edge are retired.

For operating details, see the [cluster architecture](docs/architecture.md),
the [service integration catalog](docs/service-catalog.md), the
[catalog design decision](docs/service-catalog-design.md), the
[configuration ownership policy](docs/configuration-ownership.md), the
[service lifecycle manual](docs/service-operations.md), the
[cluster and node operations manual](docs/cluster-operations.md), the
[Open WebUI operating model](docs/open-webui.md), and the
[personal assistant integrations](docs/personal-assistant.md), plus the
[incident runbook](docs/runbook.md).

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
  node. Kea DHCP is pinned here because ISC's official image is amd64-only.
- `raspberrypi` (`192.168.1.2`, arm64) runs network-facing workloads such as
  Blocky DNS, WireGuard, Samba, and Syncthing. It also exports the media tree
  (including downloads and books), Syncthing data, and the read-only legacy
  tree over NFS.
- Traefik runs as a DaemonSet with host ports 80 and 443. The router can retain
  the Pi as its public forwarding target, while `192.168.1.240` is the MetalLB
  address for the same Gateway inside the LAN.
- cert-manager obtains the `reza.network` wildcard certificate with Cloudflare
  DNS-01. Application and infrastructure secrets are SOPS/age-encrypted in Git.
- Longhorn stores small application databases and configuration with two
  replicas. The Pi NFS exports remain the single source for large shared data.

This is intentionally not a highly available cluster. There is no third K3s
server or independent shared-storage/NAS system planned at present. The
Beelink control plane and the Pi NFS server are known single points of failure.

## Operator manuals

| Task | Start here |
| --- | --- |
| Understand the topology, traffic, storage, and security boundaries | [Cluster architecture](docs/architecture.md) |
| Register cross-service DNS, auth, Homepage, monitoring, placement, and backup intent | [Service integration catalog](docs/service-catalog.md) |
| Understand why the catalog is designed this way or extend its compiler | [Catalog design decision](docs/service-catalog-design.md) |
| Decide whether a setting belongs in Git or in backed-up application state | [Configuration ownership](docs/configuration-ownership.md) |
| Add, modify, roll back, or retire an application | [Service lifecycle manual](docs/service-operations.md) |
| Understand placement, add/remove a node, or move a workload | [Cluster and node operations manual](docs/cluster-operations.md) |
| Use or modify Open WebUI profiles, models, research, retrieval, or memory | [Open WebUI operating model](docs/open-webui.md) |
| Operate Vikunja, personal Gmail/Calendar, Obsidian, and research MCP tools | [Personal assistant integrations](docs/personal-assistant.md) |
| Diagnose an outage, reconcile Flux, or restore data | [Incident runbook](docs/runbook.md) |

The node operations manual also records current live deviations that still need
follow-up. Do not infer that a YAML file is active merely because it exists;
each directory's `kustomization.yaml` defines the desired resources.

## Workloads

| Area | Workloads | Entry points |
| --- | --- | --- |
| Identity and home | Authentik, Homepage, Home Assistant | `auth.reza.network`, `homepage.reza.network`, `homeassistant.reza.network` |
| Personal apps | Actual Budget, Vikunja, MCPHub, Open WebUI with Tika, internal SearXNG, MCP-managed research/Google/Obsidian tools, Speedtest Tracker | `budget.reza.network`, `tasks.reza.network`, `mcphub.reza.network`, `chat.reza.network`, `speedtest.reza.network` |
| Annotation | Argilla with PostgreSQL, Elasticsearch, Redis, and worker | `argilla.reza.network` |
| Media | Jellyfin, Jellyseerr | `jellyfin.reza.network`, `jellyseerr.reza.network` |
| Downloads | Gluetun, qBittorrent, FlareSolverr, Prowlarr, Radarr, Sonarr | `qbittorrent.reza.network`, `prowlarr.reza.network`, `radarr.reza.network`, `sonarr.reza.network` |
| Books | Audiobookshelf, Calibre-Web, Shelfmark | `audiobooks.reza.network`, `library.reza.network`, `shelfmark.reza.network` |
| Network services | Blocky DNS, Kea DHCP, ISC Stork, wg-easy, Samba, Syncthing | DNS at `192.168.1.2`, DHCP from `192.168.1.3`, read-only `stork.reza.network`, `vpn.reza.network`, SMB on the Pi, `syncthing.reza.network` |
| Operations | Grafana, Prometheus, Alertmanager, Syncthing Restic backups, Headlamp, Kubernetes event exporter, Cloudflare DDNS | `grafana.reza.network`, scheduled B2 backups, `headlamp.reza.network`, Telegram alerts, background DNS updates |

Headlamp is the read-only Kubernetes dashboard at `headlamp.reza.network`;
Stork is the read-only Kea dashboard at `stork.reza.network`; Grafana is the
metrics dashboard at `grafana.reza.network`. All three are limited to the LAN
or WireGuard and use native Authentik OIDC where supported. Prometheus and
Alertmanager have no external routes. Glances is no longer deployed. The
former Loggifly function is now a Kubernetes event exporter that sends warning
events to Telegram. Its historical application name is retained in the
manifests.

Homepage is the YAML-managed service directory at `homepage.reza.network`. It
is limited to the LAN or WireGuard, requires an Authentik session through the
embedded proxy outpost, and uses read-only Kubernetes and Metrics API access to
show workload health and resource use. It has no permission to read Secrets,
logs, or application data and cannot mutate cluster resources.

AnythingLLM and the Gemini Telegram bot are intentionally excluded from the
cluster. Open WebUI remains the supported local LLM interface. Its profiles,
model approval cycle, GPT Researcher integration, retrieval model, and
personal-memory boundaries are documented in the
[Open WebUI operating model](docs/open-webui.md).

## GitOps workflow

1. Change application or infrastructure manifests.
2. Add or update the colocated `<service-id>.catalog.yaml` descriptor when
   integration intent changes, then run
   `python3 scripts/service_catalog.py render`.
3. Encrypt any new Secret with SOPS before it enters Git.
4. Render and validate the cluster locally.
5. Push a branch and open a pull request. The protected `main` branch requires
   the validation workflow, including shell and Python checks, SOPS structure,
   Kustomize rendering, Kubernetes schemas, and the reviewed high-risk-policy
   baseline.
6. Merge only after the required check passes. Flux then pulls the protected
   `main` revision and reconciles it into the cluster.

Useful local checks:

```bash
set -euo pipefail
scripts/ci/validate-shell.sh
python3 -m unittest discover --start-directory scripts/ci --pattern 'test_*.py'
python3 scripts/ci/validate-secrets.py
{
  kubectl kustomize clusters/home-server
  printf '\n---\n'
  kubectl kustomize infrastructure/snapshot-controller/storage
  printf '\n---\n'
  kubectl kustomize infrastructure/longhorn/readiness
  printf '\n---\n'
  kubectl kustomize infrastructure/longhorn/backups
  printf '\n---\n'
  kubectl kustomize apps/syncthing/backups
} >/tmp/home-server.yaml
test -s /tmp/home-server.yaml
python3 scripts/service_catalog.py check --rendered /tmp/home-server.yaml
python3 scripts/ci/validate-secrets.py --rendered /tmp/home-server.yaml
python3 scripts/ci/check-high-risk-policy.py \
  /tmp/home-server.yaml scripts/ci/high-risk-baseline.txt
python3 scripts/ci/validate-git-source-pins.py /tmp/home-server.yaml
```

The former Compose definitions have been removed. New work belongs in the
Kubernetes application and infrastructure manifests.

## Repository layout

```text
apps/                    application workloads, routes, policies, and secrets
catalog/                 cross-service integration intent and generated-input data
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
  the public Gateway. A user-facing application that supports OIDC, OAuth2, or
  SAML natively must use that native integration with Authentik. Proxy or
  forward-auth is an exception for applications without suitable native
  support, not the default. The service lifecycle manual records the required
  integration and exception checks.
- Default-deny network policies and explicit egress rules limit namespace
  traffic. The Gluetun pod provides the VPN firewall and kill switch for the
  consolidated download workload.
- Never commit plaintext credentials or an age private identity. See the
  runbook for the locations of the root-only recovery copies.
- Git-defined workload and Helm-selected images are pinned by digest.
  cert-manager, Traefik, and MetalLB charts use digest-pinned OCI artifacts;
  Longhorn's chart uses its exact upstream Git commit. CI independently
  fetches, checksums, renders, schema-validates, and policy-scans those
  immutable charts. Existing Longhorn volumes retain tag-only EngineImage
  metadata that currently resolves to the same reviewed digest; same-version
  normalization is intentionally deferred until a future supported engine
  upgrade because Longhorn warns against upgrading between identical commits.
- GitHub Actions uses GitHub-hosted runners only. Do not register either cluster
  node as a repository runner or store deployment credentials in Actions.
