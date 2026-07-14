# Home cluster architecture

## Operating model

K3s is the only production application platform. Flux reconciles this public
repository and decrypts SOPS resources in the cluster. The root Kustomization
intentionally has `prune: false`; resource retirement is a reviewed, explicit
operation rather than an automatic consequence of removing a manifest. GitHub
Actions validates configuration; it does not SSH into either node or run Docker
Compose.

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
The administrative LAN ranges deliberately omit the two node addresses
(`192.168.1.2` and `.3`). K3s SNATs some cross-node pod-to-hostPort traffic to
the peer node address, so trusting those addresses would let an unrelated pod
inherit LAN access. Requests originating on a node itself are denied for the
same reason; use the MetalLB VIP from a normal LAN client for administration.

wg-easy masquerades client traffic before it leaves its pod, so Traefik and the
application access proxies see the Pi node's fixed pod CIDR (`10.42.1.0/24`)
rather than the original `10.8.0.0/24` client address. Administrative allow
lists therefore include that one node CIDR. This deliberately trusts pods on
the Pi for those routes; it must never be broadened to the cluster-wide
`10.42.0.0/16`. The high-risk-policy check records every such exception so a
new or wider pod-CIDR allow-list requires explicit review.

Pi-hole uses the Pi host network for DNS, DHCP, and NTP, but its web server is
bound to loopback and reached only through a colocated proxy. That host-network
proxy requires a cert-manager-managed client certificate presented by Traefik;
source allow-lists are evaluated only after backend mTLS succeeds. A pod cannot
bypass the backend merely by reaching its node port or forging forwarded headers.
Gateway allow-lists also reject the ambiguous K3s node addresses; the Pi pod
CIDR remains the explicit wg-easy exception described above.
Samba and Syncthing also use the Pi host network for LAN discovery. Syncthing's
GUI is TLS loopback-only, and its colocated proxy uses the same dedicated
cert-manager backend-mTLS pattern as Pi-hole; port 18384 must never serve
plaintext or accept a client without Traefik's certificate. wg-easy is pinned
to the Pi and maps the router-facing UDP port 1234 to its WireGuard listener.
These constraints are physical requirements rather than general scheduling
policy.

Syncthing's automatic UPnP/NAT-PMP port mapping is disabled. LAN discovery,
WireGuard access, global discovery, and relays remain available, but Syncthing
must not silently create a new Internet-facing router mapping.

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

K3s does not bundle the Kubernetes CSI snapshot APIs. The cluster therefore
reconciles the upstream external-snapshotter CRDs and common snapshot controller
from the exact `v8.5.0` commit used by Longhorn's snapshotter sidecars; the
controller image is pinned to a multi-architecture digest. This restores the
snapshot API, but local snapshots are not an independent backup target.

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
without weakening NFS root-squashing for the rest of the cluster. NetworkPolicy
limits this high-access pod to cluster DNS and public HTTPS for Backblaze B2.

Duplicati's current `/source` mount covers only the legacy Pi
`/home/reza/persistent` tree; it cannot see the active Longhorn PVC filesystems.
Longhorn currently has no remote BackupTarget. Its two replicas, local snapshots,
and the same-site recovery archives therefore protect availability but are not
an independent backup of migrated application state. The selected follow-up
design is a dedicated, encrypted Backblaze B2 S3-compatible BackupTarget used
directly by Longhorn. Duplicati will not be expanded to mount active PVCs; it
remains paused only as a recovery fallback until a Longhorn B2 backup and
disposable restore test succeed, after which its workload can be retired.

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

The protected `main` branch requires a GitHub-hosted validation job. It checks
helper syntax and tests, rejects plaintext or malformed SOPS Secrets, renders
the complete cluster, validates pinned Kubernetes/CRD schemas, and rejects
unreviewed additions to a precise high-risk-policy baseline. Workload and
chart-selected images are pinned by digest. The Gateway API source is pinned by
commit; cert-manager, Traefik, and MetalLB use digest-pinned OCI charts; and
Longhorn's chart is built from an exact upstream Git commit. CI independently
fetches, checksums, renders, schema-validates, and policy-scans the immutable
chart output. Route, access-proxy, middleware, and NetworkPolicy ingress
boundaries are hashed for the same reason.
Flux itself is a bootstrap exception to self-management: the bootstrap script
checks the exact release-manifest SHA-256 and immediately replaces every
controller tag with its reviewed multi-architecture image digest.

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
  compute workloads;
- Jellyfin's host-network port 8096 remains reachable from the LAN because the
  same network namespace is required for DLNA; Jellyfin authentication is the
  final control on that direct path;
- Traefik's Kubernetes providers require cluster-wide Node and Secret reads,
  so a Traefik compromise has a larger disclosure radius than an ordinary app.

These are current operating assumptions, not pending migration steps. Revisit
them only if a third node or independent storage is intentionally introduced.
