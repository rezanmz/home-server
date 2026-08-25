---
name: service-lifecycle
description: Add, modify, roll back, or retire a Kubernetes service in the home-server GitOps tree. Use for workload lifecycle changes, not for node replacement or incident-only diagnosis.
---

# Manage a service lifecycle

Use Git as the normal change path and preserve application data, access
boundaries, and explicit ownership throughout the service's life.

## Required reading and discovery

Read docs/service-operations.md fully for a lifecycle change. Also read:

- docs/service-catalog.md for the colocated integration contract;
- docs/configuration-ownership.md before choosing Git-owned settings;
- docs/architecture.md for topology, storage, and trust boundaries;
- docs/cluster-operations.md for placement or host dependencies;
- the relevant recovery section in docs/runbook.md for stateful or specialized
  services.

Inspect the closest active service with the same exposure, authentication,
storage, and privilege model. Confirm it is active through its
kustomization.yaml; do not copy unreferenced recovery YAML or a privileged
exception into an ordinary application.

Classify the requested operation as add, modify, rollback, or retire. If the
request crosses into node replacement, K3s upgrade, unsupported control-plane
recovery, or external provider work, stop and route that part separately.

## Shape decisions

Resolve these before implementation:

- existing namespace and Pod Security class;
- every state store, its authority, off-site protection, and restore test;
- floating versus physical placement and supported image architectures;
- internal-only, private, public, or exceptional host-network exposure;
- native OIDC/OAuth/SAML, reviewed forward-auth, native login, or no login;
- exact ingress and egress paths under namespace default-deny;
- observability level and operational alerts;
- Git-owned versus application-owned configuration;
- root versus deliberately designed child Flux ownership.

Because private routes trust the Pi PodCIDR after WireGuard masquerading, do
not let a new Internet-facing workload float onto the Pi without a reviewed
placement and NetworkPolicy proof. Existing floating public services are not
automatic precedents.

A new namespace, privileged construct, host dependency, broad RBAC grant, or
unrestricted network path requires explicit security design and a reviewed
high-risk baseline change.

## Add

1. Create a focused application module with explicit resources.
2. Use digest-qualified images; require all target architectures for a floating
   workload.
3. Default to no service-account token, non-root execution, RuntimeDefault
   seccomp, no privilege escalation, dropped capabilities, explicit resources,
   meaningful probes, and a read-only root filesystem when supported.
4. Prefer Recreate for a singleton Deployment using an RWO PVC unless another
   rollout strategy is proven safe.
5. Add Secrets through SOPS and storage through the correct recovery class. A
   new empty claim has no pre-change backup; prove it is new, protect any import
   source, and require its first independent backup and restore/read test after
   initialization.
6. Add workload-specific NetworkPolicy, Service, access proxy, route, and
   middleware only as required.
7. Add a colocated service descriptor, render shared integrations, and read the
   compiler explanation.
8. Register the module in the root, or fully define a child owner including
   dependency, pruning, decryption, health, CI rendering, and retirement.
9. Run the complete local validation skill, use protected review, then prove the
   live service at the exact merged revision.

Do not add a child solely to obtain pruning. Do not make an uninitialized
first-owner page public; complete a documented fail-closed bootstrap first.

## Modify

Apply the normal add validation and live-proof path, plus the relevant gate:

- Image or package: read release notes, verify digest and architectures, retain
  the previous immutable reference, and classify data-format migrations as
  stateful changes.
- Configuration: keep operational/UI choices in application state. Account for
  stale hash-named ConfigMaps because root pruning will not remove them.
- Secret or identity: rotate one integration at a time and prove the dependent
  path before revoking the old value.
- PVC, database, encryption key, or storage layout: create a readable
  application export and exact-volume off-site backup before mutation. Quiesce
  or coordinate multi-PVC applications.
- Placement or network: review hardware, architectures, host ports, NFS
  permissions, route, middleware, access proxy, Service, and NetworkPolicy as
  one boundary.

## Roll back

Revert desired state through a protected pull request. Root-owned resources
introduced by a reverted addition remain live until explicitly retired.

Never roll back only an image after an incompatible database migration. Prove
the old binary can read current data, restore a matching pre-change export into
an isolated target, or forward-fix according to upstream support.

Git does not roll back host files, DNS provider objects, router rules, OIDC
clients, webhooks, or revoked credentials. Reverse those only when separately
authorized and identity-checked.

For emergency live recovery, follow the suspend/minimum-change/matching-Git/
resume/drift-proof sequence in docs/service-operations.md. Do not leave a live
patch as permanent state.

## Retire

Retirement is not a manifest deletion.

1. Build the full owner graph, then write a per-field retain/destroy decision for
   application data, exports, PVC/PV/Volume/attachments/backups, NFS data,
   Secrets and encryption keys, generated aggregates, Authentik database state,
   provider objects, DNS/router state, compatible image/schema, and historical
   manifests. State whether recovery remains functional or data-only.
2. Remove traffic and stop every writer through reviewed desired state.
   Inventory CronJobs, already-created Jobs and their owned Pods/retries,
   controllers, HPAs, DaemonSets, API/database clients, pods, mounts,
   VolumeAttachments, host services, and any operator or human that can recreate
   a writer.
3. Use the service-specific export consistency point, then continuously monitor
   writer/controller/attachment absence through the final quiesced,
   content-tested backup and isolated restore.
4. For root ownership, remove desired runtime objects, reconcile, then delete
   each exact now-unowned live object only after rechecking its UID and cascade
   behavior. Never use a broad delete-k command.
5. For a prune-enabled child, keep the child alive while it prunes only
   destroy-approved inventory. Keep retained resources under a stable owner.
   Remove the child only after its inventory is empty or ownership transfer is
   separately proven.
6. Handle storage through the exact PVC UID, PV UID/reclaim policy, CSI handle,
   Longhorn Volume, attachment, backup, and NFS path chain. There is no generic
   production storage delete command.
7. Remove the service descriptor only after active integration intent is gone,
   then render. A retained recovery-only root path needs a narrow
   CatalogExclusion; never use one to conceal an integration-bearing service
   that belongs in a Service descriptor.
8. Remove Cloudflare, router, provider credentials, OAuth clients, and other
   external state only with separate authorization.
9. Prove runtime absence and document every retained recovery prerequisite.

Removing a generated Authentik `state: present` declaration does not delete the
database objects. The repository currently has no generic tested catalog
cleanup lifecycle. Retain and report those objects unless the task first adds a
versioned lifecycle or supplies a service-specific reviewed application-state
and destructive cleanup procedure.

Catalog changes also roll shared hash-named ConfigMaps and remove high-risk
findings. Verify every aggregate consumer, delete only unreferenced old hashes,
review baseline removals, reconcile the same final revision twice, and prove no
controller or stale child recreated the runtime.

Do not infer that a disposable restore cleanup procedure is safe for production
data.

## Completion evidence

Provide the operation class, ownership map, storage/recovery decision, changed
and generated files, full validation result, protected review status, exact Flux
revision, live acceptance result, and rollback/retention record. State clearly
when merge, deployment, external cleanup, or live proof was outside scope.
