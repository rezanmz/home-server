# Task brief: design delegated agent action capability

Design a reviewed capability grant for the Hermes assistant so it can perform a
small, named set of operational actions, without giving it a shell, cluster-admin,
or any path to a node. The default outcome is a design, a threat model, and an
explicit authorization decision. It is not authorization to create Role bindings,
register MCP servers, or expose new endpoints in production.

This brief exists because the assistant reported being "blocked by missing tool
access" while the actual failures were configuration defects. Read the evidence
section before proposing any new privilege: the instinct to widen access was
wrong at least twice, and the design must show why a grant is necessary rather
than assumed.

## Required inputs

- Repository and exact reference revision: [path and commit]
- Agent under change (namespace, workload, current toolset and MCP group): [inventory]
- Exact actions the operator wants delegated, as verbs: [list]
- For each verb: the API or controller it drives, and its blast radius: [analysis]
- Current agent authority: capabilities, service account, mounts, NetworkPolicy: [inventory]
- Current MCPHub servers, groups, and tool filters reaching this agent: [evidence]
- The observed failures that motivate the request, with log/database evidence: [links]
- Which of those failures were capability gaps versus defects: [classification]
- Alternative solutions considered (no change, read-only widening, MCPHub tools,
  scoped verbs, shell/SSH, VPS relocation) with rejection reasons: [comparison]
- Credential model for any new integration and its rotation path: [design]
- Rollback: how the grant is revoked and how effects already made are reversed: [design]

## Authorization

Fill every line. Blank or ambiguous means no. The suggested default for live,
privileged, and external scopes is no.

- Repository edits: [yes/no; workload, RBAC, catalog, docs, guidance paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target and draft/ready]
- Merge: [yes/no; exact PR and required checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag]
- Read-only cluster/host access: [yes/no; scope]
- Live cluster mutation: [yes/no; exact rollout/RBAC-apply scope; default no]
- Host mutation: [yes/no; default no]
- Application-state mutation: [yes/no; exact MCPHub group/server records]
- External/provider mutation: [yes/no; exact scope]
- Credential or secret-material action: [yes/no; exact scope; never include values]
- New privilege, host access, RBAC, or network path: [yes/no; requires reviewed
  high-risk baseline change and an explicit threat review]
- Destructive actions: [yes/no; exact scope]

A grant that reaches a node, a kubeconfig, or a cluster-wide write role is not a
scoped action: treat it as an elevation requiring its own review, not as an
extension of this brief.

Before any push or merge, inspect the current workflow branch and path filters and
authorize every inevitable effect of that exact Git action — including any
automatic workflow run, registry publication, or artifact build it triggers. A
push that a workflow filter matches is not a passive act. If an inevitable effect
is denied, use a proven non-triggering path or stop before the triggering action.
A pull-request deliverable requires separate authority to create its commit, push
its branch, and open or update the pull request.

## Manuals, skills, and primary research

Load `home-server-safety`, `configuration-ownership`, `service-lifecycle`,
`network-auth`, `high-risk-review`, `observability`, and `validation`.

Read the repository [AGENTS.md](../AGENTS.md) non-negotiable rules (especially
rules 5, 9, and 13), [configuration ownership](../docs/configuration-ownership.md),
[personal assistant integrations](../docs/personal-assistant.md), the
[runbook](../docs/runbook.md) sections for the affected services, the
[service lifecycle manual](../docs/service-operations.md), and the
[high-risk policy script](../scripts/ci/check-high-risk-policy.py) plus its
baseline. Inspect the closest existing narrow-RBAC pattern before designing a
new one: the MCPHub observer and Homepage viewer roles are the current models for
"useful but read-only" and neither is a template for writes.

## Evidence first: classify the motivating failure

Before designing any grant, reproduce the failure the operator actually saw and
classify it. In the case that motivated this brief, the assistant reported that
a music download was blocked by missing tools. The evidence showed:

- the database and the running image disagreed, so every release was rejected by
  the application itself, not by a permission check;
- the assistant already held the tool it needed and called it successfully;
- the read-only Kubernetes MCP was fully exposed and simply never used; and
- the model failed a deferred-tool protocol repeatedly, which no permission
  change would fix.

A capability grant must not be justified by a defect. State, per requested verb,
the specific task that is impossible today and the evidence that it is
impossible rather than merely awkward. If the honest answer is "the model needs
better tool discipline", say so and route that to a model/configuration change
instead.

## Design decisions to resolve

- **Verbs, not shells.** Express the grant as a small list of named, idempotent,
  single-purpose operations (for example: restart one named workload in one
  namespace; scale one named workload within a reviewed range). A generic "run a
  command", "apply YAML", or "call any API" tool is not a scoped verb and must be
  rejected, including generic HTTP or `raw_request` escape hatches.
- **Authority boundary.** Decide whether the action goes through the Kubernetes
  API under a dedicated service account with a narrow Role, through an existing
  application API, or through MCPHub. Kubernetes API access requires a token
  mount, which the current design deliberately withholds; state the trade and the
  exact verbs, resources, and namespaces permitted.
- **Namespace and resource scope.** Prefer explicit resource names over label
  selectors, and `resourceNames` over broad verbs. List every permitted verb.
  State what a compromised agent could destroy within that scope.
- **Confirmation model.** Consequential, destructive, or user-visible actions
  require an explicit request and an immediate confirmation. Design where that
  gate lives and prove it cannot be bypassed by ordinary conversation.
- **Injection exposure.** The agent ingests untrusted content (mail, web
  research, notes). Model what an injected instruction can trigger under the
  proposed grant, and why that is acceptable or not.
- **Network and placement.** A workload that floats onto the Pi inherits the
  WireGuard masquerade trust in every private route allow-list. Decide placement
  explicitly and state whether the grant changes reachability.
- **Ownership.** Server registrations, groups, tool filters, and credentials are
  MCPHub application state. Cluster RBAC, workload, and route are Git. Do not put
  one system's setting in the other, and do not add a startup reconciler.
- **Observability.** Every granted action must be attributable: which tool, which
  operator request, which outcome, and where the record lives. MCPHub activity is
  the existing mechanism; state whether it is sufficient.
- **Revocation.** Define the exact order to withdraw the grant, and how to detect
  a lingering token, group membership, or OAuth session.

## Threat and failure model

Cover at least:

- prompt injection from ingested content triggering a permitted action;
- a permitted verb applied to the wrong object through a name collision or a
  selector that matched more than intended;
- an agent-driven restart or scale causing an availability event on a singleton
  or on the only node holding a physical service;
- RWO/PVC attachment, last-replica, or stateful-application risk from a restart;
- credential sprawl: a token that outlives its purpose, or one copied into a
  workload it was not scoped for;
- a new privileged construct, broad RBAC role, host path/network/port, token
  mount, or unrestricted egress requiring a reviewed high-risk baseline delta;
- the agent acting on stale state after a Flux change moved the target;
- an action succeeding in the cluster but failing to update the application that
  owns the state, leaving the two disagreeing; and
- error handling that reports success when the effect did not occur.

## Design workflow

1. Reproduce and classify the motivating failure as a defect or a genuine
   capability gap, with log, database, or API evidence rather than recollection.
2. Inventory the agent's current authority: toolset list per platform, MCPHub
   group and tool filters, service account, mounted tokens, capabilities, and
   NetworkPolicy ingress and egress.
3. Enumerate candidate verbs from the operator's actual requests. Prefer the
   narrowest operation that completes the task over a general one that could.
4. For each verb, identify the authority it needs, the exact objects it may
   touch, the confirmation requirement, and the blast radius if misused.
5. Compare alternatives honestly: no change, read-only surface widening, an
   existing MCPHub tool, a new scoped verb, a shell or SSH grant, and relocating
   the agent off-cluster. Reject each on stated grounds rather than by omission.
6. Decide where the capability lives — MCPHub registration, a new MCP server, or
   a Kubernetes API path — and justify the choice against the ownership boundary.
7. Model prompt injection against the proposed grant and state the residual risk
   the operator is accepting.
8. Determine whether any part of the design moves a high-risk boundary, and
   itemize the baseline delta for review if so.
9. Define the attribution record, the revocation order, and how to detect a
   lingering credential after revocation.
10. State what remains impossible under the design, so the operator knows the
    grant's limits before approving it.

## Hard stops and abort gates

Stop and report rather than designing further when:

- the motivating failure cannot be reproduced, or classifies as a defect that a
  grant would not fix;
- a requested verb requires a shell, arbitrary command execution, arbitrary YAML
  application, or a generic HTTP escape hatch to satisfy it;
- the design would grant cluster-wide write, node access, a kubeconfig, or a
  host path, mount, port, or network namespace;
- the required scope cannot be expressed with explicit resource names and
  bounded verbs;
- the confirmation requirement cannot be enforced outside ordinary conversation;
- ownership would be violated by placing an application setting in Git or a
  cluster setting in application state;
- the action cannot be attributed, or a granted credential cannot be revoked;
- the blast radius of a permitted verb includes a singleton, a physical service
  node, or the last healthy replica without an accepted-availability decision; or
- the operator expects a broad capability and the honest design is narrow.

Do not implement the grant under this brief. Do not create Role bindings,
register MCP servers, mount tokens, or change NetworkPolicy as part of a design
task.

## Rollback and recovery

- Design/repository: revert the design through protected review; leave the
  running agent's authority untouched until an implementation is separately
  authorized.
- Authorization: withdraw a granted verb in the reverse order it was added,
  confirming each layer (MCPHub group or server record, then any RBAC object or
  token projection) before removing the next.
- Credentials: revoke the exact token or bearer key, then verify it is refused;
  delete any projected secret or mounted file and confirm the workload no longer
  reads it.
- Effects already made: a grant cannot be un-applied. Record what the agent
  changed and reverse it through the owning system's supported interface, not by
  a Git revert, which does not reverse application or provider state.
- Application state: the MCPHub database is authoritative; restore it or use its
  UI rather than editing manifests to reconstruct a group.
- Baseline: if the grant required a high-risk baseline entry, removing the grant
  also removes that finding; review the resulting delta rather than assuming it.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return the agent identity and current-revision inventory, the failure
classification with its evidence, the verb table with per-verb authority, scope,
confirmation, and blast radius, the alternative comparison, the injection model
and residual risk, the ownership decision, the attribution record, the revocation
order, any high-risk baseline delta itemized for review, the validation result,
and an explicit statement of the capability and non-applicability that remains
outside the design. Report anything not verified. Never expose credential values.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] The motivating failure is reproduced and classified as defect or gap, with evidence.
- [ ] Each requested verb names a specific task that is impossible today and why.
- [ ] No generic shell, arbitrary-API, or YAML-apply capability is introduced.
- [ ] Authority, scope, and confirmation gate are explicit, with a blast-radius table.
- [ ] Prompt-injection exposure is modeled for every permitted action.
- [ ] Placement and network reachability consequences are stated.
- [ ] Ownership follows the Git-versus-application-state boundary.
- [ ] Every action is attributable in an existing observability surface.
- [ ] Revocation and reversal are defined, including lingering credentials.
- [ ] Any high-risk baseline delta is itemized for review, or non-applicability is proven.
- [ ] Alternatives (no change, read-only widening, VPS relocation) are compared and rejected on stated grounds.
