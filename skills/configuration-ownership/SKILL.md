---
name: configuration-ownership
description: Decide whether a home-server setting belongs in Git/Flux or in backed-up application state. Use for UI settings, bootstraps, migrations, MCP integrations, profiles, automations, and declarative configuration proposals.
---

# Decide configuration ownership

Apply one rule:

> Put a value in Git when Kubernetes must know it to start, isolate, expose,
> protect, or observe the workload. Put it in persistent application state when
> an administrator or user would reasonably change it while operating the
> application.

Read docs/configuration-ownership.md before changing ownership. For Open WebUI or
MCPHub read docs/open-webui.md and docs/personal-assistant.md. For a particular
service, inspect its active manifests, persistent volumes, and runbook section.

## Classify the setting

Git and Flux normally own:

- image and package identity;
- replicas, resources, placement, probes, and pod security;
- Services, routes, DNS intent, access boundaries, and NetworkPolicy;
- persistent-volume shape and backup classification;
- workload identity, native OIDC trust, and secrets required at startup;
- shared monitoring, alerting, DNS, DHCP, and repository-provisioned dashboards.

Persistent application state normally owns:

- models, model roles, prompts, profiles, personas, memory, and automations;
- MCP server registrations, commands, remote URLs, credentials, OAuth sessions,
  groups, and tool allow-lists;
- API credentials entered through a supported UI;
- libraries, folders, users, dashboards/preferences, and experiment-friendly
  tuning;
- Home Assistant automations/helpers and media-application operating policy.

The fact that a value can be represented in YAML does not make it cluster
configuration. Ask whether an operator expects a supported UI change to survive
an unrelated Flux reconciliation. If yes, keep it in application state unless a
specific non-bypassable cluster boundary requires Git ownership.

## Prohibited reconciliation

Do not add a recurring init container, post-start hook, sidecar, CronJob, or
startup script that opens an initialized application database and restores a
preferred configuration. Do not disguise repeated seeding as reconciliation.

A create-if-absent bootstrap is acceptable only when no supported first-run path
exists, it fails closed, and it never overwrites initialized state. A migration
is temporary release work: verify it, record completion in the data, and remove
it from normal startup. It must not become a permanent policy engine.

Legitimate declarative exceptions include Authentik trust definitions, Homepage
inventory, shared Grafana/Prometheus provisioning, DNS/DHCP, routes and network
policy, and config-file-only helpers with no administration database. Keep each
exception narrow.

## MCP and personal-assistant boundary

MCPHub is the registry and policy boundary for chat clients. Git may pin a
reviewed package or upstream revision and impose network/RBAC ceilings. MCPHub's
backed-up database owns server environment, URLs, API keys, OAuth, groups, tool
visibility, and activity.

Choose an official upstream server first, then a reference implementation, then
a focused maintained package. A local adapter is a reviewed exception. Package
selection and immutable build provenance are infrastructure; runtime server
settings are application state.

Tool availability is not user authorization to mutate an external system.
Ordinary conversation does not authorize task, calendar, note, home-control, or
other side effects. Preserve the least-privilege group and immediate
confirmation requirements documented in docs/personal-assistant.md.

## Secrets and OIDC

A relying-party OIDC secret may be:

- a SOPS Kubernetes Secret when the workload needs it at startup; or
- application-managed state when the application stores it through its
  supported UI.

In the second pattern, Authentik still needs its encrypted provider copy.
Rotation is one coordinated maintenance operation; a pull request alone cannot
safely update the application half.

Do not copy operational credentials into Kubernetes merely to automate rotation.
Do not replace a database-coupled encryption key to make a deployment start.

## Backup consequence

Application ownership is safe only when its persistent state is protected.
Restoring Git recreates the cluster shell, not application behavior. Before a
stateful change, identify the authoritative volume and its current backup.

After restoring application state, verify login, a representative read, and a
safe write. For MCPHub also verify server connection status, groups, filters,
and one harmless call through the same client endpoint. Repair restored state
through the supported UI rather than adding a reconciler.

## Authorization and review evidence

A request to change manifests does not authorize editing an application UI,
database, provider account, or user data. Conversely, an operational UI change
does not authorize changing Git infrastructure.

For each proposed setting, report:

- selected owner and the concrete reason;
- persistence and backup location;
- behavior after restart and unrelated reconciliation;
- whether any bootstrap or migration writes initialized state;
- credential duplication or coordinated rotation requirements;
- restore acceptance needed.

When ownership remains ambiguous, default to application-owned state and request
a specific cluster-level justification before making Git authoritative.
