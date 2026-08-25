---
name: application-state
description: Operate, back up, restore, migrate, or validate settings already classified as application-owned state. Use for Open WebUI, MCPHub, Hermes, and other UI-managed persistent behavior, not for deciding Kubernetes ownership.
---

# Operate application-owned state

Use this skill after the ownership decision has been made. If ownership itself
is disputed, first read the repository's configuration-ownership skill and
manual; do not use an operational shortcut to make Git authoritative.

## Required reading

Read:

- [configuration ownership](../../docs/configuration-ownership.md);
- [Open WebUI operating model](../../docs/open-webui.md) for models, profiles,
  retrieval, search, memory, and tools;
- [personal assistant integrations](../../docs/personal-assistant.md) for
  MCPHub, Hermes, OAuth, and tool permissions; and
- the affected application's section in the [runbook](../../docs/runbook.md).

Inspect the active workload, PVC, descriptor, backup classification, and the
application's supported administration interface. Git recreates the cluster
shell; it does not recreate application behavior stored in a database or data
directory.

## Ownership boundary

Git/Flux normally owns what Kubernetes needs to start, isolate, expose,
protect, and observe a workload: immutable executable identity, resources,
placement, probes, pod security, volumes, routes, DNS intent, NetworkPolicy,
OIDC trust, startup Secrets, and monitoring.

Application state normally owns operator-editable behavior, including:

- models, profiles, prompts, personas, memory, retrieval, and tool assignments;
- MCP server commands/URLs, environment, credentials, OAuth sessions, groups,
  tool filters, and activity;
- Hermes provider settings, companion files, schedules, skills, memory,
  messaging identity, and MCP registration;
- application users, libraries, folders, dashboards/preferences, automation,
  and ordinary service settings; and
- credentials entered through a supported UI and stored in the backed-up data
  volume.

Do not duplicate application-owned values into ConfigMaps, Secrets, init
containers, or reconciliation scripts for convenience.

## Authorization and sensitive discovery

- A request to edit Git does not authorize changing an application UI,
  database, user data, OAuth grant, or external account.
- A request to tune application behavior does not authorize manifest, image,
  network, or storage changes.
- Tool availability does not authorize tasks, events, messages, home control,
  media requests, or other external mutations. Require explicit user intent and
  immediate confirmation for consequential or destructive actions.

Keep discovery minimally invasive. Determine application version, readiness,
authoritative PVC, backup freshness, and supported UI/API path without dumping
the database or credentials. Do not paste tokens, OAuth files, personal
content, conversation exports, financial data, or full configuration into
terminal or chat logs.

## Supported workflows

### Change ordinary behavior

1. Identify the exact application-owned record and the supported UI/API.
2. Record the prior non-secret value and expected effect.
3. Confirm the authoritative data volume and current backup when the change is
   difficult to reverse or affects many records.
4. Change only the requested setting.
5. Reload or restart only through the application's supported mechanism when
   required; do not roll the Kubernetes pod merely to force a database write.
6. Exercise one representative read and safe write through the real client.
7. Verify an unrelated Flux reconciliation would leave the setting intact.

Open WebUI owns provider selection, profiles, prompts, model roles, retrieval,
embeddings, memory, and the single MCPHub connection. MCPHub owns all MCP
servers, runtime settings, credentials, OAuth, groups, and visible tools.
Hermes owns mutable content under its persistent data directory. Do not spread
one operational setting across those systems without a documented need.

### Rotate an application-managed credential

Keep the old credential valid while updating only the affected server or
integration. Reload and test that integration before revocation. When an OIDC
client secret has a provider-side SOPS copy and an application-managed relying
party copy, rotate them as one maintenance operation; a pull request cannot
complete the application half.

Do not copy an application-managed credential into Kubernetes to automate the
rotation.

### Restore application state

Prefer an isolated restore when validating a backup. Preserve the production
volume and matching encryption keys. After restore, verify authentication, a
representative read, a safe write, and the application-specific behavior the
volume is meant to preserve.

For Open WebUI, verify model visibility, profiles, MCPHub connection, search,
retrieval over disposable content, and a harmless personal-tool read. For
MCPHub, verify server connection status, group membership, tool filters,
credential/OAuth loading, activity, and a harmless call through the same client
endpoint. For Hermes, verify the approved entry point, schedules/tool boundary,
memory/config presence, and that unapproved ingress or private-network access
has not appeared.

Repair restored state through the supported UI. Do not add a Git reconciler to
make a restore appear complete.

### Migrate or re-index state

Treat migrations as temporary release work. Back up the authoritative volume,
prove the input, bound the target records, and make the operation restartable or
explicitly one-shot. Record completion in application state and remove the
migration from normal startup after verification.

Changing embedding models or vector dimensions requires a complete verified
re-index; old and new embeddings are not interchangeable. Do not leave a
startup migration installed indefinitely.

## Hard stops

Do not:

- add a recurring init container, post-start hook, sidecar, CronJob, or startup
  script that overwrites initialized application data;
- directly edit a production database when a supported UI/API exists;
- generate a replacement encryption key for existing encrypted state;
- claim that restoring Git restores application configuration;
- widen MCPHub groups or enable generic escape hatches to fix one missing tool;
- authorize work accounts or copy work data into personal-cluster state;
- expose secrets or personal data while gathering evidence; or
- turn a one-time migration into a permanent policy engine.

Stop when the authoritative volume, matching key, current backup, supported
administration path, or user authorization is uncertain.

## Rollback and evidence

Rollback through the application's supported interface or restore the exact
pre-change backup into an isolated target before production replacement. A pod
restart or Git revert does not roll back application data. Verify binary/schema
compatibility before restoring or downgrading.

Report the selected owner, authoritative persistence and backup, exact
non-secret setting changed, supported interface used, external actions,
read/write acceptance, credential revocation status, restore/migration
identifiers, rollback path, and anything not validated. Do not claim success
from pod readiness alone.
