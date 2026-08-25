# Task brief: rotate a Secret or OIDC credential

Rotate one credential integration at a time without disclosing plaintext or
revoking the old value before the replacement path is proven.

## Required inputs

- Integration/service ID and credential type: [token/password/OIDC/encryption key]
- Kubernetes Secret names/namespaces and encrypted file paths: [redacted metadata]
- Provider-side and relying-party copies: [owners/locations, no values]
- Application-state/UI copy, if any: [owner and supported edit path]
- Consumers, restart order, callbacks, and catalog references: [inventory]
- Provider overlap/versioning capability: [old+new supported or cutover only]
- Rotation reason, deadline, and compromise status: [facts]
- Recovery identities and database-coupled encryption use: [dependencies]
- Functional proof and old-value revocation plan: [checks]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact `.sops.yaml`, descriptor, generated paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; Secret metadata/workload status only]
- Live cluster/host mutation: [yes/no; exact restart/reconcile scope]
- Application-state mutation: [yes/no; exact credential/UI/API object]
- External/provider mutation: [yes/no; create/update/revoke exact credential]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; revoke/delete exact old value or key]

Never include a secret value in this brief, logs, command arguments, chat, a
temporary plaintext file, or evidence. Git edit authority does not authorize the
provider or application-state half of a rotation.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load `home-server-safety`, `secrets-sops`, `configuration-ownership`,
`service-catalog`, `network-auth` for OIDC, and `validation`. Read the SOPS,
identity-change, and completion sections of service-operations; secrets/recovery
identities in the runbook; configuration-ownership; service-catalog OIDC rules;
and the service-specific recovery/login procedure.

## Workflow

1. Confirm the existing age identity is available and protected. Do not generate
   a new age identity to bypass a missing key.
2. Inventory every copy/consumer: provider, shared Authentik provider Secret,
   relying namespace, catalog-generated worker reference, application database,
   mobile/client callback, webhook, backup target, and recovery artifact.
3. Classify ownership. A Kubernetes-startup value belongs in SOPS; a value entered
   through a supported application UI remains in backed-up application state.
   Do not duplicate it into Kubernetes merely for automation.
4. Define cutover order and overlap. Preserve the old credential until the new
   dependent path is proven whenever the provider supports overlap.
5. Create or edit only the intended `*.sops.yaml` Secret manifest through
   `sops`. Confirm `ENC[...]` structure and SOPS metadata without decrypting to
   disk. Coordinate both confidential OIDC copies; preserve public/PKCE clients
   without invented shared secrets.
6. Render catalog output and inspect generated Authentik secret references.
   Validate encrypted files and the complete rendered bundle.
7. If authorized, perform provider/application-state changes and protected
   Git/Flux rollout in the documented service-specific order. Verify provider
   processing, relying workload, login/API/backup path, callbacks, logout, and
   unrelated integrations.
8. Revoke or delete the exact old value only after successful proof and only when
   external/destructive authorization explicitly names it.

For an age-recipient rotation, stop treating this as an ordinary service secret:
inventory every SOPS file, historical recovery need, in-cluster decryption path,
and independently protected old identity; re-encrypt and restore-test before
retiring access.

## Hard stops

Stop for a missing/degraded age identity, decryption MAC/recipient error, unknown
copy or consumer, database-coupled encryption key without a supported migration,
no safe provider cutover sequence, missing application-state authority, plaintext
exposure, malformed encrypted Secret, failed validation, or pressure to revoke
before the replacement path is proven. Do not weaken SOPS rules or Flux
decryption to clear an outage.

## Rollback and recovery

Keep the old value active until proof where possible and record how to restore
encrypted Git plus application/provider copies. If overlap is impossible, define
the exact maintenance rollback point before cutover. Never replace a database
encryption key as a restart shortcut; its rollback requires compatible encrypted
data and the matching key.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Report only encrypted paths, Secret metadata names, ownership/consumer inventory,
catalog structural agreement, redacted validation results, provider/application/
live actions, exact reconciled revision, functional success, old-value revocation
status, and retained recovery dependencies. Report no plaintext or private key.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] Every copy and consumer has the intended new credential or documented owner.
- [ ] SOPS structure, catalog references, and full validation pass without leakage.
- [ ] The dependent path works at the exact deployed revision when rollout is in scope.
- [ ] The old value remains available until proof or follows an approved no-overlap plan.
- [ ] Revocation/deletion occurs only under explicit authority and unrelated
      integrations still work.
