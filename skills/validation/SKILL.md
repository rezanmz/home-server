---
name: validation
description: Validate a home-server manifest, catalog, secret, image-pin, or Helm change before review and verify the corresponding live result after merge. Use for CI parity, high-risk diffs, and completion evidence.
---

# Validate home-server changes

Validation has two distinct outcomes:

1. repository evidence that the proposed desired state is internally valid; and
2. live evidence, only after merge, that Flux applied the exact intended
   revision and the service works.

Never substitute one for the other. Running validation does not authorize a
push, merge, reconcile, baseline rewrite, or live mutation.

## Read before running

Read README.md's GitOps workflow, docs/service-operations.md from validation
through live proof, and .github/workflows/validate-cluster.yml. If catalog input
changed, also read docs/service-catalog.md. If a HelmRelease or pinned source
changed, inspect the workflow's independent fetch, checksum, render, schema, and
policy path rather than assuming the root Kustomize render covers it.

## Prepare the final desired state

- Work from the repository root.
- Preserve unrelated changes and identify exactly which diff is in scope.
- If a service descriptor changed, run the catalog render first and inspect all
  generated diffs. Never hand-edit generated regions.
- Build the same additional Flux child paths that CI builds. Rendering the root
  creates child Kustomization objects but does not render the resources those
  children later build.
- Use a new temporary rendered file; do not overwrite a repository artifact.

## Preflight

Run validation in a real Git checkout: the shell and Secret validators use
`git ls-files` to model the prospective tree. Confirm the basic runtime before
interpreting test failures:

    command -v git kubectl python3 >/dev/null
    python3 -c 'import yaml'
    git rev-parse --show-toplevel >/dev/null

PyYAML is an actual test dependency even though it may already exist on the
GitHub-hosted runner. Full CI parity additionally needs the exact actionlint,
yq, kubeconform, Helm, and schema pins declared by the current validation
workflow. Do not silently substitute ambient newer versions when comparing a
local result with CI.

## Repository-local gate

After the final edit, run every repository-owned check and render:

    set -euo pipefail
    if command -v actionlint >/dev/null 2>&1; then actionlint; fi
    scripts/ci/validate-shell.sh
    FLUX_VERIFY_ONLY=true scripts/bootstrap-flux.sh
    python3 -m py_compile scripts/*.py scripts/ci/*.py
    python3 scripts/ci/validate-agent-guidance.py
    python3 -m unittest discover --start-directory scripts/ci --pattern 'test_*.py'
    python3 scripts/ci/validate-secrets.py
    python3 scripts/ci/validate-application-state-ownership.py

    {
      kubectl kustomize clusters/home-server
      printf '\n---\n'
      kubectl kustomize infrastructure/snapshot-controller/storage
      printf '\n---\n'
      kubectl kustomize infrastructure/longhorn/readiness
      printf '\n---\n'
      kubectl kustomize infrastructure/longhorn/backups
      printf '\n---\n'
      kubectl kustomize apps/syncthing/backups
    } >/tmp/home-server.yaml

    test -s /tmp/home-server.yaml
    python3 scripts/service_catalog.py check --rendered /tmp/home-server.yaml
    python3 scripts/ci/validate-secrets.py --rendered /tmp/home-server.yaml
    python3 scripts/ci/check-high-risk-policy.py \
      /tmp/home-server.yaml scripts/ci/high-risk-baseline.txt
    python3 scripts/ci/validate-git-source-pins.py /tmp/home-server.yaml

`actionlint` is mandatory when a workflow changed and for a full parity claim;
its conditional form above lets unrelated local work reach the repository
checks on a workstation that lacks the pinned binary. Report that omission.

If the current workflow renders more children or runs more checks, extend the
local run to match it. Do not delete a current check because an older manual
omits it.

## Strict schemas and independent Helm rendering

For full CI parity, continue with the exact current blocks in
`.github/workflows/validate-cluster.yml`:

1. Run `scripts/ci/prepare-schema-manifest.py` on `/tmp/home-server.yaml`.
2. Run strict kubeconform with the workflow's Kubernetes version, schema
   repository commits, and schema-location URLs.
3. Run `scripts/ci/render-helm-releases.sh` against the root render. This fetches
   each immutable chart/source, verifies the configured identity and checksum,
   and refuses an uncovered HelmRelease.
4. Prepare the Helm schema manifest and run the workflow's strict Helm-output
   kubeconform block, skipping only CRDs as the workflow does.
5. Scan the Helm render against
   `scripts/ci/helm-high-risk-baseline.txt`.

These stages require network access and the workflow-pinned tools. A root
Kustomize render does not cover chart-generated RBAC, policies, host access, or
CRDs. If the network or a pinned upstream artifact is unavailable, report the
strict/Helm stage as unverified and rely on the protected CI run; do not call a
repository-only pass full CI parity.

## Interpret failures

- Catalog drift means regenerate and review; do not patch generated output.
- A plaintext/malformed Secret failure blocks review. Do not hide a Secret from
  the renderer or validator.
- A source-pin failure requires an immutable, reviewed source. Do not relax a
  digest or commit pin.
- A schema failure requires fixing the manifest or deliberately updating the
  pinned schema contract; do not disable strict validation.
- A Helm fetch, checksum, render, or policy failure blocks the change. A new
  HelmRelease is incomplete until CI independently renders and scans it.
- A high-risk finding is a security decision, not formatting noise.

When a high-risk change is intentional, inspect every old and new finding before
using the documented baseline writer. Review the resulting baseline diff, then
rerun the checker. Never write the baseline merely to turn CI green, and never
accept unrelated findings.

Stop if a required tool, immutable upstream artifact, schema, decryption
identity, or network fetch is unavailable. Report the exact unverified stage
instead of claiming that a partial bundle passed.

## Pull-request evidence

Before review, provide:

- concise changed-file and generated-file inventory;
- full bundle result from the final tree;
- explanation of each high-risk baseline delta;
- image/chart/source identity and architecture evidence when applicable;
- stateful recovery evidence required by the service manual;
- any difference between local checks and the protected workflow.

CI must pass on the exact PR revision. A prior green run or a local subset is
not sufficient.

## Post-merge live verification

Only when deployment/live verification is in scope:

1. Confirm the Flux GitRepository artifact and relevant Kustomization report the
   exact merged revision.
2. Check rollout status, desired/ready replicas, restarts, events, and expected
   node placement.
3. Check PVC binding and Longhorn/NFS/JuiceFS health as appropriate.
4. Require non-empty Service endpoints and HTTPRoute Accepted=True and
   ResolvedRefs=True where routed.
5. Test from the intended client network. Node-origin requests to private routes
   are expected to be denied.
6. Exercise one representative application operation and inspect relevant logs.
7. Confirm backup inclusion and recovery evidence for stateful changes.

Record commands or equivalent observations without disclosing secrets. If live
access is unavailable, say repository validation passed but deployment was not
verified.
