---
name: secrets-sops
description: Create, edit, validate, rotate, or recover SOPS/age-protected Kubernetes secrets for the home-server repository. Use for credentials, OIDC client secrets, provider tokens, and application encryption keys.
---

# Manage secrets with SOPS

Only SOPS ciphertext belongs in Git. Secret work must avoid plaintext files,
terminal output, command arguments, shell history, tickets, and chat transcripts.
Editing an encrypted manifest does not authorize a live restart, provider-side
rotation, revocation, or deletion.

## Required reading and preflight

Read:

- docs/service-operations.md sections on prerequisites, SOPS, and secret/identity
  changes;
- docs/configuration-ownership.md sections on OIDC and application state;
- docs/runbook.md section on secrets and recovery identities;
- docs/service-catalog.md for a catalog-managed OIDC client;
- the service-specific runbook section before rotation or recovery.

Verify tools and the existing age identity without printing secret material:

    command -v sops python3 >/dev/null
    SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
    export SOPS_AGE_KEY_FILE
    test -r "$SOPS_AGE_KEY_FILE"

Confirm that the selected identity file is mode-protected. Do not create a new
age identity to work around a missing key. Existing Secrets target the
repository's current recipient.

## Decide where the secret belongs

Use a Kubernetes Secret only when the workload, identity trust, cluster
integration, or startup boundary requires Kubernetes to know the value.
Credentials entered and changed through a supported application UI belong in
that application's backed-up state.

For OIDC:

- Authentik's provider-side confidential-client copy belongs in the shared SOPS
  Secret declared by catalog/cluster.yaml.
- A relying application that consumes an environment/file secret uses its own
  SOPS Secret.
- An application configured through its UI declares application-state ownership
  in the catalog; do not invent a duplicate Kubernetes Secret.

Preserve database-coupled encryption keys. A newly generated replacement can
make existing encrypted fields permanently unreadable.

## Create or edit

- Secret manifests must end in .sops.yaml.
- Use the repository .sops.yaml creation rule and edit through sops:

      sops apps/SERVICE/secrets.sops.yaml

- Put secret values only under a Kubernetes Secret's data or stringData fields
  covered by the repository rule.
- After save, inspect structure only: values must be ENC[...] ciphertext and the
  document must contain SOPS metadata. Do not decrypt to a repository or /tmp
  plaintext file.
- Run:

      python3 scripts/ci/validate-secrets.py

- Render the full cluster and run the rendered-secret validator before review.
- A separately reconciled child that contains SOPS resources must explicitly
  configure decryption with the in-cluster sops-age Secret.

Generate high-entropy values using a method that does not echo them or place them
in process arguments. If the available environment cannot do that safely, stop
and ask the operator to enter the value in the SOPS editor or provider UI.

## Rotate one integration at a time

1. Inventory every copy and consumer: provider, Kubernetes namespaces, catalog
   references, application state, external webhook/client, and recovery
   material.
2. Identify whether overlap is possible. Preserve the old value until the new
   dependent path is proven.
3. Update all required encrypted Git copies in one reviewed change. For an
   application-managed OIDC secret, coordinate the supported UI change with the
   provider copy; Git cannot rotate that half alone.
4. Run the complete validation bundle and inspect catalog-generated worker
   secret references.
5. Merge and reconcile only when deployment is authorized. Follow the
   service-specific order for restarting Authentik/provider processing and the
   relying application.
6. Prove the exact new login/API/backup path while the old credential remains
   available when the provider permits overlap.
7. Revoke the exact old provider credential only with separate authorization.
   Deleting a Kubernetes Secret does not revoke an external token.
8. Confirm unrelated integrations still work and record the rotation without
   recording values.

Do not batch unrelated rotations. Do not replace an application encryption key
until its supported data migration has succeeded and a readable recovery point
exists.

## Age-recipient rotation

Rotating the age recipient changes who can decrypt future repository ciphertext;
it does not revoke application credentials present in Git history, backups, or
provider systems. Preserve old identities required by historical recovery
artifacts until those artifacts are deliberately expired or re-encrypted and
restore-tested.

An age rotation must cover every SOPS file and the in-cluster sops-age recovery
path, retain independently protected recovery material, pass structural and
rendered validation, and prove Flux decryption before old access is retired.
Do not perform this as a side effect of an ordinary service-secret change.

## Failure and incident boundaries

- A missing age identity, decryption MAC failure, unknown recipient, or malformed
  Secret is a stop condition.
- Never paste decrypted output into a diagnostic transcript.
- Do not weaken file permissions, SOPS encrypted-field rules, CI scanning, or
  Flux decryption to clear an outage.
- Preserve the first useful failure signal. Determine whether failure is Git
  decryption, Secret projection, provider mismatch, application state, or
  external revocation before changing values again.

## Evidence

Report only redacted facts:

- encrypted file paths and Secret metadata names;
- consumers and ownership classification;
- validation results;
- whether catalog provider and relying-party references agree structurally;
- reconciled revision and rollout status when deployment was authorized;
- successful functional test and whether the old credential was revoked;
- retained recovery dependencies.

Never report plaintext, decrypted hashes that enable guessing, private age
identities, tokens, passwords, or secret-bearing environment output.
