---
name: network-services
description: Operate or diagnose Blocky DNS, Kea DHCP, Stork, WireGuard, Samba, Syncthing, and Pi-hosted NFS. Use for LAN protocol and physical network-service work, not ordinary HTTPRoute or OIDC changes.
---

# Operate LAN and Pi network services

These services combine Kubernetes objects with host networking, physical
interfaces, Pi-local data, router forwards, and host exports. A pod moving or
becoming Ready does not move those dependencies.

## Required reading and ownership

Read:

- [runbook DNS, DHCP, and Pi services](../../docs/runbook.md#dns-and-dhcp);
- [cluster networking and placement](../../docs/cluster-operations.md);
- [architecture traffic and failure domains](../../docs/architecture.md);
- [service lifecycle network/storage rules](../../docs/service-operations.md);
  and
- [JuiceFS operations](../../docs/juicefs-media.md) when Samba or a media mount
  is involved.

Classify every requested change:

| Plane | Examples |
| --- | --- |
| Root Flux | Blocky, Kea, Stork, WireGuard, Samba, Syncthing workloads and policies |
| Pruning Flux child | Syncthing backup Secret, policy, CronJobs, and NetworkPolicy |
| Pi/Beelink host | NFS exports, host resolvers, listeners, package/network policy |
| Application state | Syncthing identity/folders, WireGuard peers, service settings |
| Router/provider | public port forwards and external DNS/provider objects |

Repository editing does not authorize host export reload, router changes,
peer creation, provider mutation, live restart, or data deletion.

## Service contracts

### Blocky DNS

Blocky is a host-network DaemonSet serving DNS from each node's LAN address.
Its management and metrics listeners bind only to node CNI gateways; there is
no admin route. Split-horizon application mappings are catalog-generated and
must not be hand-edited.

Cluster nodes use independent public host resolvers, not Blocky. This prevents
recovery from depending on the DNS workload whose image may need to be pulled.
Do not point node resolvers back at Blocky.

### Kea DHCP and Stork

Kea is tied to the Beelink host network, physical LAN interface, architecture,
and Longhorn lease state. Stork is a read-only monitoring UI and database; DHCP
must continue when Stork is unavailable. Preserve the Stork lockdown and
read-only role rather than granting an administrator account to repair UI
access.

Never run a retired DHCP service in parallel with Kea. During DHCP failure,
existing leases may continue while new or renewing clients fail; preserve that
distinction when assessing impact.

### WireGuard

WireGuard is tied to the Pi router target, host port, exact unsafe sysctls, and
Longhorn configuration. Client traffic is masqueraded to the current Pi
PodCIDR, which is a reviewed private-route trust exception. Never broaden it to
the cluster PodCIDR. Replacing the Pi or changing its PodCIDR requires route,
middleware, NetworkPolicy, high-risk, and real-client review.

### NFS, Samba, and Syncthing

Pi NFS exports are exact child paths with `root_squash`; do not add a broad
parent export. The downloads tree is transient/reproducible and has no automatic
off-site backup. The Syncthing data tree has its dedicated encrypted Restic B2
workflow. A newly added export is not covered merely because another Pi path is
backed up.

Samba and Syncthing are Pi-pinned host-network services. Syncthing combines a
Pi-local NFS data tree with Longhorn configuration and a separately owned
backup child. Keep automatic NAT traversal disabled so Syncthing cannot create
an Internet-facing router mapping. Production Syncthing disaster recovery is
not established by the disposable restore proof.

## Read-only discovery

Start with current desired manifests, exact Flux revision, and bounded live
checks:

```bash
ssh beelink 'sudo k3s kubectl -n network-services get daemonset,deployment,statefulset,cronjob,job,pod,svc,endpointslice,pvc -o wide'
ssh beelink 'sudo k3s kubectl -n flux-system get kustomizations -o wide'
ssh beelink 'sudo k3s kubectl get pv,volumeattachment'
ssh pi 'sudo exportfs -v; sudo ss -lntup'
ssh beelink 'sudo ss -lntup'
```

Then test from the correct client vantage point:

- ordinary upstream DNS, split-horizon DNS, and a known blocked name through
  every advertised resolver;
- DHCP listener/interface, lease PVC, pool metrics, and a controlled client
  renewal when safe;
- NFS export/mount/read-write behavior from every intended node;
- WireGuard handshake and private-route access from a real peer;
- SMB discovery/auth/read-write behavior from a LAN client; and
- Syncthing discovery, transfer, GUI boundary, identity, storage mounts, and
  backup freshness.

Do not dump peer configurations, leases containing private identifiers,
Syncthing config, SMB credentials, or SOPS plaintext.

## Supported workflows

### Change DNS or DHCP

Make Blocky split-DNS intent through the colocated service descriptor and
catalog render. Change filtering, Kea reservations, or DHCP options in their
reviewed explicit configuration. Review public-repository disclosure before
committing device identifiers.

After merge, verify the exact revision, both resolver paths, listener bind
addresses, upstream recovery, split answers, blocking, DHCP metrics, lease
state, and a real client. A Kea reservation does not automatically create DNS.

### Change NFS or move the Pi role

Inventory every PV, mount, writer, UID/GID, export client, backup, and
application dependency. Update Git and host export policy as separate reviewed
steps. Apply and reload the host file only when explicitly authorized, then
compare the installed file and test intended and denied clients.

Moving/replacing the Pi is a storage and network migration: preserve NFS data,
Syncthing identity, DNS endpoint, SMB behavior, WireGuard router target, and the
PodCIDR trust design. Do not treat it as an ordinary pod reschedule.

### Change WireGuard, Samba, or Syncthing

Separate Git-owned pod boundaries from UI/application-owned peers, users,
shares, folders, and identities. Prove the relevant Longhorn and file-level
backup before changing configuration or storage. Router forwards and peer
distribution need separate authorization.

For Syncthing backup changes, inspect the pruning child owner and its inventory;
root rendering alone does not include the backup resources. Preserve the exact
repository identity, source canary, read-only mounts, folder-ID policy,
candidate-to-trusted promotion, and independent freshness check.

## Failure-domain safety and hard stops

Pi maintenance removes its NFS data, public ingress target, WireGuard, SMB,
Syncthing role, and one DNS endpoint. Beelink maintenance removes DHCP, the
control plane, and its DNS endpoint. State those expected losses before work;
the other node being Ready does not remove them.

Never:

- start a second DHCP server or revive retired Pi-hole alongside Blocky/Kea;
- expose Blocky or Kea management listeners to the LAN or Gateway;
- make node DNS depend on Blocky;
- broaden NFS exports, disable `root_squash`, or delete an export tree without
  writer and retention proof;
- bypass WireGuard's reviewed sysctl, host-port, router, or PodCIDR boundary;
- enable Syncthing automatic router mapping;
- treat the downloads export as backed up or place databases there;
- use the Syncthing disposable restore cleanup against production data; or
- loosen host networking, capabilities, broad egress, or the high-risk baseline
  merely to restore connectivity.

## Rollback and completion evidence

Write rollback per plane. Git revert restores desired manifests but does not
restore a host export, router forward, peer configuration, application identity,
or provider record. During DNS/DHCP rollback, never run old and new DHCP/DNS
listeners on conflicting ports; stop and verify one side before starting the
other under a reviewed revision.

Report exact Git/Flux and child revisions, installed host-file comparison,
listener addresses, DNS/DHCP/NFS/WireGuard/SMB/Syncthing client tests as
applicable, volume and backup health, physical node dependencies, every
live/host/router/application mutation, rollback state, and unsupported recovery
gaps.
