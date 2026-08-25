# Task brief: design a state-aware K3s upgrade

Design and review a patch/minor K3s upgrade and rollback procedure for the
existing cluster. The default outcome is research, a version-specific plan, and
an isolated rehearsal. It is not authorization to upgrade or restart production.

The repository's install and join helpers are fresh-host-only and deliberately
refuse existing K3s state. They must never be repurposed as an upgrade mechanism.

## Required inputs

- Repository and exact reference revision: [path and commit]
- Current and target K3s/Kubernetes versions: [exact immutable versions]
- Target release asset/source, checksums, architectures, and provenance: [evidence]
- Current install method, binary path, service units, environment, and config: [inventory]
- Server and agent identities, roles, architectures, labels, taints, and disks: [inventory]
- Current SQLite datastore/token backup and off-host restore evidence: [IDs/read test]
- Target and intermediate release notes, known issues, and support status: [links/findings]
- Kubernetes API removals, webhooks, CRDs, charts, and packaged Addon impact: [analysis]
- Workload/PDB/local-data/Longhorn/NFS/physical-service outage matrix: [inventory]
- Maintenance window, RPO/RTO, abort thresholds, and rollback owner: [details]
- Isolated rehearsal environment, mandatory amd64 and arm64 agents, storage
  equivalence, and representative workload set: [details/evidence]

## Authorization

Fill every line. Blank or ambiguous means no. The suggested default for live,
host, external, and destructive scopes is no.

- Repository edits: [yes/no; procedure, scripts, pins, tests, docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target and draft/ready]
- Merge: [yes/no; exact PR and required checks]
- Read-only cluster/host access: [yes/no; version, config, health, and log scope]
- Live cluster mutation: [yes/no; exact cordon/drain/reconcile scope; default no]
- Host mutation: [yes/no; exact binary/service/reboot scope; production default no]
- Application-state mutation: [yes/no; exact disposable or production application data]
- External/provider mutation: [yes/no; exact release mirror, DNS, alerting objects]
- Destructive actions: [yes/no; exact disposable data or rollback replacement]

Approval to edit an upgrade plan does not authorize binary replacement, K3s
restart, drain, datastore restoration, or rollback in production.

## Manuals, skills, and primary research

Load `home-server-safety`, `cluster-operations`, `node-host-operations`,
`dependency-upgrades`, `backup-restore`, `storage-recovery`, `secrets-sops`,
`incident-response`, `observability`, `ci-supply-chain`, `high-risk-review`, and
`validation`.

Read the current repository [cluster operations manual](../docs/cluster-operations.md),
[architecture](../docs/architecture.md), and [runbook](../docs/runbook.md).
Inspect the actual fresh-host helpers only to document why they are excluded.

Research current primary sources at task time:

- [K3s manual upgrades](https://docs.k3s.io/upgrades/manual)
- [K3s rolling back](https://docs.k3s.io/upgrades/roll-back)
- [K3s backup and restore](https://docs.k3s.io/datastore/backup-restore)
- [Kubernetes version-skew policy](https://kubernetes.io/releases/version-skew-policy/)
- [K3s upstream releases](https://github.com/k3s-io/k3s/releases)

Record access dates and target-specific release-note links. Verify facts against
the exact current/target releases; do not copy a floating channel or mutable
installer example into the production design.

## Threat and failure model

Cover at least:

- skipping a required intermediate minor release or unsupported component skew;
- an agent/kubelet becoming newer than the single API server;
- API removals, admission webhook incompatibility, CRD conversion, or chart drift;
- target binaries/images missing one node architecture or valid checksums;
- installer behavior overwriting service arguments/environment/config;
- the selected server operation removing API availability and, when it drains,
  kills containers, or reboots the host, interrupting Kea DHCP and other pods;
- drain deadlock, local/emptyDir data loss, RWO attachment, or last replica risk;
- SQLite/schema migration that makes binary-only downgrade unsafe;
- rollback snapshot/token mismatch or missing off-host restore evidence;
- K3s-packaged CoreDNS/Metrics/Traefik/Addons changing outside root Flux ownership;
- CNI, network policy, CSI, Longhorn, JuiceFS, NFS, GPU, or host-network regression;
- Flux or Helm reconciliation during a partially upgraded cluster; and
- application writes after the pre-upgrade snapshot that a datastore rollback loses.

State whether the target is patch or minor and how that changes drain,
datastore, skew, and rollback requirements.

## Design workflow

1. Inventory exact server and agent K3s/Kubernetes/component versions, service
   configuration, binary provenance, architectures, packaged Addons, active API
   resources, webhooks, CRDs, CNI/CSI, Flux, Longhorn, and physical services.
2. Build a current-to-target compatibility matrix from primary release notes.
   Include every intermediate minor, deprecated/removed API, architecture asset,
   container-runtime/kernel requirement, chart/AddOn transition, and known issue.
   Do not skip minor versions.
3. Select a pinned upgrade mechanism appropriate to the existing install. It
   must preserve the complete effective config and verify artifact checksums
   before host mutation. The fresh-host install/join helpers are excluded.
4. Define order from upstream constraints: server/control-plane first, then
   agents one at a time. Ensure agents never run a kubelet newer than the API
   server. Define when cordon/drain is required and why for every node.
5. State mechanism-specific physical outage consequences. An ordinary K3s
   service restart, a drain, `killall`, and a host reboot do not have the same
   effect on already-running containers or host services. For the Beelink,
   analyze API, Kea DHCP, compute, ingress, and Longhorn effects of the exact
   operation. For the Pi, separately analyze K3s workloads versus host NFS and
   the WireGuard, SMB, Syncthing, ingress-target, and DNS roles.
6. Define preflight health and abort thresholds for Flux revision, backups,
   SQLite/token recovery, Longhorn replicas/attachments, NFS/JuiceFS, node
   capacity, PDBs, alerts, disk space, certificates, and current errors.
7. Require a consistency-safe pre-upgrade SQLite backup paired with its current
   server token and exact old binary/config, stored off-host and restore-tested.
   If control-plane recovery remains unproven, production upgrade remains blocked
   even when the upgrade design itself is complete.
8. Define a canary/verification gate after the server and after each agent:
   version/skew, API discovery, controllers, webhooks, CRDs, packaged Addons,
   Flux/Helm, CNI/policy, CSI/Longhorn, mounts, endpoints, DNS/DHCP, logs, alerts,
   and representative application reads/writes.
9. Define checkpoint-specific rollback before upgrade. A previous binary alone
   is insufficient when datastore/schema changes occurred. If no agent has been
   upgraded, stop K3s on the server before restoring the exact pre-upgrade
   database, matching historical token, binary, and config. If an agent has
   already been upgraded, first fence workloads and stop that agent, install its
   old binary/config without starting it, and keep every target-version agent
   stopped. Restore the stopped server's matched set, start and validate the old
   server, then start old-version agents one at a time. Never expose an old API
   server to a newer kubelet. State the accepted data-loss boundary.
10. Create version-specific scripts/tests only when repository edits are
    authorized. They must refuse floating targets, checksum failure, skipped
    minors, wrong node order, unsupported skew, unhealthy backup/replicas,
    existing upgrade lock, or an unexpected current version/config.
11. Run complete repository validation and review host/root/high-risk changes.
    Produce a human go/no-go checklist and a separate future production execution
    brief; do not hide mutations inside the design task.

## Isolated rehearsal

Restore a matched SQLite/token backup into an isolated, production-disconnected
server clone using the exact old binary and config. Attach disposable amd64 and
arm64 agents representing both production architectures. Block provider,
router, B2-write, and real LAN side effects. Missing either architecture blocks
promotion of the procedure from design to supported.

Exercise every required intermediate step and the exact server-first/agent-next
order. Capture datastore migrations, API resources, Addon/chart changes, node
rejoin, workload scheduling, CNI/CSI, Flux suspend/resume behavior, and the
acceptance matrix. Use disposable Longhorn with the relevant engine/manager/CSI
versions and node/disk/replica behavior, or document an explicit equivalence
matrix and retain every untested storage behavior as a production blocker;
calling generic storage “Longhorn-equivalent” is not evidence.

At intentional checkpoints before and after an agent upgrade, execute the
designed rollback. Fence writers; stop affected K3s services; downgrade upgraded
agents without starting them; restore the stopped server's pre-upgrade datastore,
matching token, old binary, and config; validate the old API; then start the
downgraded agents one at a time. Measure loss since the snapshot and verify
version skew, API/object identity, and representative workloads. A forward-only
successful rehearsal does not validate rollback.

Test negative gates for wrong current version, checksum mismatch, skipped minor,
agent-first order, unsupported skew, corrupt datastore set, and failed canary.

## Hard stops and abort gates

Stop for a floating/mutable target, missing primary release research, unsupported
skew, skipped minor, missing architecture, unhealthy cluster/storage, unproven
SQLite-token rollback, incompatible APIs/webhooks, unexplained Addon changes, or
an upgrade tool that cannot preserve exact configuration.

Never use fresh-host scripts as upgrade/recovery, run a mutable remote script
without pinned verification, upgrade an agent before the server, weaken drain/
Longhorn policy, or claim a binary downgrade alone reverses a datastore change.

## Rollback and recovery

- Repository: revert version-specific scripts/pins/docs through protected review.
- Binary/config: preserve checksummed old artifacts and exact service config;
  replace/restart only under future host authority.
- Datastore/token: use the matched pre-upgrade SQLite set for any rollback that
  requires schema reversal; state the resulting loss window explicitly.
- Node order: abort after the last proven gate; do not continue to agents when
  the server canary fails. For rollback after any agent upgrade, keep workloads
  fenced, stop and downgrade upgraded agents without starting them, restore and
  validate the stopped old server, then start old agents one by one. Keep failed
  nodes cordoned and never let a newer kubelet contact the rolled-back API.
- Workloads/storage: preserve one writable authority and current backups; do not
  force attachments or discard drain blockers.
- Flux/Helm/Addons: restore compatible source/values and reconcile only after the
  API is stable at the selected version.
- External/application: reverse separately; datastore rollback may revert
  Kubernetes objects but not provider or application data.

## Evidence contract

Return repository and upstream research revisions, exact version/provenance
matrix, deprecation/skew/addon findings, mechanism-specific outage model,
selected mechanism, server/agent forward and rollback order, SQLite-token
rollback set, amd64/arm64 and storage-equivalence evidence, isolated forward and
rollback results, negative gates, validation/security findings, measured
interruption/data-loss bounds, all authorized actions, and blockers.

## Acceptance criteria

- [ ] The design uses exact artifacts and covers all intermediate releases,
      skew rules, server-first order, and architecture support.
- [ ] Fresh-host helpers are explicitly excluded and protected from upgrade use.
- [ ] Datastore, token, old binary/config, drain, and rollback are one coherent plan.
- [ ] Addons, APIs, webhooks, networking, storage, Flux, and workloads have gates.
- [ ] Isolated forward upgrade, checkpoint-specific ordered rollback, and
      negative rehearsals cover both amd64 and arm64; storage equivalence is
      proven or remains an explicit blocker.
- [ ] Production execution remains separately authorized and blocked without a
      proven control-plane recovery set.
- [ ] The procedure becomes supported only after reviewed rehearsal evidence exists.
