---
name: service-catalog
description: Create, change, retire, or extend colocated service catalog descriptors and their deterministic shared integrations. Use for Homepage, DNS, Authentik, placement, data, and observability intent.
---

# Work with the service catalog

The catalog is a build-time policy contract. It is not a Kubernetes controller,
a complete workload specification, or a substitute for inspecting manifests and
live recovery evidence.

## Read before editing

Read docs/service-catalog.md and docs/service-catalog-design.md. Also inspect:

- catalog/cluster.yaml for genuine cluster-wide inputs;
- catalog/service.schema.json for the current descriptor envelope;
- the closest active colocated descriptor;
- scripts/service_catalog.py and its tests when changing schema, profiles, or
  generation behavior;
- docs/configuration-ownership.md when a proposed field could take ownership
  from application state.

Service decisions belong beside their owning manifests in
<service-id>.catalog.yaml. Do not put per-service values in
catalog/cluster.yaml.

## Compiler ownership

The compiler exclusively owns the committed:

- Homepage service inventory;
- Cloudflare DDNS domain region;
- Blocky split-DNS mapping region;
- Authentik aggregate application blueprints;
- Authentik worker secret-reference patch.

Never hand-edit these outputs. Workloads, Services, routes, middleware, access
proxies, NetworkPolicies, PVCs, backup jobs, monitoring, relying-party
authorization, application bootstrap, and secret values stay explicit.

## Add or modify a descriptor

1. Confirm the service path is active through Kustomization traversal.
2. Make explicit decisions for Homepage, route visibility, both DNS systems,
   authentication, placement, data/protection, and observability. Do not infer a
   public route, backup promise, node pin, role mapping, or callback.
3. Preserve stable identities: metadata.name, Authentik slug, OIDC client ID,
   provider/application identifiers, and the provider secret key derived from
   metadata.name. Treat changes as migrations.
4. Change explicit manifests and the descriptor together.
5. Render, inspect every generated diff, then read both ownership sections of
   the explanation:

       python3 scripts/service_catalog.py render
       python3 scripts/service_catalog.py explain SERVICE_ID

6. Render the complete root plus independent child bundle and check it:

       python3 scripts/service_catalog.py check --rendered /tmp/home-server.yaml
       python3 scripts/service_catalog.py summary

7. Complete all explicit responsibilities named by explain and perform
   service-specific live acceptance after merge.

Unknown fields and stale generated output are errors, not comments.

## Authentication profiles

Use native OIDC when the application supports it. Declare exact same-host HTTPS
callbacks, minimum grants and scopes, client type, logout behavior, and any
custom claim with its reason.

- A confidential client declares either a SOPS relying-party Secret reference
  or application-state ownership with a reason. The provider copy still belongs
  in the shared encrypted Authentik Secret.
- A public client declares reviewed PKCE evidence and no shared secret.
- Forward-auth is an exception for compatible browser applications.
- authentik-forward-single-v1 provides the ordinary single-application proxy
  integration.
- authentik-forward-single-v2 additionally requires a non-empty unique
  allowedGroups list and generates an Authentik policy binding. Do not downgrade
  v2, remove its group gate, or add allowedGroups to v1 as a convenience.

Application-side roles and authorization remain explicit even when the catalog
generates identity-provider plumbing.

## Semantic verification limit

A successful compiler check proves schema and selected integration relationships;
it does not prove that the descriptor truthfully describes the workload.

For every data or placement change, independently inspect:

- the controller's actual volume and volumeMount declarations;
- the bound storage class, PV/PVC, NFS endpoint, JuiceFS claim, or Longhorn
  volume;
- readOnly, subPath, and mount-propagation behavior;
- the real node selector, affinity, host network/port, and device dependency;
- backup inclusion, exclusion, and restore procedure;
- the referenced monitoring objects and actual metrics path.

Referenced manifest existence is not semantic storage validation. In particular,
do not label an organized JuiceFS library as Pi NFS merely because a historical
NFS module still exists or the descriptor vocabulary lacks a precise value.

If the current schema cannot truthfully express the data authority or protection
boundary, stop and propose a versioned schema/adapter evolution. Do not force a
false classification into an existing enum or hide the mismatch in a vague
note. Keep the workload explicit until the catalog can model it safely.

## Retire or exclude

Because root pruning is disabled and Authentik does not delete an object merely
when a blueprint disappears:

1. remove traffic and stop writers;
2. complete final backup and explicit live retirement;
3. remove the descriptor and render, understanding that this removes the
   generated `state: present` declaration but does not delete existing Authentik
   database objects;
4. retain and report those objects unless a separately authorized, tested
   service-specific cleanup exists or the change first implements a versioned
   catalog lifecycle covering providers, applications, mappings, bindings, and
   outpost membership; and
5. use a colocated CatalogExclusion only for an active root path that now owns
   recovery artifacts or a genuinely internal helper outside the service model.

An exclusion must never hide an integration-bearing active service that belongs
in the catalog model.

## Extend the compiler

Add an integration only when it is cross-service or repetitive, deterministic
from explicit input, testable in CI, reviewable as committed output, and clear
in explain. Prefer a fixed versioned adapter. Do not add arbitrary YAML,
templating, recursive inheritance, or a privileged runtime controller.

Existing profile behavior is immutable. Breaking descriptor behavior gets a new
apiVersion and deterministic migration; new profile behavior gets a new profile
version. Update schema, compiler validation/generation, tests, manuals, examples,
and generated output in one change.

## Authorization and evidence

Catalog editing does not authorize generating secret values, configuring the
relying application through its UI, deleting Authentik objects, changing
Cloudflare records, merging, or deploying.

Report descriptor and explicit-manifest diffs, generated outputs, explain
results, rendered check results, semantic mount/storage/placement verification,
and the live acceptance still required.
