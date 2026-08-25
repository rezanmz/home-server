---
name: high-risk-review
description: Investigate and review home-server high-risk policy findings or intentional baseline changes involving privilege, host access, RBAC, images, routes, network boundaries, storage, Flux, or Helm output. Use when CI reports a high-risk baseline delta or a change introduces one of these boundaries; do not use as a substitute for a broader security review.
---

# High-risk baseline review

The baselines are review locks. A match means the exact accepted inventory did
not change; it does not mean the cluster has no high-risk constructs.

## Authoritative implementation

Read these before interpreting a finding:

- [Policy checker](../../scripts/ci/check-high-risk-policy.py)
- [Root rendered baseline](../../scripts/ci/high-risk-baseline.txt)
- [Independently rendered Helm baseline](../../scripts/ci/helm-high-risk-baseline.txt)
- [Validation workflow](../../.github/workflows/validate-cluster.yml)
- [Service validation and baseline instructions](../../docs/service-operations.md#8-validate-before-the-pull-request)
- [Architecture security boundaries](../../docs/architecture.md)

The checker source, not a remembered category list, defines current coverage and
canonicalization. Read the matching rule and inspect the rendered resource that
produced each finding.

## Authorization boundary

- Rendering and comparing findings are read-only.
- A request to diagnose CI does not authorize accepting findings into a
  baseline.
- Update a tracked baseline only when the user requested the underlying
  high-risk change or an intentional baseline refresh and every changed entry
  has been reviewed.
- Do not change workload security, networking, RBAC, routes, storage, or source
  pins merely to restore a textual match without understanding the runtime
  effect.
- Baseline edits do not authorize live cluster actions or a merge to `main`.

Never run `--write-baseline` against the tracked file as the first diagnostic
step. It replaces the complete accepted inventory and can silently accept
unrelated findings.

## Produce a clean, exact diff

1. Start from a known Git state and record the base revision and candidate diff.
   Separate pre-existing unrelated changes.
2. Render the same complete bundle used by
   [the workflow](../../.github/workflows/validate-cluster.yml). Do not validate
   only the edited directory.
3. Run the checker against the tracked root baseline and preserve its diff.
4. Independently render all Helm releases with
   [render-helm-releases.sh](../../scripts/ci/render-helm-releases.sh), then run
   the checker against the Helm baseline.
5. To preview canonical candidate baselines without changing Git, copy each
   tracked baseline to a temporary directory, run `--write-baseline` against the
   temporary copy, and diff tracked versus temporary.
6. Confirm the rendered manifest and temporary files are nonempty and from the
   same candidate revision before reviewing entries.

Review both additions and removals. A removed/stale entry may represent a real
security improvement, an accidental loss of a needed control, a renamed object,
or a render-coverage regression.

## Review every entry

For each changed canonical finding, identify:

- rendered kind, namespace/name, container or rule identity, and exact field
- source manifest, generator, Helm values/post-renderer, or remote source that
  owns it
- what capability or trust boundary changed
- reachable principals, networks, nodes, host paths, secrets, tokens, or data
- why the construct is necessary
- whether a narrower alternative exists
- expected runtime effect and rollback
- whether CODEOWNERS/manual review and stateful or network-critical gates apply

Treat these as especially sensitive: privileged containers/namespaces,
hostNetwork/hostPID/hostIPC, host paths/ports, root or added capabilities,
service-account token mounting, wildcard or secret/exec RBAC, cluster-admin,
unrestricted ingress/egress, missing default deny, public routes, authentication
middleware, external Services, local storage, mutable/unpinned images, and
Flux/Helm source boundary changes.

A finding hash changing can mean any canonicalized subfield changed. Inspect the
actual before/after resource; do not approve based on the category label alone.

## Decide the result

Choose one outcome per finding:

- **Reject:** unintended or broader than required; fix the manifest or source.
- **Narrow:** preserve the feature with less privilege, scope, exposure, or
  mutability, then rerender.
- **Accept intentionally:** document necessity, blast radius, controls, and
  rollback, then update the appropriate baseline.
- **Remove intentionally:** confirm functionality remains and retain the stale
  baseline deletion as evidence of the reduced/changed boundary.
- **Coverage defect:** fix the render/checker coverage before considering the
  underlying change accepted.

Only after all entries are classified may the tracked baseline be regenerated
or edited. Immediately inspect `git diff -- scripts/ci/*high-risk-baseline.txt` and
confirm it contains only reviewed canonical entries. Rerun both checkers against
fresh renders.

Never use a commit message or PR label as a substitute for the entry-by-entry
review.

## Validation

Run the full current validation sequence from
[`.github/workflows/validate-cluster.yml`](../../.github/workflows/validate-cluster.yml),
including strict schema checks, Secret validation, catalog checks, source pins,
and Helm coverage. A passing high-risk checker alone is insufficient.

For an authorized merged change, live verification must cover the exact merged
revision and the relevant boundary: security context/RBAC, node/host access,
NetworkPolicy, route/authentication, storage, or source/controller behavior.

## Abort conditions

Stop without updating the baseline if:

- the render is partial, stale, empty, or from a different revision;
- Helm rendering or release-coverage comparison fails;
- any changed entry cannot be mapped to source and runtime effect;
- unrelated findings are mixed into the candidate inventory;
- an accepted privilege/exposure lacks a concrete necessity and rollback;
- the proposed action is “regenerate until CI is green”;
- the checker or render coverage changed without tests proving the intended
  boundary;
- full validation fails.

## Known limits

The checker is heuristic. It cannot understand arbitrary fields inside every
CRD, detect every credential-like value, assess application authorization, or
prove runtime enforcement. Independently rendered Helm output is scanned, but
non-Helm manifests fetched later by Flux Git sources are not necessarily
rendered and policy-scanned by CI. Baselines also do not evaluate image
signatures, vulnerabilities, or live drift.

Report root and Helm diffs separately, the source and meaning of every entry,
decision and rationale, alternative considered, validation evidence, live proof
if authorized, and all unscanned or unverified surfaces.
