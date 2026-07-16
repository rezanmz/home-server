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
is no third server/control-plane member planned, so a Beelink outage is an
accepted control-plane outage. Additional agents do not change that. Existing
pods on the Pi may continue temporarily, but the cluster cannot reconcile or
reschedule until the server returns.

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

Home Assistant is a security-placement exception to ordinary floating apps. It
is pinned to the Beelink and begins with no LAN egress so third-party integration
code cannot inherit the Pi node's access to trusted NFS exports. LAN devices are
opened individually by address, protocol, and port as integrations are approved.
It uses Home Assistant's built-in authentication because the upstream service
does not provide native OIDC; no custom auth component or generic Authentik
forward-auth layer is installed. `homeassistant.reza.network` is intentionally
internet-accessible through the TLS Gateway and colocated access proxy. Home
Assistant receives the original client address for login throttling and IP bans;
every administrator must use a unique password and enable TOTP MFA. The durable
owner marker keeps a new or unsafe replacement PVC fail-closed before onboarding.

Audiobookshelf is pinned to the Beelink as a security-placement constraint. Its
public route uses Audiobookshelf's native OIDC implementation with an Authentik
provider, including the official mobile client's PKCE callback. Keeping this
Internet-facing workload off the Pi prevents it from inheriting the Pi pod
CIDR's deliberate trust on private routes for masqueraded WireGuard clients. A
post-start bootstrap keeps the pod out of Service endpoints until the local
recovery root, OIDC settings, and initial libraries exist, preventing a public
visitor from claiming an empty instance. Dedicated audiobook and podcast NFS
paths are writable so uploads, subscriptions, and downloaded episodes persist;
the shared Calibre ebook library is mounted separately and read-only.

## Storage

Two storage mechanisms serve different data classes:

- Longhorn stores small databases, configuration, and application state. Its
  default StorageClass uses two replicas, `Retain`, and
  `WaitForFirstConsumer`.
- Static NFS volumes exported by the Pi store media, downloads, audiobooks, books, shared
  Syncthing data, and read-only access to the former persistent-data tree.

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
recovery set, not an off-site backup.

Longhorn uses the dedicated private
`rezanmz-home-server-longhorn-backups` Backblaze B2 bucket as its default
S3-compatible BackupTarget. The credential is stored only in the SOPS-encrypted
`longhorn-system/longhorn-backblaze-b2` Secret. Backblaze provides default
SSE-B2 encryption at rest; transport uses the regional HTTPS endpoint.

The `b2-nightly` recurring job applies to Longhorn's `default` job group and
runs at 06:17 UTC with one backup at a time, 14 retained recovery points, and a
full backup after every seven completed incremental backups. Volumes that are
detached at that time may be attached temporarily so they are not silently
skipped. These block-level backups are crash-consistent, not coordinated
application-consistent backups across PostgreSQL, Redis, Elasticsearch, or
multi-PVC applications. Native database exports remain a worthwhile additional
recovery layer.

The Longhorn HelmRelease configures the default BackupTarget and detached-volume
setting through Longhorn's supported `defaultBackupStore` and `defaultSettings`
values. This leaves the singleton resources under `longhorn-manager` ownership
instead of creating a server-side-apply conflict with Flux. The dedicated
`flux-system/longhorn-backups` Kustomization owns the encrypted credential and
recurring job with pruning enabled. The separate `longhorn-ready` gate waits for
the existing HelmRelease without changing its root Flux ownership or creating
an uninstall race during rollout.

The same HelmRelease pins storage scheduling off for cordoned Kubernetes nodes
and keeps concurrent automatic engine upgrades at zero. These settings prevent
new replicas from landing during maintenance and prevent Longhorn from trying
to treat the current identical-commit EngineImage reference difference as a
real version upgrade.

Backblaze Object Lock and bucket lifecycle expiry remain disabled because
Longhorn owns logical backup retention. B2's `Keep all versions` behavior can
retain hidden historical object versions after Longhorn deletes a logical
backup. Periodic full backups may also replace already-present block objects and
create billable hidden versions, so bucket size and hidden-version growth
require operational monitoring. Indefinite physical version retention is
accepted initially because Longhorn prohibits a backupstore lifecycle rule; it
is not a bounded 14-copy guarantee.

The Longhorn BackupTarget does not include the Pi's NFS exports. Media remains
an explicitly reconstructible data class, while the active Syncthing tree at
`/home/reza/persistent/syncthing/data` has a separate file-level Restic backup.
The hardened `network-services/syncthing-backup` CronJob mounts that NFS PVC
read-only plus only `config.xml` from Syncthing's config PVC. It writes a
client-side encrypted repository to the dedicated private
`rezanmz-home-server-syncthing-backups` B2 bucket. It has no Kubernetes API
token, no inbound network access, and egress only to cluster DNS and public
HTTPS. The bucket is independent of both Longhorn's backupstore and the old
Duplicati repository so their lifecycle rules, credentials, object formats,
and deletion blast radii cannot interfere.

The CronJob backs up the complete Syncthing data root. Every current and future
folder is therefore included by default, along with currently unclassified
root-level data. A Git-reviewed stable-folder-ID list provides explicit
per-folder opt-outs. The preflight reads only folder IDs and paths from the live
Syncthing config, requires every configured folder to remain below `/data`,
rejects path overlap and symlinks, and resolves excluded IDs to their current
paths. A durable root canary prevents an empty or wrong NFS export from being
accepted. Restic keeps 14 daily,
8 weekly, 12 monthly, and 3 yearly snapshots. Weekly pruning is followed by a
structural repository check, and the job cycles through deterministic
encrypted-data subsets each month. A quarterly isolated restore remains the
stronger end-to-end proof. These are live-file backups rather than atomic
filesystem snapshots, so a partial scan is a failed job and is retried.

New snapshots initially receive only a candidate tag. Restic can save an
incomplete snapshot before returning its partial-backup exit code, so only an
exit-zero snapshot is promoted to the trusted recovery tag. Restore and trusted
retention ignore unpromoted candidates; a separate keep-last-three policy bounds
failed candidates without ever pruning from the failure path. The repository's
immutable ID is also pinned after one-time initialization, so backups fail if
the bucket, prefix, password, or repository identity differs.

A separate `syncthing-backup-freshness` CronJob runs on the Beelink after the
daily backup window. It mounts no Syncthing data or configuration, reads only
the B2 credential, and fails when the newest exact trusted snapshot is older
than 36 hours. A failed Job emits a Kubernetes Warning event for the existing
event-alert pipeline, covering the case where the data-reading CronJob never
started or stopped producing recovery points.

The Restic bucket uses SSE-B2 in addition to Restic's client-side encryption and
has Object Lock disabled so repository maintenance can hide obsolete packs. It
currently keeps all hidden object versions. Those versions are object-level
forensic history, not an atomic or tested point-in-time rollback of the Restic
repository, and their unbounded storage growth must be monitored. The Restic
password and bucket-scoped S3 key are stored in the SOPS-encrypted
`network-services/syncthing-backup-credentials` Secret. Losing the Restic
password makes the repository unrecoverable. The rollout key is restricted to
the dedicated bucket but has broader capabilities than Restic normally needs;
rotating it to the `syncthing/` prefix and name-only list/read/write operations
is a worthwhile defense-in-depth follow-up after the exact reduced key passes
init, prune, check, and restore tests. Object Lock would require a separately
designed maintenance and retention model.

Duplicati's active workload, route, Services, and live Secret are retired.
Its historical native-B2 repository, AES passphrase dependency, SOPS settings
key, retained config PVC, and local repository tree remain recovery artifacts.
Restic must never share that bucket: the old root-scoped Duplicati job treats
foreign repository objects as unsupported.

## Application boundaries

Applications are separated into four operational namespaces:

- `apps` for identity, personal, home-automation, and general web applications;
- `media` for Jellyfin, books, download automation, and VPN-isolated egress;
- `network-services` for Pi-hole, WireGuard, Samba, Syncthing, and backups;
- `monitoring` for Prometheus, Alertmanager, Grafana, Headlamp, and Kubernetes
  event export.

Namespace default-deny policies and workload-specific rules permit only the
required ingress and egress. Administrative routes use LAN/WireGuard allow
lists. SOPS/age-encrypted Secret manifests are safe to store in the public
repository; the private age identity remains root-only outside Git.

Authentik's native OIDC providers and applications are also desired state. One
shared ConfigMap mounts a separate, independently reconciled blueprint document
for each relying application, while one aggregate SOPS Secret supplies the
provider-side client secrets to the worker. Each key is referenced explicitly in
the worker's shared OIDC environment list so adding a client rolls the pod and a
missing key fails visibly. Adding an OIDC client therefore changes those shared
resources and the relying application only; it does not add a per-service
Authentik manifest or Deployment patch.

The metrics path is deliberately separate from the event-notification path.
Prometheus scrapes K3s, kube-state-metrics, both node exporters, Longhorn,
Traefik, cert-manager, Flux, Headlamp, and the event exporter. Alertmanager
groups and inhibits Prometheus alerts before sending warning and critical
notifications to the existing Telegram destination. The event exporter still
sends noteworthy Kubernetes events directly, so a failed Prometheus scrape is
not the only signal available during an incident.

Only Grafana has a Gateway API route. The route and an in-pod access proxy both
enforce the LAN/WireGuard boundary, and Grafana performs native Authentik OIDC
with `home-admins` mapped to Grafana administrators. Prometheus and Alertmanager
remain ClusterIP-only and require a deliberate `kubectl port-forward` for direct
access to their diagnostic UIs. Alert GeneratorURLs use Grafana's authenticated
Prometheus datasource proxy. This lets Telegram recipients investigate the exact
query without creating another external service. Prometheus retains at most 14 days
or 20 GB in a 30 GiB PVC;
Grafana and Alertmanager use smaller persistent volumes. These three volumes
use `longhorn-observability`, whose non-default recurring-job selector keeps
reproducible metrics data out of the nightly Backblaze backup set.

The protected `main` branch requires a GitHub-hosted validation job. It checks
helper syntax and tests, rejects plaintext or malformed SOPS Secrets, renders
the complete cluster, validates pinned Kubernetes/CRD schemas, and rejects
unreviewed additions to a precise high-risk-policy baseline. Git-defined
workload and chart-selected images are pinned by digest. The Gateway API source
is pinned by commit; cert-manager, Traefik, and MetalLB use digest-pinned OCI
charts; and Longhorn's chart is built from an exact upstream Git commit. CI
independently fetches, checksums, renders, schema-validates, and policy-scans
the immutable chart output. Route, access-proxy, middleware, and NetworkPolicy
ingress boundaries are hashed for the same reason.

Two live-state exceptions remain recorded in the cluster operations manual:
existing Longhorn Volume CRs still reference the tag-only form of the otherwise
matching reviewed engine image, and CoreDNS has an undocumented live-only
Beelink selector. The same-version Longhorn reference is intentionally left
alone until a future supported engine upgrade because Longhorn warns against
upgrading between identical commits; CoreDNS still needs a declarative
placement decision. Neither exception is represented as intended Git state.
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
- The Prometheus Operator's upstream chart grants cluster-wide reconciliation
  over monitoring CRs plus StatefulSets, ConfigMaps, and Secrets. Its watch loop
  is scoped to the `monitoring` release namespace, but compromise of its service
  account remains a high-impact cluster event.

These are current operating assumptions, not pending migration steps. Revisit
them only if a third node or independent storage is intentionally introduced.
