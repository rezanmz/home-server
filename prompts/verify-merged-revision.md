# Task brief: verify an exact merged revision

Prove that Flux and the affected live services reached merge commit `[SHA]` and
that the requested production behavior is ready. Do not report “deployed” from a
green pull request, local render, or newer unrelated cluster revision.

## Required inputs

- Exact merged commit SHA and pull request: [values]
- Affected root and child Kustomizations/HelmReleases: [inventory]
- Affected namespaces/controllers/services/routes/PVCs: [inventory]
- Expected image/source identities and placement: [values]
- Intended client networks and auth paths: [public/LAN/WireGuard/mobile/etc.]
- Stateful/backup checks: [required stores and policy]
- Representative operation and expected result: [check]
- Allowed wait window: [duration/stop time]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; normally no]
- Create commits: [yes/no; normally no]
- Push a branch: [yes/no; normally no]
- Open or update a pull request: [yes/no; reporting/follow-up only]
- Merge: [yes/no; normally already merged]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; exact scope]
- Live cluster/host mutation: [yes/no; reconcile annotation/restart scope]
- Application-state mutation: [yes/no; representative read/write operation scope]
- External/provider mutation: [yes/no; normally no]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; normally no]

Waiting and observation do not authorize an immediate reconcile, restart, patch,
or rollback. If the cluster has advanced past the target commit, report that the
exact target was not directly observed and verify the currently reconciled state
only if that satisfies the requested evidence.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety` and `validation`; add `service-lifecycle`,
`network-auth`, `storage-recovery`, `backup-restore`, and the affected service
skill/manual as needed. Read service-operations deployment proof, runbook Flux and
service checks, architecture traffic/storage boundaries, and cluster-operations
for root/child ownership.

## Workflow

1. Verify the requested SHA is the actual protected-branch merge result and map
   its changed files to active root and separately reconciled child owners.
2. Through authorized read-only access, inspect Flux GitRepository artifact
   revision and relevant Kustomization/HelmRelease conditions, observed revisions,
   dependencies, inventories, and events. Require the exact target revision; do
   not infer it from object age or a successful GitHub check.
3. If reconciliation has not reached the commit, wait within the allowed window.
   Triggering reconciliation requires live mutation authority and should not hide
   a controller/source failure.
4. Check affected controller generation/rollout, desired/ready replicas, pod
   digest, placement, restarts, probes, and recent events/logs.
5. Check exact Service endpoints and HTTPRoute `Accepted=True` and
   `ResolvedRefs=True`. Verify DNS, certificate, proxy/auth, and both success and
   expected denial from applicable intended/forbidden client networks.
6. Check PVC binding, actual mounts, Longhorn/NFS/JuiceFS health, state integrity,
   and backup inclusion for stateful changes. Catalog declarations alone are not
   live storage evidence.
7. Exercise one representative application operation and inspect logs around it.
   Verify migrations, callbacks, roles, or provider processing relevant to the
   merged change.
8. Return pass/fail per affected component. Do not mutate to fix failures unless a
   separate scope authorizes the recovery.

## Hard stops

Do not claim exact-revision deployment when Flux reports another commit, a child
has not reconciled, required objects are owned by an omitted child, or the target
was skipped by a newer revision. Stop on degraded storage, failed migration,
empty endpoints, rejected/unresolved route, image mismatch, access-control
regression, missing backup, or unavailable required client path.

## Rollback and recovery

Verification itself is read-only. For a failure, identify the last known-good Git
and immutable artifact plus state/external compatibility; recommend protected
revert or forward fix. Do not execute it without repository/merge/live authority,
and do not recommend an image revert across incompatible migrated data.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return requested SHA, observed Flux source/root/child/Helm revisions and
conditions, controller/image/placement state, endpoints/routes/DNS/auth results,
storage/backup state, representative-operation/log evidence, elapsed wait, every
untested path, and a component-level verdict. Include no secret values.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] The exact merged SHA is evidenced through every relevant Flux owner.
- [ ] Workload image, rollout, placement, endpoints, routes, and policies are ready.
- [ ] Intended clients succeed and forbidden paths fail where applicable.
- [ ] Stateful services have healthy storage and confirmed backup inclusion.
- [ ] A representative operation works, or the report clearly identifies the
      failed gate without an unauthorized repair.
