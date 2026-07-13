# Home cluster architecture

## Operating model

K3s is the only production application platform. Flux reconciles this public
repository, decrypts SOPS resources in the cluster, and prunes objects removed
from the cluster entry point. GitHub Actions validates configuration; it does
not SSH into either node or run Docker Compose.

The former Compose containers and SWAG reverse proxy are retired. Their
definitions are no longer part of this repository.

## Nodes and failure domains

The cluster has two wired nodes:

- `beelink` (`192.168.1.3`, amd64) is the single K3s server and the main compute
  node. It hosts ordinary application workloads, databases, the consolidated
  VPN/download pod, and Jellyfin with `/dev/dri` hardware access.
- `raspberrypi` (`192.168.1.2`, arm64) is a K3s agent and the network/storage
  node. Workloads that depend on its LAN address, broadcasts, local files, or
  forwarded ports are pinned there.

K3s uses its single-server SQLite datastore. Embedded etcd is not enabled
because two control-plane members cannot provide useful failure quorum. There
is no third node planned, so a Beelink outage is an accepted control-plane
outage. Existing pods on the Pi may continue temporarily, but the cluster
cannot reconcile or reschedule until the server returns.

## Traffic flow

```text
Public clients -> Cloudflare DNS -> router -> 192.168.1.2:80/443
                                               |
LAN clients ----------------------------> Traefik DaemonSet
                                               |
LAN validation -> 192.168.1.240 ---------------+
                                               |
                                       Gateway API HTTPRoutes
                                               |
                                          applications
```

Traefik runs on both nodes as a DaemonSet and claims host ports 80 and 443. The
Pi therefore preserves the router's previous public-forwarding contract without
SWAG. MetalLB also advertises `192.168.1.240` for the Traefik LoadBalancer
Service, providing a stable cluster VIP for LAN access and direct validation.
The reserved MetalLB range is `192.168.1.240-192.168.1.249`, outside Pi-hole's
DHCP range of `192.168.1.10-192.168.1.239`.

Gateway API HTTPRoutes attach applications to the shared Traefik Gateway.
cert-manager uses Cloudflare DNS-01 to issue and renew a wildcard Let's Encrypt
certificate for `reza.network`. Traefik's CRD provider is also enabled so
Gateway API extension filters can reference LAN/VPN IP allow-list middleware.

Pi-hole uses the Pi host network for DNS, DHCP, and NTP. Samba and Syncthing also
use the Pi host network for LAN discovery. wg-easy is pinned to the Pi and maps
the router-facing UDP port 1234 to its WireGuard listener. These constraints are
physical requirements rather than general scheduling policy.

Pi-hole's split-horizon overrides point HTTP hostnames at the Traefik VIP
`192.168.1.240`, so application pod placement is independent of DNS. Pi-specific
protocols such as SMB, NFS, DNS/DHCP, and WireGuard continue to use
`192.168.1.2`. Jellyfin advertises its Traefik HTTPS hostname; its host network
is retained only for LAN discovery and DLNA multicast.

## Workload placement

Ordinary workloads are eligible for any node with a compatible image and enough
resources. Explicit placement is used where the application needs:

- the Pi address, LAN broadcasts, NFS source data, or a router-forwarded port;
- Beelink hardware such as `/dev/dri`;
- a compatible CPU architecture; or
- colocated containers that must share one network namespace.

The downloads deployment combines Gluetun, qBittorrent, FlareSolverr, Prowlarr,
Radarr, Sonarr, Shelfmark, and their access proxies in one pod. This preserves
the VPN network-namespace contract. Gluetun owns the encrypted egress path,
firewall, kill switch, and ProtonVPN forwarded port.

Singleton applications and databases stay at one replica even though their
volumes are replicated. Storage replication is not application-level
clustering.

## Storage

Two storage mechanisms serve different data classes:

- Longhorn stores small databases, configuration, and application state. Its
  default StorageClass uses two replicas, `Retain`, and
  `WaitForFirstConsumer`.
- Static NFS volumes exported by the Pi store media, downloads, books, shared
  Syncthing data, an optional local Duplicati repository tree, and read-only
  access to the former persistent-data tree.

The Pi NFS exports are the current authoritative shared storage. No independent
NAS is planned at present. This is an accepted single point of failure: the two
Longhorn replicas protect small state against one disk or node loss, but they do
not make the K3s control plane or Pi-hosted NFS data highly available.

The pre-migration rollback snapshot at
`/srv/home-server-backups/pre-k3s-20260712` on the Beelink contains a copy of the
Pi application-state tree and consistency-safe PostgreSQL dumps. It is a local
recovery set, not an off-site backup. Duplicati writes encrypted backup archives
to Backblaze B2. Because it is pinned to the Pi, its source is a read-only host
path; this lets the backup process traverse application-owned directories
without weakening NFS root-squashing for the rest of the cluster.

## Application boundaries

Applications are separated into four operational namespaces:

- `apps` for identity, personal, and general web applications;
- `media` for Jellyfin, books, download automation, and VPN-isolated egress;
- `network-services` for Pi-hole, WireGuard, Samba, Syncthing, and Duplicati;
- `monitoring` for Headlamp and Kubernetes event export.

Namespace default-deny policies and workload-specific rules permit only the
required ingress and egress. Administrative routes use LAN/WireGuard allow
lists. SOPS/age-encrypted Secret manifests are safe to store in the public
repository; the private age identity remains root-only outside Git.

Headlamp provides read-only cluster and metrics permissions at
`headlamp.reza.network`. It is available only from the LAN or WireGuard and
requires an Authentik session. The historical Loggifly workload name now runs a
Kubernetes event exporter that delivers warning events to Telegram. AnythingLLM
and the Gemini Telegram bot are deliberately not part of the production
cluster.

## Accepted constraints

This design prioritizes a complete K3s migration over adding hardware:

- one K3s server means no control-plane HA;
- Pi-hosted NFS means no shared-storage HA;
- two Longhorn replicas tolerate only one replica failure and still depend on
  the single control plane for orchestration;
- maintenance on the Pi interrupts DNS/DHCP, public ingress, WireGuard, SMB,
  Syncthing discovery, and NFS-backed applications;
- maintenance on the Beelink interrupts cluster administration and most
  compute workloads.

These are current operating assumptions, not pending migration steps. Revisit
them only if a third node or independent storage is intentionally introduced.
