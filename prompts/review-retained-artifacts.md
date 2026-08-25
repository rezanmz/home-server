# Task brief: review retained or orphaned artifacts

Audit `[PATH/SERVICE/OBJECT SET]` and classify each artifact as active desired
state, deliberately retained recovery material, safely removable orphan, stale
generated output, or unexplained drift. Review is read-only unless explicit
fields authorize edits or exact deletion.

## Required inputs

- Git path, service ID, namespace, or object selector to review: [exact scope]
- Suspected origin and retirement/change history: [commits/PRs if known]
- Root or child Flux owner and prune setting: [evidence]
- Desired recovery/retention horizon: [policy]
- Catalog descriptor or CatalogExclusion: [path/status]
- Storage, Secret/key, backup, and provider dependencies: [inventory]
- Candidate live/external objects: [exact identities]
- Requested outcome: [report/re-own/document/remove]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact manifest/exclusion/docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Read-only cluster/host access: [yes/no; inventory scope]
- Live cluster/host mutation: [yes/no; exact ownership/delete operations]
- Application-state mutation: [yes/no; exact export/quiesce/UI/API operations]
- External/provider mutation: [yes/no; exact DNS/auth/backup/provider objects]
- Destructive actions: [yes/no; exact Git/live/data/secret objects]

A candidate labeled “orphan” is not authorized for deletion. Retain when identity,
ownership, writer status, or recovery dependency is uncertain.

## Manuals and skills

Load `home-server-safety`, `retained-artifacts`, `service-lifecycle`, `service-catalog`,
`storage-recovery`, `backup-restore`, `secrets-sops`, and `validation` for any
correction. Read service-operations retirement, cluster-operations Flux ownership,
architecture storage boundaries, the service runbook, and catalog exclusion
rules. Load `juicefs-media` and use the JuiceFS manual for any JuiceFS artifact.

## Workflow

1. Record exact Git revision/worktree and traverse the root plus referenced child
   Kustomizations. Do not infer activity from file presence. Identify generated
   regions separately from source input.
2. When read-only live access is authorized, inspect Flux inventories and status,
   owners/labels/finalizers, controllers, pods, Jobs/CronJobs, routes/endpoints,
   mounts/attachments, PVC/PV/CSI/NFS identity, backups, and relevant events.
3. Classify each artifact:
   - active desired and reconciled;
   - active but unexplained drift;
   - root-unowned live object retained because root pruning is disabled;
   - child-owned inventory subject to that child’s explicit prune setting;
   - deliberate recovery artifact with a stable owner/dependencies;
   - stale generated output that must be fixed through compiler input;
   - exact removal candidate with no writer, reference, data, key, or recovery use.
4. Check whether removing a child from the root would leave it reconciling the old
   path. Never remove the owner before its inventory is empty or transferred.
5. For descriptors, use CatalogExclusion only for genuine active recovery-only
   paths/internal helpers. Never exclude a live modeled workload to silence check.
6. Trace every storage and Secret candidate to exact identity and recovery need.
   Repeat writer inventory immediately before any future destruction.
7. Produce a keep/re-own/document/remove recommendation per artifact. If Git edits
   are authorized, make only ownership/documentation/catalog corrections, render,
   and run full validation. Exact live/external/destructive work remains separate.

## Hard stops

Stop deletion for an active/unknown writer, ambiguous owner or identity, finalizer
not understood, shared data/credential, retained key needed for backup decryption,
child inventory not empty, false CatalogExclusion, missing backup/read test, or
object named only by a broad label/path. Do not delete generated files by hand or
normalize documented live exceptions without their required investigation.

## Rollback and recovery

For re-ownership, define handoff order so no two controllers race and no object is
ownerless. For removal, record prior Git state, exact object manifests, data/export/
backup and key dependencies, and external recreation steps. Root-prune-disabled
objects and deleted provider/data objects are not recovered by a Git revert alone.

## Evidence contract

Return a per-artifact table with Git path, live identity, Flux owner/prune behavior,
references/writers, data/key/backup dependencies, classification, confidence,
recommended action, and required authority. Include changed/generated files and
validation only if edits were authorized.

## Acceptance criteria

- [ ] Every artifact has an evidence-backed classification and exact owner.
- [ ] Root/child pruning and retained-child reconciliation behavior are explicit.
- [ ] Recovery artifacts have stable ownership and complete key/data prerequisites.
- [ ] Removal candidates have no writers, references, shared state, or untested
      recovery dependency.
- [ ] No edit or deletion exceeds authorization; unresolved objects remain retained.
