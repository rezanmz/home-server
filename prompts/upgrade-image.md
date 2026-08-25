# Task brief: upgrade a workload image

Upgrade one digest-pinned workload image and preserve a tested rollback reference.
Treat an image update that changes data format, privileges, ports, or defaults as
a service migration rather than a mechanical pin bump.

## Required inputs

- Service, namespace, controller/container, and active manifest: [values]
- Current full reference: [repository[:tag]@sha256:digest]
- Target upstream release/tag and candidate digest: [values]
- Release notes, security advisory, and upstream provenance: [links]
- Required target architectures and placement: [values]
- Image variant/flavor that must remain fixed: [value or none]
- Data/config schema changes and downgrade compatibility: [details]
- Current application export and independent backup: [if stateful/migrating]
- Representative functional check: [operation]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact image/descriptor/docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; current architecture/state checks]
- Live cluster/host mutation: [yes/no; reconcile/rollout scope]
- Application-state mutation: [yes/no; exact migration/UI/API operations]
- External/provider mutation: [yes/no; registry actions, normally no]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; exact state/data action, normally no]

Do not push, merge, reconcile, rebuild, publish, or mutate application data unless
that separate permission is explicit.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `dependency-upgrades`, `ci-supply-chain`,
`service-lifecycle`, and `validation`; load `service-catalog` when descriptor
image/placement/operational facts change. Read the image/config and migration
sections of service-operations, architecture pinning rules, the service runbook,
and cluster-operations for architecture/placement concerns.

## Workflow

1. Prove the manifest is active and record the exact current full reference.
   Preserve it verbatim as the rollback artifact.
2. Read upstream release notes across every skipped release. Identify data/schema
   migrations, changed defaults, ports, users, permissions, health paths,
   architectures, deprecations, and known downgrade limits.
3. Resolve the target tag to an immutable digest through an authoritative
   registry view. Verify the manifest list contains every required architecture
   and that the tag/variant matches the intended release channel. Never replace
   a tag-qualified reference with tag-only or digest-only ambiguity.
4. Inspect adjacent configuration, probes, resources, securityContext,
   NetworkPolicy, PVCs, and catalog claims for required coordinated changes.
5. For stateful or format-changing updates, require a readable application export
   and current independent backup before rollout. Document whether old code can
   read post-migration data.
6. Change the smallest set of manifests, preserving the service's reviewed
   immutable form. Ordinary images remain `repository:tag@digest`. Do not combine
   an unrelated digest refresh with a feature/version update.
7. Render catalog output if relevant and run the complete local validation
   bundle. Review source-pin, schema, secret, Helm-render, and high-risk results.
8. If authorized, use protected review and Flux. At the exact merged revision,
   check pulls, architecture, rollout, restarts, probes, logs, one representative
   operation, state integrity, and backup inclusion.

## Hard stops

Stop if the digest cannot be independently resolved, the target is missing a
required architecture, the tag changed variant/channel unexpectedly, release
notes or license/provenance are unavailable, data migration lacks recovery,
security posture broadens without review, a database major/channel change lacks
an explicit migration, validation fails, or live rollout authority is absent.

## Rollback and recovery

Record the prior full image reference and Git revision. A Git revert is allowed
only when the old binary can safely read current state. Otherwise define the
matching pre-upgrade export/backup restore or a supported forward fix. Include
configuration, Secret, and external API changes that must reverse with the image.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return current/target full references, authoritative digest evidence, manifest
architectures, release-note and migration findings, changed files, recovery
proof, complete validation/CI results, and the exact reconciled revision plus
functional/log evidence if deployed. State whether rollback remains data-safe.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] The target remains tag-and-digest pinned and supports required architectures.
- [ ] Release, configuration, security, and migration impacts are accounted for.
- [ ] Stateful rollout has current readable recovery and a valid downgrade plan.
- [ ] Full applicable validation and protected checks pass.
- [ ] If deployed, the exact merged revision passes rollout and representative
      service behavior without unexplained restarts or data loss.
