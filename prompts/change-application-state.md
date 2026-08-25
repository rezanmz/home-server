# Task brief: change application-owned state

Change `[SETTING]` in `[APPLICATION]` through its supported UI/API while keeping
Git/Flux from taking ownership of ordinary operator state. This prompt does not
authorize an application mutation until its explicit field says yes.

## Required inputs

- Application, URL/endpoint, and setting/object identity: [values]
- Current and desired behavior: [facts; redact sensitive values]
- Why the setting is application-owned: [ownership rationale]
- Supported UI/API procedure and upstream documentation: [links]
- User/group/tenant scope and expected side effects: [details]
- Persistent database/volume and backup/export: [identity/evidence]
- Credential/OAuth/external-system effects: [inventory]
- Restart/reload requirement: [facts]
- Verification operation and rollback procedure: [details]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; docs/backup/infra paths only if needed]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; storage/workload status scope]
- Live cluster/host mutation: [yes/no; restart/reload scope]
- Application-state mutation: [yes/no; exact UI/API objects and operations]
- External/provider mutation: [yes/no; exact task/calendar/home/provider effects]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; exact application/user/data objects]

Ordinary conversation, repository edit permission, or access to an MCP/tool does
not authorize application or external side effects.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `configuration-ownership`, `application-state`,
`backup-restore`, and `secrets-sops` when credentials are involved. Read
configuration-ownership fully,
the application-specific manual/runbook, and service-operations stateful gates.
For Open WebUI/MCPHub/personal assistant settings, read the Open WebUI and personal-
assistant manuals and preserve their group/confirmation boundaries.

## Workflow

1. Prove the setting is operator-managed application state rather than a
   Kubernetes startup, isolation, exposure, protection, or observation boundary.
   If unclear, stop and request a cluster-level justification before moving it to Git.
2. Identify the authoritative database/volume and current readable backup/export.
   Record the current setting safely without exposing credentials or personal data.
3. Review supported upstream UI/API behavior, validation, persistence across
   restart, role/tenant scope, auditability, and downstream/external side effects.
4. Present the exact application changes before acting. Require immediate
   confirmation for task/calendar/note/home-control or other external mutations
   when the application manual requires it.
5. Make the narrow authorized UI/API change. Do not use direct SQL, database file
   edits, recurring init containers, post-start hooks, sidecars, CronJobs, or
   startup scripts to overwrite initialized state.
6. Verify the setting in the same supported interface, then test representative
   behavior. If a restart is required, perform it only with live mutation
   authority and prove the setting survives and unrelated state remains intact.
7. For MCPHub, verify connection status, groups, tool filters/visibility, and one
   harmless call through the real client endpoint. Tool registration does not
   grant external action authority.
8. Record the change and recovery dependency without recording secret values.
   Make Git changes only for genuine infrastructure/backup/documentation needs and
   run validation if any are authorized.

## Hard stops

Stop for ambiguous ownership, missing application-state authority, no supported
UI/API, absent readable backup, direct database editing, a request for a permanent
Git reconciler, destructive user/data effect, credential disclosure, unexpected
tenant/group scope, or external side effect without explicit provider authority.

## Rollback and recovery

Prefer the supported UI/API reversal. For irreversible or bulk changes, define an
application export/database restore and downtime before mutation. Restoring Git
does not restore application behavior. Preserve database-coupled encryption keys
and explain whether a restart, cache clear, or external provider reversal is part
of rollback.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return ownership rationale, supported procedure, backup/export identity and read
test, exact non-secret application objects changed, role/tenant scope, external
actions, restart status, representative functional check, persistence result, and
rollback readiness. If repository files changed, include complete validation.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] The setting remains owned by the application’s supported state boundary.
- [ ] A readable recovery point existed before mutation.
- [ ] Only explicitly authorized UI/API and external objects changed.
- [ ] Desired behavior, persistence, group/tenant scope, and unrelated state are verified.
- [ ] No Git reconciler, direct DB edit, or secret disclosure was introduced.
