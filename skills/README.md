# Repository skills

These skills are task-specific operating playbooks for the home-server GitOps
repository. Start with [`../AGENTS.md`](../AGENTS.md), select the skill from its
task-routing table, and then read the authoritative manual named by that skill.

Each directory is a portable skill package whose `SKILL.md` uses only the
common `name` and `description` frontmatter fields. A runtime that discovers
repository-local skills may load it directly. In a runtime that does not, open
the matching file explicitly or link the directory into that runtime's skill
search path. Keep this repository copy authoritative; do not maintain a second
edited copy in an agent-specific directory.

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

The complete routing table is kept in `AGENTS.md` so there is one index to
maintain. Reusable briefs under [`../prompts/`](../prompts/) already name the
expected combination for each recurring task.

## Maintaining a skill

When repository behavior changes, update the relevant operator manual first or
in the same change. Then update the skill so that a fresh agent can identify:

1. when to load it and when not to;
2. the current source of truth to inspect rather than mutable copied values;
3. authorization and side-effect boundaries;
4. preflight evidence and abort conditions;
5. the supported GitOps or operational workflow;
6. rollback across Git, live, host, application, and provider planes; and
7. the exact evidence required before claiming completion.

Run the skill validator and a cold-reader scenario after material edits. If a
skill and a manual disagree, stop, fix the drift, and keep the manual
authoritative rather than teaching agents to choose whichever is convenient.
