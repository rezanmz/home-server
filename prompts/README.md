# Home-server task prompts

These files are copy/paste task briefs for an agent working on this repository.
They do not grant authority. Fill every bracketed field before use; an empty,
ambiguous, or omitted authorization field means **no** for that action.
Keep the checked-in canonical briefs unfilled: a literal `yes` in this directory
would encode standing authority instead of task-specific permission.

Start every task from a clean understanding of the current repository rather
than from remembered cluster state. The prompt tells the agent which repository
skills and manuals to load. Skills are workflow shortcuts; the manuals remain
authoritative when they disagree. Agents that do not support skill invocation
should open the named `skills/<directory>/SKILL.md` file directly.

The canonical prompts stay in this directory so their relative links resolve
consistently. An `@file` reference attaches a file unchanged; trailing prose
does not fill its placeholders. For Oh My Pi, copy the selected brief to a
temporary file outside the repository, replace every required input and
authorization placeholder in that task copy, then start from the repository
root with `omp @/absolute/path/to/filled-brief.md`. Do not commit the filled
copy, put secret values in it, or copy/symlink the canonical prompt tree into a
runtime-specific directory.

Use the smallest prompt that fits the task. Add concrete identities, paths,
desired outcomes, rollback prerequisites, and known constraints. Do not put
passwords, tokens, private age identities, or other secret values in a prompt.

## Authorization model

Every prompt separates these permissions; specialized briefs subdivide a plane
further when one action has a distinct side effect:

- repository edits;
- commit creation;
- pushing a branch;
- opening or updating a pull request;
- merging;
- remote workflow dispatch or rerun;
- registry or artifact publication;
- read-only cluster or host inspection;
- live cluster or host mutation;
- application-state mutation;
- external/provider mutation;
- credential or secret-material access, creation, rotation, or revocation; and
- destructive actions.

Permission for one does not imply another. In particular, permission to edit
Git does not permit a merge or live reconciliation, read-only cluster access
does not permit a restart, and service retirement does not implicitly permit
PVC, backup, credential, DNS, or provider deletion.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable workflow,
registry, or artifact-publication effect. If such an effect is denied, use a
proven non-triggering path or stop before the triggering action.

One dependency is unavoidable: merging to protected `main` causes Flux to
deploy the merged desired state. A diff may then make declared controllers
change Authentik objects, Cloudflare records, or other managed systems. Do not
fill `Merge: yes` while denying an automatic effect inherent in that exact
diff. Keep the task review-only, or explicitly authorize the deployment and
controller-managed effects. Manual reconcile/restart and later provider cleanup
remain separate permissions.

## Prompt index

### Agent guidance and repository governance

| Prompt | Use it for |
| --- | --- |
| [maintain-agent-guidance.md](maintain-agent-guidance.md) | Updating canonical instructions, skills, prompts, discovery adapters, indexes, and their structural validation |

### Service and configuration lifecycle

| Prompt | Use it for |
| --- | --- |
| [task-template.md](task-template.md) | Drafting a new repository-specific brief with the same safety contract |
| [add-service.md](add-service.md) | Adding a new Kubernetes application or service |
| [modify-service.md](modify-service.md) | Changing an existing service without using a narrower prompt |
| [retire-service.md](retire-service.md) | Removing runtime service intent while making explicit retain/destroy decisions |
| [change-route-or-auth.md](change-route-or-auth.md) | Changing DNS, Gateway exposure, NetworkPolicy, OIDC, or forward-auth |
| [change-storage.md](change-storage.md) | Resizing, migrating, reclassifying, or otherwise changing application storage |
| [rotate-secret-or-oidc.md](rotate-secret-or-oidc.md) | Rotating a Secret, token, OIDC client, or coordinated provider/application credential |
| [change-application-state.md](change-application-state.md) | Changing UI/API-owned application configuration rather than Git-owned state |
| [evolve-service-catalog.md](evolve-service-catalog.md) | Extending catalog schema, versioned adapters, compiler behavior, or generated output |
| [review-retained-artifacts.md](review-retained-artifacts.md) | Auditing recovery-only, orphaned, excluded, or deliberately retained objects |

### Dependencies, images, and physical firmware

| Prompt | Use it for |
| --- | --- |
| [upgrade-image.md](upgrade-image.md) | Updating a digest-pinned workload image |
| [review-renovate-pr.md](review-renovate-pr.md) | Reviewing an automated dependency pull request |
| [upgrade-helm-release.md](upgrade-helm-release.md) | Updating an immutable Helm chart source, values, and rendered policy surface |
| [publish-custom-image.md](publish-custom-image.md) | Building and publishing a repository-owned reproducible image |
| [change-cyd-dashboard.md](change-cyd-dashboard.md) | Changing, building, publishing, and physically accepting CYD firmware on both devices |
| [operate-cyd-ota.md](operate-cyd-ota.md) | Diagnosing, retrying, pausing, or recovering a partial CYD OTA rollout |

### Cluster, node, host, and network operations

| Prompt | Use it for |
| --- | --- |
| [add-agent-node.md](add-agent-node.md) | Preparing and safely admitting a fresh K3s agent |
| [remove-agent-node.md](remove-agent-node.md) | Permanently evacuating and removing an agent without pretending to replace the control plane |
| [move-workload.md](move-workload.md) | Moving or repinning a workload across architecture, storage, and physical dependencies |
| [planned-node-maintenance.md](planned-node-maintenance.md) | Cordon, drain, reboot, or other bounded node maintenance |
| [change-host-configuration.md](change-host-configuration.md) | Changing tracked K3s, NFS, SSH, package, or JuiceFS host policy and applying it separately |
| [change-network-service.md](change-network-service.md) | Changing Blocky, Kea, Stork, WireGuard, Samba, Syncthing, or Pi NFS behavior |

### Verification, recovery, and incidents

| Prompt | Use it for |
| --- | --- |
| [verify-backups.md](verify-backups.md) | Proving backup inclusion, freshness, readability, and restore prerequisites |
| [restore-drill.md](restore-drill.md) | Rehearsing an isolated restore without writing over production |
| [juicefs-operation.md](juicefs-operation.md) | Operating JuiceFS metadata, B2 chunks, FUSE mounts, caches, credentials, quota, or migrations |
| [investigate-outage.md](investigate-outage.md) | Diagnosing an outage without silently expanding into repair |
| [verify-merged-revision.md](verify-merged-revision.md) | Proving Flux and the live cluster reached an exact merged revision |
| [audit-desired-live-drift.md](audit-desired-live-drift.md) | Classifying desired/live differences by root retention, child inventory, host, application, and provider ownership |
| [add-observability.md](add-observability.md) | Adding truthful metrics, alerts, dashboards, and notification evidence |
| [review-high-risk-baseline.md](review-high-risk-baseline.md) | Explaining and, when authorized, narrowly refreshing a high-risk review lock |

### Unsupported recovery and upgrade design

These briefs produce reviewed designs and isolated rehearsal evidence. They do
not authorize production execution, and the capability stays unsupported until
the brief's acceptance evidence exists.

| Prompt | Use it for |
| --- | --- |
| [design-control-plane-recovery.md](design-control-plane-recovery.md) | Designing matched SQLite/server-token, encrypted off-host, bare-metal control-plane recovery |
| [design-k3s-upgrade.md](design-k3s-upgrade.md) | Designing a version-specific, state-aware K3s upgrade and rollback procedure |
| [design-syncthing-disaster-recovery.md](design-syncthing-disaster-recovery.md) | Designing joint NFS data, Syncthing identity/configuration, Restic, and network recovery |

## Maintaining prompts

When durable repository behavior changes, update its authoritative manual first
or in the same change, then review `AGENTS.md`, the routed skill, every affected
specialized brief, this index, and the generic task template. A new, renamed, or
retired prompt must be reflected in this index and pass
`scripts/ci/validate-agent-guidance.py`; change the validator itself only when
the structural contract changes. Do not leave an unindexed file for a runtime
to discover accidentally.

Each reusable brief must remain self-contained: required inputs, all applicable
authorization planes, commit/push/PR dependencies, automatic workflow or
publication effects, routed skills/manuals, hard stops, rollback, falsifiable
evidence, and an acceptance check for durable documentation and agent guidance.
Run the guidance validator and the complete repository validation bundle after
the final edit. During a read-only task, report prompt drift instead of editing
it.
