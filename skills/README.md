# Repository skills

These skills are task-specific operating playbooks for the home-server GitOps
repository. Start with [`../AGENTS.md`](../AGENTS.md), select the skill from its
task-routing table, and then read the authoritative manual named by that skill.

Each directory is a portable skill package whose `SKILL.md` uses only the
common `name` and `description` frontmatter fields. Keep this directory
authoritative; runtime-specific locations are discovery adapters, not edited
copies.

## Runtime discovery

| Runtime family | Repository entry point | Skill discovery |
| --- | --- | --- |
| Codex | Root `AGENTS.md` | `.agents/skills` is the documented repository skill path and symlinks to canonical `skills/`, which Codex follows |
| OpenCode, Cursor, GitHub Copilot, and other Agent Skills-compatible tools | Root `AGENTS.md` or that runtime's thin instruction adapter | Use `.agents/skills` only when the current runtime follows directory links correctly; otherwise open `skills/<name>/SKILL.md` explicitly |
| Claude Code | Root `CLAUDE.md` imports `AGENTS.md` | Open `skills/<name>/SKILL.md` explicitly or configure this canonical directory in the runtime |
| Oh My Pi | `.omp/AGENTS.md` imports root `AGENTS.md`; `.omp/RULES.md` keeps the mutation gate sticky when project rules are enabled | `.omp/config.yml` disables OMP's project `.agents` skill source and adds canonical root `skills/` through `skills.customDirectories` |
| Any runtime without repository skill discovery | Root `AGENTS.md` routing table | Open `skills/<name>/SKILL.md` explicitly |

A user configuration can disable a provider or skill loader, so automatic
discovery is never itself an authorization or correctness claim. Use the
explicit-file fallback when a runtime does not list the expected skill. Do not
add copied trees or unverified symlink bridges: a runtime may retain the bridge
path as a skill's base directory and break relative links in the canonical
package. The single `.agents/skills` link is retained for Codex, whose current
primary documentation explicitly supports linked skill folders. Other runtime
adapters use imports, configured canonical directories, or explicit loading.
`scripts/ci/validate-agent-guidance.py` checks these exact adapters.

Project runtime locations are a closed discovery surface. `.agents/` contains
only the canonical skill link; `.omp/` contains only `AGENTS.md`, `RULES.md`,
and `config.yml`; `.cursor/` contains only its always-applied pointer. Other
project runtime directories and GitHub agent/instruction/prompt/hook overlays
are forbidden because they can add instructions, commands, hooks, plugins,
permissions, or external side effects outside the canonical review path.
Nested runtime directories are also forbidden because a session started in a
subtree can select them ahead of the root contract. Add reusable work to
canonical `skills/` or `prompts/`; if a genuine runtime capability is ever
needed, evolve and test this discovery contract explicitly.

When changing discovery, re-check the current primary references: the
[Codex skill discovery guide](https://developers.openai.com/codex/skills),
[Claude Code memory/import guide](https://code.claude.com/docs/en/memory), and
Oh My Pi's [context-file](https://github.com/can1357/oh-my-pi/blob/main/docs/context-files.md)
and [skill](https://github.com/can1357/oh-my-pi/blob/main/docs/skills.md)
documentation. Treat installed-runtime behavior and tagged source as evidence
when prose and implementation disagree; record that drift in the change review.

Start Oh My Pi from the repository root (`cd <repo-root> && omp`, or use its
equivalent `--cwd` option) so the configured `skills` directory resolves to the
canonical tree. The project `.agents` skill source is disabled only inside OMP
so it cannot retain the symlink alias as the package base; native Codex still
uses that link. Root prompts are templates, and OMP's `@file` syntax does not
interpolate their placeholders. Copy the selected prompt to a temporary file
outside the repository, fill every required input and authorization field in
that copy, and load its absolute path from the repository root with
`omp @/absolute/path/to/filled-brief.md`. Do not commit the task copy or symlink
prompts under `.omp/prompts`.

Skills do not grant authority. They distinguish repository edits, Git remote
actions, read-only cluster/host inspection, live mutation, external/provider
changes, and destructive work. A task must independently authorize each plane.

## Choosing and combining skills

Load the smallest set that covers the real boundaries. Common combinations
include:

- service work: `home-server-safety`, `service-lifecycle`, `service-catalog`,
  `configuration-ownership`, and `validation`;
- public or authenticated service work: add `network-auth` and `secrets-sops`;
- stateful work: add `storage-recovery` and `backup-restore`;
- platform upgrades: `dependency-upgrades`, `ci-supply-chain`,
  `high-risk-review`, and `validation`;
- CYD firmware: `device-firmware`, `custom-image-builds`, `secrets-sops`,
  `network-services`, and `validation`;
- node or physical network work: `cluster-operations`,
  `node-host-operations`, and `network-services`; and
- outages: `incident-response` plus the skill for the failing boundary.
- guidance changes: `home-server-safety`, `agent-guidance`, and `validation`,
  plus `ci-supply-chain` when CI or executable policy changes.

The complete routing table is kept in `AGENTS.md` so there is one index to
maintain. Reusable briefs under [`../prompts/`](../prompts/) already name the
expected combination for each recurring task.

## Maintaining guidance

When repository behavior changes, update the relevant operator manual first or
in the same change. Apply this impact matrix rather than updating only the file
that exposed the drift:

| Changed contract | Update and inspect |
| --- | --- |
| Durable topology, ownership, security, storage, recovery, or supported command | Authoritative manual, `AGENTS.md`, affected skills and prompts |
| Repository-wide authority, automatic effects, workflow, routing, or completion | `AGENTS.md`, `home-server-safety`, generic task template, affected prompts |
| One task's trigger, workflow, stop, rollback, or evidence | Its skill, manual, prompts, routing and index entries |
| New, renamed, or retired workflow | Canonical skill/prompt, both indexes, routing, adapters and validation |
| Runtime discovery | Thin adapters, this compatibility table, validation and current upstream evidence |
| Validation command | CI workflow/script, `validation` skill, README, service manual and `AGENTS.md` |

Update each affected skill so a fresh agent can identify:

1. when to load it and when not to;
2. the current source of truth to inspect rather than mutable copied values;
3. authorization and side-effect boundaries;
4. preflight evidence and abort conditions;
5. the supported GitOps or operational workflow;
6. rollback across Git, live, host, application, and provider planes; and
7. the exact evidence required before claiming completion.

After the final edit, run:

```bash
python3 scripts/ci/validate-agent-guidance.py
python3 -m unittest discover --start-directory scripts/ci --pattern 'test_agent_guidance.py'
```

Then run the complete repository bundle from the `validation` skill. For a
material semantic change, follow the fresh-agent cold-reader procedure in
`agent-guidance`; structural CI cannot prove that an agent makes the right
decision. If a skill and a manual disagree, fix the canonical manual or
implementation first, then the skill. During a read-only task, report the drift
instead of editing it.
