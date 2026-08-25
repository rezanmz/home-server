# Task brief: [short outcome]

Work in the home-server GitOps repository. Treat Git changes as proposed changes
to a live production cluster. Do not infer authority from the requested outcome.

## Outcome

[State one observable result. Separate investigation, implementation, deployment,
and external-system work.]

## Required inputs

- Repository and base revision: [path/repository and exact branch or commit]
- In-scope component/object identities: [namespaces, resource names, paths]
- Current behavior and desired behavior: [facts, not assumptions]
- Known dependencies and external systems: [list]
- State, storage, and recovery implications: [list or none with evidence]
- User-visible or security implications: [list]
- Constraints and maintenance window: [list]
- Upstream references or issue/PR: [links or none]

If an input needed for a safe decision is missing, discover it read-only when
authorized or stop and ask. Never ask for a plaintext secret in this prompt.

## Authorization

Fill every line with `yes` or `no` and an exact scope. Blank or ambiguous means
no. Permission does not cascade from one line to another.

- Repository edits: [yes/no; exact paths or change class]
- Create commits: [yes/no; commit scope]
- Push a branch: [yes/no; remote and branch]
- Open or update a pull request: [yes/no; target and draft/ready state]
- Merge: [yes/no; exact pull request and required checks]
- Read-only cluster/host access: [yes/no; commands/targets]
- Live cluster/host mutation: [yes/no; exact resources and allowed operations]
- Application-state mutation: [yes/no; exact UI/API objects and operations]
- External/provider mutation: [yes/no; exact provider objects and operations]
- Destructive actions: [yes/no; exact identities and retain/destroy decision]

Do not use direct `kubectl apply`, `edit`, or `set image` as the normal change
path. Do not push, merge, reconcile, restart, revoke, delete, or modify an
external system unless the matching line explicitly authorizes it.

If `Merge` is yes, enumerate the automatic effects of the exact diff: Flux will
deploy it, and reconciled workloads may update Authentik, Cloudflare, or another
managed system. Merge cannot be yes while an inevitable effect is denied.
Manual reconcile/restart and later cleanup remain separate operations.

## Manuals and skills

First load skill `home-server-safety`. Add the task-specific skills from:

- `service-lifecycle`
- `service-catalog`
- `configuration-ownership`
- `application-state`
- `network-auth`
- `network-services`
- `secrets-sops`
- `validation`
- `observability`
- `incident-response`
- `cluster-operations`
- `node-host-operations`
- `storage-recovery`
- `backup-restore`
- `juicefs-media`
- `dependency-upgrades`
- `custom-image-builds`
- `device-firmware`
- `high-risk-review`
- `ci-supply-chain`
- `retained-artifacts`

Read the task-specific manual named in `AGENTS.md`. At minimum, route among the
architecture, service-catalog, catalog-design, configuration-ownership,
service-operations, cluster-operations, application-specific, JuiceFS, and
runbook manuals. Manuals override shortcuts; flag drift instead of guessing.

## Workflow

1. Record the exact revision and worktree state. Preserve unrelated changes.
2. Traverse Kustomizations to prove which files are active and identify the
   Flux, host, application, or external owner.
3. Establish current state using repository evidence and only the read-only live
   access authorized above.
4. Present material assumptions, safety gates, and the smallest viable plan.
5. Make only authorized edits or mutations. Update colocated catalog intent and
   generated output when applicable; never hand-edit generated regions.
6. Run the complete validation bundle after the final repository edit. Treat
   catalog semantic claims, Helm rendering, secret safety, source pins, and
   high-risk findings as independent gates.
7. Use the protected branch/PR/Flux path only to the extent authorized.
8. Verify the exact merged revision and task-specific live behavior when live
   verification is authorized. Otherwise state that deployment is unverified.

## Hard stops

Stop before proceeding when:

- the active owner, exact object identity, or requested authority is ambiguous;
- a secret or private recovery identity would be disclosed;
- a stateful/destructive change lacks an independent backup and content read test;
- an immutable source, digest, architecture, or upstream migration contract
  cannot be verified;
- a privileged, host-level, broad-RBAC, or unrestricted-network change lacks
  explicit review and an explained high-risk baseline delta;
- the operation depends on an unsupported control-plane restore, replacement,
  upgrade, or application disaster-recovery procedure;
- required validation fails or only a narrowed subset can run.

Report the blocker and the minimum safe next decision. Do not improvise around a
hard stop.

## Rollback and recovery

[Name the exact prior Git state, immutable artifacts, data/export/backup recovery
point, external/provider reversal, and stop conditions. Explain migrations that
make a simple Git revert unsafe. Root pruning is disabled, so list any live
objects that a revert would leave behind.]

## Evidence contract

Return:

- exact Git revision and worktree status inspected;
- active ownership path and current-state evidence;
- changed and generated file inventory;
- validation commands and results, with every skipped check explained;
- high-risk, secret, image/source, storage, and catalog semantic evidence as
  applicable;
- every live or external action taken, with exact non-secret identities;
- reconciled revision and live acceptance evidence when deployed;
- rollback readiness, retained artifacts, unresolved drift, and remaining work.

## Acceptance criteria

- [ ] The requested outcome is met within the authorization matrix.
- [ ] Desired state, catalog intent, generated output, and ownership agree.
- [ ] Full applicable validation passes on the final tree.
- [ ] No plaintext secret or unreviewed high-risk construct is introduced.
- [ ] Stateful and destructive gates have current recovery evidence.
- [ ] Deployment is verified at the exact merged revision, or clearly reported
      as outside scope/unverified.
- [ ] Rollback and any external or retained state are explicit.
