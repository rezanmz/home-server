---
name: observability
description: Add, change, or diagnose Prometheus scraping, alerts, Grafana dashboards, Telegram alert routing, and repository observability declarations. Use for monitoring truth, not as a substitute for service acceptance or log aggregation.
---

# Operate observability

Observability declarations must say what is actually measured. Pod visibility
through Kubernetes metrics is not application telemetry, and an alerting stack
cannot independently prove its own notification path.

## Required reading

Read:

- [runbook observability and alerting](../../docs/runbook.md#observability-and-alerting);
- [architecture application boundaries](../../docs/architecture.md#application-boundaries);
- [service catalog observability modes](../../docs/service-catalog.md#placement-data-and-monitoring);
- [configuration ownership](../../docs/configuration-ownership.md); and
- the active observability HelmRelease, NetworkPolicies, dashboards, rules,
  ServiceMonitors/PodMonitors, affected Service, and service descriptor.

Chart-selected resources are Helm-generated state. A HelmRelease edit requires
the repository's independent immutable chart render, schema validation, and
chart high-risk scan; root Kustomize output alone is insufficient.

## Observability truth model

Catalog modes mean:

- `kubernetes`: only controller/pod health and generic CPU/memory visibility;
- `metrics`: a real application metrics endpoint plus referenced scrape/rule or
  dashboard manifests;
- `platform`: shared platform monitoring resources own the signals; and
- `none`: an explicit documented absence.

Do not declare `metrics` because kube-state-metrics can see a pod. Do not claim
logs are centrally searchable: no Loki deployment is part of the desired state;
use bounded `kubectl logs` and host logs.

Important repository dashboards are Git-provisioned and non-editable. Grafana
UI preferences and incidental UI-created dashboards live on its PVC; export an
important dashboard into reviewed Git rather than relying on that local copy.

## Authorization and read-only discovery

A monitoring review or incident authorizes queries and bounded log inspection,
not rule changes, silences, restarts, route exposure, storage growth, or
notification tests that page people. Obtain explicit scope for those actions.

Start with:

```bash
ssh beelink 'sudo k3s kubectl -n monitoring get helmrelease,pods,svc,pvc'
ssh beelink 'sudo k3s kubectl -n monitoring get servicemonitor,podmonitor,prometheusrule'
ssh beelink 'sudo k3s kubectl -n monitoring get prometheus,alertmanager'
```

Prometheus and Alertmanager intentionally have no HTTPRoute. Use short-lived
operator port forwards when their UIs or APIs are needed. Grafana is the only
routed observability UI and remains LAN/WireGuard-only with Authentik.

For a missing signal, distinguish:

- absent target: selector, namespace selection, or generated scrape config;
- present/down target: Service, EndpointSlice, TLS, bind address, or
  NetworkPolicy;
- healthy target/missing series: metric name/labels or application behavior;
- present series/bad alert: PromQL, time range, `for`, cardinality, or labels;
  and
- firing/no notification: severity routing, inhibition, silence, credential,
  or Telegram path.

Do not widen NetworkPolicy until the selected Service and endpoint path are
proven.

## Supported workflows

### Add application metrics

1. Prove the endpoint is native or a narrowly reviewed exporter and identify
   its bind address, authentication, and sensitive labels.
2. Expose only the metrics port through an internal Service.
3. Add exact NetworkPolicy between Prometheus and that port.
4. Add a ServiceMonitor or PodMonitor whose selectors match rendered labels.
5. Query a stable metric and inspect cardinality.
6. Change the descriptor to `metrics` and reference the monitoring manifest.
7. Add an alert/dashboard only when it answers an operational question.

Do not expose a management API merely to obtain metrics. Avoid user IDs,
request paths, tokens, URLs containing secrets, and unbounded labels.

### Add or change an alert

Define the failure, actionable severity, evaluation window, and recovery
condition. Test the PromQL against healthy and representative failing data.
Use only the routed warning/critical severities when human notification is
intended; unknown and informational severities deliberately go to a null path.
Include a useful summary, description, and repository runbook link.

Use a time-bounded Alertmanager silence for planned work. Never disable a rule
or route globally merely to conceal an unexplained alert.

The Kubernetes event exporter is an independent Telegram signal. Validate both
paths when changing notification credentials or routing; one working path does
not prove the other.

### Add or change a dashboard

Use stable, bounded queries and a clear operational question. Account for
missing metrics and multi-node labels. Provision important dashboards through
ConfigMaps and the existing sidecar contract; do not hand-edit generated chart
objects or depend on a UI-only dashboard for recovery.

### Change retention or storage

First investigate cardinality, accidental scrapes, and retention behavior.
Observability volumes deliberately select a backup-excluded Longhorn storage
class because their state is considered reproducible. Do not claim B2 coverage
or move them into the ordinary recurring backup group without a deliberate data
and cost decision. Preserve Git-managed dashboards and alert definitions as the
recovery source.

## Hard stops

Do not:

- publish Prometheus or Alertmanager through a route for convenience;
- expose the Grafana break-glass credential or make its login public;
- label Kubernetes-only visibility as application metrics;
- widen scrape egress/ingress without proving the endpoint;
- raise storage to mask cardinality growth;
- assume dashboard green status proves backup, DNS, client access, or a real
  application operation;
- claim centralized logs or an independent external dead-man check exists; or
- regenerate Helm/high-risk baselines merely to accept an unexplained chart
  diff.

## Rollback and completion evidence

Rollback rules, monitors, dashboards, and chart values through reviewed Git.
Remove temporary silences and test resources by exact identity. A Git revert
does not reverse a Telegram credential rotation or restore UI-only Grafana
state.

Report the descriptor mode, metric provenance, target state, sample query and
cardinality, alert healthy/failing evaluations, dashboard provisioning,
notification/inhibition result, NetworkPolicy proof, storage/backup class,
exact reconciled revision, and any human notification or external action.
