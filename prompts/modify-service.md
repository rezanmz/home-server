# Task brief: modify a service

Change an existing service while preserving its ownership, access, data, and
rollback contracts. Use a narrower prompt instead when the primary task is an
image, Helm, route/auth, secret, storage, or application-state change.

## Required inputs

- Service ID, namespace, and active manifest path: [values]
- Current behavior and exact desired behavior: [facts]
- Requested change class: [runtime/config/network/storage/auth/observability]
- Current and target immutable sources: [if applicable]
- Data/schema/config migration: [none or documented sequence]
- Expected downtime and maintenance window: [values]
- Dependent services, clients, and provider objects: [list]
- Current recovery point and restore test: [identity/time/evidence, no secrets]
- Success signal and representative operation: [observable checks]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact paths/change class]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; resources/hosts]
- Live cluster/host mutation: [yes/no; exact reconcile/restart/migration scope]
- Application-state mutation: [yes/no; exact UI/API objects and operations]
- External/provider mutation: [yes/no; exact objects]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; exact data/resources]

An implementation request does not authorize merge, live rollout, UI mutation,
provider changes, or deletion.
If merge is authorized, it necessarily authorizes Flux and the declared
controller effects of that exact diff; manual reconcile/restart and unrelated
provider work remain separate.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `service-lifecycle`, `configuration-ownership`,
`service-catalog`, and `validation`; also load `network-auth` or `secrets-sops`
when relevant, plus `storage-recovery`, `backup-restore`, or `high-risk-review`
when their gates apply. Load `application-state`, `network-services`, or
`observability` when the change is in those domains. Read service-operations and
the service-specific runbook/manual. Route placement to cluster-operations,
cross-service intent to service-catalog, and ownership questions to
configuration-ownership.

## Workflow

1. Establish the exact revision, active Kustomization path, Flux owner, live
   revision when read access is allowed, and existing drift. Preserve unrelated
   worktree changes.
2. Map the requested setting to Git, application state, host input, or an
   external provider. Do not move application-owned UI settings into a recurring
   Git reconciler.
3. Identify coupled surfaces: descriptor/generated integrations, routes/DNS/auth,
   NetworkPolicy, Secrets, image architectures, storage, backup, placement,
   monitoring, and external objects.
4. For stateful or format-changing work, obtain an application export plus the
   exact independent volume backup and read-test evidence before implementation.
5. Make the smallest Git change. Preserve stable service, OIDC, PVC, and provider
   identities unless the task explicitly defines a migration.
6. Render the catalog when intent changes; inspect generated output and verify
   descriptor claims against actual mounts, storage classes, placement, and
   backup objects.
7. Run the complete validation bundle after the final edit. Treat every added,
   removed, or changed high-risk finding, source-pin failure, secret failure, or
   Helm-render delta as a blocking review decision.
8. If rollout is authorized, verify the exact merged revision and observe the
   migration/rollout, endpoints, access, logs, state integrity, and backup status.

## Hard stops

Stop if the active owner is unclear, a stable identity would change without a
migration, a stateful change lacks independent readable recovery, a data schema
makes the proposed binary rollback unsafe, the requested config is application-
owned, the image/source is mutable, the security boundary broadens without
review, validation fails, or required live/provider authority is absent.

## Rollback and recovery

Name the exact prior Git revision and immutable artifact. Explain whether the old
binary can read current data, which export/backup matches it, and how external or
application-state changes reverse. Account for root-prune-disabled leftovers,
stale generated ConfigMaps, immutable PVC/StatefulSet fields, and credentials
that a Git revert cannot un-revoke.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return the ownership map, before/after behavior, changed/generated files,
migration and recovery proof, catalog semantic checks, complete validation and
CI results, high-risk explanation, exact live/external actions, and the exact
reconciled revision plus functional evidence when deployed. List any check that
was not authorized or could not run.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] The requested behavior changes without taking ownership of unrelated state.
- [ ] Stable identities and recovery prerequisites are preserved or migrated
      explicitly.
- [ ] Manifests, descriptor, generated output, and real storage/network semantics
      agree.
- [ ] Full applicable validation passes on the final revision.
- [ ] Deployment and functional proof are complete if authorized; otherwise
      their absence is explicit.
- [ ] A credible rollback or recovery path is recorded.
