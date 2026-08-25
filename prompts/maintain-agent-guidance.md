# Task brief: maintain agent guidance

Change the home-server repository's agent instructions, skills, prompts,
discovery adapters, or guidance validation while preserving one authoritative
source and the production authorization boundaries.

## Required inputs

- Guidance defect or changed operating behavior: [current and intended contract]
- Authoritative manual or repository source proving the change: [identity]
- Affected agents/runtimes and current upstream discovery evidence: [list/links]
- Affected repository-wide rules, task workflows, prompts, and indexes: [list]
- Compatibility and migration requirement: [existing entry points to preserve]
- Structural invariants that can be validated mechanically: [list]
- Cold-reader scenario and expected safe decisions: [task, not intended answer]
- Requested deliverable: [analysis only/files/commit/push/PR update]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact guidance, adapter, test, and documentation scope]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target and draft/ready state]
- Merge: [yes/no; exact PR and required checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; normally unnecessary]
- Live cluster/host mutation: [yes/no; normally no]
- Application-state mutation: [yes/no; normally no]
- External/provider mutation: [yes/no; normally no]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; normally no]

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `agent-guidance`, and `validation`. Add
`ci-supply-chain` when changing the validation workflow or executable policy.
Read AGENTS.md, skills/README.md, prompts/README.md, the generic task template,
the affected operator manual, and the current guidance validator. For runtime
discovery claims, use current primary upstream documentation.

## Workflow

1. Record the exact base revision and inventory canonical guidance, runtime
   adapters, indexes, tests, and all affected manual statements.
2. Classify whether the change affects durable operations, repository-wide
   authority, one task workflow, prompt inputs/acceptance, runtime discovery,
   or mechanical validation.
3. Update the authoritative manual and AGENTS.md first or in the same change.
   Do not make prose agree by changing production or canonizing unexplained
   live drift.
4. Update affected skills and prompts. Keep trigger descriptions precise,
   permission planes separate, rollback explicit, and evidence falsifiable.
5. Keep runtime adapters as imports, pointers, documented supported links, or
   configured canonical directories. Do not create independently edited copies
   for a particular agent, and reject bridges that change relative-reference
   resolution.
6. Update the routing table, skill/prompt indexes, generic template, examples,
   and structural validator wherever the changed contract reaches them.
7. Run guidance validation and the complete repository validation bundle.
8. Give a fresh read-only agent the cold-reader scenario without the intended
   answer. Correct any discovery, authority, workflow, stop, or evidence gap.
9. Create commits, push, or update a PR only when each action, remote workflow,
   and inevitable artifact-publication effect is authorized.

## Hard stops

Stop for missing primary discovery evidence, copied policy in an adapter,
broadened standing authority, a broken/cyclic symlink or import, an unindexed
skill or prompt, a manual/skill conflict, missing documentation scope, a
validator failure, or a cold reader that cannot identify safe boundaries.

Structural checks do not prove semantic correctness. Do not claim universal
runtime support from one successful agent, and do not add mutable versions,
transient live state, or secret values to durable guidance.

## Rollback and recovery

Revert canonical sources, adapters, indexes, and validation as one coherent Git
change. Preserve the last discoverable entry point during a migration. A
guidance-only change has no reason to mutate the cluster or external systems;
report any such requested expansion and obtain its separate authority.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Report the changed operating contract, authoritative evidence, complete file
inventory, runtime discovery matrix, adapter targets, skill/prompt index
changes, structural validator and full-bundle output, cold-reader scenario and
findings, every Git/workflow/publication action, and remaining runtime-specific
fallbacks.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] Canonical manuals, AGENTS.md, skills, prompts, indexes, adapters, and tests agree.
- [ ] Every supported runtime has a verified discovery path or an explicit-file fallback.
- [ ] Adapters contain no independently maintained copy of canonical policy.
- [ ] Authorization, inevitable side effects, rollback, and evidence remain explicit.
- [ ] Guidance validation, the complete repository bundle, and a cold-reader scenario pass.
- [ ] No Git, workflow, live, application, provider, or destructive action exceeded authorization.
