---
name: home-server-safety
description: Safely orient, scope, and perform work in this production K3s GitOps repository. Use before changing manifests, inspecting the live cluster, applying host configuration, or planning a destructive operation.
---

# Home server safety

Treat this repository as the desired state of a live production cluster. Use this
skill to establish authority, ownership, and safe boundaries before doing the
task. It does not by itself authorize a merge, live mutation, provider change,
credential revocation, or data deletion.

## Read the right authority

Start at the repository root and read:

- AGENTS.md for repository-wide rules and the current documentation index.
- README.md for the entry-point topology and validation workflow.
- docs/architecture.md for traffic, placement, storage, and security boundaries.
- The task-specific manual named in AGENTS.md before taking task actions.

For service work, also read docs/service-operations.md. For node or host work,
read docs/cluster-operations.md. For incidents, read docs/runbook.md. For a
setting whose owner is unclear, read docs/configuration-ownership.md.

Do not infer desired state from a file merely because it exists. Follow
clusters/home-server/kustomization.yaml and each referenced kustomization.yaml.
Unreferenced manifests may be frozen recovery material. Treat a conflict between
an active manifest and prose as a documentation defect to flag, not permission
to guess or silently make them match.

## Establish the operating plane

Identify which plane owns the requested object before proposing a change:

| Plane | Normal change path |
| --- | --- |
| Root Flux tree | Git branch, protected pull request, then Flux; root pruning is disabled |
| Flux child Kustomization | Git plus that child's explicit prune, dependency, decryption, and inventory contract |
| K3s packaged component | Repository-owned host/K3s input and its documented application procedure |
| Node or Pi host file | Repository input applied with its drift-checking helper over SSH |
| Application-owned state | The application's supported UI or API and its persistent backup |
| Router, Cloudflare, OAuth provider, or other external system | A separately authorized provider operation |

Never assume removal from Git deletes a live object. Inspect the owning Flux
Kustomization and its status inventory. The root owner has prune disabled.
Selected backup/readiness children use prune; others deliberately do not. Merely
removing a child from the root can leave the live child reconciling its old path.

## Safe discovery

Keep discovery read-only. Useful starting points are:

    git status --short --branch
    git fetch origin main
    git rev-parse HEAD
    git rev-parse origin/main
    kubectl kustomize clusters/home-server >/tmp/home-server.yaml
    ssh beelink 'sudo k3s kubectl get nodes -o wide'
    ssh beelink 'sudo k3s kubectl get pods -A -o wide'
    ssh beelink 'sudo k3s kubectl -n flux-system get gitrepositories,kustomizations -o wide'

There is no usable local kubeconfig. Run live Kubernetes commands through the
Beelink with sudo k3s kubectl. Do not revive Docker Compose or SWAG as a fallback.

Preserve unrelated worktree changes. Resolve the exact active resources and
identities before any deletion, overwrite, ownership transfer, or storage
operation.

## Decision and authorization gates

- A request to review, diagnose, or explain authorizes read-only inspection, not
  implementation or live repair.
- A request to edit Git authorizes repository changes in scope, not pushing,
  merging, reconciling, applying host files, or mutating external providers.
- A request to deploy through the normal workflow authorizes the documented
  Git/PR/Flux path, not direct kubectl apply, edit, or set image.
- Merging to protected `main` necessarily authorizes Flux to deploy the exact
  diff and any declared controller effects, such as Authentik blueprint or
  Cloudflare DDNS updates. Do not merge while denying an inevitable effect of
  that diff. Manual reconcile, restart, bootstrap, and cleanup remain separate.
- Temporary live recovery is exceptional: suspend the relevant Flux owner,
  make the minimum authorized change, land matching desired state, verify the
  exact revision, resume, and prove that no unexplained drift remains.
- Any operation that changes existing PVC data, a database, encryption key,
  storage layout, or retirement state requires an independent backup and a
  content read test before mutation. A proven new empty PVC is the exception:
  protect its import source and require the first independent backup and
  recovery test after initialization, before completion.
- A new privileged mode, host network/path/port, capability, broad RBAC,
  service-account token, unsafe sysctl, or unrestricted network path requires a
  reviewed high-risk-policy change. Never regenerate that baseline merely to
  make a check pass.
- Never print or commit plaintext secrets or an age private identity.

Stop and report rather than improvise when the documented prerequisites,
identity chain, backup evidence, or authorization are missing.

## Explicitly unsupported shortcuts

The current manuals do not provide a tested routine for Beelink control-plane
replacement, consistency-safe off-host restoration of the K3s SQLite datastore
and matching server token, or a state-aware K3s upgrade. Production Syncthing
disaster recovery is also not established merely by its disposable restore
proof. Do not turn agent-node, fresh-host, or isolated-test procedures into
those operations.

Do not raw-patch Longhorn Engine, Replica, Volume, or same-commit EngineImage
metadata to normalize the recorded live exception. Do not treat the live-only
CoreDNS selector as intended state without the investigation required by
docs/cluster-operations.md.

## Evidence before completion

Report:

- the exact Git revision and worktree state inspected;
- the active Kustomization path and Flux owner;
- files changed and generated output reviewed;
- validation results and any skipped check;
- whether any live, host, application, or external state was changed;
- for a deployed change, the exact reconciled revision and task-specific live
  acceptance evidence;
- unresolved drift, unsupported operations, and rollback or recovery
  prerequisites.

Do not claim deployment success from a render, compile, narrowed test, or
plausible manifest alone.
