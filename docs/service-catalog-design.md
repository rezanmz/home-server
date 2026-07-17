# Service catalog design decision

## Decision

Use versioned service descriptors colocated with their owning manifests and a
repository build-time compiler with fixed integration adapters. Generate only
deterministic cross-service aggregates and standard Authentik plumbing. Keep
Kubernetes workloads and service-specific security, storage, backup,
authorization, and monitoring resources explicit.

The operator interface is the descriptor plus four commands: `render`,
`explain`, `check`, and `summary`. `explain` is a first-class safety feature,
not debug output: it shows what was generated, what was only validated, and
what still requires live acceptance.

## Research basis

The design adopts the useful part of several established approaches without
installing their platforms:

- [Backstage's Software Catalog](https://backstage.io/docs/features/software-catalog/)
  stores versioned metadata YAML with the software it describes and treats the
  catalog as a derived view rather than runtime truth.
- [Backstage's catalog graph guidance](https://backstage.io/docs/features/software-catalog/creating-the-catalog-graph/)
  recommends GitOps-managed descriptors that humans govern, with automation
  assisting rather than guessing classification.
- [OpenGitOps](https://opengitops.dev/) requires desired state to be
  declarative, versioned, automatically pulled, and continuously reconciled.
  Committed generated files keep the exact cluster input visible in review.
- [Flux's repository structure guidance](https://fluxcd.io/flux/guides/repository-structure/)
  supports the existing monorepo separation between applications,
  infrastructure, and cluster reconciliation.
- [Score](https://docs.score.dev/docs/) demonstrates the value of a small
  declarative workload contract, but this catalog intentionally does not try
  to become a portable workload specification.
- [CUE's configuration guidance](https://cuelang.org/docs/concept/how-cue-enables-configuration/)
  highlights the danger of confusing overlapping defaults. This design has no
  recursive inheritance or deep merge; consequential choices stay explicit.
- [Kubernetes custom-resource guidance](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/)
  reserves CRDs/controllers for APIs that need Kubernetes-native storage,
  watches, and reconciliation. This repository compiler needs none of those
  runtime capabilities.
- [Authentik blueprints](https://docs.goauthentik.io/customize/blueprints/)
  are the provider's native infrastructure-as-code mechanism. They apply
  atomically and mounted files are watched, making a generated ConfigMap a
  supported integration.
- [Authentik's OAuth/OIDC guidance](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/)
  recommends per-provider issuers, exact redirects, authorization code, and
  PKCE instead of implicit flow.
- [JSON Schema](https://json-schema.org/learn/getting-started-step-by-step)
  provides a standard editor- and tool-readable contract for the YAML
  descriptors.

## Alternatives considered

### Keep one central catalog

This provides an easy global view, but separates a service's intent from its
manifests, repeats paths, grows merge conflicts, and makes retirement or review
require searching a second part of the repository. It was the useful first
step, not the scalable endpoint.

### Generate every Kubernetes resource

A high-level application API could generate Deployments, Services, routes,
policies, storage, and monitoring. That looks simple until real exceptions
arrive. It would either expose a second Kubernetes-sized API or hide material
security and recovery decisions behind templates. It would also make the
catalog a competing runtime source of truth.

### Install a CRD/controller or platform framework

Crossplane Compositions, Kratix Promises, or a custom operator can reconcile a
high-level platform API. They are appropriate when many teams request runtime
resources across many clusters. For one two-node homelab, they add privileged
controllers, RBAC, upgrades, and new failure modes without solving a runtime
reconciliation problem.

### Use free-form profiles or YAML inheritance

Profiles that combine “private web app,” OIDC, Longhorn, backup, and monitoring
make the first file short but hide the exact choices the operator most needs to
review. Deep merges also make it hard to know which value won. Profiles here
are narrow, immutable, and limited to Authentik mechanics.

### Use annotations on Kubernetes objects only

Annotations work for Homepage links and discovery, but not for explanations
such as why a public route lacks OIDC, which NFS data is reproducible, why a
workload is pinned, or which off-site policy protects each state class. The
descriptor is a human-maintained policy object, not inferred inventory.

## Safety boundaries

The compiler may hide mechanical assembly. It may not hide:

- public versus private reachability;
- authentication mode, client type, grants, scopes, callbacks, or custom
  claims;
- application-side authorization and bootstrap;
- physical placement;
- state classification and off-site protection;
- monitoring level;
- secret values; or
- live acceptance and restore evidence.

Unknown fields fail. Public unauthenticated routes fail. Private/public route
parity is checked against rendered middleware. OIDC redirects must be exact
same-host HTTPS URLs. Public clients require reviewed PKCE evidence.
Confidential clients require both provider and relying-party encrypted keys.
Inputs interpolated into generated syntax are restricted to safe DNS,
Kubernetes, or Authentik identifier forms.

Generated output ownership is exclusive and deterministic. Validation completes
before atomic writes. CI compares committed output with a fresh render.

## Extension rules

A new integration should be added only when it is:

1. cross-service or mechanically repetitive;
2. deterministic from explicit descriptor input;
3. safely testable in CI;
4. reviewable as committed output; and
5. understandable in `explain`.

Prefer a fixed, versioned adapter over arbitrary descriptor-supplied code. Do
not add raw YAML or generic templating as an escape hatch. If a service cannot
fit a standard adapter, keep its explicit manifest and let the catalog validate
the reference and reason.

Promote the descriptor from alpha only after future additions have shown that
the envelope and security boundaries are stable. A breaking shape change gets
a new `apiVersion` and a deterministic migration; an existing version is never
silently reinterpreted.
