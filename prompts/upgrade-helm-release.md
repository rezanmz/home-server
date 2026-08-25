# Task brief: upgrade an immutable Helm release

Upgrade HelmRelease `[NAME]` without weakening the repository's immutable chart,
rendering, schema, image-pin, or high-risk contracts.

## Required inputs

- HelmRelease name/namespace and active path: [values]
- Source kind/name and current immutable identity: [OCI digest or Git commit]
- Target chart release and immutable identity: [values]
- Current and proposed values: [paths/summary]
- Upstream release notes, upgrade guide, CRD and compatibility matrix: [links]
- Chart-selected images and target architectures: [inventory]
- Stateful controllers, data formats, hooks, Jobs, and downtime: [details]
- Existing renderer/checksum logic and policy baseline paths: [paths]
- Current backup/export and rollback compatibility: [evidence]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; source, HelmRelease, values, CI, baseline paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; release/CRD/state inspection]
- Live cluster/host mutation: [yes/no; reconcile/upgrade scope]
- Application-state mutation: [yes/no; exact migration/UI/API operations]
- External/provider mutation: [yes/no; registry/source actions, normally no]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; CRD/data/storage operations]

Editing a chart pin does not authorize migration Jobs, manual Helm commands,
Flux reconciliation, or storage mutation.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `dependency-upgrades`, `ci-supply-chain`,
`high-risk-review`, `service-lifecycle`, and `validation`; add `service-catalog`,
`network-auth`, `secrets-sops`, `storage-recovery`, and `backup-restore` as
required by rendered changes. Read architecture immutable-source rules,
service-operations Helm validation guidance, the affected platform/service
runbook, the current validation workflow, and the Helm rendering script.

## Workflow

1. Prove the HelmRelease and source are active and record the current source,
   chart, values, selected images, CRDs, hooks, and Flux dependencies.
2. Read all skipped upstream releases. Identify Kubernetes compatibility, CRD
   conversion/storage versions, value renames, default changes, immutable fields,
   data migrations, RBAC/security growth, and downgrade limits.
3. Pin the target using the repository's matching immutable source pattern. Do
   not replace a digest-pinned OCI artifact or exact Git commit with a mutable
   version/tag. Preserve tag-to-commit consistency where used.
4. Update values deliberately, including digest-qualified chart-selected images.
   Do not accept new chart defaults merely because they render.
5. Independently fetch/checksum/render the exact target as CI does. Diff the full
   rendered object set, CRDs, hooks, RBAC, webhooks, host access, securityContext,
   NetworkPolicies, storage, Jobs, and image references against the current render.
6. Update the renderer/checksum/pinning logic when adding a new HelmRelease; its
   YAML alone is incomplete. Explain changes to both the cluster and Helm-rendered
   high-risk review locks. Never bulk-regenerate either lock to get green.
7. Obtain state/export/backup proof before any stateful or CRD migration. Run the
   complete local validation bundle and require the protected check at the exact
   PR head.
8. If authorized, merge through Flux and observe source readiness, HelmRelease
   conditions, hooks/migrations, controller rollout, CRDs, storage, logs, and
   service-specific behavior at the exact merged revision.

## Hard stops

Stop for a mutable/moved source, unverifiable checksum, unpinned selected image,
missing architecture, unsupported Kubernetes version, destructive CRD conversion,
unplanned hook or migration, unreadable backup, unexplained high-risk expansion,
or incomplete independent rendering. For Longhorn, do not raw-patch Engine,
Replica, Volume, or same-commit EngineImage metadata to normalize the recorded
exception; wait for a supported engine upgrade path.

## Rollback and recovery

Record prior source/chart/value/image identities and the compatible data/CRD
state. Determine whether Helm/CRD migrations permit downgrade. If not, define a
tested data restore or supported forward fix. A Git revert does not undo migrated
CR storage, completed hooks, external state, or manually deleted objects.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return source identity proof, release/upgrade findings, before/after rendered
inventory and security diff, image pins/architectures, CRD/hook/state analysis,
backup evidence, both high-risk explanations, complete validation/CI results,
and exact live revision/Helm conditions when deployed.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] Chart source and selected images remain immutable and independently rendered.
- [ ] Values, CRDs, hooks, RBAC, security, storage, and migrations are reviewed.
- [ ] Recovery and downgrade/forward-fix paths are explicit.
- [ ] Full local and protected validation pass without unexplained baseline drift.
- [ ] If deployed, Flux and Helm report the exact merged revision ready and the
      affected service passes its functional acceptance.
