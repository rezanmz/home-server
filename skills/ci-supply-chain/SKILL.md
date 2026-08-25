---
name: ci-supply-chain
description: Modify or audit the home-server GitHub Actions validation contract, action/tool pins, schema sources, Flux/Helm source verification, or CI supply-chain controls. Use for workflow changes, CI failures caused by validators/renderers, checksum updates, and new Helm/source coverage; do not use for routine application changes that only need to run existing validation.
---

# CI and supply-chain maintenance

Keep validation reproducible, read-only with respect to the cluster, and strict
about immutable inputs. CI validates desired state; Flux deploys after merge.

## Sources of truth

Read the complete files relevant to the change:

- [Cluster validation workflow](../../.github/workflows/validate-cluster.yml)
- [CI helpers and tests](../../scripts/ci)
- [Immutable Helm renderer](../../scripts/ci/render-helm-releases.sh)
- [Flux Git source validator](../../scripts/ci/validate-git-source-pins.py)
- [Flux bootstrap verifier](../../scripts/bootstrap-flux.sh)
- [Renovate policy](../../renovate.json)
- [CODEOWNERS](../../.github/CODEOWNERS)
- [Service validation manual](../../docs/service-operations.md#8-validate-before-the-pull-request)
- [Architecture validation model](../../docs/architecture.md)

Discover current runner images, action commits, tool versions/checksums, schema
commits, Kubernetes version, render inputs, chart identities, and source pins
from these files. Do not duplicate mutable values in a new guide or assume an
older CI log is current.

## Authorization and side effects

- Workflow/helper inspection and local validation are read-only with respect to
  GitHub and the cluster, though external chart/source fetches use the network.
- Editing CI is permitted only when requested. Do not weaken checks to make an
  unrelated manifest pass.
- Running or rerunning a GitHub workflow, pushing a branch, dispatching an image
  build, changing branch protection/CODEOWNERS enforcement, or publishing an
  artifact is an external mutation requiring scope from the user.
- Validation workflows must not SSH to cluster nodes, hold deployment
  credentials, apply resources, or use cluster nodes as self-hosted runners.
- Preserve least-privilege workflow permissions and avoid persisted checkout
  credentials unless a reviewed job requires them.

## Preserve the validation contract

The workflow's order is intentional. Maintain coverage for:

- workflow lint and helper syntax/tests
- Flux bootstrap verify-only behavior
- source and rendered Secret validation
- application-state ownership regressions
- the complete root plus independently reconciled manifest bundle
- service-catalog/generated-output consistency
- sanitized strict Kubernetes/CRD schema validation
- root high-risk baseline
- immutable Flux Git source tag/commit validation
- independent immutable Helm fetch and render
- sanitized strict Helm-output schema validation
- Helm high-risk baseline

When adding a separately reconciled child, determine whether it must be added to
the combined render. When adding a HelmRelease, extend the immutable renderer;
its exact identity comparison must continue to fail closed when any rendered
HelmRelease lacks coverage.

Do not silently change strict validation to ignore missing schemas. If a CRD or
schema truly cannot be validated, document the narrow exception and test it.

## Preflight a supply-chain change

1. Define the trust boundary being changed: workflow action, downloaded tool,
   schema repository, container image, OCI chart, Git chart/source, bootstrap
   installer/manifest, or custom image.
2. Record the current and proposed immutable identifiers and every place they
   are coupled. Use `rg`; do not assume Renovate found every occurrence.
3. Use primary upstream release metadata. Verify tags against full commits and
   downloaded bytes against a published or independently reviewed checksum.
4. Inspect permissions, credential persistence, runner selection, network
   downloads, command interpolation, and untrusted PR inputs.
5. Determine whether the change alters rendered cluster resources, schemas,
   policy findings, or test fixtures.
6. Preserve a rollback reference and explain how validation will fail closed if
   the new artifact drifts.

## Pinning rules

### GitHub Actions

Use a full action repository commit in every `uses:` reference. Verify that the
human-readable release tag resolves to that commit; comments are not the pin.
Retain GitHub-hosted runners, minimal job/workflow permissions, bounded timeouts,
and `persist-credentials: false` where checkout does not need to push.

Do not introduce a tag-only action because actionlint accepts it: actionlint
checks syntax, not immutable pin policy.

### Downloaded CI tools

Fetch over HTTPS, pin a release, verify the exact archive/binary SHA256 before
execution, and avoid `curl | sh`. Update version and checksum as one reviewed
change. Confirm archive layout and executable identity rather than trusting a
successful download.

### Kubernetes and schemas

Keep kubectl, kubeconform target version, Helm `--kube-version`, and pinned
schema sources coherent. Search the repository for every occurrence when the
target version changes. A schema bump can expose previously hidden invalid
manifests; do not suppress those failures globally.

### Flux Git sources

Require HTTPS plus a release tag and full immutable commit. Use
[validate-git-source-pins.py](../../scripts/ci/validate-git-source-pins.py) to
prove the tag resolves to the commit. Treat the root `main` source separately:
it is intentionally mutable so Flux can follow the protected desired-state
branch.

### Helm sources

For OCI charts, preserve tag, registry digest, and the renderer's independent
package checksum. For Git-hosted charts, preserve tag plus exact commit and
verify the fetched checkout. Review fully rendered RBAC, security contexts,
host access, CRDs, routes, storage, and networking—not only Helm values.

### Flux and K3s bootstrap

Read each bootstrap/install helper in full. Version bumps must update all
associated installer checksums, generated manifest checksums, and controller or
image digests. Run verify-only modes where provided. Never convert a fresh-host
installer into an improvised live-cluster upgrade procedure.

## Tests and local verification

Run the exact current workflow commands in the workflow's order. Ensure local
prerequisites match CI, including Python modules and the pinned external tools.
Do not claim parity from README snippets if they omit workflow steps.

For helper changes:

- add or update behavioral tests for the security invariant, not only string
  snapshots;
- run workflow lint and shell syntax validation;
- run the full Python test discovery in a real Git checkout;
- render the complete manifest bundle;
- run schema, Secret, catalog, Git-pin, root high-risk, Helm render, Helm schema,
  and Helm high-risk checks;
- inspect network-fetched artifact identities in the logs.

Do not update baselines until their changed findings have been reviewed with
[high-risk-review](../high-risk-review/SKILL.md).

## Abort conditions

Stop if:

- a release tag cannot be tied to the proposed commit or checksum;
- a workflow action is not full-commit pinned;
- a downloaded artifact executes before verification;
- permissions broaden without a specific requirement;
- a job would receive deployment credentials, SSH to a node, or run on a cluster
  node;
- a HelmRelease or separately reconciled child falls outside intended render
  coverage;
- a schema or high-risk failure is being hidden rather than resolved;
- the exact workflow cannot run because a prerequisite is implicit or missing;
- full validation fails.

## Known coverage limits

State these limits rather than overstating CI:

- There is no dedicated policy test that rejects future tag-based actions or
  self-hosted runners; review must enforce those invariants until such a test is
  added.
- Non-Helm manifests fetched by Flux Git sources are pinned at the source
  boundary but are not necessarily fetched, rendered, schema-checked, and
  high-risk scanned by CI.
- Checksums, digests, SBOMs, and provenance do not by themselves verify
  signatures, vulnerabilities, reproducibility, or admission policy.
- Source Secret checks focus on Kubernetes Secret resources and do not prove
  arbitrary files contain no credentials.
- Live drift, remote backup readability, runtime authorization, and successful
  Flux deployment are outside CI's proof.
- Local documentation can lag the workflow, and the Python test environment has
  implicit module requirements. The workflow remains authoritative.

Report the trust boundary, old/new immutable identities, upstream verification,
permissions and runner impact, render/test coverage, full validation evidence,
rollback, and every remaining supply-chain or runtime gap.
