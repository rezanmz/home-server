# Configuration ownership

Use this rule when adding or changing a service: Git owns the cluster; the
application owns the application.

After reading this page, a maintainer should be able to decide where a setting
belongs without risking an unrelated Flux reconciliation overwriting a change
made in an application's UI.

## The rule

Put a value in Git when Kubernetes must know it to start, isolate, expose,
protect, or observe the workload. Put it in the application's persistent state
when an administrator or user would reasonably change it while operating the
application.

| Git and Flux own | The application owns |
| --- | --- |
| Image and package versions | Models and model-role assignments |
| Replicas, resources, placement, and probes | Prompts, profiles, personas, and automations |
| Services, routes, DNS intent, and network policy | MCP server registrations and tool allow-lists |
| Persistent-volume shape and backup policy | API credentials entered through an application UI |
| Workload identity, native OIDC wiring, and required runtime secrets | Dashboards, libraries, folders, and user preferences |
| Cluster monitoring and alert routing | Retrieval parameters and other experiment-friendly tuning |

The important test is not whether a value *can* be expressed in YAML. Ask what
an operator expects to happen after changing it in the application. If the
answer is “this choice should survive the next unrelated deployment,” it is
application state.

## What this forbids

Do not add a recurring init container, post-start hook, sidecar, CronJob, or
startup script that opens an application's database and restores a preferred
configuration. Do not continually seed records under the softer label of
“reconciliation.” A create-if-absent bootstrap must not later become an
authoritative overwrite.

Data migrations are temporary release work. Verify them, record their
completion in the application's data, and remove the migration from the normal
startup path. A migration must never remain as a permanent policy engine.

## Legitimate declarative configuration

Some behavior is inherently part of the cluster and remains declarative:

- Authentik application/provider definitions describe trust between services.
- Homepage is intentionally a YAML-configured directory rather than a database
  application.
- Grafana provisioning, Prometheus rules, DNS, DHCP, routes, and network policy
  are shared infrastructure.
- Config-file-only helpers such as the internal search backend have no separate
  administration database; their reviewed file is their runtime contract.
- A create-only first-run bootstrap is acceptable when an application has no
  supported noninteractive first-run path, provided it never overwrites an
  initialized data volume.

These are narrow exceptions. “GitOps” by itself is not a reason to take
ownership away from an application's supported UI.

## OIDC secrets

The service catalog supports two confidential-client patterns:

- A workload that requires the secret as an environment variable references a
  SOPS-encrypted Kubernetes Secret.
- An application configured through its own UI records that the relying-party
  secret is application-managed state. Authentik still receives its encrypted
  provider copy, while the application's backed-up data contains the other
  copy.

For the second pattern, rotate the provider and relying-party values as one
maintenance operation. A pull request cannot safely rotate the application
half on its own.

## MCP package and settings policy

MCPHub is the only MCP registry and policy boundary for chat clients. It owns
server commands, remote URLs, environment variables, API keys, OAuth sessions,
groups, tool visibility, and activity history in its PostgreSQL database.
Open WebUI connects to MCPHub once; it does not receive one infrastructure
connection for every tool.

Do not implement an MCP adapter locally merely because it is small. Select
software in this order:

1. the upstream service's official MCP server;
2. a reference server maintained by the MCP project;
3. a focused, maintained package with readable source, a narrow dependency
   tree, released versions, and an appropriate permission model;
4. a local adapter only when no suitable package exists and the exception is
   explicitly reviewed and documented.

Pin the selected source revision or package version in the runtime image.
Produce a multi-architecture image, provenance, and an SBOM. Package selection
is infrastructure; server settings are application state in MCPHub.

## Backup and restore

This boundary depends on application data being protected. Longhorn snapshots
and the B2 backup target protect Open WebUI, MCPHub, Audiobookshelf, Vikunja,
and other Longhorn-backed application state. Restoring only Git recreates the
cluster shell, not user configuration.

After restoring an application volume, verify login, one read operation, and
one safe write operation. After restoring MCPHub, also verify server status,
group membership, tool filters, and a harmless call through the same endpoint
Open WebUI uses.

## Pull-request checklist

Before merging a service change, answer all of these:

- Is every Git-owned value required for deployment, trust, isolation, exposure,
  storage, or observability?
- Would a UI change survive a restart and an unrelated Flux reconciliation?
- Does any startup hook mutate an initialized application database or config?
- Is an MCP integration using the best reputable existing package?
- Are operational credentials and tuning centralized in the application's
  backed-up state rather than duplicated across manifests?
- Is a one-time migration actually removed after completion?

If any answer is unclear, treat the value as application-owned until there is a
specific cluster-level reason to do otherwise.
