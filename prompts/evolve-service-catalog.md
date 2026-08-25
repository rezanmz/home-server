# Task brief: evolve the service catalog

Evolve the catalog schema/compiler with a deterministic, versioned adapter that
solves `[MODELING/INTEGRATION GAP]` without turning the catalog into a runtime
controller or taking ownership of application state.

## Required inputs

- Concrete gap and affected active services/descriptors: [examples]
- Current schema/profile/apiVersion behavior: [facts]
- Desired declarative input and generated/validated output: [contract]
- Why this is cross-service/repetitive rather than service-specific YAML: [reason]
- Backward-compatibility and migration requirements: [details]
- Existing generated outputs/adapters affected: [inventory]
- Semantic facts the compiler can and cannot prove: [boundaries]
- Proposed tests and documentation examples: [cases]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; schema/compiler/tests/docs/descriptors/generated paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Read-only cluster/host access: [yes/no; semantic comparison only]
- Live cluster/host mutation: [yes/no; normally no]
- Application-state mutation: [yes/no; normally no]
- External/provider mutation: [yes/no; normally no]
- Destructive actions: [yes/no; generated/provider cleanup identities]

Compiler/schema edit permission does not authorize changing live services,
application databases, Authentik/provider objects, or deleting prior integrations.

## Manuals and skills

Load `home-server-safety`, `service-catalog`, `configuration-ownership`,
`validation`, `ci-supply-chain`, and task-specific `network-auth`, `secrets-sops`,
`storage-recovery`, or `backup-restore` when the adapter touches those domains.
Read service-catalog and service-catalog-design fully, plus architecture,
configuration-ownership, service-operations, compiler tests, current schemas,
and generated targets.

## Workflow

1. Reproduce the gap with real active descriptors/manifests. Prove that a narrow
   explicit workload field or documentation fix is insufficient.
2. Apply the admission test: the feature must represent cross-service intent,
   derive deterministic reviewable output from explicit input, support CI tests
   and `explain`, and avoid privileged runtime reconciliation.
3. Define schema types, invariants, defaults, errors, ownership text, adapter
   inputs/outputs, stable identities, and semantic limits before implementation.
   Reject arbitrary YAML, templates, recursive inheritance, and hidden inference.
4. Preserve existing profile behavior. Use a new profile version for new behavior
   and a new apiVersion plus deterministic migration for breaking descriptor
   semantics. Keep older valid descriptors deterministic during transition.
5. Update schema, compiler validation/generation/explanation, focused unit tests,
   negative/unknown-field tests, manuals, examples, affected descriptors, and
   committed generated output in one change.
6. Render twice and prove determinism/idempotence. Inspect every generated diff
   and run summary/explain/check against the complete rendered root/child bundle.
7. Independently inspect active mounts, storage classes, backup objects,
   placement, routes, claims, callbacks, roles, and monitoring. A successful
   compiler check proves relationships, not that descriptor prose matches runtime.
8. Run the complete validation and supply-chain/Helm checks. If cleanup of prior
   Authentik/DNS/live objects is needed, make it a separately authorized lifecycle
   step; disappearing generated intent does not imply provider/live deletion.

## Hard stops

Stop when the feature needs arbitrary YAML, recursive overrides, application DB
rewrites, a CRD/controller, cluster credentials at runtime, nondeterministic
discovery, hidden defaults, or incompatible mutation of an existing profile. Stop
if the schema cannot truthfully express storage/data authority; propose a versioned
model rather than forcing a false enum or note. Unknown fields must remain errors.

## Rollback and recovery

Preserve old schema/profile behavior and define reverse descriptor migration.
Generated output can be regenerated from the prior compiler/input, but external
provider objects and root-owned live objects may persist and require explicit
cleanup. Name stable identity migrations that make a simple revert unsafe.

## Evidence contract

Return admission rationale, schema/adapter contract, compatibility matrix,
changed descriptors and generated targets, unit/negative/determinism results,
`explain` ownership output, complete rendered check, independent semantic
verification, validation/CI results, and any deferred live/provider cleanup.

## Acceptance criteria

- [ ] The extension is deterministic cross-service intent with clear ownership.
- [ ] Existing versioned behavior remains stable or has an explicit migration.
- [ ] Schema, compiler, tests, manuals, descriptors, and generated output agree.
- [ ] Catalog checks and independent runtime-semantic inspection both pass.
- [ ] No runtime controller, arbitrary template surface, or application-state
      reconciliation is introduced.
