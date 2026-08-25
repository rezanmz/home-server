# Task brief: add a service

Add a production service to the home-server GitOps repository and leave it ready
for protected review. Treat implementation, push/PR, application bootstrap,
manual live work, and provider cleanup as separate scopes. Merging to `main`
necessarily authorizes Flux deployment and the controller-managed effects of
the exact diff.

## Required inputs

- Service ID, display name, and upstream project: [values and links]
- Intended namespace and placement: [namespace; floating or node/device-bound]
- Container source and immutable target: [repository, tag/release, expected digest]
- Ports and protocols: [container, Service, LAN/host dependencies]
- Exposure and hostname: [none/private/public; hostname]
- Authentication: [native OIDC/OAuth/SAML, native login, forward-auth, or none]
- DNS intent: [Blocky split DNS; Cloudflare/public DNS]
- Persistent data: [paths, access mode, size, authoritative store, backup class]
- Dependencies and required egress: [destinations and ports]
- Per-setting secret and configuration ownership map: [provider SOPS,
  relying-party SOPS or application state, startup/recovery keys, UI settings]
- Bootstrap/first-owner behavior: [fail-closed plan]
- Observability and backup acceptance: [level and recovery proof]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; service, catalog, generated, CI, and policy paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target and draft/ready]
- Merge: [yes/no; exact PR and required checks]
- Read-only cluster/host access: [yes/no; targets]
- Live cluster/host mutation beyond automatic Flux: [yes/no; reconcile/bootstrap/restart scope]
- Application-state mutation: [yes/no; exact onboarding/UI/API scope]
- External/provider mutation: [yes/no; DNS, OAuth, router, registry objects]
- Destructive actions: [yes/no; normally no for an addition]

Repository-edit permission does not authorize a provider change, merge, Flux
reconcile, direct apply, application onboarding, or secret revocation.
If merge is yes, enumerate and authorize the automatic deployment plus any
declared Authentik or Cloudflare effects; otherwise stop at a reviewable PR.

## Manuals and skills

Load `home-server-safety`, `service-lifecycle`, `service-catalog`,
`configuration-ownership`, `application-state`, `network-auth`, `secrets-sops`,
and `validation`. Add `storage-recovery` and `backup-restore` for any PVC,
database, import, or persistent data. Add `high-risk-review` for every new route
or NetworkPolicy boundary and for any privilege/RBAC/host change. Add
`ci-supply-chain` for a new Helm/source path, and add `network-services` or
`observability` when those surfaces change. Read the architecture,
service-operations, service-catalog, configuration-ownership, relevant runbook,
and application-specific manuals. Read cluster-operations for placement/host
dependencies.

## Workflow

1. Record the exact base revision, prove the root owner and closest exemplar are
   active through Kustomization traversal, and confirm the new target path is
   not already registered. Do not require a nonexistent addition to be active
   and do not copy recovery-only YAML.
2. Resolve namespace/Pod Security, placement/architectures, ownership, storage
   authority, backup, exposure, authentication, network paths, bootstrap, and
   observability before writing manifests. A new public workload must not float
   onto the trusted Pi PodCIDR without explicit placement/threat proof.
3. Add the smallest explicit workload module. Use digest-qualified images,
   restrictive pod security, meaningful probes/resources, no service-account
   token by default, and `Recreate` for an unproven singleton using an RWO PVC.
4. Add only necessary Service, access proxy, Gateway route, middleware,
   NetworkPolicy, PVC, monitoring, and SOPS Secret resources. Default-deny
   namespaces require explicit traffic paths. For a proven new empty PVC,
   protect any import source and define the first post-initialization independent
   backup plus isolated recovery test; do not invent a pre-creation backup.
5. Add the colocated service descriptor. Render catalog output, inspect every
   generated diff, and run `explain` for the new service. Independently verify
   that storage, mounts, placement, and protection claims match manifests.
6. Register the module in the root. Create a child Flux owner only with an
   explicit dependency, pruning, decryption, health, CI-rendering, and retirement
   design; never create one solely to gain pruning. Re-render and prove the new
   target is now reachable through the intended owner.
7. Run the complete local validation bundle on the final tree. Explain every
   high-risk finding and require independent immutable Helm rendering if used.
8. If authorized, use protected review and Flux. Prove the exact merged revision,
   rollout, placement, storage, endpoints, route conditions, intended-client
   access, authentication, one real operation, logs, and backup inclusion.

## Hard stops

Stop for a mutable or unverifiable image, unsupported target architecture,
unknown license/provenance, missing SOPS identity, unowned state, absent recovery
plan, public unauthenticated route, public first-owner page, unbounded egress,
unreviewed privileged/host/RBAC behavior, or a catalog classification that is
not true of the actual mounts. Do not invent external credentials or provider
objects. Do not use direct live apply as the normal path.

## Rollback and recovery

Preserve the previous desired state and any prior immutable image. For a brand
new root-owned service, a Git revert does not delete live objects because root
pruning is disabled; prepare an explicit retirement inventory. For stateful or
externally registered services, name data-retention, credential, DNS, OAuth, and
provider reversals. Do not promise an image rollback across an incompatible data
migration.

## Evidence contract

Report base revision, closest pattern used, ownership decisions, files added,
generated diffs, image digest/architectures, security and network decisions,
storage/backup evidence, catalog `explain` and semantic checks, complete
validation results, and every authorized live/external action. If deployed,
include the exact reconciled revision and non-secret acceptance observations.

## Acceptance criteria

- [ ] Active manifests and a colocated descriptor express consistent intent.
- [ ] Image, security, network, auth, storage, ownership, and recovery gates pass.
- [ ] Generated outputs are compiler-produced and fully reviewed.
- [ ] The full applicable validation bundle and required PR check pass.
- [ ] If deployment was authorized, the exact merged revision is live and the
      service-specific functional and backup checks pass.
- [ ] Anything outside authority remains clearly listed, not silently performed.
