# Home cluster architecture

## Current migration phase

The production Docker Compose stack remains on `raspberrypi` (`192.168.1.2`).
It continues to provide DNS, DHCP, HTTPS ingress, VPN, SMB, media, and all
application workloads while the Kubernetes platform is built alongside it.

The interim Kubernetes topology is intentionally non-HA:

- `beelink` (`192.168.1.3`, amd64) is the single K3s server and a worker.
- `raspberrypi` (`192.168.1.2`, arm64) joins as a worker but is initially
  cordoned so Kubernetes cannot compete with the production Compose stack.
- K3s uses its single-server SQLite datastore. A two-member embedded-etcd
  cluster is not used because it has no failure quorum.
- Bundled Traefik, ServiceLB, and local-path storage are disabled. Platform
  components are installed declaratively through Flux.

This phase creates a scheduler and GitOps control plane without moving the
existing network edge or stopping any production service.

## Target state

The long-term topology is three wired K3s server/worker nodes with embedded
etcd, plus storage that is independent of the cluster nodes:

```text
Internet -> router -> MetalLB VIP -> Traefik Gateway API -> applications
                                  \
GitHub -> Flux -> K3s (3 server/worker nodes)
                    |       |
                    + Longhorn (small application volumes)
                    + NAS/NFS (media, downloads, books, backups)
```

- A third SSD-backed node is required before enabling embedded-etcd HA.
- A NAS or other independent storage server is required before large shared
  datasets can move off the Pi without replacing one single point of failure
  with another.
- Longhorn uses two replicas during the interim and must move to three replicas
  when a third eligible storage node is added.
- The eventual edge is Traefik using Kubernetes Gateway API. `ingress-nginx`
  is not used because the upstream project was retired in March 2026.
- MetalLB needs a LAN address that is excluded from the router's DHCP pool.
  No address is guessed or advertised until that reservation is confirmed.
- cert-manager uses Cloudflare DNS-01. The Cloudflare token and all application
  credentials are SOPS/age-encrypted in Git; the age identity is never stored
  in the repository.

## Scheduling rules

Ordinary workloads have no hostname affinity. Kubernetes can place them on any
node that has sufficient resources and a compatible image architecture.
Constraints are allowed only for physical requirements such as amd64-only
images, `/dev/dri`, host networking, multicast, or storage locality.

Singleton applications and single-writer databases remain one replica even
when their volumes are replicated. Storage replication is not application or
database-level clustering.

## Storage classes

- Longhorn: small databases, configuration, and application state.
- NAS/NFS: movies, TV, books, downloads, shared Syncthing data, and backup
  repositories.
- Node-local paths: not used for durable application state.

The interim Longhorn StorageClass requests two replicas and retains volumes
when claims are deleted. Because the Pi is initially cordoned, no durable PVC
is created until both storage nodes are eligible; degraded single-replica
volume creation is disabled.

The pre-K3s rollback snapshot is stored outside Kubernetes at
`/srv/home-server-backups/pre-k3s-20260712` on the Beelink. It contains the Pi
application-state tree and consistency-safe logical dumps of all four live
PostgreSQL instances. It is a migration rollback copy, not an off-site backup.

The Beelink uses only its static wired address. Wi-Fi is intentionally absent
from the checked-in Netplan configuration so Kubernetes never advertises or
routes through a second LAN address.

## Service migration order

1. Platform: Flux, SOPS/age, Longhorn, MetalLB, Gateway API, Traefik,
   cert-manager, monitoring, and default-deny network policy.
2. Low-risk applications with no special host integration.
3. Stateful applications, one at a time, using an export/restore or logical
   database dump and an explicit rollback check.
4. Media and VPN workloads after shared storage and sidecar networking are
   ready.
5. DNS/DHCP, WireGuard, SMB, and other host-network services last. Prefer the
   router for DHCP/WireGuard and the NAS for SMB.

Compose and SWAG are retired only after every route, data restore, backup, and
rollback test succeeds.
