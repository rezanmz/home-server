# Service integration catalog

This manual describes the repository's cross-service contract. Read it before
adding a service or changing a hostname, exposure boundary, authentication
method, placement rule, storage class, backup policy, monitoring integration,
or Homepage card.

The catalog is `catalog/services.yaml`. It answers the questions that otherwise
get scattered across application manifests:

- Is this service reachable through the shared Gateway?
- Is the route public or LAN/WireGuard-only?
- Does it use native OIDC, forward-auth, native application authentication, or
  an explicitly documented exception?
- Does its hostname belong in Cloudflare DDNS and Blocky split DNS?
- What appears in Homepage, and which pods supply its health/resource data?
- Is the workload floating, pinned, or present on every node?
- Where does its state live, and what protects that state off-site?
- Does it have application metrics, platform metrics, or only Kubernetes
  health/resource visibility?

Kubernetes manifests remain the runtime source of truth. The catalog does not
replace Deployments, Services, HTTPRoutes, NetworkPolicies, Authentik
blueprints, ServiceMonitors, dashboards, PVCs, or backup jobs.

## Why this design

The catalog is a repository build-time contract, not a Kubernetes CRD or
controller. That is deliberate:

- adding a service does not add a privileged in-cluster reconciler;
- Flux still consumes ordinary, reviewable Kubernetes YAML;
- generated changes appear in the pull-request diff;
- Authentik and monitoring keep their service-specific configuration rather
  than being forced through a lowest-common-denominator template; and
- CI can reject an omitted integration before the change reaches the cluster.

Application annotations alone are not enough. They can describe a web card,
but not why a public route lacks OIDC, which physical node a workload depends
on, whether NFS data is backed up, or which Grafana/Prometheus resources own its
observability. A runtime controller would also be unable to safely invent
service-specific OIDC callbacks, backup semantics, or NetworkPolicy.

## What is generated

Run:

```bash
python3 scripts/service_catalog.py render
```

The command deterministically updates three aggregate YAML areas:

| Output | Catalog source | Why it is generated |
| --- | --- | --- |
| `apps/homepage/config/services.yaml` | Every enabled `homepage` declaration | Keeps the service directory and Kubernetes status selectors in one contract |
| `apps/cloudflare-ddns/kustomization.yaml` generated region | `web.hostname` entries with `dns.cloudflare: true`, plus `dns.extraPublicNames` | Makes a hostname addition roll the DDNS pod through a hash-named ConfigMap |
| `apps/blocky/config.yml` generated region | `web.hostname` entries with `dns.splitHorizon: true` | Keeps LAN clients on the MetalLB Gateway address |

Do not edit those generated areas directly. The generator leaves the rest of
the Cloudflare and Blocky configuration untouched.

Authentik blueprints, ServiceMonitors, PrometheusRules, Grafana dashboards,
NetworkPolicies, and backup resources are not generated. Their behavior is too
service-specific to synthesize safely. The catalog references them, and CI
proves that the declared files, blueprint application, client type, confidential
client environment variable, route hostname, and private-route middleware are
present.

## Catalog model

Each `services` item represents one operator-facing component. Several items
may share a deployment path or pod selector; Prowlarr, Radarr, Sonarr,
qBittorrent, and Shelfmark intentionally point at the consolidated
`media-vpn` pod.

### Identity and ownership

```yaml
- id: example
  name: Example
  path: apps/example
  workload:
    namespace: apps
    app: example
```

- `id` is stable, unique, lowercase operator vocabulary.
- `path` is the repository directory that owns the service. It must be reachable
  from `clusters/home-server/kustomization.yaml`.
- `workload` gives Homepage the namespace and exactly one selector:
  `app` for `app.kubernetes.io/name`, or a full `podSelector` for a compound
  workload.

Every active root `apps/*` path must have at least one catalog item. A retired
or intentionally non-service path needs a reason in `registrationExclusions`;
an unexplained omission fails CI.

### Homepage

```yaml
homepage:
  group: Home & Identity
  icon: example.png
  description: Short operator-facing purpose
```

The group must be declared in `homepage.groups`. A service with a `web` block
gets an HTTPS link by default. Set `link: false` for a status-only card.

An intentional omission must still be explicit:

```yaml
homepage:
  enabled: false
  reason: The dashboard does not need a card linking back to itself.
```

Homepage itself is the current example. This prevents “forgot the dashboard”
and “deliberately omitted” from looking identical in review.

### Web, DNS, exposure, and authentication

```yaml
web:
  hostname: example.reza.network
  route: apps/example/route.yaml
  visibility: private
  accessMiddleware: lan-vpn-only
  dns: {cloudflare: true, splitHorizon: true}
  auth:
    mode: oidc
    blueprint: example.yaml
    application: example
    client: confidential
    secretEnv: AUTHENTIK_OIDC_EXAMPLE_CLIENT_SECRET
    secretFiles:
      - path: apps/authentik/oidc-client-secrets.sops.yaml
        key: AUTHENTIK_OIDC_EXAMPLE_CLIENT_SECRET
      - path: apps/example/secrets.sops.yaml
        key: oidc-client-secret
```

`visibility` is either:

- `private`: the rendered HTTPRoute must reference the exact
  `accessMiddleware`; or
- `public`: there is no IP allow-list middleware and Internet exposure is an
  explicit review decision.

The DNS booleans are explicit even though almost every current route uses both.
This allows a future internal-only or externally managed name without hiding
the exception.

Authentication modes are:

| Mode | Required declaration |
| --- | --- |
| `oidc` | Authentik blueprint key, application slug, public/confidential client type; confidential clients also declare the Authentik worker environment variable and both encrypted Secret files |
| `forward-auth` | Authentik blueprint key, application slug, and route middleware; use only after checking APIs, WebSockets, callbacks, and native clients |
| `native` | A reason naming the supported application authentication or the missing upstream SSO capability |
| `none` | A reason and a private route; CI rejects unauthenticated public routes |

Native OIDC remains the default whenever upstream supports it. The catalog
records the decision; it does not weaken the requirements in the service
lifecycle manual. Exact callback URIs, scopes, group/role mapping, and bootstrap
logic remain in the Authentik blueprint and application manifests.

### Placement

```yaml
placement:
  mode: beelink
  manifest: apps/example/deployment.yaml
  reason: Requires an amd64-only image.
```

Allowed modes are `floating`, `beelink`, `raspberrypi`, `every-node`, and
`platform`. A pinned declaration must reference a manifest that actually
contains the matching `kubernetes.io/hostname` selector. Every non-floating
mode requires a reason.

The catalog records desired placement, not the node on which a floating pod
happens to run today. See the cluster operations manual before changing a pin.

### Data and protection

```yaml
data:
  class: mixed
  protection: longhorn-b2
  manifests:
    - apps/example/pvc.yaml
    - infrastructure/nfs-media/apps.yaml
  note: Longhorn protects configuration; large NFS media is reproducible.
```

Data classes are `stateless`, `longhorn`, `longhorn-observability`,
`nfs-reproducible`, `mixed`, and `platform`. Protection values are intentionally
specific:

- `longhorn-b2`;
- `longhorn-and-restic-b2`;
- `excluded-reproducible`;
- `excluded-observability`;
- `not-applicable`; or
- `platform-managed`.

Stateful classes must reference the manifests that define their storage.
`mixed` and excluded/platform protection require a note explaining the
boundary. A declaration is not proof that a backup completed; live backup and
restore verification remains an operational acceptance step.

### Observability

```yaml
observability:
  mode: metrics
  manifests:
    - apps/example/monitoring.yaml
    - infrastructure/observability/dashboard.yaml
```

Modes are:

- `kubernetes`: Homepage and the existing cluster stack provide pod health and
  CPU/memory visibility, but there is no application-specific metrics endpoint;
- `metrics`: the service owns explicit ServiceMonitor/PodMonitor/rule/dashboard
  resources listed in `manifests`;
- `platform`: metrics are supplied by the shared observability release or
  platform dashboard resources; or
- `none`: an explicit `reason` is required.

Do not claim `metrics` merely because a pod is visible in kube-state-metrics.
Conversely, do not add a bespoke Grafana dashboard to every tiny service when
Kubernetes health and resource data are the useful signal.

## Add a service

Use this sequence:

1. Create the application manifests following the service lifecycle manual.
2. Add the directory to `clusters/home-server/kustomization.yaml`.
3. Add one catalog item with explicit Homepage, web/auth/DNS, placement, data,
   protection, and observability decisions. A background service still needs
   explicit `homepage`, `data`, and `observability` declarations.
4. Add service-specific Authentik, metrics, dashboard, alert, storage, and
   backup resources referenced by the catalog.
5. Generate aggregate YAML:

   ```bash
   python3 scripts/service_catalog.py render
   ```

6. Review every generated diff. A new public DNS record or a disappeared
   Homepage card is a behavior change, not formatting noise.
7. Render and validate:

   ```bash
   kubectl kustomize clusters/home-server >/tmp/home-server.yaml
   python3 scripts/service_catalog.py check --rendered /tmp/home-server.yaml
   python3 scripts/service_catalog.py summary
   ```

8. Run the remaining repository checks and complete the pull-request/live
   acceptance flow in the service lifecycle manual.

`check` also works without `--rendered`; it runs the root Kustomize render
itself:

```bash
python3 scripts/service_catalog.py check
```

## Modify or retire a service

Change the catalog in the same pull request as the owning manifests. Run
`render` after any hostname, Homepage, or DNS change. CI rejects:

- a rendered `*.reza.network` HTTPRoute absent from the catalog;
- a catalog hostname with no rendered HTTPRoute;
- a private route missing its declared access middleware;
- a stale Homepage, Cloudflare, or Blocky generated area;
- an OIDC/forward-auth blueprint or application slug that is absent;
- a confidential OIDC client not loaded by the Authentik worker;
- a pinned workload whose referenced manifest does not contain that pin;
- a missing storage, observability, secret, route, or placement manifest; and
- a newly registered `apps/*` directory without a catalog decision.

For retirement, remove or disable the route first, stop writers, take the final
backup, and follow the root-pruning cleanup procedure. Remove the catalog item
only when its active integration intent is gone, then run `render`. If a
retained recovery-only directory remains in the root tree, add a narrow
`registrationExclusions` entry with its retention reason. Never use an
exclusion to hide an active service.

## Review commands

```bash
# Human-readable matrix.
python3 scripts/service_catalog.py summary

# Show only aggregate changes after a catalog edit.
python3 scripts/service_catalog.py render
git diff -- \
  apps/homepage/config/services.yaml \
  apps/cloudflare-ddns/kustomization.yaml \
  apps/blocky/config.yml

# Prove the catalog matches the final rendered cluster.
kubectl kustomize clusters/home-server >/tmp/home-server.yaml
python3 scripts/service_catalog.py check --rendered /tmp/home-server.yaml
```
