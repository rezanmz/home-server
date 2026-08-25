# Task brief: retire a service

Retire `[SERVICE_ID]` through an explicit, reviewable data-lifecycle operation.
Do not equate deleting YAML with deleting live objects, data, credentials, or
external integrations.

## Required inputs

- Service ID, namespace, root/child/Helm owner graph, and prune settings: [values]
- Retirement reason and required end state: [runtime absent/recovery retained/etc.]
- Durable-state classification and service-specific export/restore procedure:
  [manual path/heading; or `N/A — proven stateless` with evidence]
- Root/child inventory plus generated/controller-owned descendants: [evidence]
- Every writer/controller/job and direct/routed/callback traffic path: [inventory]
- Data stores and exact identity chain: [PVC/PV/claimRef UIDs, StorageClass,
  CSI/Longhorn/attachment/backup identities, NFS path, object store]
- Retain/destroy decision and retention horizon for each artifact: [table]
- Latest independent backup, application export, and content read test:
  [evidence; or `N/A — no durable data` with supporting inventory]
- Required outcome: [functionally restorable service, data-only archive,
  `no retained data — proven stateless`, or `no retained data — stateful
  destruction explicitly authorized after the recovery horizon`]
- Per-field Secrets/encryption keys/image/schema/recovery dependencies: [redacted inventory]
- DNS, router, OAuth, webhook, registry, and provider objects: [inventory]
- Catalog descriptor/exclusion, Authentik DB objects, generated integrations,
  and hash-named ConfigMaps: [current state]

## Authorization

Fill every line with exact identities. Blank or ambiguous means no.

- Repository edits: [yes/no; runtime, descriptor, exclusion, docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Read-only cluster/host access: [yes/no; inventory scope]
- Live cluster/host mutation: [yes/no; suspend/scale/delete exact objects]
- Application-state mutation: [yes/no; exact quiesce/export/UI/API operations]
- External/provider mutation: [yes/no; exact DNS/OAuth/router/backup objects]
- Destructive actions: [yes/no; exact Git/live/storage/secret objects approved]

The word “retire” does not authorize any destructive line. Retain is the default
for an object whose decision or identity is missing. Refresh destructive
authorization after discovery with exact names, UIDs, cascade behavior, and
newly created drill/cleanup identities; a broad pre-inventory approval is not a
safe deletion scope.

## Manuals and skills

Load `home-server-safety`, `service-lifecycle`, `service-catalog`,
`configuration-ownership`, `application-state`, `network-auth`, `cluster-operations`,
`storage-recovery`, `backup-restore`, `retained-artifacts`, `secrets-sops`,
`high-risk-review`, and `validation`. Read the retirement and storage sections
of service-operations, the exact service-specific export/restore procedure,
architecture storage rules, and cluster-operations for Flux ownership. Load
`juicefs-media` and read the JuiceFS manual before any JuiceFS operation. A
missing service-specific recovery procedure is a blocker whenever durable or
recovery-retained data exists; it is not permission to generalize another
service's commands. A stateless classification is valid only after proving the
workload, external dependencies, credentials, and application/provider systems
hold no durable service data that needs export or restoration.

## Workflow

1. Prove every desired-state owner and its inventory/prune behavior, then map
   Kubernetes owner references, dynamic Job/Pod/EndpointSlice descendants,
   CSI/Longhorn controllers, catalog aggregates, Authentik database objects, and
   external providers. Removing a child from the non-pruning root can leave it
   reconciling its former path.
2. Build a per-field retain/destroy matrix for runtime and generated objects,
   data, volumes, attachments, backups/exports, Secrets/keys, compatible
   image/schema, provider objects, and historical recovery material. State
   whether retained material supports functional restoration or only archival
   data access. If claiming stateless, record the negative evidence for every
   Kubernetes, host, application, and provider storage path; do not infer it from
   the absence of a PVC. `CatalogExclusion.reason` is not the recovery record.
3. Design CI-valid staged revisions rather than a one-PR directory deletion.
   First remove traffic and stop scheduling/writers through supported desired
   state, render generated integrations, and review every removed high-risk
   finding. If the schema cannot express a safe intermediate state, stop and
   design that lifecycle rather than bypassing catalog validation.
4. Inventory PVC and non-PVC writers: CronJobs, created Jobs and their owned
   Pods/retry state, controllers, HPAs, DaemonSets, APIs, mounts, attachments,
   operators, webhooks, host services, credentials, and human clients. When
   durable state exists, produce the application export at the service-specific
   consistency point—before shutdown when its API requires that, or offline only
   when supported. For a proven stateless service, record the evidence-backed
   export decision as N/A.
5. After the quiescence revision is exact and traffic is absent, continuously
   watch for writer/controller/attachment reappearance. For durable data,
   read-test the export, create the final quiesced independent backup, and prove
   it in an isolated restore. For a proven stateless service, mark those data
   gates N/A and preserve the storage-inventory evidence. Abort on any writer
   race or newly discovered state.
6. For root ownership, remove desired runtime objects, reconcile, then delete
   only exact now-unowned objects whose names, UIDs, owner/cascade behavior, and
   refreshed destructive authority match. For a pruning child, leave it alive
   as the stable retained owner; transfer only through a separately tested
   adoption plan, and remove it only after approved inventory is empty. Keep a
   retained Longhorn claim bound under desired ownership, attach a named final
   recovery point and review date, and explicitly opt a frozen claim out of the
   default recurring group; do not create an unmanaged Released PV.
7. Remove the descriptor only after active integration intent is gone, then
   render and verify the shared Homepage, Blocky, Cloudflare DDNS, and Authentik
   consumers. Check stale hash-named ConfigMaps by exact live reference before
   deleting them. Use a narrow CatalogExclusion only for genuine retained
   recovery material or an internal helper.
8. Removing the descriptor does not delete Authentik objects. The repository has
   no tested generic cleanup lifecycle at this revision. Retain and report those
   objects unless the task first implements a versioned lifecycle or supplies a
   separately authorized service-specific cleanup covering every mapping,
   binding, and outpost relationship.
9. Remove DNS records, OAuth clients, router/provider objects, backups, Secret
   fields, or storage only when exact external/destructive authority is refreshed
   and recovery dependencies no longer require them. Shared router 80/443 is not
   a per-service object; deleting a Kubernetes Secret does not revoke a provider
   value or erase Git/backups.
10. Run complete validation at each stage. Reconcile the final revision twice
    and prove former UIDs, owner-reference/label sweeps, routes/endpoints, Jobs,
    writers, retained owners, shared integrations, and deferred external state.

## Hard stops

Stop for an active or unknown writer; absent required quiesced backup/read test;
an unsupported or unproven stateless classification; ambiguous PVC/PV/CSI/NFS
identity; shared data or credential; a retained object with no stable owner; a
prune inventory containing retain-approved resources; an
encryption key still required for recovery; missing external/destructive
authorization; or a disposable restore-cleanup procedure being treated as a
production delete procedure.

Also stop before Authentik deletion when no complete tested cleanup lifecycle
exists, before any name-only deletion without UID/cascade proof, or when
credential revocation would make the chosen recovery horizon nonfunctional.

## Rollback and recovery

Before destructive work, define how to restore traffic, writers, desired state,
credentials, and, when durable state exists, exact data from the retained
export/backup. A proven stateless service still needs a desired-state, identity,
and external-integration rollback. Record the last known-good Git revision and
immutable image. Once a provider credential, remote backup, or storage object is
destroyed, a Git revert may not recover it; expose that point of no return and
require confirmation within the destructive scope.

## Evidence contract

Return the initial and final Flux inventories, writer inventories, retain/destroy
matrix, owner graph, exact storage/backup identity chain or stateless negative
evidence, continuous quiescence evidence, export/restore result or justified
N/A, changed and generated files, high-risk removals, validation results,
UID-scoped live deletions, shared-consumer regressions, external actions,
retained owners, CatalogExclusions plus recovery record, and unresolved
dependencies. Never include secret values.

## Acceptance criteria

- [ ] If live retirement was authorized, traffic and all writers are absent at
      the verified final revision; otherwise the unexecuted live phase is explicit.
- [ ] Root/child pruning behavior was handled explicitly; no owner was removed
      before approved inventory was empty or transferred.
- [ ] Every data, backup, secret, and external object has an executed or deferred
      retain/destroy decision; any stateless/N/A claim has cross-plane evidence.
- [ ] Retained recovery artifacts have a stable owner and documented prerequisites.
- [ ] Generated catalog output and full validation are clean.
- [ ] Live deletion used refreshed UID/cascade scope, and a second same-revision
      reconcile did not recreate the retired runtime.
- [ ] Authentik and shared generated objects are either proven through a tested
      lifecycle or explicitly retained as unresolved cleanup.
- [ ] No destructive or provider operation exceeded its explicit authorization.
