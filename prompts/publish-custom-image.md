# Task brief: publish a custom image

Build and publish repository-owned image `[IMAGE]` reproducibly, capture its
multi-platform manifest digest and provenance, then update consumers only if
separately authorized.

## Required inputs

- Image directory, Dockerfile, build helper, and workflow: [paths]
- Purpose and why a reviewed upstream image is insufficient: [reason]
- Upstream source release/tag/commit and checksum/provenance: [values/links]
- Repository patches and imported binaries/packages: [inventory]
- Required platforms and runtime placement: [architectures/nodes]
- Registry/repository and tag policy: [target]
- Build-time secrets or credentials: [names/transport only, never values]
- Test, SBOM, provenance/attestation, and vulnerability expectations: [details]
- Consumer manifests and current rollback digest: [paths/reference]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; image/build/workflow/consumer paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Read-only cluster/host access: [yes/no; architecture/runtime checks]
- Live cluster/host mutation: [yes/no; consumer rollout scope]
- Application-state mutation: [yes/no; normally no]
- External/provider mutation: [yes/no; exact registry publish/tag/attestation]
- Destructive actions: [yes/no; tag/package deletion, normally no]

Repository-edit permission does not authorize publishing to a registry. Registry
publish permission does not authorize changing or deploying consumers.

## Manuals and skills

Load `home-server-safety`, `custom-image-builds`, `ci-supply-chain`,
`service-lifecycle`, and `validation`; load `service-catalog` and
`configuration-ownership` if the
image changes runtime integration or ownership. Read service-operations custom-
image and image-pin guidance, architecture supply-chain rules, the existing
image's build helper/workflow, and the affected service runbook.

## Workflow

1. Inspect the closest existing repository image pattern and the complete build
   context. Minimize copied files and prove no plaintext secret or private key is
   included.
2. Resolve upstream input to immutable source evidence. Verify moved-tag guards,
   checksums for downloaded artifacts, package lockfiles, license, patch purpose,
   and reproducibility. Pin all base/runtime inputs as the existing pattern
   requires.
3. Build and test every required platform. Use GitHub-hosted runners for
   repository automation; never register a cluster node as a runner or store
   cluster deployment credentials in Actions.
4. Produce the repository's expected SBOM and provenance attestations. Inspect
   the published manifest list and record its digest and platform members.
5. Publish only to the exact authorized repository/tag. Do not overwrite or
   delete existing tags unless destructive authority names them.
6. If consumer edits are authorized, update `repository:tag@digest` together,
   preserve the previous digest, and adjust probes/security/config only for
   evidenced image behavior. Do not deploy unless live authority is explicit.
7. Run image-specific tests plus the complete cluster validation bundle. Review
   generated, source-pin, secret, schema, and high-risk results.
8. If rollout is authorized, prove the exact merged revision pulls the intended
   digest on each required architecture and passes service acceptance.

## Hard stops

Stop for mutable/unverified upstream input, missing checksum or license,
secret-bearing build context/logs/arguments, unavailable required platform,
failed test or vulnerability policy, missing manifest digest/provenance, use of a
cluster node as CI runner, unsupported upstream-development risk without explicit
acceptance, or absent registry authorization.

## Rollback and recovery

Retain the prior manifest-list digest and consumer Git revision. Do not delete the
old registry artifact while rollback depends on it. Explain data/config migration
compatibility before consumer rollout; use a matching backup or forward fix if
the previous binary cannot read new state.

## Evidence contract

Return immutable upstream identities/checksums, patch and dependency inventory,
platform test results, non-secret build/publish workflow evidence, manifest-list
digest/platforms, SBOM/provenance locations, consumer diffs, validation/CI results,
registry actions, and exact live digest/revision proof if deployed.

## Acceptance criteria

- [ ] Inputs are immutable, licensed, checksum/provenance verified, and secret-free.
- [ ] Every required platform builds and tests successfully.
- [ ] Published output has a recorded manifest digest and expected attestations.
- [ ] Consumers remain tag-and-digest pinned with the previous digest retained.
- [ ] Repository, registry, PR, and rollout actions stay within separate authority.
