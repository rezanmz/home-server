# Task brief: review a high-risk baseline change

Review proposed changes to the cluster or Helm-rendered high-risk review lock.
Explain every added, removed, and changed finding before deciding whether a
narrow baseline refresh is justified.

## Required inputs

- Branch/PR and exact head/base revisions: [values]
- Changed manifests/charts and stated security rationale: [inventory]
- Cluster rendered bundle path/command: [value]
- Helm rendered bundle path/command, if applicable: [value]
- Current baseline file(s) and proposed diff: [paths]
- Intended new privileged/RBAC/host/network constructs: [list]
- Threat model, compensating controls, and owner: [details]
- Unrelated pre-existing findings expected to remain unchanged: [inventory]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact baseline/manifests/tests paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target/comments]
- Merge: [yes/no; exact PR and checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; live comparison scope]
- Live cluster/host mutation: [yes/no; normally no]
- Application-state mutation: [yes/no; normally no]
- External/provider mutation: [yes/no; normally no]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; normally no]

Review permission does not authorize writing a baseline. Baseline-write permission
does not authorize accepting unrelated findings, changing manifests, merging, or
deploying.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `high-risk-review`, `validation`, and
`ci-supply-chain`; add `service-lifecycle`, `network-auth`, `storage-recovery`, or
`cluster-operations` to match the finding. Read service-operations high-risk
gate, architecture security exceptions, the policy checker and tests, current
validation workflow, both applicable baseline files, and the owning manifest/chart.

## Workflow

1. Record exact base/head and render the final root plus separately reconciled
   children exactly as validation does. Independently render immutable Helm
   releases when chart output is involved.
2. Run the checker against the current cluster baseline and, separately, the Helm
   rendered baseline. Capture findings without editing either lock.
3. Diff finding sets by stable object/container/rule identity. Classify every
   addition, removal, and changed field; trace it to the exact source manifest,
   chart value/default, or renderer change.
4. For each intended finding, document necessity, attack surface, namespace/Pod
   Security, service-account token/RBAC, capabilities/root, host network/path/port,
   devices/sysctls, ingress/egress, secret access, blast radius, and compensating
   controls. Compare with a less-privileged design.
5. Treat unexpected removals as seriously as additions: determine whether the
   risky construct was actually removed, renamed, hidden from rendering, or moved
   to an unrendered child/chart.
6. If and only if repository-edit authority permits and all deltas are intentional,
   run the checker’s documented writer for the exact relevant baseline. Inspect
   the resulting diff line by line. Never regenerate both locks reflexively.
7. Rerender and rerun the checker plus the complete validation bundle after the
   final edit. Require the protected CI result on the exact head.
8. Return approve/block/needs-redesign. Do not merge or deploy unless separately
   authorized.

## Hard stops

Stop for an unexplained finding, unrelated accepted delta, broad wildcard/RBAC/
egress when a narrow rule exists, hidden/unrendered resource, baseline format
change without checker tests, intentional removal without manifest evidence,
failed full validation, or a request to “make CI green” without threat review.

## Rollback and recovery

Keep the prior baseline and manifest revision. A baseline revert restores only the
review lock, not the live security boundary; manifest rollback and state/external
compatibility must be handled separately. Do not use a baseline-only commit to
conceal an already deployed high-risk change.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return exact render inputs/revisions, added/removed/changed finding table, source
trace, per-finding threat/necessity/compensating controls, alternate design,
baseline diff, checker/full validation results, and recommendation. State every
finding deliberately retained.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] Every baseline delta maps to an understood rendered source change.
- [ ] Each accepted risk has necessity, scope, owner, and compensating controls.
- [ ] No unrelated or hidden finding is accepted.
- [ ] Both applicable render/policy surfaces and full validation pass on final tree.
- [ ] Baseline write, PR, merge, and live actions remain separately authorized.
