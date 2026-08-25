---
name: retained-artifacts
description: Review, preserve, restore-test, extend, or retire recovery-only Secrets, PVCs, backups, and historical manifests. Use when a service runtime is gone but Git or live storage intentionally remains.
---

# Manage retained recovery artifacts

Retained artifacts are data-lifecycle objects, not inactive clutter. Their
continued presence, backup exclusion, review date, and historical manifests can
be required to interpret or recover old data.

## Required reading and reachability

Read:

- [service retirement and storage identity](../../docs/service-operations.md#retire-or-remove-a-service);
- the affected recovery section in the [runbook](../../docs/runbook.md);
- [cluster operations](../../docs/cluster-operations.md) for detached Longhorn
  volumes or node removal; and
- the active directory `kustomization.yaml` and colocated `CatalogExclusion`.

Follow actual Kustomize reachability. Historical YAML in a registered directory
is not desired merely because it exists. Conversely, root pruning is disabled,
so removing desired YAML does not prove the live object disappeared.

## Known retained modules to re-read before acting

At the audited revision:

- Argilla's active module retains its encrypted recovery Secret and the
  `argilla-data`, `argilla-postgres`, `argilla-elasticsearch`, and
  `argilla-redis` claims. Each claim records
  `home-server.reza.network/review-after: "2026-09-01"`, a retention label, a
  final-export checksum, and an explicit opt-out from the default recurring
  backup group in `apps/argilla/pvc.yaml`.
- Argilla runtime workloads, Services, route, and NetworkPolicy remain
  unreferenced historical material for recovery analysis.
- Duplicati's active module retains only `duplicati-config`. Its runtime,
  Service, route, proxy, policy, and encrypted runtime Secret are unreferenced
  historical material. The claim opts out of the default recurring backup
  group but has no manifest review-after date.

Re-read these manifests on every review; do not rely on this summary if Git has
changed. A review-after date is a decision trigger, not a TTL, deletion request,
or grant of authority. Reaching it requires an explicit retain/extend/destroy
decision. Do not invent a date for Duplicati; report the missing expiry as an
open retention concern.

## Authorization boundary

A request to inventory or review retained data is read-only. It does not
authorize mounting, restoring, deleting, changing reclaim policy, removing a
Backup CR, revoking a key, or reactivating a workload.

Repository removal does not authorize live deletion. Backup deletion can remove
remote recovery data. Provider repositories, B2 objects, NFS directories, and
credentials require separate identity and authorization.

## Read-only inventory

For every retained set, record:

- active Kustomize owner and root/child prune behavior;
- descriptor/exclusion reason and historical files;
- Secret/key dependencies needed to interpret data;
- PVC namespace/name/UID and annotations/labels;
- PV name/UID, reclaim policy, and phase;
- CSI handle and Longhorn Volume/attachment/replica state;
- exact completed off-site backup and application export identifiers;
- NFS server/path or remote repository identity where applicable;
- current mounts, pods, Jobs, CronJobs, controllers, HPAs, and operators that
  could write or recreate a writer; and
- review date, responsible decision, and recovery objective.

Use live commands through the Beelink. Do not mount a retained claim just to see
what is inside until an isolated, read-only restore plan has been authorized.

## Supported workflows

### Periodic retention review

1. Confirm desired reachability and live ownership/inventory.
2. Confirm no active writer, mount, endpoint, route, or schedule exists.
3. Verify the named independent backup and required encryption/recovery keys.
4. Decide explicitly to retain, extend with a new reviewed date, restore-test,
   transfer ownership, or destroy.
5. Update annotations, exclusion reason, and recovery notes through Git when the
   decision changes.
6. Reconcile and prove surviving artifacts match the decision.

Do not re-enable default recurring backups for a frozen volume merely to make a
freshness alert green. Preserve the named archival recovery point or deliberately
bring the data back into writable service under a new reviewed plan.

### Isolated recovery test

Restore from the off-site recovery point into uniquely named disposable
resources. Preserve production retained objects untouched. Mount read-only when
possible, verify application/database identity and representative content, and
record exact backup, checksum, key, and software prerequisites. Delete only the
exact disposable test resources.

Historical runtime manifests may explain schema or paths, but do not re-add them
to the active Kustomization as an ordinary rollback. Build a reviewed isolated
recovery shape with minimum mounts, no public route, narrow egress, and no
production writer.

### Final destruction

Destruction requires a written retain/destroy matrix and a fresh writer
inventory. Capture the complete PVC/PV/CSI/Longhorn identity chain and prove the
exact independent backup selected for retention or deletion. Remove root-owned
desired resources, reconcile to the exact revision, then delete each exact
now-unowned live object. A prune-enabled child must remain alive while it prunes
only destroy-approved inventory.

Provider backup, NFS, and credential destruction happen only after Kubernetes
identity is proven and with separate authorization. There is intentionally no
generic production storage delete command.

## Hard stops

Never:

- use `kubectl delete -k` or a directory-wide delete;
- treat `Retain`, a Longhorn replica, or a local snapshot as an independent
  backup;
- delete or alter a Backup CR without understanding remote-object effects;
- change a PV reclaim policy by copying a disposable restore cleanup;
- transfer ownership during retirement without a separately tested adoption
  plan;
- remove a child owner before its inventory is empty or safely adopted;
- reactivate Argilla or Duplicati by re-referencing historical runtime YAML; or
- delete a Secret/key before proving retained data no longer depends on it.

Stop if any UID, CSI handle, backup identity, encryption dependency, writer, or
authorization is uncertain.

## Rollback and evidence

For a retention metadata change, use a reviewed Git revert and prove the stable
owner still inventories the artifact. For a restore test, cleanup is limited to
the exact disposable namespace/PV/volume. Destruction of production storage or
remote backups may be irreversible; the rollback is the independently verified
recovery point established before deletion.

Report desired owner, live inventory, review date/decision, complete storage
identity chain, writer absence, backup and read-test evidence, keys retained,
files and annotations changed, exact reconciled revision, each explicit live or
provider deletion, and unresolved expiry/recovery concerns.
