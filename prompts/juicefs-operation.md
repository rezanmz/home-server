# Task brief: perform a JuiceFS media operation

Perform `[OPERATION]` on the organized-media filesystem while preserving its
metadata, encrypted B2 chunks, recovery keys, downloads boundary, and one
writable authority. Supported operation classes are mount recovery, cache
clear, B2 key rotation, metadata drill, capacity change, and migration.

## Required inputs

- Exact operation, reason, maintenance window, and expected interruption: [details]
- Filesystem identity and active static PV/PVC consumers: [non-secret identities]
- Metadata PostgreSQL database/PVC and Longhorn volume: [identities]
- B2 bucket/application-key identities and current permission scope: [redacted facts]
- RSA-key/passphrase and SOPS-age recovery-copy locations: [locations only, no values]
- Latest Longhorn metadata backup and portable metadata export: [IDs/times/read tests]
- Affected categories and explicit downloads exclusion: [list]
- Current writers, mount pods, CSI pods, nodes, and cache directories: [inventory]
- Current logical usage/quota, target capacity, and B2 cost impact: [if applicable]
- Migration source/checkpoint/canary/checksum/rollback plan: [if applicable]
- Success, abort, and data-integrity signals: [criteria]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; JuiceFS, storage, alerts, SOPS, docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and required checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; mounts, metadata, cache, logs]
- Live cluster/host mutation: [yes/no; exact mount, cache, config, copy, restore scope]
- Application-state mutation: [yes/no; exact consumer quiesce/config operations]
- External/provider mutation: [yes/no; exact B2 key/bucket operations]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; exact cache, disposable restore, source data, old key]

Repository edits do not authorize `juicefs config`, B2 credential work, cache
deletion, metadata restoration, host mutation, migration, or source cleanup.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `juicefs-media`, `storage-recovery`,
`backup-restore`, `cluster-operations`, `node-host-operations`,
`network-services`, `secrets-sops`, `observability`, `high-risk-review`, and
`validation` as applicable. Read the JuiceFS manual in full, architecture
storage contract, runbook storage/recovery sections, and cluster operations for
node maintenance. Do not substitute generic CSI or object-store guidance.

## Workflow

1. Identify all six planes before action: Git/Flux CSI and bindings; JuiceFS
   metadata/configuration; encrypted B2 chunks; Longhorn PostgreSQL metadata
   volume; node FUSE/cache host state; and the separate Pi NFS downloads tree.
2. Establish read-only health: exact Flux revision, CSI and mount pods,
   consumers/writers, metadata readiness, Longhorn replicas/backups, portable
   export freshness, B2 errors/latency, logical capacity, cache pressure, and
   independent downloads free space. Do not print credentials or metadata URLs.
3. Prove the recovery set: metadata backup or export, original RSA private key
   and passphrase, SOPS age identity, B2 key identity, filesystem name, and
   representative known checksums. A B2 object listing is not a restore test.
4. Apply the branch matching the requested operation:
   - Mount recovery: preserve the first FailedMount signal, isolate CSI/FUSE/
     host/metadata/B2/bind-mount cause, and restart only one affected layer.
   - Cache clear: cordon one exact node, stop or move all JuiceFS consumers,
     prove the shared mount and open handles are gone, clear only that cache
     under exact destructive authority, then checksum-read a known file.
   - B2 key rotation: keep the old key valid, update both the SOPS Secret and
     credential stored in JuiceFS metadata, remount/test each eligible node, and
     revoke only after new write, uncached read, and delete/trash recovery pass.
   - Metadata drill: restore Longhorn backup and portable export into separate,
     uniquely named empty databases; reapply omitted B2 config to disposable
     state and mount read-only without overwriting production.
   - Capacity change: change the logical JuiceFS quota once through supported
     configuration, then update format intent, dashboards, and percentage
     alerts. Do not resize the bound static PV/PVC to change quota.
   - Migration: use the repository category-scoped fail-closed helper, exclude
     downloads, quiesce writers for final sync, preserve checkpoints, bound B2
     read amplification, and verify inventory/modes/symlinks/checksums.
5. Make authorized Git/SOPS changes without exposing plaintext. Render and run
   complete validation; review storage, host, secret, network, and high-risk
   findings.
6. For any live change, define the single writable authority and stop condition
   first. Operate one node/category/credential plane at a time and preserve the
   old recovery path until acceptance.
7. Prove the exact merged Flux revision where Git changed, then verify
   cross-node mounts, representative reads/writes, known checksums, category
   paths, empty JuiceFS downloads mountpoint under the NFS overlay, metrics,
   alerts, backup/export identifiers, and expected B2 traffic/cost.
8. Remove old keys, checkpoints, source categories, cache contents, or disposable
   drill resources only when exact destructive/provider authority names them and
   all retention conditions pass.

## Hard stops

Stop for uncertain filesystem identity, missing original RSA key/passphrase,
missing SOPS identity, unproven metadata backup/export, active unknown writer,
live cache mount, stale or insufficient B2 credential, unexpected downloads
content, target ambiguity, or a migration that cannot quiesce writers.

Never generate a replacement RSA key for existing chunks, overwrite production
metadata in a drill, edit/rename/delete chunk objects with the B2 browser, enable
writeback, store databases in JuiceFS, treat cache as backup, copy downloads to
B2 by accident, shrink below current use, or change nominal static PV/PVC size
as a quota operation.

## Rollback and recovery

- Git/Flux: restore prior CSI/binding/Secret-reference/alert intent through
  protected review; root pruning does not remove old objects automatically.
- JuiceFS metadata: record every config mutation and reverse it from one
  controlled client only when compatible.
- B2/provider: retain the old key until every node passes; credential revocation
  is separately reversible only by issuing another authorized key.
- Longhorn/PostgreSQL: keep production untouched during drills; restore only to
  a new isolated target unless a separately reviewed disaster plan authorizes
  replacement.
- Host/cache: keep failed nodes cordoned; cache loss is repopulated from B2 but
  may incur latency/cost and cannot repair metadata.
- Migration/data: retain the frozen source, stop writers, account for post-
  cutover writes, reverse only into one authority, restore old mounts, and test
  before writes resume.
- Downloads: preserve the independent Pi NFS tree and overlay boundary.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return exact filesystem/metadata/PV identities, base and deployed revisions,
writer and mount inventory, backup/export/key dependency proof, operation branch
executed, non-secret config planes changed, node/category coverage, checksums and
read/write results, cache/B2 traffic and cost effect, validation, live/provider/
destructive actions, retained recovery material, and rollback status.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] Filesystem identity and all recovery dependencies are proven before mutation.
- [ ] Production metadata, encrypted chunks, and downloads remain correctly separated.
- [ ] The requested operation follows its narrow supported branch and one-writer rule.
- [ ] Cross-node/data-integrity and backup/export checks pass at the exact revision.
- [ ] Secret values and recovery keys never enter Git, logs, or the report.
- [ ] Cleanup/revocation occurs only after acceptance and exact authorization.
