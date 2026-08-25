---
name: agent-guidance
description: "Maintain home-server agent guidance comprising AGENTS.md, repository skills, task prompts, runtime discovery adapters, and validation. Use when repository behavior or agent discovery changes, guidance drifts, or a workflow is added, renamed, or retired; not for ordinary service edits whose operating contract is unchanged."
---

# Maintain agent guidance

Keep a fresh agent able to discover the right source, determine its authority,
perform the supported workflow, stop at unsafe boundaries, and leave durable
guidance truthful. Structural validation is necessary but does not replace a
cold-reader test.

## Read before editing

Read AGENTS.md, skills/README.md, prompts/README.md, prompts/task-template.md,
the affected operator manual, and scripts/ci/validate-agent-guidance.py. For a
runtime-discovery change, verify the current primary documentation for that
runtime instead of relying on remembered paths.

This skill does not authorize repository edits, commits, pushes, pull-request
updates, workflow runs, or any live/external action. A review-only task reports
drift. A change task may update only the authorized repository scope; use the
separate Git and side-effect permissions in AGENTS.md for delivery.

## Preserve the source hierarchy

- AGENTS.md owns repository-wide safety, authority, routing, workflow, and
  completion rules.
- Operator manuals own durable architecture, ownership, supported commands,
  recovery, and service-specific procedures.
- Each canonical skills/<name>/SKILL.md owns conditional task workflow and stop
  conditions.
- Each canonical prompts/<name>.md owns the inputs, permission matrix, evidence,
  and acceptance criteria for one recurring task.
- Runtime-specific files are thin discovery adapters. Keep policy out of those
  files except for the deliberately short OMP sticky safety rules.

When sources conflict, fix the canonical manual or AGENTS.md first or in the
same change, then update dependent skills and prompts. Never change production
or rewrite a manual merely to make unexplained drift appear intentional.

## Classify the change

Determine which contract changed before editing:

| Change | Required impact review |
| --- | --- |
| Topology, ownership, security, storage, recovery, or supported command | Relevant operator manual, AGENTS.md, affected skills/prompts, examples/tests |
| Repository-wide authority, side effects, or definition of done | AGENTS.md, home-server-safety, task template, all affected prompts/adapters |
| One task's trigger, workflow, stop, rollback, or evidence | Its skill, manual, prompts, routing/index entries |
| New, renamed, or retired skill/prompt | Canonical package/file, AGENTS routing, both indexes, adapters, validator expectations |
| Runtime discovery convention | Thin adapter, compatibility table, structural validator, current upstream evidence |
| Validation command or CI contract | CI workflow/script, validation skill, AGENTS.md, README, service manual |

Document durable behavior in repository manuals. Keep exact task revisions,
command output, CI links, rollout observations, and temporary live facts in the
commit, pull request, or task record. Never record secret values.

## Edit in dependency order

1. Establish the exact base revision and inventory every canonical and adapter
   file affected by the change.
2. Confirm the task's repository, commit, push, PR, remote-workflow,
   artifact-publication, and other permission planes. Stop if the requested
   deliverable conflicts with its permissions.
3. Update the authoritative manual and AGENTS.md where their contracts changed.
4. Update affected skills. Keep names stable unless a rename is intentional;
   keep descriptions discriminating and instructions limited to decisions the
   skill must change.
5. Update affected prompts, their authorization dependencies, documentation
   acceptance, and prompt/skill indexes.
6. Update discovery adapters without copying canonical content. Preserve the
   exact import, supported-link, and custom-directory targets documented in
   skills/README.md.
7. Extend validation for every new structural invariant that can be checked
   without pretending to prove semantic correctness.
8. Inspect the complete diff for duplicated policy, broadened standing
   authority, stale paths, mutable copied facts, or accidental secret content.

## Validate and reader-test

After the final edit, run:

    python3 scripts/ci/validate-agent-guidance.py
    python3 -m unittest discover --start-directory scripts/ci --pattern 'test_agent_guidance.py'

Then run the complete repository validation bundle from the validation skill.
For every new or materially changed skill, also run the available Agent Skills
frontmatter validator when the current agent runtime provides one.

Use a fresh read-only agent as a cold reader for a material change. Give it the
repository and a realistic task, but not the intended answer. Ask it to state:

1. which guidance it discovered and loaded;
2. what is and is not authorized;
3. the desired-state owner and supported workflow;
4. its stop conditions and rollback boundary; and
5. the evidence needed before completion.

Correct the guidance when the cold reader cannot act safely. Record the
scenario and findings in the PR/task evidence; do not encode one test scenario
as a universal rule unless it reveals a real contract.

## Hard stops

Stop for copied canonical guidance in an adapter, undocumented authority
broadening, a broken or cyclic adapter, an unindexed workflow, a manual/skill
conflict, a runtime convention supported only by memory, a structural validator
failure, or a required documentation update outside authorized scope.

Do not claim that one runtime's discovery proves another's. Do not claim that
structural CI proves an agent will make the right semantic decision.

## Rollback and evidence

A guidance-only rollback is a focused Git revert that restores the last
coherent set of canonical sources, adapters, indexes, and validation together.
Do not partially revert an adapter or validator while leaving its canonical
contract changed.

Report changed contracts and files, current upstream discovery evidence when
applicable, validator and full-bundle results, cold-reader scenario/results,
Git/remote workflow effects, unresolved semantic risks, and any runtime that
still requires explicit file loading.
