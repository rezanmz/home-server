# Task brief: run an isolated restore drill

Restore `[BACKUP/DATASET]` into uniquely identified disposable resources and
prove application-level readability without replacing production. A restore
object reaching Ready is not proof that the data, keys, schema, or client
behavior are recoverable.

## Required inputs

- Service/data set and recovery objective: [what must be recoverable]
- Data authority and exact PVC/PV/CSI/NFS/object-store identities: [inventory]
- Backup/export type, immutable identifier, completion time, and repository: [values]
- Required SOPS age, application, database, RSA, Restic, or provider keys: [locations only]
- Matching application/database image and schema/version prerequisites: [evidence]
- Isolation target, unique resource names, storage class, and namespace: [plan]
- Network, DNS, route, auth, and external side-effect isolation: [controls]
- Representative metadata, row/file counts, checksums, and safe write test: [criteria]
- Drill cleanup identities, retention exceptions, and expiry: [inventory]
- Production impact, window, abort condition, and operator: [details]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; drill manifests, docs, recovery metadata paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and required checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; backup, storage, production comparison]
- Live cluster/host mutation: [yes/no; exact disposable restore resources]
- Application-state mutation: [yes/no; exact disposable or production UI/API objects]
- External/provider mutation: [yes/no; exact B2/backup/API objects]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; exact disposable cleanup only unless separately stated]

Authority to create a drill does not authorize production detach, overwrite,
route exposure, provider deletion, credential rotation, or retained-data cleanup.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `backup-restore`, `storage-recovery`,
`retained-artifacts`, `secrets-sops`, `application-state`, `service-lifecycle`,
`cluster-operations`, and `validation`. Add `juicefs-media` for JuiceFS metadata
and `network-services` for Syncthing/NFS recovery. Read service-operations
stateful recovery, architecture storage semantics, the affected runbook, and the
application-specific manual. Use only an established drill; flag unsupported
production recovery rather than extending it by analogy.

## Workflow

1. Record exact Git/Flux revision and trace the production data identity from
   controller and mount through PVC, PV, CSI handle/NFS path, backup object,
   export, and required key. Identify every production writer without mounting
   or modifying the source.
2. Select one exact completed recovery point and prove its independent nature.
   A Longhorn replica, local snapshot, retained PV, cache, or authoritative
   JuiceFS B2 payload alone is not an independent complete recovery set.
3. Verify required keys exist in protected recovery locations without printing
   them. Confirm image/database/schema compatibility and whether the restore is
   application-consistent, crash-consistent, or requires a coordinated export.
4. Design uniquely named disposable resources that cannot bind, adopt, or write
   the production volume. Use no public route, deny unnecessary egress, isolate
   credentials, and suppress external jobs/messages/webhooks without changing
   production application state.
5. If repository edits are needed, add only explicit drill resources with an
   owner and cleanup identity, run complete validation, and use protected review.
   Do not alter production claim names, reclaim policies, selectors, or owners.
6. Restore the exact backup into the isolated target. Keep production mounted
   and untouched. Mount read-only first where possible and preserve restore logs,
   backup IDs, volume IDs, and key requirements.
7. Validate storage-level identity and representative checksums, then start the
   compatible disposable application/database with no external side effects.
   Verify schema, authentication boundary, representative reads, and a safe
   write only to disposable state.
8. Apply domain-specific proof:
   - Application/database: verify key tables/objects and a real supported client
     operation, not only pod readiness.
   - Retained artifact: verify historical software/key prerequisites and record
     the review decision without reactivating old runtime manifests.
   - JuiceFS metadata: separately test restored Longhorn PostgreSQL and portable
     metadata export against existing encrypted chunks and original RSA key;
     never overwrite production.
   - Syncthing: treat the repository's restore proof as disposable evidence only;
     do not claim it establishes production disaster recovery.
9. Compare results with the stated recovery objective and record recovery time,
   data age, missing objects, and manual prerequisites. Do not conceal partial
   recovery behind a successful controller condition.
10. With exact destructive authority, remove only the uniquely named disposable
    workloads, claims, volumes, temporary credentials, and files. Re-run
    production writer/health checks and prove no route, owner, backup selection,
    or retained object changed.

## Hard stops

Stop for ambiguous source or target identity, missing key, incompatible binary/
schema, no independent recovery point, restore tool targeting production,
unexpected writer, public route, external side effects, or cleanup scoped by a
broad label/path. Never change a production PV reclaim policy by copying a
disposable drill cleanup pattern.

Do not call an isolated JuiceFS or Syncthing proof a complete production DR
procedure. Do not use this brief for Beelink/K3s SQLite restoration; the
repository lacks a tested consistency-safe off-host datastore plus matching
server-token recovery path.

## Rollback and recovery

- Production: the primary rollback is no production mutation; stop the drill
  immediately if any production owner, mount, route, or writer changes.
- Disposable Kubernetes/Longhorn: clean up only the exact recorded identities;
  preserve evidence first and never infer target from a broad selector.
- Git/Flux: revert temporary drill intent through review and explicitly retire
  any root-prune-retained objects.
- Secrets/keys: destroy only temporary copies; preserve production and retained-
  artifact recovery keys.
- Provider/NFS: reverse only exact temporary objects or directories with separate
  authority.
- Application state: discard disposable changes; production application state
  must remain untouched.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return exact source/backup/export/key-dependency chain, base/deployed revision,
isolation design and object identities, restore logs/status, schema/version,
checksums/counts, representative read/write/auth behavior, RTO/data-age result,
external isolation, cleanup inventory/result, final production health, and any
unsupported recovery gap.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] The recovery point, keys, image/schema, and full identity chain are proven.
- [ ] Restore resources are uniquely isolated and cannot mutate production.
- [ ] Storage and application-level recovery objectives are tested with evidence.
- [ ] Cleanup targets only exact disposable objects under explicit authority.
- [ ] Production owners, data, routes, credentials, and backups remain unchanged.
- [ ] Unsupported Beelink or production Syncthing recovery is not overstated.
