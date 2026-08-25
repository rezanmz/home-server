# Task brief: review a Renovate pull request

Review Renovate pull request `[PR]` as a proposed production-cluster change.
Return a merge/block/split recommendation with evidence. Do not equate an
automated pin update or green subset of checks with safety.

## Required inputs

- Pull request number/URL, head commit, and target branch: [values]
- Renovate dependency names, datasources, update types, and grouping: [values]
- Current and target references/digests/commits: [values]
- Release notes, changelogs, advisories, and provenance: [links]
- Affected services, charts, custom images, scripts, or Flux sources: [list]
- Stateful/schema/architecture implications: [details]
- Existing CI state and required check names: [facts]
- Requested outcome: [review only/fix branch/mark ready/merge]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact PR branch fixes]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; PR branch/remote]
- Open or update a pull request: [yes/no; comments/labels/ready state]
- Merge: [yes/no; exact PR and conditions]
- Read-only cluster/host access: [yes/no; baseline or post-merge checks]
- Live cluster/host mutation: [yes/no; usually no]
- Application-state mutation: [yes/no; usually no]
- External/provider mutation: [yes/no; usually no]
- Destructive actions: [yes/no; usually no]

Review authority alone permits no branch edit, PR mutation, merge, deploy, or
live/provider change.

## Manuals and skills

Load `home-server-safety`, `dependency-upgrades`, `ci-supply-chain`, and
`validation`; add `service-lifecycle` for workload changes and `service-catalog`,
`network-auth`, `secrets-sops`, or `configuration-ownership` when those surfaces
change. Read `renovate.json`, service-operations update guidance, the affected
service runbook, architecture source-pinning rules, and the current validation
workflow. For Helm or custom-image updates, use their dedicated prompt as a
second checklist.

## Workflow

1. Confirm the PR head/base revisions and read the complete diff, including lock
   files, generated output, scripts, source commits, checksums, and policy locks.
2. Explain why Renovate grouped the updates and whether they truly form one
   runtime/rollback unit. Recommend splitting unrelated or independently risky
   changes; preserve deliberately coupled groups.
3. Verify every target against authoritative upstream release notes and immutable
   registry/source identity. Check skipped releases, variants, architectures,
   moved tags, checksum guards, and commit/tag pairing.
4. Classify each update as digest rebuild, patch/minor feature, major migration,
   chart/source change, bootstrap/tooling change, or security response. Apply the
   appropriate state, compatibility, and rollback gate.
5. Inspect adjacent probes, permissions, defaults, APIs, CRDs, config, NetworkPolicy,
   storage, and catalog semantics. Automated changes do not update these safely by
   implication.
6. Run the complete validation bundle at the exact PR head if authorized to use
   the worktree. Require the protected validation result at that same head.
   Independently inspect immutable Helm render and both high-risk surfaces when
   applicable.
7. Return one of: merge-ready, fixable with named edits, split required, blocked
   pending migration/recovery, or reject. Merge or modify the PR only when its
   authorization field explicitly permits it.
8. If merge and read-only post-merge verification are authorized, prove Flux
   reached the merge commit and run affected-service acceptance. Do not trigger a
   reconcile without live mutation authority.

## Hard stops

Block a mutable/unverifiable source, relaxed digest/commit/checksum, missing
required architecture, unexplained variant change, database/channel major
change without migration, unavailable release notes, unexpected generated or
high-risk diff, failing/stale required CI, mixed unrelated risks, or absent
stateful recovery. Never merge merely because Renovate produced the PR.

## Rollback and recovery

Identify each prior immutable reference and whether the group can be reverted as
one unit. For migrations, define matching pre-change backups or state that a Git
revert is unsafe. A post-merge revert still uses protected Git/Flux and does not
reverse external, application-state, or destructive effects.

## Evidence contract

Return an update-by-update table with current/target identity, release impact,
architecture/state/security risk, validation status, rollback safety, and
recommendation. Include exact PR head, required-check result, any authorized PR
actions, and post-merge revision evidence if performed.

## Acceptance criteria

- [ ] Every changed dependency/source is immutable and tied to upstream evidence.
- [ ] Grouping, migration, architecture, generated, and high-risk effects are
      explicitly reviewed.
- [ ] Required validation is green at the exact reviewed head.
- [ ] The recommendation is unambiguous and names every blocker or required fix.
- [ ] No PR, merge, live, or provider mutation exceeded authorization.
