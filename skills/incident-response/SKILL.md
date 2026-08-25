---
name: incident-response
description: Diagnose and contain a home-server outage, failed Flux reconciliation, ingress failure, storage fault, or degraded service. Use for evidence-first incident work; it does not authorize implementation or live repair by default.
---

# Respond to an incident

The default incident mode is read-only diagnosis. Preserve evidence, identify
the owning plane, and separate containment from permanent repair. Urgency does
not broaden authorization.

## Read the relevant runbooks

Start with:

- [incident and recovery runbook](../../docs/runbook.md);
- [architecture and failure domains](../../docs/architecture.md);
- [cluster operations](../../docs/cluster-operations.md) for node, placement,
  or Longhorn incidents;
- [service lifecycle and rollback](../../docs/service-operations.md) for an
  application or Flux-owned resource; and
- [JuiceFS operations](../../docs/juicefs-media.md) for media storage.

Read the affected service's active manifests and descriptor. Confirm
reachability through its `kustomization.yaml`; historical YAML is not a recovery
instruction.

## Establish time, scope, and revision

Record:

- symptom, first observed time, client/network vantage point, and last known
  good operation;
- affected and unaffected failure domains;
- recent Git merges, host work, application-state changes, credential/provider
  changes, and maintenance;
- exact local `HEAD` and `origin/main`; and
- Flux source artifact, root and relevant child `lastAppliedRevision`, and
  HelmRelease revision/status.

Useful first checks:

```bash
git status --short --branch
git fetch origin main
git log --oneline --decorate -n 20 origin/main

ssh beelink 'sudo k3s kubectl get nodes -o wide'
ssh beelink 'sudo k3s kubectl get pods -A -o wide'
ssh beelink 'sudo k3s kubectl get deploy,statefulset,daemonset,cronjob,job -A'
ssh beelink 'sudo k3s kubectl get events -A --sort-by=.lastTimestamp | tail -n 80'
ssh beelink 'sudo k3s kubectl -n flux-system get gitrepositories,kustomizations -o wide'
ssh beelink 'sudo k3s kubectl get helmreleases -A'
```

Do not infer that `Ready=True` means the intended commit is deployed. Compare
the exact merged commit to the source artifact and every relevant owner's last
applied revision.

## Triage by plane

1. **Client and edge:** DNS answer, certificate, router/host-port path, MetalLB
   path, Gateway/HTTPRoute conditions, middleware, Service and EndpointSlice.
2. **Workload:** controller desired/ready counts, placement, probes, restarts,
   events, current and previous container logs.
3. **Dependency:** database, Authentik, DNS, NFS, JuiceFS, Longhorn, B2, provider,
   and credential state.
4. **Node:** readiness, pressure, filesystem space, listeners, mounts, host
   service logs, and physical dependency.
5. **GitOps owner:** source fetch, decryption, build, health check, child
   inventory, Helm install/upgrade, and prune behavior.
6. **Observability:** current alerts, scrape targets, dashboard signals, and the
   independent Kubernetes event exporter path.

Collect the smallest logs and object descriptions that test a hypothesis. Do
not dump Secrets, full application databases, sensitive URLs, or unbounded logs.
Do not restart every layer simultaneously; that destroys ordering evidence and
can multiply the outage.

## Form and test hypotheses

For each plausible cause, state:

- evidence supporting it;
- evidence against it;
- one read-only discriminating check;
- blast radius if true; and
- lowest-risk containment and durable repair.

Classify observed differences as intended desired state, known retained root
objects, child-owned state, host drift, external state, application state, or
unexplained drift. Root pruning is disabled, so an object absent from Git may
still be an expected retained or forgotten live object; do not delete it as a
diagnostic shortcut.

## Mutation gate and containment

A diagnosis request does not authorize a rollout restart, reconcile annotation,
scale, cordon, drain, secret rotation, provider change, or deletion. Present the
evidence and request or confirm authority for the exact containment action.

When an explicitly authorized emergency live change is necessary:

1. Identify and suspend the exact Flux owner, including any child that would
   overwrite the change.
2. Prove storage and recovery prerequisites before touching state.
3. Make the smallest reversible change and record the before/after object.
4. Create and merge matching desired state or a reviewed rollback.
5. Require the source artifact and owner to reach that exact revision.
6. Resume, reconcile, and prove no unexplained drift remains.

Never delete the root Flux Kustomization. Do not use Docker Compose or retired
services as a fallback. A temporary live patch must not become permanent
production state.

## Hard stops and unsupported recovery

Stop and report when resolution would require:

- an untested Beelink bare-metal/control-plane restore;
- treating fresh-host K3s scripts as an upgrade or recovery procedure;
- production Syncthing disaster recovery based only on its disposable restore
  proof;
- destructive Longhorn manipulation, a weakened drain policy, or blind stale
  lock removal;
- overwriting JuiceFS production metadata or replacing its encryption key;
- restoring an incompatible application image over a migrated database;
- broad `kubectl delete -k`, PVC/PV deletion, or external credential revocation
  without identity and retention proof; or
- exposing plaintext secrets in evidence.

## Rollback and closure evidence

Prefer a reviewed Git revert for a desired-state regression, but first prove
data-format compatibility. Git rollback does not reverse host files,
application-owned settings, DNS/provider records, router rules, or credential
revocation; list those planes explicitly.

Close the incident only with:

- timeline and root cause or bounded remaining hypotheses;
- exact deployed revision and owner readiness;
- node, workload, dependency, endpoint, route, access, storage, and backup
  evidence appropriate to the symptom;
- all containment/live/host/provider actions;
- confirmation that Flux is resumed and unexplained drift is absent;
- rollback status and any unsupported recovery gap; and
- follow-up work separated from immediate restoration.
