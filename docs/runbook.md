# Home cluster runbook

Commands in this runbook describe the supported procedure after authorization;
they are not standing permission. Repository edits, commits, pushes, pull
requests, merges, remote workflows or publication, live cluster or host work,
application state, external providers, credentials, and destructive actions
remain separate authorization planes.

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

Normal Flux polling is the default. The following annotations mutate live Flux
objects; use them only with explicit live-mutation authorization for the exact
GitRepository and Kustomization after the intended revision reaches protected
`main`:

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
- Kea DHCP range: `192.168.1.10-192.168.1.239`

Blocky's split-horizon mappings point HTTP hostnames at the Traefik VIP (`.240`),
not at an application node. Kubernetes Services then follow pods as they move
between nodes. DNS, SMB, NFS, and the WireGuard UDP endpoint use the Pi address
(`.2`). Kea answers DHCP from the Beelink (`.3`) and advertises `.2` as DNS.

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

The TP-Link integration reaches Kasa/Tapo devices on the Archer BE700 IoT SSID
through protocol-scoped LAN egress: UDP 9999/20002 for targeted discovery and
TCP 80/9999 for local control. The IoT SSID shares `192.168.1.0/24`; it is not a
security VLAN. Do not broaden this rule to unrestricted LAN egress or add
`hostNetwork` merely to make discovery automatic. Home Assistant sees only its
`10.42.0.0/24` pod broadcast domain, so add a new TP-Link device by its address
in **Settings > Devices & services > Add integration > TP-Link Smart Home**.

Home Assistant also includes the C.A.F.E. visual automation editor. Open
**C.A.F.E.** in the Home Assistant sidebar to import an existing native
automation into a node-and-wire flowchart, inspect its branches, or create a
new automation by dragging trigger, condition, delay, and action nodes onto the
canvas. C.A.F.E. is an editor only: saved logic remains a native Home Assistant
automation, continues to execute without C.A.F.E., and remains visible under
**Settings > Automations & scenes**.

C.A.F.E. is beta software with write access to automations. Its reviewed release
is checksum-pinned in `apps/home-assistant/deployment.yaml`; do not update it
through HACS independently of the manifest. Release 0.6.0 also receives a
checksum-verified compatibility patch during installation so automations with
descriptive string IDs can be loaded through Home Assistant's REST config
endpoint and `max`/`max_exceeded` settings survive C.A.F.E. save requests. The
init container fails closed if the reviewed release bytes or patched bundle
differ. Before saving changes to an important automation, duplicate it, keep
the copy disabled, and verify an import/save/reload round trip on that copy.
Home Assistant's native trace view remains the authoritative execution record.
A one-time VolumeSnapshot named
`home-assistant-pre-cafe-20260719` protects the pre-install PVC state; ordinary
ongoing protection still comes from the configured Longhorn B2 backups.

Stable addresses live in the single
`apps/kea/iot-reservations.json` inventory. To add a device, first provision it
on the IoT SSID, find its current address and MAC in Stork or
`/var/lib/kea/kea-leases4.csv`, add one unique reservation in ascending address
order, and validate before merging. A new TP-Link device does not require a
Home Assistant NetworkPolicy change. A non-TP-Link integration still requires
review of its exact destinations and ports.

Verify the reservation and the path without exposing credentials:

```bash
ssh beelink 'sudo k3s kubectl -n network-services exec deploy/kea-dhcp4 -c kea-dhcp4 -- cat /var/lib/kea/kea-leases4.csv'
ssh beelink 'sudo k3s kubectl -n apps get networkpolicy home-assistant -o yaml'
```

#### House modes

`input_select.house_mode` is the authoritative, long-lived occupancy intent for
Home Assistant. Change it from the **Modes** dashboard view, the selector on
**Overview**, or `script.set_house_mode`. The selector is a native editable
helper and restores its last state after a restart. Its four options deliberately
exclude temporary activity and lighting contexts:

| Mode | Behavior |
| --- | --- |
| `Home` | Normal presence, sunset, Jellyfin, and morning routines. Selecting it restores the time-appropriate lighting profile. |
| `Sleep` | Gradually shuts down all managed bulbs, both bedside plugs, the Living Room floor-lamp plug, and the espresso machine. It also discards any Jellyfin lighting snapshot so pausing playback cannot turn lights back on. |
| `Away` | Uses the same safe shutdown with a shorter fade, sets the legacy away flag, and blocks the scheduled espresso routine. Both tracked people being away for two minutes selects it automatically. The first arrival selects `Home`. |
| `Guest` | Keeps common-room routines active and suppresses automatic `Away` selection when both household phones leave. It remains active until explicitly changed. |

`Sleep` is intentionally manual. Phone presence and clock time do not prove
that everybody is asleep; add a reliable bedroom/bed-presence signal before
automating that transition. Lighting phase and Jellyfin playback remain
separate contexts that are allowed to operate only in compatible modes.

`script.apply_house_mode` owns mode side effects and can reapply the current
mode. `script.house_shutdown` owns the shared Sleep/Away shutdown sequence.
The `House mode - apply transitions` automation calls the former when the
selector changes. `House mode - legacy state synchronization` derives
`input_boolean.household_away` from the selector for older logic; do not treat
that boolean as a second source of truth.

Edit the helper under **Settings > Devices & services > Helpers**, scripts under
**Settings > Automations & scenes > Scripts**, and the two mode automations in
the native editor or C.A.F.E. Home Assistant stores these editable objects and
the dashboard on `home-assistant-config`, so Longhorn/B2—not a duplicate
repository copy—is their durable source of recovery. The ready VolumeSnapshot
`home-assistant-pre-house-modes-20260719` captures the immediately preceding
state.

### Audiobookshelf recovery and OIDC bootstrap

Audiobookshelf is internet-accessible at `audiobooks.reza.network` and uses its
native Authentik OIDC flow for browsers and the official mobile app. Its local
root account is a recovery path stored in Audiobookshelf's backed-up application
state; preserve its credential in the operator's protected recovery system.
Authentik's provider copy of the OIDC secret is SOPS-managed, while the
relying-party copy is application-managed as declared by the catalog. Do not
invent a workload Secret or disable local auth without replacing and testing
that recovery path.

The local root, OIDC relying-party settings, and libraries are application-owned
state. The Deployment intentionally has no Git-managed post-start reconciler,
bootstrap password, or durable marker; the ownership validator rejects those
patterns. Its `/healthcheck` readiness probe also does not prove onboarding.
When restoring to an empty replacement PVC, first remove or withhold the public
route through reviewed desired state, configure and verify the recovery root,
OIDC, and initial libraries through a separately authorized private path, then
restore public exposure in a second reviewed change. Never expose an empty
first-owner page or add an init hook that overwrites restored settings.

Longhorn and its B2 target protect `/config` and `/metadata`. The writable
`audiobooks` and `podcasts` directories and read-only `books` directory are
category mounts from the shared JuiceFS media filesystem. Their encrypted
payloads are authoritative in the dedicated media B2 bucket; PostgreSQL
metadata recovery is required to interpret those chunks. They are not included
in the Audiobookshelf PVC backup and B2 is not an independent second copy.

### Jellyfin and Seerr public exposure

Jellyfin (`jellyfin.reza.network`) and Seerr (`seerr.reza.network`) are
internet-accessible with their native application authentication. Both are
pinned to the Beelink so an exposed pod cannot inherit the Pi pod CIDR's
deliberate trust on private routes. Jellyfin has no supported OIDC path for
official mobile clients, so its accounts are the boundary; the same accounts
sign in to Seerr. Before or immediately after any public exposure change,
verify the application-side controls, which are application-owned state:

- the shared Jellyfin account is non-administrator, library-scoped, and has
  content downloads disabled; administrator accounts use unique strong
  passwords;
- the reverse proxy is listed under Jellyfin's `Known Proxies` so remote-access
  rules and login throttling see real client addresses;
- DLNA and LAN discovery are disabled on Jellyfin while the route is public
  (the host-network 8096 listener is otherwise a direct LAN surface);
- Seerr open signups are disabled and shared users hold only the requester
  role.

Jellyfin's raw port 8096 remains reachable from the LAN through its
host-network listener; that accepted deviation is unchanged and still relies on
Jellyfin authentication as the final control. After an exposed service's
Longhorn configuration is restored to an empty replacement PVC, withhold the
public route first, rebuild and verify the accounts and integrations through a
separately authorized private path, then restore exposure in a second reviewed
change.

### Omnifin retirement

Omnifin is retired. Its `omnifin-data` PVC (SQLite: connector credentials, OIDC
configuration, sessions, and audit records) and the `omnifin-secrets`
encryption/recovery Secret remain reconciled as recovery artifacts; the
application-native backups under `/data/backups` are retained inside the PVC.
The Authentik OIDC provider, application, and provider-side client secret
(`AUTHENTIK_OIDC_OMNIFIN_CLIENT_SECRET`) are retained because no tested
Authentik cleanup lifecycle exists. Take a verified final export of the PVC
before any destructive cleanup.

## DNS and DHCP

Blocky is a host-network DaemonSet and provides DNS and filtering from both the
Pi (`192.168.1.2`) and Beelink (`192.168.1.3`) on TCP/UDP 53. Kea provides
DHCPv4 from the Beelink on UDP 67. Kea serves `192.168.1.10-192.168.1.239`,
advertises router `192.168.1.1` and both DNS addresses, and issues one-hour
leases. There is no DHCPv6 server. A single node failure therefore does not
remove LAN DNS, although a Beelink failure still removes DHCP and the control
plane.

Desired configuration lives in `apps/blocky/config.yml` and
`apps/kea/kea-dhcp4.conf`. Blocky's split-horizon mappings must be changed in
Git whenever an internal application hostname is added or removed. Kea client
reservations, if introduced, also belong in Git, but do not commit a device MAC
address without deciding that public-repository disclosure is acceptable. A
Kea reservation does not automatically create a Blocky DNS record; add the
corresponding Blocky mapping if the client hostname must resolve.

The default filtering policy is HaGeZi Multi PRO in Blocky's wildcard format.
It is the balanced, stronger household tier: arbitrary subdomains are covered
without combining several overlapping aggregate lists. Change only the source
under `blocking.denylists.ads` when deliberately changing policy:

- HaGeZi Normal is the more conservative choice.
- HaGeZi Pro is the default balanced choice.
- HaGeZi Pro++ is more aggressive and is more likely to need local exceptions.
- OISD Big prioritizes avoiding false positives and preserving referral and
  shopping links, so it can feel less strict despite its larger list.

Do not stack these all-in-one lists by default. Overlap consumes memory and
makes it unclear which source caused a false positive. If a legitimate domain
is blocked, add the smallest exact entry to an `ads` allowlist in
`apps/blocky/config.yml` rather than weakening the policy for every client.
Blocky automatically refreshes the source every four hours and keeps an
independent pod-local copy on each node. This is reproducible cache data, not
Longhorn or backup data. Losing one pod does not remove the other pod's cache.

The previous dnsmasq lease-name integration is intentionally absent: ordinary
dynamic DHCP client hostnames are not synthesized into local DNS. Application
hostnames under `reza.network` remain explicit and deterministic. Pi-hole's NTP
listener is also retired; DHCP never advertised it, and the nodes and clients
use their own configured time sources. Do not restore UDP 123 merely to match
the old listener inventory.

There is no Blocky administration route or LAN-facing HTTP API. Its management
and metrics endpoints bind only to the node CNI gateways at
`10.42.0.1:4000` and `10.42.1.1:4000`.
Kea exposes a Unix control socket shared only with the exporter, whose metrics
bind to the Beelink CNI gateway at `10.42.0.1:9547`. The `DNS and DHCP` Grafana
dashboard shows availability, query results, denylist state, DHCP traffic, and
pool usage. Warning and critical alerts are `BlockyUnavailable`,
`BlockyQueryErrors`, `BlockyDenylistStale`, `KeaDHCPUnavailable`,
`KeaDHCPPoolNearlyFull`, and `KeaDHCPAllocationFailures`.

Check workload state and storage from the Beelink:

```bash
ssh beelink 'sudo k3s kubectl -n network-services get daemonsets,deployments,pods,pvc -o wide'
ssh beelink 'sudo k3s kubectl -n network-services logs daemonset/blocky --all-pods --tail=100'
ssh beelink 'sudo k3s kubectl -n network-services logs deployment/kea-dhcp4 -c kea-dhcp4 --tail=100'
ssh beelink 'sudo k3s kubectl -n network-services logs deployment/kea-dhcp4 -c kea-exporter --tail=100'
ssh beelink 'sudo k3s kubectl -n network-services get endpoints,endpointslice | grep -E "blocky|kea"'
ssh beelink 'sudo k3s kubectl -n monitoring get servicemonitor,prometheusrule | grep -E "blocky|kea"'
```

From a LAN machine, prove all three DNS paths: ordinary upstream resolution,
split-horizon routing, and blocking. A blocked name should return a zero address
and the application hostname should return the MetalLB VIP.

```bash
dig +short @192.168.1.2 github.com A
dig +short @192.168.1.3 github.com A
dig +short @192.168.1.2 homepage.reza.network A
dig +short @192.168.1.3 homepage.reza.network A
dig +short @192.168.1.2 securepubads.g.doubleclick.net A
dig +short @192.168.1.3 securepubads.g.doubleclick.net A
```

Check host listeners independently; DNS must be on both nodes and DHCP only on
the Beelink. Blocky's control ports and the exporter must bind only to their
CNI gateway addresses, not `0.0.0.0` or the LAN address.

```bash
ssh pi 'sudo ss -lntup | grep -E "(:53|:4000)\\b"'
ssh beelink 'sudo ss -lntup | grep -E "(:53|:4000|:67|:9547)\\b"'
ssh beelink 'curl -fsS http://10.42.0.1:9547/metrics | grep -E "^kea_dhcp4_addresses_(assigned|total)"'
ssh pi 'curl -fsS http://10.42.1.1:4000/metrics | grep -E "^blocky_(build_info|query_total|denylist_cache_entries)"'
ssh beelink 'curl -fsS http://10.42.0.1:4000/metrics | grep -E "^blocky_(build_info|query_total|denylist_cache_entries)"'
```

The durable Kea lease database is `/var/lib/kea/kea-leases4.csv` inside the
`kea-dhcp4` container and is backed by `network-services/kea-leases`. It is in
the default Longhorn recurring-job group and must have a recent B2 backup.
Blocky's list caches are independent bounded `emptyDir` volumes. They are
reproducible and deliberately excluded from Longhorn and B2.

If DNS fails, check both nodes, both Blocky pods, TCP/UDP 53 listeners,
upstream reachability to `8.8.8.8` and `8.8.4.4`, pod-local list caches, and
Blocky logs. If both Blocky instances fail, new DNS lookups are affected
immediately. If DHCP fails, existing
clients normally keep their current address until renewal, while new clients
may fail immediately; check the Beelink, UDP 67, `enp1s0`, the lease PVC,
control socket, and Kea logs. The ping-check hook can decline an address that is
already answering on the LAN; that is collision protection, not necessarily a
pool defect.

Never start the retired Pi-hole Deployment alongside Blocky or Kea: its
host-network TCP/UDP 53 and UDP 67 listeners conflict with the replacements.
For migration rollback, suspend Flux, stop both replacement Deployments,
restore the last Pi-hole manifests, reuse the retained config PVC while it
exists (or restore it from the final Longhorn backup), verify Pi-hole owns both
ports, then resume Flux only after the rollback revision is merged. Do not run
both DHCP servers during rollback.

The retained migration recovery points are Longhorn Snapshot
`pihole-pre-blocky-20260716t211514z` and completed B2 Backup
`pihole-pre-blocky-backup-20260716t211514z` for volume
`pvc-5ccd4ed4-e195-4c47-a408-ecc1d5091122`. Keep them until the DNS/DHCP
migration recovery window is deliberately closed; the Backup is the independent
off-node copy, while the Snapshot alone is not.

The detached `network-services/pihole-config` PVC is retained only for the
initial rollback window. It is labeled
`home-server.reza.network/retention=pihole-migration-rollback` and annotated
with that B2 backup plus `home-server.reza.network/review-after=2026-07-23`.
No pod may mount it while Blocky or Kea is active. On or after the review date,
either record a new retention decision or remove the PVC/PV/Longhorn volume
through the identity-checked storage procedure; do not let an unlabeled orphan
persist. Deleting the local volume must not delete the retained B2 Backup.

The 2026-07-26 review retained the frozen local copy for another manual
rollback option but removed it from the default recurring-job group. The PVC
has `recurring-job.longhorn.io/source=enabled` and
`recurring-job-group.longhorn.io/default=disabled`; its named final B2 backup
remains the off-node recovery point. Re-enable recurring backups only if the
Pi-hole archive is intentionally brought back into writable service.

### ISC Stork

Stork is available at `https://stork.reza.network/` only from the LAN or
WireGuard. Login uses the native Authentik OIDC provider. Group mapping must
remain disabled: that is what assigns every OIDC account Stork's built-in
`read-only` role. Do not assign `admin` or `super-admin` to an OIDC account and
do not restore the built-in local administrator.

Stork 2.5 normally withholds its lease-list GET endpoint from the `read-only`
role even though the general authorization middleware permits other GET
endpoints. The pinned home-server server image carries the narrow
`scripts/stork-read-only-lease-list.patch`: it permits that one read operation
and does not grant any create, update, or delete permission. Do not replace the
patch by promoting an OIDC user to `admin`.

The Kea pod has three containers: Kea, the existing Prometheus exporter, and
the Stork agent. The agent binds only to the Beelink CNI gateway at
`10.42.0.1:8080`; it is not a LAN or Gateway listener. Stork's PostgreSQL
database and agent certificates are on `stork-postgresql` and
`stork-agent-data` Longhorn PVCs, both covered by nightly B2 backups. DHCP does
not depend on the Stork server, UI, or database and continues if they fail.
The agent mounts the Kea lease PVC at `/var/lib/kea` read-only and tracks its
memfile for the lease-list page. Failure to read that file makes the agent
unready but never grants it write access to the DHCP lease database.

Check the complete path with:

```bash
ssh beelink 'sudo k3s kubectl -n network-services get deploy/stork-server statefulset/stork-postgresql job/stork-lockdown-v1'
ssh beelink 'sudo k3s kubectl -n network-services get pods,pvc -l app.kubernetes.io/name=stork'
ssh beelink 'sudo k3s kubectl -n network-services logs deploy/kea-dhcp4 -c stork-agent --tail=100'
ssh beelink 'sudo k3s kubectl -n network-services logs deploy/stork-server -c server --tail=100'
ssh beelink 'sudo k3s kubectl -n network-services logs job/stork-lockdown-v1'
ssh beelink 'sudo ss -lntp | grep "10.42.0.1:8080"'
```

`stork-lockdown-v1` must finish exactly once. It replaces Stork's generated
registration token with the encrypted bootstrap token, waits for the Kea agent
to register, then replaces that token with an unknown random value, randomizes
the default `admin/admin` login and password, and stores
`enable_machine_registration=false`. Restart `stork-server` after a clean
bootstrap so the in-memory endpoint control reloads that final setting:

```bash
ssh beelink 'sudo k3s kubectl -n network-services rollout restart deployment/stork-server && sudo k3s kubectl -n network-services rollout status deployment/stork-server --timeout=180s'
```

If both Stork PVCs are restored together, the existing mTLS identity should
continue to work. If only `stork-agent-data` is lost, do not re-enable
registration casually: verify the old machine record, rotate the SOPS bootstrap
token, create a versioned replacement lockdown Job, and review the exact agent
address before reconciling. A read-only UI does not make a forged monitoring
agent trustworthy.

## Other Pi network services

Samba, Syncthing, and wg-easy are Kubernetes workloads in the
`network-services` namespace. They are pinned to the Pi when they require its
address or data.

```bash
ssh beelink 'sudo k3s kubectl -n network-services logs deployment/wg-easy --tail=100'
```

The legacy `network-watchdog.timer` must remain disabled and inactive. It used
a public TCP/53 probe to decide whether to restart NetworkManager and reload a
Wi-Fi driver, which can disconnect the Ethernet K3s/NFS/DNS node during an
unrelated upstream failure. Its files are retained for forensics only:

```bash
systemctl is-enabled network-watchdog.timer  # expected: disabled
systemctl is-active network-watchdog.timer   # expected: inactive
```

The cluster nodes themselves use three independent public upstream resolvers
(`1.1.1.1`, `8.8.8.8`, `9.9.9.9`) from three distinct operators, tracked in
`infrastructure/hosts/beelink/netplan.yaml`. Exactly three: kubelet caps the
nameserver list it copies into `dnsPolicy=Default` pods at three and emits
`DNSConfigForming` warnings about any excess. K3s explicitly passes that
resolver file (`/run/systemd/resolve/resolv.conf`) to kubelet, so CoreDNS
cannot retain an old Blocky address in a long-lived pod sandbox. The nodes
must not use Blocky: after an eviction or reboot, a node may need DNS to pull
the Blocky or Longhorn image required to restore DNS. Kea advertises both
Blocky addresses to LAN clients. CoreDNS forwards external names to that same
upstream list, so it survives a single operator's blip but still fails if the
node's whole UDP/53 WAN path is lost. CoreDNS reads the resolver list once at
pod startup: after changing netplan nameservers, restart the CoreDNS pod to
adopt them. Verify every path:

```bash
ssh pi 'cat /etc/resolv.conf; getent ahostsv4 ghcr.io'
ssh beelink 'resolvectl status enp1s0; getent ahostsv4 ghcr.io'
dig +short @192.168.1.2 github.com A
dig +short @192.168.1.3 github.com A
```


### Cluster DNS failures (GitOperationFailed, "server misbehaving")

External-name resolution for every workload follows one path: pod → CoreDNS
(`10.43.0.10`) → forward plugin → the node's public upstream list (above).
Cluster-internal names never leave CoreDNS's `kubernetes` plugin and are not
affected by upstream loss. A transient WAN or UDP/53 failure on the node
therefore appears as short bursts of
`GitOperationFailed ... dial tcp: lookup github.com ... server misbehaving`
from Flux while internal DNS keeps working. Flux retries and recovers on the
next sync interval; treat repeated windows as a node WAN-path problem, not a
Flux or GitHub problem.

Probes (read-only):

```bash
ssh beelink 'sudo k3s kubectl run dns-probe --rm -i --restart=Never --image=busybox:1.36 -- sh -c "for i in 1 2 3 4 5; do nslookup github.com 10.43.0.10 | tail -2; done"'
ssh beelink 'resolvectl status enp1s0; resolvectl query github.com'
ssh beelink 'sudo k3s kubectl -n flux-system get gitrepository flux-system -o jsonpath="{range .status.conditions[*]}{.type}={.status} {.lastTransitionTime}{\" \"}{end}"'
```

Alerts `CoreDNSForwardUpstreamBroken` (forward plugin marked every upstream
unhealthy) and `CoreDNSServfailRateHigh` (>5% SERVFAIL sustained for 10
minutes) distinguish a total upstream loss from a partial degradation; their
rules live in `infrastructure/coredns/metrics.yaml`. Transient windows shorter
than the alert windows are tolerated by design.

If the Pi reports `DiskPressure=True`, the downloads storage guard should
already have stopped every torrent at 200 GiB or 20% free. Confirm the guard
log, keep torrents stopped, and recover verified completed payloads before
restarting anything. Do not delete organized media or Longhorn replicas merely
to make disk space. Blocky is a critical DaemonSet with explicit
ephemeral-storage requests, but the guard is the primary protection against
kubelet eviction.

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

Keep `127.0.1.1 raspberrypi` in the Pi's `/etc/hosts`. Administrative commands
must be able to resolve the local hostname while Blocky is stopped or being
replaced; relying on the DNS workload for `sudo` can otherwise break recovery.

Expected Pi-facing services include DNS on TCP/UDP 53, SMB on TCP 139/445,
Syncthing on TCP/UDP 22000 and UDP 21027, and WireGuard on UDP 1234. DHCP on UDP
67 is expected on the Beelink. UDP 123 and the former Pi-hole web/backend-mTLS
ports are not expected.

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
declares those settings directly and holds only `NET_ADMIN` plus `NET_RAW`; it
must never regain a privileged init container or `SYS_MODULE`. A
`SysctlForbidden` pod status means the deployed Pi K3s config no longer matches
`infrastructure/k3s/agent-pi-config.yaml`.

The wg-easy v15 database configuration includes an IPv6 address, so wg-quick
applies ip6tables-legacy NAT rules at interface bring-up. The container cannot
insert kernel modules, so the Pi host must preload `ip6_tables` and
`ip6table_nat` from `infrastructure/k3s/pi-modules-load.yaml` (installed as
`/etc/modules-load.d/wg-easy-ip6.conf`); the deployment's read-only
`/lib/modules` mount exists only so the container's modprobe resolves those
already-loaded modules. If a rescheduled pod starts with the modules unloaded,
wg-quick rolls back, deletes `wg0`, and the VPN goes dark while the pod still
passes its TCP web-UI probes. Check `sudo lsmod | grep ip6` on the Pi and
expect both modules listed.

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

Active downloads and Syncthing data remain on separate NFS exports from the Pi.
Check the server and exports directly when those consumers fail at once:

```bash
ssh pi 'systemctl is-active nfs-server && sudo exportfs -v'
sudo k3s kubectl get pv | grep nfs-media
```

The Pi is authoritative only for those NFS trees. A Pi outage interrupts active
downloads and Syncthing but does not remove the organized JuiceFS library stored
in B2. Do not treat Longhorn replicas as copies of NFS or JuiceFS payload data.

### Media storage inventory

The **Media Storage** Grafana dashboard separates three storage layers: the
10 TiB logical JuiceFS/B2 library (whose static Kubernetes binding metadata
remains 2 TiB), the Pi filesystem holding active downloads and K3s, and each
node's disposable JuiceFS cache. Category figures cover
`movies`, `tv`, `music`, `books`, `audiobooks`, and `podcasts`; downloads have
their own local metrics because imports are copies across filesystems and no
longer share hardlinks.

The `media/media-storage-exporter` reads the JuiceFS library and local-downloads
claims without write access and refreshes its bounded inventory every 15
minutes. It publishes only the 20 largest library files so that filenames do
not create unbounded Prometheus cardinality. The dashboard's scan-age and
scrape-health panels distinguish a stale inventory from actual storage growth.

Check the collector and current metrics from the Beelink:

```bash
sudo k3s kubectl -n media get deploy,pod,service media-storage-exporter
sudo k3s kubectl -n media logs deploy/media-storage-exporter --tail=50
sudo k3s kubectl -n monitoring get servicemonitor media-storage-exporter
sudo k3s kubectl -n monitoring exec statefulset/prometheus-observability-prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=home_server_media_exporter_scan_success'
```

Homepage deliberately shows separate minimal summaries for the cloud library
and local downloads. Use Grafana for category history, file counts, cache hit
ratio, B2 traffic, health, and the largest-file list.

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

The target must report `AVAILABLE=true`. `b2-nightly` runs at 06:17 Toronto
local time, retains 14 logical backups per volume, processes one volume at a
time, and requests a full backup after every seven completed incremental
backups. Longhorn generates a Kubernetes CronJob without `spec.timeZone`, so
Kubernetes interprets the schedule in the kube-controller-manager's local
timezone. Normal backup jobs skip unchanged data, so that full interval is
count-based rather than a strict weekly calendar. Longhorn may temporarily
attach an otherwise detached volume at backup time. A second Longhorn replica
or a local snapshot on either node is not an off-site backup.

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

The Longhorn target does not cover any `nfs-media` PersistentVolume or JuiceFS
payload chunks. Organized media is authoritative in its dedicated B2 bucket;
active Syncthing data is protected separately by Restic in the private
`rezanmz-home-server-syncthing-backups` bucket. Never mix media chunks, Restic
objects, Longhorn blocks, or historical Duplicati data between buckets.

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

### Backup observability

Grafana provisions the **Backup Health and Integrity** dashboard in the
**Home Server** folder. It combines Longhorn's backup metrics with
kube-state-metrics for the two Syncthing Restic CronJobs. The top row answers
the operational questions first: whether every eligible PVC is covered,
whether any backup is stale, and how old the oldest Longhorn, Restic, and
independent freshness-check successes are.

Only PVCs using the default `longhorn` StorageClass are eligible for nightly
B2 coverage. PVCs using `longhorn-observability` are intentionally excluded
because Prometheus and Alertmanager telemetry is reproducible and
backing Prometheus up with the same Prometheus-dependent alert path would give a
misleading coverage number. A new eligible PVC may be shown as missing until
the next 06:17 America/Toronto nightly Longhorn run. It alerts only if it
remains uncovered for 36 hours.

Dashboard and alert semantics are deliberately narrower than “the backup can
definitely restore every application”:

- `longhorn_backup_state == 3` means Longhorn reports the backup as Completed.
  It does not prove application consistency across one or more PVCs.
- The inherited Longhorn `fast-check` every seven days verifies local snapshot
  data, not the remote Backblaze repository or a restored workload.
- A successful Syncthing backup validates the pinned Restic repository ID,
  source canary, exact folder policy, and Restic result. Sunday also runs a
  structural repository check; the first day of each month reads a
  deterministic quarter of repository data.
- The dashboard records that a full Restic encrypted-data check and isolated
  restore proof passed on 2026-07-14. This is evidence, not a live metric.
  Repeat the full-data and restore procedures below at least quarterly and
  after material changes.
- Longhorn's logical and uploaded-data byte metrics are not Backblaze's billed
  bucket size. Hidden B2 object versions are also not visible in Prometheus.

Active backup alerts are routed through the normal Alertmanager Telegram path:

```bash
sudo k3s kubectl -n monitoring get prometheusrule home-server-backup-health
sudo k3s kubectl -n monitoring port-forward \
  service/observability-prometheus 9090:9090
```

Then open the LAN/WireGuard-only, Authentik-protected Grafana dashboard or
inspect the Prometheus **Alerts** page through Grafana's Prometheus datasource.
For a stale or missing Longhorn PVC, open the per-PVC table, confirm the PVC and
StorageClass, then inspect the `b2-nightly` recurring-job history and backup
target. For a Syncthing alert,
inspect the newest retained Jobs and logs using the commands in the previous
section. Do not clear a Restic lock or create a replacement repository merely
to make an alert green.

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

### Open WebUI application state and search

Open WebUI owns its profiles, prompts, models, automations, retrieval settings,
memories, and MCP connection in its persistent database. Do not repair these by
editing SQLite or adding a startup reconciler. Use the supported administrator
UI, then verify that the change survives an ordinary pod restart.

Check the application and supporting services:

```bash
sudo k3s kubectl -n apps get deploy,pod,svc \
  -l 'app.kubernetes.io/name in (open-webui,mcphub)'
sudo k3s kubectl -n apps logs deploy/open-webui -c open-webui --tail=150
sudo k3s kubectl -n apps logs deploy/mcphub -c mcphub --tail=150
```

Exercise the internal search path from Open WebUI without exposing SearXNG:

```bash
sudo k3s kubectl -n apps exec deploy/open-webui -c open-webui -- python -c \
  'import json,urllib.parse,urllib.request; q=urllib.parse.quote("Open WebUI search health"); d=json.load(urllib.request.urlopen(f"http://searxng:8080/search?q={q}&format=json",timeout=35)); print("results:",len(d.get("results",[])))'
```

Inspect the search-provider adapter and paid-fallback counters:

```bash
sudo k3s kubectl -n apps logs deploy/searxng -c search-provider-proxy --tail=150
```

The **AI Services** Grafana dashboard shows SearXNG failures, provider outcomes,
paid fallback attempts, pod availability, restarts, CPU, and memory. A failed
free provider is not an outage when a later provider succeeds.

After changing the embedding model, re-index files, knowledge collections, and
memory through Open WebUI before treating retrieval as healthy. Verify a known
fact from a disposable document and inspect the cited chunk. Never leave a
completed migration in the normal pod startup path.

If application state must be restored, restore the Longhorn volume from B2,
then verify OIDC login, profile model choices, the single MCPHub connection,
search, retrieval, memory, one STT/TTS round-trip (OpenRouter external
engines), the web-search confirmation gate, and interactive tool approvals.
Git recreates the workload but not these application-owned settings.

### MCPHub and official GPT Researcher

MCPHub is the only MCP registry. The official GPT Researcher server, Vikunja,
Obsidian filesystem access, Actual Budget, Google personal-service adapters,
both PDF-reading providers, and the isolated `mcp-v8` evaluator are configured
there.
Open WebUI connects to one curated MCPHub group rather than to each server.

Check MCPHub, its database, and the installed packages:

```bash
sudo k3s kubectl -n apps get deploy,pod,svc,pvc \
  -l app.kubernetes.io/name=mcphub
sudo k3s kubectl -n apps logs deploy/mcphub -c mcphub --tail=200
sudo k3s kubectl -n apps exec deploy/mcphub -c mcphub -- \
  sh -lc 'command -v mcp-server-filesystem && command -v vikunja-mcp && command -v gcloud-mcp && test -x /usr/local/bin/start-gcloud-mcp && test -f /opt/gptr-mcp/server.py && test -x /opt/actual-mcp/build/index.js'
sudo k3s kubectl -n apps get deploy,pod,svc -l app.kubernetes.io/name=llamacloud-mcp
sudo k3s kubectl -n apps get networkpolicy llamacloud-mcp
sudo k3s kubectl -n apps get deploy,pod,svc,networkpolicy \
  -l app.kubernetes.io/name=mcp-v8
sudo k3s kubectl -n apps logs deploy/mcp-v8 --tail=100
```

Open MCPHub from the LAN or WireGuard and use **Servers** for connection state,
**Groups** for the tool allow-list, and **Activity** for call history and errors.
Server environment values are intentionally stored in MCPHub's database. Edit
GPT Researcher models, retriever, breadth, depth, and limits there, then reload
only that server.

The official GPT Researcher server should expose `deep_research`,
`quick_search`, `write_report`, `get_research_sources`, and
`get_research_context`. A missing or different list indicates the wrong entry
command or an upstream package change. Do not replace it with a local MCP
implementation.

The `mcp-v8` server should expose only `run_js` in stateless mode. It is a
calculation and small-transformation tool, not a shell. Verify a harmless
expression such as `(17 * 23) + Math.sqrt(144)` returns `403`, then confirm
`fetch("https://example.com")`, file reads, external imports, and subprocesses
are rejected. In MCPHub, keep it out of the read-only group and include it only
in the action-capable and Hermes companion groups. The pod must have no
service-account mount or persistent volume, and its NetworkPolicy must retain
empty egress.

To upgrade the executor, review the upstream `r33drichards/mcp-js` release and
security notes, update both architecture-specific release checksums in
`images/mcp-v8/Dockerfile`, increment the image revision in
`scripts/build-mcp-v8-image.sh`, build the multi-architecture image, and replace
the manifest's tag and digest together. Re-run the arithmetic and blocked-host-
capability tests before merging. Do not switch to the archived Pyodide-based
`pydantic/mcp-run-python`; its maintainers explicitly retired it over sandbox
and memory-isolation failures.

For a smoke test, use a small, explicit research request from the Deep Research
profile. Confirm the response includes sources, then inspect the matching
MCPHub activity. Avoid repeated tests because the server can make several paid
model and search calls.

For PDF tools, confirm `llamaparse` exposes only `execute` and `search_docs`,
and `google-vision-ocr` exposes only `run_gcloud_command`. LlamaParse's source
path is `/app/node_modules/@llamaindex/vault/<vault-relative-path>`; Google uses
`/vault/<vault-relative-path>`. Use one unique object prefix per Google job:

```text
gcloud storage cp /vault/path/file.pdf gs://rezanmz-homelab-ocr-staging/input/<uuid>.pdf
gcloud ml vision detect-text-pdf gs://rezanmz-homelab-ocr-staging/input/<uuid>.pdf gs://rezanmz-homelab-ocr-staging/output/<uuid>/
gcloud storage cat gs://rezanmz-homelab-ocr-staging/output/<uuid>/output-1-to-<min(20,pages)>.json
gcloud storage rm gs://rezanmz-homelab-ocr-staging/input/<uuid>.pdf gs://rezanmz-homelab-ocr-staging/output/<uuid>/**
```

The OCR operation is asynchronous, so wait and retry only the output read; do
not resubmit the OCR command. The output prefix must end in `/`. Google writes
up to 20 pages into each deterministic `output-N-to-M.json` shard by default;
use the page count reported by the guarded upload to determine the shard names.
Delete the exact input and the output-prefix wildcard without `--recursive`.
Do not broaden the gcloud allowlist, service-account roles, bucket, or source path.
The persistent counter is `/app/data/google-vision/quota.sqlite3`; back up the
MCPHub volume before any manual repair and never decrement a current-month
reservation merely because a request failed. Verify the native project quotas
with `gcloud beta quotas preferences describe` for
`vision-default-rpm-5`, `vision-document-rpm-5`, and
`vision-async-pages-100`. Google has no native monthly Vision quota, so these
rate limits do not replace the local 1,000-page gate.

MCPHub must have a persistent JWT secret. A startup warning that it generated a
temporary JWT secret means existing dashboard sessions will break after a
restart and the deployment secret wiring must be repaired.

### Personal assistant MCP

Vikunja is the task system of record. Verify its application and native OIDC
before testing the MCP adapter:

```bash
sudo k3s kubectl -n apps get deploy,pod,svc,pvc -l app.kubernetes.io/name=vikunja
sudo k3s kubectl -n apps logs deploy/vikunja --tail=150
sudo k3s kubectl -n apps exec deploy/mcphub -c mcphub -- \
  sh -lc 'test -r /vault && test -w /vault/Inbox && test -w /vault/Daily'
```

In MCPHub, confirm the Vikunja server uses the published package, points at the
cluster-internal Vikunja API, and has write and delete tiers disabled unless a
reviewed workflow needs them. Test a read first. Use a disposable task for an
additive test.

The filesystem server should receive the vault root as its only allowed path.
The root is mounted read-only, while Inbox and Daily are writable submounts.
Confirm a read of an ordinary Markdown note and create disposable entries only
inside those two folders. Keep overwrite, move, and delete tools out of the
normal assistant group.

For Google, verify the authorized account is personal, Gmail scopes are
read-only, and Calendar scopes are limited to event read/write. Test mail with a
search/read, and Calendar with a disposable event. Never authorize a work
account or copy work content into this cluster.

For Actual Budget, confirm the server command is `node` with
`/opt/actual-mcp/build/index.js` as its only argument. Do not add
`--enable-write`. Keep
`ACTUAL_SERVER_URL=http://actual-budget-api.apps.svc.cluster.local:5006`,
`ACTUAL_PASSWORD`, `ACTUAL_BUDGET_SYNC_ID`, and
`ACTUAL_DATA_DIR=/tmp/actual-mcp` in MCPHub. The sync ID is the budget's
`groupId`/Advanced-settings sync ID, not its server-side file ID. The server
must advertise exactly eight tools. Test `get-accounts`, then a narrow monthly
summary. Confirm that `get-accounts` returns `lastReconciledAt` and
`daysSinceReconciliation` for a reconciled account; do not paste raw transaction
output into logs or tickets.

After a MCPHub restore or credential rotation, verify every server connection,
review the group's exact tool list, and perform one harmless call through Open
WebUI. Never print server environment values, OAuth tokens, bearer keys, or API
keys while troubleshooting.

### Navidrome and Lidarr

Navidrome streams the music library at `music.reza.network`; Lidarr manages
music acquisition at the LAN/WireGuard-only `lidarr.reza.network`. Lidarr
shares the floating downloads pod's Gluetun network namespace, qBittorrent,
and `/media` JuiceFS mount, with Pi-hosted NFS downloads mounted over
`/media/downloads`. Navidrome has a separate pod, a Longhorn data volume, and a
read-only `/music` category view of the same JuiceFS filesystem.

After deployment, sign into Navidrome through Authentik once. The first
externally authenticated user becomes its administrator. Create a separate,
non-administrator native Navidrome user for MCPHub; store that username and
password only in `navidrome-mcp`'s settings file on MCPHub's backed-up
application-data volume. The MCPHub server record contains only the path to
that file. Browser traffic reaches
the public policy-proxy port, native Subsonic clients use `/rest/*`, MCPHub uses
`http://navidrome-api.media.svc.cluster.local:4533`, and Prometheus has a
metrics-only port. Navidrome itself listens on loopback and trusts external
identity headers only from the local proxy.

Configure Lidarr in its UI or API-backed application state, not in Git:

1. add `/media/music` as the root folder;
2. add qBittorrent at `127.0.0.1:8080` with a dedicated `music` category;
3. register Lidarr in Prowlarr so compatible indexers are synchronized;
4. choose an explicit metadata profile and a conservative lossless/lossy
   quality profile before adding artists;
5. test one monitored album and verify the completed path lands beneath
   `/media/music` with uid/gid 1000;
6. confirm Navidrome's next bounded scan imports it.

MCPHub owns all media MCP registrations and credentials. Recommended server
boundaries are:

- Seerr: allow `ping`, search, request lookup, and (only in action groups)
  media requests. Never expose `raw_request`.
- mcp-arr: allow health/library/queue/calendar/profile reads. Add only reviewed
  Lidarr artist/album acquisition operations to action groups. Exclude arbitrary
  Radarr/Sonarr deletion, queue deletion, and generic mutation.
- Navidrome: allow library/history/playlist reads; add playlist, star, and
  rating mutations to action groups. Exclude library deletion and local
  playback control.
- Audiobookshelf: run the pinned Python package in verbose mode and allow only
  `get_libraries`, `get_podcast_feed`, `create_podcast`, `check_new_episodes`,
  `get_episode_downloads`, and `download_episodes`. Its dedicated admin account
  is restricted to the Podcasts library and has delete permission disabled.
  Keep bulk OPML import, queue clearing, episode removal/update/matching, and
  all non-podcast mutation tools outside every group.

Health checks:

```bash
sudo k3s kubectl -n media get deployment/downloads deployment/navidrome pods services persistentvolumeclaims
sudo k3s kubectl -n media logs deploy/downloads -c lidarr --tail=150
sudo k3s kubectl -n media logs deploy/navidrome -c navidrome --tail=150
sudo k3s kubectl -n media logs deploy/navidrome -c policy-proxy --tail=100
sudo k3s kubectl -n apps logs deploy/mcphub -c mcphub --tail=150 | grep -i audiobookshelf
sudo k3s kubectl -n media exec deploy/downloads -c lidarr -- \
  sh -lc 'test -w /media/music && curl -fsS http://127.0.0.1:8686/ping'
```

Longhorn backups protect Navidrome and Lidarr application state. The music
payload is authoritative in the encrypted JuiceFS media bucket and requires
the separately protected JuiceFS PostgreSQL metadata and RSA recovery key.
Restore state and metadata before reconnecting MCP servers, then test reads
before any acquisition or playlist mutation.

### Soularr and slskd

Soularr complements Prowlarr for regional, older, obscure, and inconsistently
named music. It reads Lidarr's missing-album queue, searches Soulseek through
slskd, downloads a matching release, and asks Lidarr to import it. Prowlarr
remains enabled and continues to handle ordinary indexer searches.

Soularr and slskd run inside the existing `downloads` pod. They therefore share
Gluetun's network namespace and VPN kill switch with Lidarr and qBittorrent.
The stable Gluetun release and the current Proton connection provide one
forwarded port, which remains assigned to qBittorrent. slskd can initiate
Soulseek searches and downloads through the VPN but cannot accept incoming
connections from peers that are also firewalled. Removing that limitation
requires a separately generated Proton WireGuard configuration and a dedicated
Gluetun tunnel; do not reuse or disrupt the torrent tunnel for it.

The browser interfaces are LAN/WireGuard-only and protected by Authentik:

- `https://soularr.reza.network` provides logs, failed-import state, and an
  operational `config.ini` editor;
- `https://slskd.reza.network` provides Soulseek searches, transfers, and
  runtime configuration.

Application settings and credentials are deliberately stored on the
`soularr-data` and `slskd-state` Longhorn volumes, not generated into Git.
Those volumes participate in the default nightly B2 backup. Completed and
incomplete transfers use `/home/reza/media/downloads/slskd` on the Pi NFS
filesystem. Soularr sees that as `/downloads/slskd/complete`; Lidarr sees the
same directory as `/media/downloads/slskd/complete`. Lidarr copies a completed
release across the filesystem boundary into JuiceFS `/media/music`; the local
torrent/Soulseek copy remains on the Pi only for its retention period.

The initial operational configuration should keep downloads conservative:
process only a small batch on each five-minute run, retain the failed-import
denylist, accept common FLAC and MP3 variants, and skip release-region matching
so Persian releases are not rejected solely because of incomplete MusicBrainz
country metadata. Do not configure a shared directory without an explicit
decision to upload local media to Soulseek.

Health checks:

```bash
sudo k3s kubectl -n media get deployment/downloads pod services persistentvolumeclaims
sudo k3s kubectl -n media logs deploy/downloads -c gluetun --tail=150
sudo k3s kubectl -n media logs deploy/downloads -c slskd --tail=150
sudo k3s kubectl -n media logs deploy/downloads -c soularr --tail=150
sudo k3s kubectl -n media exec deploy/downloads -c slskd -- \
  wget -qO- http://127.0.0.1:5030/health
sudo k3s kubectl -n media exec deploy/downloads -c soularr -- \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8265/").status)'
```

Prometheus scrapes slskd's internal `/metrics` endpoint and alerts when slskd
or the Soularr container is unavailable. If searches stop producing results,
check the Gluetun forwarded-port log, Soulseek login state, Lidarr's wanted
queue, Soularr's failed-import list, and NFS permissions in that order.

### Assistant operations MCP

Grafana, Kubernetes, and GitHub are diagnostic context, not an administrative
back door. Grafana uses a dedicated Viewer service account and its official MCP
server's `--disable-write` mode. Kubernetes uses the projected token for
`mcphub-observer`, the official server's `--read-only` mode, and RBAC that
excludes Secrets, exec, ConfigMaps, and every write verb. GitHub uses the
official server's `--read-only` mode and a fine-grained token restricted to the
personal repositories that need inspection.

After a package or credential change, verify the binaries and effective access:

```bash
sudo k3s kubectl -n apps exec deploy/mcphub -c mcphub -- sh -lc '
  command -v mcp-grafana &&
  command -v kubernetes-mcp-server &&
  command -v github-mcp-server &&
  command -v jellyseerr-mcp &&
  command -v mcp-arr &&
  command -v navidrome-mcp'
sudo k3s kubectl auth can-i --as=system:serviceaccount:apps:mcphub-observer get pods --all-namespaces
sudo k3s kubectl auth can-i --as=system:serviceaccount:apps:mcphub-observer get secrets --all-namespaces
sudo k3s kubectl auth can-i --as=system:serviceaccount:apps:mcphub-observer create deployments -n apps
```

The first authorization check should say `yes`; the latter two must say `no`.
Run a harmless dashboard search, pod listing, and repository read through the
curated Assistant read group. Inspect MCPHub Activity, then verify the action
group still contains no operations write tools.

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

## Observability and alerting

Grafana is available at `https://grafana.reza.network` only from the LAN or
WireGuard. Choose **Sign in with Authentik**. Membership in `home-admins` maps
to the Grafana Admin role; other authenticated users are Viewers. The local
`reza` account is a break-glass path whose generated password is stored only in
the SOPS-encrypted `monitoring/grafana-secrets` Secret. Do not expose the login
form publicly or copy that password into documentation.

Prometheus and Alertmanager intentionally have no HTTPRoute. Inspect them from
an operator workstation through short-lived port forwards:

```bash
ssh beelink
sudo k3s kubectl -n monitoring port-forward svc/observability-prometheus 9090:9090
# In a second session, use 9093:9093 for svc/observability-alertmanager.
```

The first status pass is:

```bash
sudo k3s kubectl -n monitoring get helmrelease observability
sudo k3s kubectl -n monitoring get prometheus,alertmanager,pods,svc,pvc
sudo k3s kubectl -n monitoring get servicemonitor,podmonitor,prometheusrule
sudo k3s kubectl -n monitoring logs deployment/observability-operator --tail=100
sudo k3s kubectl -n monitoring logs statefulset/prometheus-observability-prometheus -c prometheus --tail=100
sudo k3s kubectl -n monitoring logs statefulset/alertmanager-observability-alertmanager -c alertmanager --tail=100
```

In Prometheus, `/targets` must show the API server, kubelets, both node
exporters, CoreDNS, kube-state-metrics, Longhorn managers, Traefik,
cert-manager, Flux controllers, Grafana, Headlamp, Loggifly, Alertmanager,
Prometheus, and the operator as healthy. A target that is absent usually means
its ServiceMonitor selector does not match; a present but down target usually
means the endpoint, TLS setting, or NetworkPolicy path is wrong. Check the
generated scrape configuration and the selected Service/Pod before widening a
NetworkPolicy.

Alertmanager is fail-closed for Telegram: only alerts explicitly labeled
`warning` or `critical` are delivered. `Watchdog`, `InfoInhibitor`, informational
alerts, and unknown or missing severities go to the null receiver. The canonical
`InfoInhibitor` rule also inhibits informational alerts in the same namespace.
Notifications are grouped by namespace and alert name and include resolved
messages. Their `Source` link uses Grafana's Authentik-protected Prometheus
datasource proxy, so it requires a Grafana session and LAN or WireGuard access;
Prometheus itself remains ClusterIP-only. Use the Alertmanager UI through the
port-forward to create a time-bounded silence during planned work. Never disable
a rule or route globally merely to hide an unexplained alert. The Kubernetes
event exporter is an independent Telegram signal and can still report events
when Prometheus or Alertmanager is unavailable.

The `Home Server Overview` dashboard is repository-managed and read-only.
Upstream Kubernetes dashboards are also provisioned by ConfigMap. UI-created
dashboards and preferences live on the Grafana PVC, but important dashboards
must be exported back into Git rather than relying on that local database.
There is currently no Loki deployment; use `kubectl logs` for logs.

Prometheus is capped by both `14d` retention and `20GB` retention size on a
30 GiB PVC. If it approaches the cap, first identify unexpected cardinality or
an accidentally broad scrape before increasing storage. Confirm that the three
observability volumes do not inherit `b2-nightly`:

```bash
sudo k3s kubectl -n monitoring get pvc
sudo k3s kubectl -n longhorn-system get volumes.longhorn.io \
  -o custom-columns=VOLUME:.metadata.name,CLAIM:.status.kubernetesStatus.pvcName,JOBS:.spec.recurringJobSelector
```

The matching volumes must select only the intentionally unused
`observability-local` group. Their data is reproducible and must not consume B2
backup capacity. If Grafana OIDC fails, check the `grafana.yaml` Authentik
blueprint status, the exact `/login/generic_oauth` redirect URI, client-secret
equality through SOPS, and Grafana logs. Preserve the local admin path until
OIDC has been verified after every authentication change.

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

qBittorrent's operational share policy lives in its backed-up application
volume rather than in the infrastructure manifests. The global ratio limit is
disabled. The global seeding-time limit is one minute and its action is
**Stop torrent**; qBittorrent must never delete the torrent or payload when the
share limit is reached. Every managed torrent inherits the global limits.

Radarr, Sonarr, and Lidarr have completed-download handling enabled but
**Remove** disabled. Arr's built-in remover trusts historical import state and
can delete the last download copy when a formerly imported library file has
since disappeared. The `downloads-import-cleaner` sidecar is therefore the
only component authorized to call qBittorrent's destructive delete endpoint.
It reads API keys from the three backed-up Arr configuration volumes; no API
keys or application settings live in the infrastructure manifests.

The cleaner accepts only stopped, complete `tv-sonarr`, `radarr`, and `music`
torrents with unique payload paths on the Pi NFS volume. It requires an exact
successful Arr import-history event, verifies every affected current Arr
record points to a non-empty file on the read-only JuiceFS mount, and repeats
the complete check in two consecutive 60-second passes. Lidarr additionally
requires every audio file in the torrent to have a matching track-import
event. Immediately before deletion it rechecks both qBittorrent state and the
current library. Incomplete imports, missing current library files, duplicate
payload paths, manual downloads, books, and uncategorized torrents fail closed
and remain stopped for review.

Review the one-minute stop-only policy in qBittorrent under **Settings >
BitTorrent > Seeding Limits** and verify **Remove** remains disabled in the Arr
applications under **Settings > Download Clients > Completed Download
Handling** after restoring their configuration volumes.

Full-file preallocation is enabled in the same backed-up qBittorrent settings.
The `downloads-storage-guard` container is the hard safety boundary: every 60
seconds it verifies that `/media/downloads` is NFS, checks free bytes and
percentage, and tags and stops only active incomplete torrents when either free
space is below 200 GiB or free space is below 20%. Completed imports and the
cleaner remain active so they can reclaim space. Once free space is at least
300 GiB and 30%, the guard automatically resumes only the torrents carrying its
`storage-guard-paused` ownership tag. It first requires a fresh successful
cleaner check of the NFS/JuiceFS mounts, Arr ownership policy, and qBittorrent
inventory. It never resumes a manually stopped torrent and never deletes a
payload. The 100 GiB hysteresis band prevents rapid stop/start cycles; do not
replace it with qBittorrent queueing. The stop threshold sits well above the
kubelet DiskPressure eviction point so the guard always wins that race; do not
lower it below 20% free.

```bash
sudo k3s kubectl -n media logs deployment/downloads -c downloads-storage-guard --tail=100
sudo k3s kubectl -n media logs deployment/downloads -c downloads-import-cleaner --tail=100
sudo k3s kubectl -n media exec deployment/downloads -c qbittorrent -- \
  sh -ec 'curl -fsS http://127.0.0.1:8080/api/v2/app/preferences | grep -o '"'"'"preallocate_all":[^,}]*'"'"''
```

## Node resource pressure

`HomeServerNodeResourcePressure` detects sustained full I/O stalls, full memory
stalls, or swap traffic. On nodes whose kernel does not expose PSI, it falls
back to CPU I/O wait and available-memory thresholds. Short bursts are ignored
for 15 minutes. When it fires, identify the resource label and inspect both the
host and the cluster:

```bash
ssh beelink 'uptime; free -h; vmstat 1 5; cat /proc/pressure/io; cat /proc/pressure/memory'
ssh beelink 'sudo k3s kubectl top nodes; sudo k3s kubectl top pods -A --sort-by=memory | head -30'
```

First check where the downloads pod is running and inspect qBittorrent's active
torrent counts. It should normally prefer a non-control-plane worker, but it is
allowed to run anywhere. If unrestricted concurrency causes sustained pressure,
temporarily pause transfers and inspect Longhorn, Prometheus, JuiceFS, and NFS
traffic before restarting or deleting any storage pod.

qBittorrent has a 512 MiB memory request and 3 GiB limit. The headroom is
intentional: loading hundreds of unrestricted torrents can exceed 512 MiB after
libtorrent and filesystem-cache overhead. Its operational settings cap the
libtorrent disk cache at 256 MiB with a 30-second expiry; that setting lives in
the backed-up qBittorrent config volume rather than in the Deployment. If it is
OOM-killed, inspect `memory.current` and the `anon`, `file`, and `file_dirty`
entries in `memory.stat` as well as the node's available memory before raising
the limit. Do not enable queueing merely to hide an undersized cgroup.

Repeated Longhorn `FailedMount` events that say `no Pending workload pods` can
be delayed retry noise after a node stall. Treat them as a storage incident only
if the event count is still increasing or the corresponding Longhorn volume is
not `attached` and `healthy`; verify the database or application health before
restarting anything.

Calibre-Web and the downloads pod are independently floating workloads. Their
Shelfmark handoff uses `calibre-web-ingest-rwx`; do not replace it with an RWO
claim or pod affinity. Pod affinity is evaluated only when scheduling and can
leave the two controllers on different nodes after a later move. The obsolete
`calibre-web-ingest` RWO claim may be deleted only after the RWX claim is mounted
by both workloads and the old claim is confirmed to contain no pending books.

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

Speedtest Tracker is retired. Its current `speedtest-tracker-config` PVC and
`APP_KEY` Secret are retained as recovery artifacts, while the legacy Speedtest
Tracker database remains a separate read-only source. The legacy database must
not replace the current PVC until a trusted copy of its matching `APP_KEY` is
recovered and proven: encrypted fields cannot be validated from a hash or a newly
generated key. Keep both sources and take a verified final export of the current
PVC before any destructive cleanup.

## Planned maintenance

The two-node design has deliberate single points of failure:

- Beelink maintenance removes DHCP, the K3s control plane, and most compute workloads.
- Pi maintenance removes DNS, public ingress, WireGuard, SMB, Syncthing
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
