# Home Assistant

Home Assistant Container runs as a single Beelink-pinned `apps` workload with
its `/config` directory on a 20 GiB Longhorn RWO volume. The pinned image does
support both cluster architectures, but third-party integration code is kept
off the Pi because that node hosts trusted NFS data. Recreate updates and a
five-minute termination grace protect the SQLite recorder from overlapping
writers and abrupt shutdowns.

## Safe first-owner onboarding

Do not publish a fresh Home Assistant instance: the first visitor can create
its owner account. `route.yaml` is therefore present but deliberately omitted
from this directory's `kustomization.yaml` until onboarding is complete.
Pi-hole DNS must also remain absent during this stage.

After Flux has deployed a healthy pod, run this from an operator workstation:

```bash
ssh -o StrictHostKeyChecking=yes -t \
  -L 127.0.0.1:18123:127.0.0.1:18123 beelink \
  'sudo k3s kubectl -n apps port-forward \
    --address=127.0.0.1 deployment/home-assistant 18123:8123'
```

Open `http://127.0.0.1:18123`, create the owner, set the correct home location,
and enable MFA for that owner. Then create the durable, PVC-backed activation
marker while the tunnel remains the only access path:

```bash
ssh -o StrictHostKeyChecking=yes beelink \
  "sudo k3s kubectl -n apps exec deployment/home-assistant \
    -c home-assistant -- sh -c 'umask 077; : > /config/.owner-onboarded'"
```

Stop the tunnel, then activate the private route:

1. add `route.yaml` to this directory's Kustomization;
2. change the Deployment's `owner-onboarded` pod-template annotation to
   `"true"` so the init container re-evaluates the marker;
3. add `192.168.1.240 homeassistant.reza.network` to Pi-hole's
   `FTLCONF_dns_hosts` list;
4. replace the pending-onboarding wording in this README, the app
   Kustomization, and the repository workload table;
5. render, review the new HTTPRoute high-risk boundary, merge, and
   verify `https://homeassistant.reza.network` from a normal LAN client;
6. verify the HTTPRoute reports `Accepted=True` and `ResolvedRefs=True`, Pi-hole
   still serves DNS/DHCP, WireGuard access works, and a forced-SNI request from
   outside LAN/WireGuard is denied;
7. in **Settings → System → Network**, set the local URL to
   `https://homeassistant.reza.network`. Leave the Internet URL blank unless
   Nabu Casa or another deliberate remote-access design is enabled. Companion
   App clients should use this HTTPS name and WireGuard when away from home.

Do not add this hostname to Cloudflare DDNS during private activation. VPN
clients should use Pi-hole DNS; public DNS and inbound webhooks are separate
exposure decisions.

The route uses Home Assistant's own authentication. Do not place generic
Authentik forward-auth in front without separately designing Companion App,
webhook, WebSocket, and integration callback behavior.

## Network and hardware boundary

The pod intentionally does not use host networking, host paths, devices,
D-Bus, added capabilities, or privileged mode. HTTPS-based cloud integrations
can work. LAN egress is denied initially; add only an actual device's `/32`,
protocol, and port after reviewing the integration. Never authorize the router,
cluster-node addresses, NFS/RPC/SMB ports, or Traefik's VIP as a convenience.
Automatic mDNS, SSDP, HomeKit, Cast, or similar multicast discovery may not
cross the K3s overlay, and direct Bluetooth/Zigbee/Z-Wave/Thread USB hardware
is unavailable.

Prefer network-attached Zigbee/Thread coordinators and ESPHome Bluetooth
proxies so Home Assistant can remain floating. If a real integration requires
host networking or a local device, design that as a separate reviewed change:
choose and pin a node, expose only the exact device, protect any direct node
listener, and re-review Pod Security and NetworkPolicy assumptions. Never add
blanket `privileged: true` merely to make discovery convenient.

This is Home Assistant Container, not Home Assistant OS. It does not include
Supervisor or its app/add-on store; container image upgrades are made through
this Git repository. Relevant upstream references are the
[container installation guide](https://www.home-assistant.io/installation/linux),
[HTTP reverse-proxy settings](https://www.home-assistant.io/integrations/http),
and [Zeroconf discovery constraints](https://www.home-assistant.io/integrations/zeroconf).

The access proxy starts with a deny-only runtime configuration whenever the
PVC lacks `.owner-onboarded`. The normal config is selected only during pod
startup when that durable marker exists. This makes a genuinely empty or older
restored PVC fail closed even if a stale HTTPRoute survives because root Flux
pruning is disabled. During recovery, explicitly delete the live HTTPRoute as
well as removing it from Git, validate the owner through the loopback tunnel,
recreate the marker, and only then restart and republish the pod.

Request paths are intentionally omitted from both this proxy's access log and
Traefik's cluster-wide access log because `/api/webhook/<id>` contains a bearer
secret. Treat webhook IDs like passwords and never use an unauthenticated
webhook alone for safety-critical actions.

## Configuration and recovery

The bootstrap ConfigMap creates the upstream-style YAML files only when they do
not already exist. Restored or user-edited files on `/config` are never
overwritten. Preserve the `http.use_x_forwarded_for` setting and keep
`http.trusted_proxies` limited to `127.0.0.1`; the colocated nginx proxy is the
only intended immediate forwarded-header peer.

Longhorn replicates the PVC across both nodes. The volume automatically inherits
the default nightly Backblaze B2 job group, but that makes it backup-eligible;
it is not an off-site recovery point until a `b2-nightly` or reviewed on-demand
backup completes. Longhorn then covers `.storage`, authentication state, the
SQLite recorder, YAML, and native backups stored under `/config/backups`, but
only as a crash-consistent block backup. After onboarding, Home Assistant's
native encrypted Backblaze B2 integration is a worthwhile independent,
application-aware recovery layer; use a dedicated bucket/key rather than either
existing Longhorn or Syncthing repository. Store its backup emergency kit and
encryption material outside this cluster and prove an isolated restore before
claiming it as recovery coverage.

See Home Assistant's [backup integration](https://www.home-assistant.io/integrations/backup/)
and [Backblaze B2 integration](https://www.home-assistant.io/integrations/backblaze_b2/)
before enabling native off-site backups.
