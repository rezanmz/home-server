# Home Server — Agent Operating Guide

This repository is the declarative source of truth for a real two-node K3s
cluster. Read this file before inspecting, editing, or operating it. A manifest
change can become a production change after it reaches protected `main` and
Flux reconciles it.

## How to use this repository's guidance

The guidance has three layers:

1. `AGENTS.md` defines repository-wide safety, authority, and completion rules.
2. `skills/*/SKILL.md` contains task-specific workflows and stop conditions.
3. `prompts/*.md` contains reusable task briefs with explicit inputs,
   authorization, and acceptance criteria.

For each task, load the matching skill and read the manual it names. Skills and
prompts are navigation aids, not replacements for the manuals.

Runtime-specific files are discovery adapters only. The repository-root
`AGENTS.md`, canonical `skills/`, and canonical `prompts/` remain authoritative;
do not maintain edited policy copies under `.claude/`, `.cursor/`, `.github/`,
`.agents/`, or `.omp/`.

When sources appear to disagree:

- active Kustomization reachability and a fresh render establish Git desired
  state;
- read-only cluster inspection establishes live state;
- the relevant `docs/` manual defines the supported operating procedure;
- a skill or prompt must never silently override a manual.

A manual describes how an already authorized operation is performed. The
presence of a command in a manual is not permission to run it.

Stop and report the discrepancy before a risky action. Do not make prose true
by changing production, and do not assume a YAML file is active merely because
it exists.

## Keep guidance and documentation current

Repository guidance is part of the supported implementation. When an
authorized change alters durable topology, ownership, security boundaries,
supported commands, automatic side effects, validation, rollback, evidence,
recurring maintenance, or agent discovery, update the affected guidance in the
same change:

- update the authoritative operator manual first or in the same change;
- update this file when repository-wide safety, authority, routing, workflow,
  or completion changes;
- update every affected skill's trigger, sources, gates, workflow, rollback,
  and evidence contract;
- update affected task prompts, the generic prompt template, and prompt/skill
  indexes when their inputs, permissions, workflow, or acceptance changes;
- update runtime adapters only when discovery changes, and keep them as thin
  imports, pointers, documented canonical links, or configured canonical
  directories; and
- update validation and tests whenever the contract can be checked
  mechanically.

Guidance repair is not standing authority. In a read-only task, report drift
and the files that need correction. During an authorized implementation, repair
the guidance needed to keep that implementation truthful. If required guidance
is outside the authorized edit scope, stop before shipping an incoherent
change. Never rewrite documentation merely to rationalize unexplained live
drift.

Put durable architecture, ownership, safety decisions, and supported procedures
in the appropriate manual. Put task-specific commands, revisions, validation
output, and rollout evidence in the commit, pull request, or task record. Do not
copy secrets or transient pod state into durable guidance, and prefer references
to authoritative version/configuration sources over mutable copied values.

## Operating model

```text
GitHub protected main -> Flux -> K3s
                                |-- beelink       192.168.1.3, amd64
                                `-- raspberrypi   192.168.1.2, arm64

Internet -> router -> Traefik host ports -> Gateway API -> workloads
                           `-> MetalLB VIP 192.168.1.240 for LAN access
```

- `beelink` is the only K3s server, uses the SQLite datastore, provides most
  compute and AMD GPU access, and hosts Kea DHCP.
- `raspberrypi` is an agent and the host for NFS data and LAN-facing services
  such as Blocky, WireGuard, Samba, and Syncthing.
- GitHub Actions validates; it never deploys and never SSHes to a node.
- Flux deploys only from protected `main`. Docker Compose and SWAG are retired
  and are not recovery paths.
- This is deliberately not a highly available control plane. A second server
  would not provide quorum; a supported HA redesign would require three.

Start topology, traffic, placement, storage, and trust-boundary work in
`docs/architecture.md`. Start live recovery in `docs/runbook.md`.

## Non-negotiable rules

1. **Git is normal desired state.** Do not use `kubectl apply`, `kubectl edit`,
   `kubectl set image`, Helm CLI installs, or ad-hoc Docker Compose as the
   normal change path. Flux will overwrite overlapping live drift.
2. **Root pruning is disabled.** The root Flux Kustomization has `prune: false`.
   Removing a resource from Git does not remove its live object. Some child
   Kustomizations deliberately use `prune: true`; inspect the exact owner's
   inventory and `spec.prune` rather than generalizing from the root.
3. **Never expose secrets.** Kubernetes Secrets in Git must be SOPS/age
   encrypted as `*.sops.yaml`. Never commit plaintext, an age private identity,
   decrypted temporary files, tokens, or transcript output containing values.
4. **Do not invent a replacement age identity.** If the existing identity is
   unavailable, stop. A new key cannot decrypt current repository Secrets.
5. **Git owns the cluster; applications own application state.** Git owns what
   Kubernetes needs to start, isolate, expose, protect, and observe a workload.
   UI-managed models, prompts, automations, MCP registrations, application API
   keys, libraries, and user preferences belong in backed-up application
   state. Read `docs/configuration-ownership.md` before crossing this boundary.
6. **Back up and read-test existing data before stateful change.** A Longhorn
   replica, snapshot, retained PV, bound PVC, or reachable BackupTarget is not
   an independent or restore-proven backup. A genuinely new empty PVC has no
   prior data to back up: prove that fact, protect any import source, and require
   its first independent backup and recovery test before declaring the
   initialized service complete.
7. **Images and sources are immutable.** Workload images are digest-pinned;
   ordinary references retain a human release tag as
   `repository:tag@sha256:digest`. Flux Git tags carry exact commit pins. Helm
   sources are fetched, checksummed, rendered, schema-checked, and policy
   scanned. Omnifin's tracked edge build is a deliberate digest-only exception
   enforced by its contract test; do not copy or normalize that exception
   without a reviewed release-identity change.
8. **High-risk baselines are review locks.** Never regenerate
   `scripts/ci/high-risk-baseline.txt` or the Helm baseline merely to make CI
   green. Review every added and removed finding.
9. **Privilege requires an explicit threat review.** New root, privileged,
   host-network, host-path, host-port, added-capability, broad-RBAC, Kubernetes
   API token, unsafe-sysctl, or unrestricted-ingress/egress behavior needs a
   reviewed reason and high-risk baseline change.
10. **Retirement is explicit data lifecycle work.** Deleting YAML is not a
    retirement plan. Classify every runtime object, credential, external
    integration, PVC/PV/Longhorn volume, backup, NFS path, and recovery artifact
    as retain or destroy before acting.
11. **GitHub-hosted runners only.** Never register a cluster node as a runner or
    place deployment credentials in GitHub Actions.
12. **Evidence precedes completion claims.** A render or narrow test alone does
    not prove a production change. State exactly what was and was not verified.

## Authorization boundaries

Match actions to the user's request:

- An audit, explanation, review, or diagnosis authorizes read-only inspection,
  not repository edits, live mutation, push, PR, merge, credential rotation,
  or provider changes.
- A request to change or build authorizes scoped working-tree edits and local
  validation only. Creating commits, pushing, opening or updating a pull
  request, merging, dispatching or rerunning a remote workflow, publishing an
  image or artifact, and every live, application, provider, credential, or
  destructive mutation remain separate actions.
- Read-only live checks are appropriate when they are needed to prove current
  state and cluster access is in scope. Avoid reading Secret payloads.
- A merged change may be verified live read-only. Any live mutation outside the
  normal Flux path requires explicit authorization and the documented emergency
  loop.

Do not infer one permission from another. When a filled authorization matrix
exists, it controls. If its permissions cannot produce the requested
deliverable—for example PR permission without the prerequisite commit and push
permissions—stop and resolve the conflict instead of broadening authority.

Merging to protected `main` is itself authorization for Flux to deploy that
desired state. It can also cause declared controllers to mutate external or
application systems—for example Cloudflare DDNS records and Authentik blueprint
objects. A prompt cannot coherently set `Merge: yes` while denying an inevitable
effect of the merged diff. Split review-only work from deployment, or explicitly
authorize every automatic effect before merge. Manual reconcile, restart,
bootstrap, provider cleanup, and other extra mutations remain separate.

Before a push or merge, inspect current workflow branch and path filters. A
qualifying action can run a publishing workflow, including a merge-created push
to `main`. Both the Git action and its exact workflow, registry, or artifact
effect must be authorized. If an inevitable effect is denied, use a proven
non-triggering path or stop. A manual workflow dispatch or rerun is always a
separate remote mutation.

## Start every task safely

From the repository root:

```bash
git status --short --branch
git remote -v
git fetch origin
git rev-parse --verify refs/remotes/origin/main
git log -1 --format='%H %cI %s' refs/remotes/origin/main
```

- Preserve all existing user changes. Never reset, clean, overwrite, or fold
  unrelated modifications into the task.
- If the current branch is stale, divergent, or dirty, use a dedicated worktree
  based on `origin/main` rather than forcing the current tree into shape.
- Use a `codex/` branch by default when creating a branch for Codex work.
- Read the relevant manuals and the nearest active implementation before
  editing. Copy a security and storage *shape*, not an exception.
- Identify intended authorization, desired-state owner, live owner, data owner,
  external state, rollback, and proof before making a risky change.

## Cluster and host access

There is no usable local kubeconfig. Local `kubectl kustomize` is an offline
render; all live Kubernetes API calls go through the Beelink:

```bash
ssh beelink 'sudo k3s kubectl get nodes -o wide'
ssh beelink 'sudo k3s kubectl get pods -A'
```

Use `sudo k3s kubectl`, not `sudo kubectl`. Host-level Pi work uses the `pi`
SSH alias:

```bash
ssh pi 'sudo ...'
```

Expected operator tools are `git`, `ssh`, `kubectl`, `python3` with PyYAML,
`sops`, and `jq`. CI also uses pinned `actionlint`, `yq`, `kubeconform`, Helm,
and Kubernetes schemas. The workstation age identity must already be readable
through `SOPS_AGE_KEY_FILE` or the documented default location. Verify
non-interactive SSH and sudo before a workflow that depends on them.

Never accept a first-seen host key for a new node without comparing the
Ed25519 fingerprint obtained from that host's local console.

## Repository map and desired-state ownership

```text
apps/                    workloads, routes, policies, Secrets, catalog descriptors
catalog/                 cluster/catalog inputs and versioned JSON Schemas
clusters/home-server/    root Flux reconciliation entry point
infrastructure/          platform, storage, ingress, networking, host source files
scripts/                 bootstrap, host preparation, migration, catalog, CI policy
images/                  custom reproducible image sources
docs/                    authoritative architecture and operator manuals
.github/workflows/       validation and selected image publishing workflows
renovate.json            dependency discovery, grouping, scheduling, risk labels
skills/                  task-specific agent workflows
prompts/                 reusable operator task briefs
.agents/, .omp/, and runtime instruction files
                         thin discovery adapters to canonical guidance
```

`clusters/home-server/kustomization.yaml` is the root reachability list. Follow
each referenced `kustomization.yaml`, generator, and Flux child. Directories can
contain deliberately unreferenced recovery manifests; Argilla and Duplicati are
current examples of why filenames and directory presence are not activation
evidence.

Before modifying or retiring a resource, establish all three views:

```bash
# Desired state rendered from Git.
kubectl kustomize clusters/home-server >/tmp/home-server.yaml

# Independent Flux owners and their behavior.
ssh beelink 'sudo k3s kubectl -n flux-system get kustomizations -o wide'

# Current live state.
ssh beelink 'sudo k3s kubectl get deploy,statefulset,daemonset,cronjob,job,pod,service,endpointslice,networkpolicy,pvc,httproute -A'
```

For a child Kustomization, its `.status.inventory.entries` records what it last
owned. Removing the child object can leave it live and reconciling its old path
because the root does not prune.

## Generated files and the service catalog

Each active service path needs a colocated `<service-id>.catalog.yaml` Service
descriptor or a narrow, truthful `CatalogExclusion`. The catalog is a build-time
policy compiler, not an in-cluster controller.

Use:

```bash
python3 scripts/service_catalog.py summary
python3 scripts/service_catalog.py explain SERVICE_ID
python3 scripts/service_catalog.py render
python3 scripts/service_catalog.py check --rendered /tmp/home-server.yaml
```

The compiler owns these aggregate outputs; never hand-edit their generated
regions:

- `apps/homepage/config/services.yaml`
- Cloudflare DDNS domains in `apps/cloudflare-ddns/kustomization.yaml`
- Blocky split-DNS records in `apps/blocky/config.yml`
- `apps/authentik/application-blueprints.yaml`
- `apps/authentik/generated-oidc-worker-env.yaml`

The catalog does not generate or fully prove workload mounts, routes,
NetworkPolicies, access proxies, storage, monitoring, application-side auth, or
secret values. A passing catalog check is not evidence that a descriptor's
storage narrative matches the volumes actually mounted. Cross-check the active
manifests.

## Namespace, network, and storage defaults

| Namespace | Intended use | Pod Security enforce |
| --- | --- | --- |
| `apps` | identity, home, and ordinary personal services | baseline |
| `media` | media and VPN-isolated download automation | privileged |
| `network-services` | DNS, DHCP, VPN, SMB, Syncthing, LAN protocols | privileged |
| `monitoring` | metrics, dashboards, and alerting | baseline |

All four application namespaces are default-deny. Every workload needs explicit
ingress and egress. Prefer an existing namespace; a new one needs deliberate
Pod Security labels, default-deny policies, and any required Traefik middleware
aliases.

WireGuard masquerading causes private-route allow lists to trust the Pi PodCIDR.
Treat eligibility for the Pi as a security boundary: a new Internet-facing
workload must not float there unless a reviewed threat analysis proves its
NetworkPolicy and route access cannot inherit that trust. Audiobookshelf is the
current pinned safe pattern; existing floating public workloads are review
subjects, not templates for silently accepting the risk.

| Data shape | Normal storage | Recovery meaning |
| --- | --- | --- |
| Small application state/databases | Longhorn RWO, normally two replicas | Nightly B2 block backup; app-consistency still matters |
| Organized media library | JuiceFS RWX | Encrypted B2 chunks are primary data, not an independent backup |
| Active downloads/seeding | Pi NFS | Transient/reproducible; no automatic backup |
| Syncthing file tree | Pi NFS plus Longhorn config | Dedicated encrypted Restic B2 workflow |
| Cache/stateless | `emptyDir` or no PVC | No recovery expectation |

Do not put databases in JuiceFS because it is shared. Do not assume a new NFS
path is backed up. Storage claims and descriptors must be verified against
active volume mounts because historical descriptions can lag a migration.

## Task routing

| Task | Load this skill | Start with this manual |
| --- | --- | --- |
| Orient, scope, or determine authority/ownership | `home-server-safety` | `docs/architecture.md` |
| Change agent instructions, skills, prompts, or runtime discovery | `agent-guidance` | `skills/README.md` |
| Run local/CI-equivalent validation | `validation` | `.github/workflows/validate-cluster.yml` |
| Add, modify, roll back, or retire a service | `service-lifecycle` | `docs/service-operations.md` |
| Change a catalog descriptor/compiler/profile | `service-catalog` | `docs/service-catalog.md` |
| Decide Git-owned vs application-owned state | `configuration-ownership` | `docs/configuration-ownership.md` |
| Change route, DNS, access proxy, or authentication | `network-auth` | `docs/service-operations.md` |
| Add or rotate encrypted credentials/identity | `secrets-sops` | `docs/runbook.md` |
| Change PVCs, databases, NFS, or recovery design | `storage-recovery` | `docs/service-operations.md` |
| Verify backups or perform a restore drill | `backup-restore` | `docs/runbook.md` |
| Review a high-risk baseline finding | `high-risk-review` | `scripts/ci/check-high-risk-policy.py` |
| Review Renovate, image, Flux, or Helm upgrades | `dependency-upgrades` | `renovate.json` |
| Change and publish a repository-built image | `custom-image-builds` | matching `scripts/build-*-image.sh` |
| Change or recover CYD dashboard firmware/OTA | `device-firmware` | active `apps/cyd-ota` manifests |
| Change CI, schemas, pins, or Helm render coverage | `ci-supply-chain` | `.github/workflows/validate-cluster.yml` |
| Inspect/reconcile Flux or operate the cluster | `cluster-operations` | `docs/runbook.md` |
| Add/remove a node, move workloads, or edit host config | `node-host-operations` | `docs/cluster-operations.md` |
| Diagnose an outage | `incident-response` | `docs/runbook.md` |
| Change DNS, DHCP, WireGuard, NFS, Samba, or Syncthing | `network-services` | `docs/runbook.md` |
| Operate or recover the media filesystem | `juicefs-media` | `docs/juicefs-media.md` |
| Add or change metrics, alerts, or dashboards | `observability` | `docs/runbook.md` |
| Change Open WebUI, MCPHub, Hermes, or app-owned settings | `application-state` | relevant app manual |
| Review frozen/retained recovery resources | `retained-artifacts` | relevant retention section |

If a runtime does not auto-discover repository skills, open the named
`skills/<name>/SKILL.md` explicitly. Prompts name all required skills.

## Recurring maintenance and known work

This inventory is routing, not standing authorization. Re-read the linked
source before acting because schedules, versions, and retained objects change.

- **Dependency review:** `renovate.json` is the current schedule, grouping, and
  risk-label authority. Renovate PRs are drafts and never self-approve a
  database major, Git-source commit move, stateful change, or network-critical
  change. Use `dependency-upgrades` and the matching service/platform skill.
- **Custom image refreshes:** repository-built images have separate source,
  publication, registry-digest, manifest-pin, and rollout steps. Several build
  helpers always push, and qualifying branch pushes can publish fixed tags.
  Use `custom-image-builds`; preserve the previous digest for rollback.
- **Backup evidence:** respond to freshness alerts and prove the exact affected
  volume before every stateful change. Follow the runbook's monthly Backblaze
  hidden-version/cost review and quarterly encrypted-data plus isolated-restore
  checks. A green schedule or `Completed` object is not a read test.
- **Retained data:** review each
  `home-server.reza.network/review-after` annotation as a decision trigger, not
  a deletion timer. At this revision Argilla has a dated review and Duplicati
  lacks one; use `retained-artifacts` and re-read the manifests before deciding.
- **Secrets and identities:** rotate one dependency at a time, keep the old
  credential valid through real-client proof, and revoke only with separate
  provider authority. Preserve recovery identities independently and never
  normalize a missing key by creating a new one.
- **Host drift:** Git records host inputs but Flux does not install them.
  Compare tracked and installed K3s, NFS, SSH, package, and JuiceFS policy after
  authorized host work and during planned maintenance.

`docs/cluster-operations.md` maintains the accepted-risk and follow-up list.
Highest-priority gaps include consistency-safe off-host control-plane recovery,
a state-aware K3s upgrade procedure, production Syncthing disaster recovery,
independent backup dead-man/coverage proof, application-consistent exports,
CoreDNS/audit-policy cleanup, Beelink unattended-update policy, credential
least privilege, a tested catalog/Authentik object-retirement lifecycle, and
repeated isolated restore drills. These are design tasks
until a prompt grants the additional authority needed to implement or rehearse
them; adjacent bootstrap or restore commands are not substitutes.

## Canonical GitOps change workflow

1. Define scope and authorization. Classify the change: stateless, stateful,
   identity, exposure, platform/Helm, host, node, migration, or retirement.
2. Establish the exact `origin/main`, preserve user changes, and work on a
   focused branch/worktree.
3. Read the relevant manual and inspect active desired state plus the closest
   safe existing pattern.
4. Establish rollback and, for any existing state or key-coupled change, create
   and read-test the required independent backup/export before mutation. For a
   new empty volume, prove there is no prior data, protect the import source,
   and define the post-initialization backup and restore gate.
5. Edit the smallest coherent set: manifests, descriptor, tests/policies,
   documentation, affected agent guidance, and host source files where
   applicable. Apply the guidance-maintenance contract above whenever durable
   behavior or a supported procedure changes.
6. Run `service_catalog.py render` when integration intent changes. Encrypt new
   Secrets before they touch disk history or staging.
7. Run the full local validation contract from the `validation` skill and
   inspect generated and high-risk diffs.
8. Create focused commits, push, and open or update a PR only when each action
   and its inevitable workflow effects are authorized. Never infer merge
   authority from PR authority. Merge only after the protected validation check
   is green and all deployment/controller effects are authorized.
9. Let Flux reconcile the merged `main` revision. Do not substitute manual
   apply for reconciliation.
10. Verify live at the exact merged revision: Flux readiness, rollout,
    placement, endpoints, route conditions, intended and denied access paths,
    logs for one real operation, storage health, and backup inclusion as
    applicable.

Git rollback does not reverse application database migrations, router rules,
Cloudflare records, provider credentials, OAuth clients, webhooks, Pi exports,
or other state outside Flux. Plan those reversals separately.

## Validation contract

Run from a clean task worktree after the final edit. The canonical commands and
child-render list live in `skills/validation/SKILL.md`; CI is authoritative if
it changes. At minimum, the gate includes:

- shell syntax and all Python unit tests;
- agent-guidance structure, indexes, adapters, and local links;
- source and rendered Secret validation;
- application-state ownership policy;
- root plus independently reconciled child renders;
- catalog generated-output and rendered-intent checks;
- high-risk policy against the reviewed baseline;
- Flux Git source pin validation;
- CI's strict Kubernetes schemas and independently fetched/rendered Helm
  releases.

When adding a separately reconciled child, extend both the local render bundle
and `.github/workflows/validate-cluster.yml`. When adding a HelmRelease, extend
`scripts/ci/render-helm-releases.sh` and its immutable fetch/checksum path; the
HelmRelease YAML alone is incomplete.

## Live proof and evidence

For a merged workload change, record:

- exact merged commit and Flux artifact revision;
- relevant GitRepository/Kustomization/HelmRelease `Ready=True`;
- rollout completion, pod readiness/restarts, and expected node;
- PVC binding plus actual storage/backup state if stateful;
- ready Service EndpointSlices;
- HTTPRoute `Accepted=True` and `ResolvedRefs=True`;
- success from the intended client path and denial from a forbidden path;
- a real application operation and relevant bounded logs;
- external/provider/host state changed outside Flux; and
- any check that could not be run safely.

Do not call an unmerged manifest change deployed. Do not call a backup
restore-tested because it is listed or `Completed`.

## Unsupported operations and hard stops

The manuals explicitly do not support these operations yet:

- consistency-safe Beelink replacement or off-host restoration of the K3s
  SQLite datastore plus matching server token; use
  `prompts/design-control-plane-recovery.md` for design and isolated rehearsal;
- a state-aware in-place K3s upgrade procedure; use
  `prompts/design-k3s-upgrade.md` for a version-specific design; and
- production Syncthing disaster recovery beyond the documented disposable
  restore proof; use `prompts/design-syncthing-disaster-recovery.md` to close
  the NFS, identity, backup, runtime, and fencing gaps.

Stop rather than inventing those procedures. Also do not casually normalize
the documented legacy Longhorn EngineImage references or the live-only CoreDNS
hostname selector; both are tracked deviations with specific cautions in
`docs/cluster-operations.md`.

For missing destructive storage, encryption-key, or ownership-transfer
procedures, preserve evidence and request a change-specific reviewed plan.

## Definition of done

A repository change is complete only when:

1. the active manifests, descriptor, generated output, tests, policies, and
   documentation agree, and affected manuals, repository guidance, skills,
   prompts, indexes, adapters, and examples are updated or explicitly proven
   not applicable;
2. the full applicable local validation contract passes and the diff contains
   no unexplained generated or high-risk changes;
3. any authorized PR has the required green CI result; and
4. if merged, Flux and the affected live behavior are verified at the exact
   merged revision, including state and external systems where applicable.

If any layer was unavailable, finish with a precise limitation rather than a
success claim.
