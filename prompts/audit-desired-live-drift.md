# Task brief: audit desired-versus-live drift

Compare `[SCOPE]` at exact repository and live revisions, classify every
difference by its real owner, and recommend action without treating all
non-rendered objects as drift. The audit is read-only unless independent fields
explicitly authorize a correction.

## Required inputs

- Repository, reference branch/commit, and audit timestamp: [values]
- Namespaces, services, Flux owners, hosts, or providers in scope: [exact scope]
- Whether root and all pruning child inventories are included: [yes/no and list]
- Known retained/recovery-only modules and review dates: [inventory]
- Known live deviations requiring reinspection: [facts, not accepted baselines]
- Host files/services and external/provider objects to compare: [inventory]
- Application-owned state boundaries to exclude or sample: [inventory]
- Secret comparison method that will not decrypt or disclose values: [procedure]
- Desired output and severity/confidence rubric: [report/correction proposal]
- Audit blind spots and unavailable access: [list]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact correction/report paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and required checks]
- Read-only cluster/host access: [yes/no; owners, namespaces, hosts, logs]
- Live cluster/host mutation: [yes/no; exact reconcile/suspend/correction scope]
- Application-state mutation: [yes/no; exact UI/API comparison or correction scope]
- External/provider mutation: [yes/no; exact DNS, auth, router, backup objects]
- Destructive actions: [yes/no; exact objects; normally no for an audit]

Audit authority does not permit reconciliation, annotation, restart, apply,
deletion, host reload, provider cleanup, or application-state normalization.

## Manuals and skills

Load `home-server-safety`, `cluster-operations`, `incident-response`,
`retained-artifacts`, `node-host-operations`, `network-services`,
`application-state`, `service-catalog`, `observability`, `secrets-sops`, and
`validation` as applicable. Read architecture ownership/failure domains,
cluster-operations Flux ownership/live deviations, service-operations
retirement, configuration ownership, service-catalog generation, and the
runbook. Manuals override stale annotations or remembered exceptions.

## Workflow

1. Record worktree state, exact local HEAD and reference revision. Traverse the
   root Kustomization and every referenced directory; render the root plus each
   independently validated child bundle. File presence alone does not establish
   desired state.
2. Build an owner registry: root Flux Kustomization and its non-pruning behavior;
   every child source/path/inventory/prune/decryption/dependency; HelmRelease
   generated resources; K3s-packaged Addons; host-installed configuration;
   application state; and external/provider state.
3. With read access, capture the Flux source artifact and each relevant owner's
   last-applied revision and inventory. Exact commit equality is required before
   comparing manifests; `Ready=True` alone is insufficient.
4. Inventory live objects with UID, ownerReferences, labels/annotations,
   controller, mounts, storage identity, route/endpoints, and relevant status.
   Compare canonical fields while excluding only documented API defaulting,
   controller status, and ephemeral metadata.
5. For each difference, assign exactly one primary classification:
   - active desired state owned by the root and matching or divergent;
   - active desired state owned by a pruning child and matching or divergent;
   - Helm/K3s/controller-generated state derived from its real owner;
   - root-unowned live object retained because root pruning is disabled;
   - deliberately retained recovery artifact with review/key/data dependencies;
   - stale or hand-edited generated output whose source is catalog/compiler input;
   - host-owned installed state matching or drifting from tracked host intent;
   - external/provider state, including DNS/router/auth/backup objects;
   - application-owned UI/database state, which is not expected to equal Git; or
   - unexplained/unauthorized live drift requiring investigation.
6. Treat owner transitions explicitly. Removing a child from the non-pruning
   root may leave that child reconciling its old path; do not classify its
   inventory as orphaned until the child is suspended/retired through a reviewed
   lifecycle. Do not call a root-retained object safely removable without writer,
   reference, key, and storage proof.
7. Compare catalog descriptors and compiler-generated Homepage, DNS, Authentik,
   and monitoring intent to rendered active workloads. Report hand edits as
   generated drift and fix source input only if repository edits are authorized.
8. Compare host state through checksums/effective settings and repository helper
   check modes. Compare provider and application state semantically without
   copying secrets or ordinary UI-managed settings into Git.
9. Reinspect any documented CoreDNS or Longhorn live deviation as a current
   observation. Do not promote it to desired state, delete it, or refresh the
   high-risk baseline merely because an older manual recorded it.
10. Produce a per-difference table with desired source, live identity, owner,
    prune behavior, classification, evidence, impact, confidence, and proposed
    Git/live/host/application/provider action plus required authority.
11. If corrections are separately authorized, make the smallest source-of-truth
    edit, render, run complete validation, use protected review, and verify exact
    revision. Emergency live correction requires the incident-response owner
    suspension/matching-Git/resume workflow.

## Hard stops

Stop before mutation for revision mismatch, incomplete owner inventory,
ambiguous UID/storage identity, unknown writer, encrypted value that would need
disclosure, child owner still reconciling, or a difference that belongs to host,
application, or provider state outside scope.

Do not use broad delete/apply, regenerate generated output or the high-risk
baseline blindly, normalize application UI state into Git, remove retained
Secrets/PVCs, or assume absence from the root render authorizes cleanup.

## Rollback and recovery

- Repository/generated: revert only source input through protected review and
  regenerate deterministically; do not hand-edit generated output.
- Root Flux: explicit retirement is required because a revert/removal does not
  prune live objects.
- Child Flux/Helm/K3s: preserve the owner until inventory is empty or safely
  adopted; reverse through that owner's supported path.
- Host: restore exact installed files and services separately from Git.
- Application: reverse supported UI/API changes separately; ordinary app state
  is not drift against Git.
- External/provider: reverse exact records, peers, credentials, or backups under
  separate authority.
- Storage/retained: require complete identity, writer absence, backup/read test,
  and retention decision before any irreversible correction.

## Evidence contract

Return exact repository/Flux/child/Helm revisions, rendered bundle inventory,
owner/prune registry, audit blind spots, and a per-difference table containing
Git source, live UID, owner, classification, evidence, impact, confidence,
recommended plane-specific action, and required authorization. If corrections
occur, include files/generated diffs, complete validation, exact reconciliation,
all live/host/provider/application actions, and rollback state.

## Acceptance criteria

- [ ] Repository and live comparisons use matching exact revisions and active paths.
- [ ] Root-retained, child-owned, generated, host, external, and application state
      are distinguished rather than collapsed into generic drift.
- [ ] Every finding has an owner, prune behavior, evidence, confidence, and action gate.
- [ ] Secrets and ordinary application state are not exposed or normalized into Git.
- [ ] No audit-only action mutates or deletes state.
- [ ] Authorized corrections pass full validation and exact-revision verification.
