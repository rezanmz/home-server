---
name: custom-image-builds
description: Review, build, publish, or deploy repository-maintained container images under images/ using the home-server build helpers and workflows. Use when changing a custom Dockerfile, publishing an image, capturing a manifest digest, or updating a workload to a custom build; do not use for ordinary third-party image digest bumps.
---

# Custom image builds

Every repository build helper performs a remote registry push. None is a local
dry-run or `--load` helper. Treat invocation as publication, not compilation.

## Authoritative files

Inventory the current helpers rather than relying on a fixed list:

```bash
rg -n -- '--push|--platform|--tag|--build-arg|--provenance|--sbom' scripts/build-*-image.sh scripts/build-*-images.sh
find images -name Dockerfile -print
find .github/workflows -type f -name '*image*.yml' -print
```

Read the selected helper and Dockerfile in full, then find every consumer of the
image with `rg`. Current build entry points include:

- [CYD OTA helper](../../scripts/build-cyd-ota-image.sh) and
  [Dockerfile](../../images/cyd-ota/Dockerfile)
- [Finance display helper](../../scripts/build-finance-display-image.sh) and
  [Dockerfile](../../images/finance-display/Dockerfile)
- [LlamaCloud MCP helper](../../scripts/build-llamacloud-mcp-image.sh) and
  [Dockerfile](../../images/llamacloud-mcp/Dockerfile)
- [MCP V8 helper](../../scripts/build-mcp-v8-image.sh) and
  [Dockerfile](../../images/mcp-v8/Dockerfile)
- [MCPHub/GPTR helper](../../scripts/build-mcphub-gptr-image.sh) and
  [Dockerfile](../../images/mcphub-gptr/Dockerfile)
- [Stork helper](../../scripts/build-stork-images.sh) and its reviewed patches

Some helpers have GitHub workflows and some are manual-only. Read the actual
workflow path filters, branch filters, registry login, permissions, platforms,
and timeout from [`.github/workflows`](../../.github/workflows); do not infer
pre-merge coverage from the existence of a workflow.

## Publication authorization gate

Before running any helper, display and verify:

- clean source checkout and exact Git commit
- helper and Dockerfile being used
- registry and namespace
- image name and exact tag
- requested target platforms
- whether that tag already exists
- which remote credentials will be used
- whether a branch push will also trigger a workflow publication

Then confirm that the user's request authorizes pushing that exact remote tag.
Editing a Dockerfile, running tests, or reviewing a build does not authorize a
registry push. If publication is not authorized, inspect and validate without
invoking the helper; do not silently replace `--push` with a different build
mode and claim equivalence.

The workflows are push-triggered, not general pull-request checks. Their branch
and path filters are authoritative. A qualifying branch push can publish the
same fixed release tag used by another build. This is an externally visible,
potentially overwriting side effect even though deployed manifests remain
digest-pinned. State this risk before pushing the branch or dispatching the
workflow.

Do not publish from a dirty checkout. Untracked files can enter a Docker build
context; this is especially important for helpers whose context is the repository
root. Confirm ignored and untracked content and ensure no decrypted secret, age
identity, kubeconfig, credential, or unrelated local artifact can be sent to the
BuildKit daemon.

## Preflight

1. Find every runtime consumer and record its current full
   `repository:tag@sha256:digest` reference and rollback digest.
2. Read upstream release notes and verify every base image, source revision,
   downloadable asset, checksum, lockfile, patch, and package pin changed by the
   build.
3. Read the helper's `PLATFORMS` or `PLATFORM` declaration. Confirm every target
   architecture is supported by all `FROM` images, downloaded assets, native
   dependencies, tests, and the intended workload placement. Some repository
   images are intentionally single-platform; others publish an index.
4. Confirm registry authentication and quota without printing credentials.
5. Determine which tests run before publication and which run only inside the
   Docker build. A push workflow that runs tests during the build may publish
   nothing on failure, but invoking it still consumes remote/build resources.
6. Ensure the tag uniquely represents the intended content. If content inputs
   change without a corresponding tag/revision change, stop rather than
   overwriting an indistinguishable release.
7. Run applicable source-level tests and repository validation before the
   authorized publication where possible.

## Image-specific invariants

### CYD OTA

The helper uses a broad build context. Recheck context contents and the dashboard
contract before publication. Read the current platform from the helper; do not
assume that a multi-platform builder means the image is multi-platform.

### Finance display

The Dockerfile owns application dependency installation and tests. Inspect the
lockfile and test results produced by the build. After publication, verify every
platform in the manifest index rather than only the top-level digest.

### LlamaCloud MCP and MCP V8

These may lack an automated publishing workflow. Do not interpret “manual-only”
as permission to use default registry credentials. For architecture-specific
assets and checksums, verify each platform independently.

### Stork

The helper clones an upstream tag, verifies its exact commit, applies repository
patches, and publishes selected components. Review the tag/commit pair, patch
application, component selection, target platform, and all resulting digests.
Do not use an upstream tag alone as identity.

### MCPHub/GPTR coupling gate

Before every MCPHub publication, compare
[the build helper](../../scripts/build-mcphub-gptr-image.sh) with
[the Dockerfile](../../images/mcphub-gptr/Dockerfile):

- The helper constructs the release tag from several version/revision constants.
- The Dockerfile independently declares many corresponding ARG defaults.
- The helper currently forwards only a subset of those values as build args;
  constants present only in the helper may not affect image contents.

Use `rg` to map every helper constant to the Docker build invocation, Dockerfile
ARG, OCI label/tag, installed artifact, and manifest consumer. Refuse publication
if:

- a tag component changes without changing the installed content;
- installed content changes without changing the identifying tag/revision;
- overlapping helper and Dockerfile values disagree;
- a helper constant is assumed to override a Dockerfile ARG that is not passed;
- the suite/tag revision does not uniquely describe the built image.

Prefer fixing the coupling or establishing one source of truth in the same
reviewed change. Do not paper over it by editing only the final tag.

## Publish and capture identity

When publication is authorized, run the repository helper unchanged with only
reviewed namespace/builder/platform overrides. Capture the complete build log
location and the helper's final `docker buildx imagetools inspect` digest.

Independently inspect the pushed reference:

- confirm the top-level digest;
- enumerate platform manifests and verify the expected architecture set;
- confirm tag, OCI source/revision/version labels where present;
- confirm the registry points the reviewed tag to the captured digest;
- record SBOM and provenance attestation presence where the registry exposes it.

SBOM and `provenance=mode=max` are metadata, not signatures, vulnerability
approval, reproducibility proof, or admission enforcement. Mutable package
repositories and incompletely locked transitive dependencies can still make two
builds differ. State these limits in the report.

## Deploy the digest

Update consumers only to the captured full `repository:tag@sha256:digest`.
Never deploy by tag alone and never copy a per-platform child digest where the
workload needs the multi-platform index. Preserve the prior reference for revert.

Run the complete validation workflow, review the rendered high-risk image
boundary, and use Git/Flux for rollout. After an authorized merge, verify Flux at
the exact merged revision, the running pod's image ID/digest, target-node
architecture, rollout, endpoints/routes, and service-specific behavior.

## Abort conditions and evidence

Stop before publication or deployment if the checkout is dirty, the target tag
is ambiguous, registry authority is absent, a target platform is unsupported,
an upstream pin/checksum cannot be verified, tests fail, MCPHub coupling is
inconsistent, the remote digest cannot be captured, or the intended tag points
to unexpected content.

Report source commit, helper, registry/tag, platforms, upstream pins, tests,
publication authorization, manifest and child digests, attestation presence and
limits, deployed manifest diff, rollback digest, and live verification. Never
claim a local inspection published or deployed an image.
