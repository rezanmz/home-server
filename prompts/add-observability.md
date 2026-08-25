# Task brief: add or change observability

Add `[METRICS/ALERT/DASHBOARD]` for `[SERVICE]` so the repository's declared
observability mode matches what is actually measured. Kubernetes pod visibility
is not application telemetry, and a green dashboard is not service acceptance.

## Required inputs

- Service ID, namespace, active descriptor, and current observability mode: [values]
- Operational question or failure to detect: [specific outcome]
- Metric endpoint provenance, bind address, port, path, and authentication: [facts]
- Stable metric names, labels, expected cardinality, and sensitive-label review: [details]
- Service/EndpointSlice and scrape selector identities: [inventory]
- Required Prometheus NetworkPolicy path: [source, destination, port]
- Alert expression, severity, evaluation window, and recovery condition: [design]
- Dashboard audience, panels, variables, and provisioning owner: [design]
- Notification route, inhibition/silence behavior, and test impact: [details]
- Retention/storage implications and representative healthy/failing data: [evidence]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; descriptor, monitor, rule, dashboard, chart, policy paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and required checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; targets, queries, bounded logs]
- Live cluster/host mutation: [yes/no; port-forward, silence, restart, test scope]
- Application-state mutation: [yes/no; exact Grafana UI/dashboard/preferences objects]
- External/provider mutation: [yes/no; Telegram or credential/provider objects]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; exact dashboards, series/storage, silences]

Read access does not authorize a silence, alert test that pages someone, route
publication, retention change, restart, or UI dashboard mutation.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `observability`, `service-catalog`,
`service-lifecycle`, `network-auth`, `configuration-ownership`,
`secrets-sops`, `high-risk-review`, `ci-supply-chain`, and `validation` as
applicable. Read the runbook observability section, architecture application
boundaries, catalog monitoring modes, configuration ownership, and the active
observability HelmRelease and monitoring resources.

## Workflow

1. Traverse active manifests and identify the current descriptor mode:
   `kubernetes` means only controller/pod and generic CPU/memory visibility;
   `metrics` requires a real endpoint and referenced monitoring manifests;
   `platform` means shared platform signals; `none` is an explicit absence.
2. State the operational question. Prove the proposed endpoint is native or a
   narrowly reviewed exporter, what it measures, how it binds, and whether it
   exposes management capability or sensitive labels.
3. With read access, trace current Service, EndpointSlice, NetworkPolicy,
   ServiceMonitor/PodMonitor, Prometheus target, sample series, rules, dashboard,
   and Alertmanager route. Distinguish absent target, down target, missing series,
   bad query, and failed notification.
4. Add only the internal metrics Service/port required. Add exact Prometheus
   ingress/egress and a monitor whose rendered selectors match real labels. Do
   not expose a management API or public route to obtain metrics.
5. Query a stable metric and inspect label cardinality. Remove user IDs, tokens,
   secret-bearing URLs, unbounded request paths, and other high-cardinality or
   sensitive labels before relying on the endpoint.
6. Add an actionable alert with tested healthy and representative failing
   evaluations, meaningful duration, recovery behavior, summary, description,
   and runbook link. Only routed warning/critical severities should notify;
   informational/unknown signals must not accidentally page.
7. Add important dashboards through the existing Git-provisioned ConfigMap and
   sidecar contract. Treat Grafana preferences or incidental UI dashboards as
   application state; export anything recovery-critical into reviewed Git.
8. Update the descriptor mode and manifest references only after the metric path
   is real. Render catalog output and verify the mode against actual resources.
9. Run the complete validation bundle. If Helm values/chart resources change,
   independently fetch, checksum, render, schema-check, and high-risk-scan the
   immutable chart; root Kustomize output is not enough.
10. After protected merge, prove exact Flux/Helm revision, target health, sample
    query/cardinality, rule evaluation, dashboard provisioning, NetworkPolicy,
    and notification/inhibition behavior. Test the independent Kubernetes event
    exporter path separately when routing credentials change.

## Hard stops

Stop for an unverified or management endpoint, Kubernetes-only visibility
misclassified as metrics, selector mismatch, sensitive/high-cardinality labels,
unbounded NetworkPolicy, unactionable alert, human notification without
authority, or chart/high-risk diff not independently reviewed.

Do not add HTTPRoutes for Prometheus or Alertmanager, expose Grafana publicly,
claim Loki/central log search exists, increase storage to mask cardinality, or
claim observability volumes have ordinary B2 backup coverage. Their state is
deliberately treated as reproducible.

## Rollback and recovery

- Git/Flux: revert monitor, rule, dashboard, descriptor, policy, and chart values
  through protected review.
- Helm: restore the prior immutable chart source/values and verify generated
  resources and data compatibility.
- Runtime: remove exact temporary port-forwards, test targets, and silences;
  never leave a global suppression behind.
- Notification/provider: reverse Telegram or credential changes separately.
- Grafana application state: restore UI-only preferences/dashboard exports
  separately; Git does not contain them unless explicitly provisioned.
- Storage: restore retention/class only from a reviewed capacity plan, not by
  deleting time series as an improvised rollback.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return previous/final descriptor mode, metric provenance, rendered selectors,
target status, sample series and cardinality, policy proof, healthy/failing
alert evaluations, dashboard owner, notification/inhibition results, storage
classification, Helm/supply-chain evidence, complete validation, exact deployed
revision, temporary/live actions, and rollback status.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] The observability mode truthfully matches the available signal.
- [ ] Scrape endpoint, selectors, and NetworkPolicy are exact and non-sensitive.
- [ ] Alerts are actionable and tested; notification side effects are authorized.
- [ ] Important dashboards are recoverable from Git where intended.
- [ ] Complete validation and exact-revision target/rule/dashboard checks pass.
- [ ] No public management route, false log claim, or false backup claim is introduced.
