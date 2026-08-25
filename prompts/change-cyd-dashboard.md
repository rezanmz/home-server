# Task brief: change the CYD dashboard firmware

Change the Git-owned ESPHome dashboard source, publish and repin the updater only
when separately authorized, and prove the resulting firmware on both reserved
devices. Treat a pod rollout as two physical-device writes.

## Required inputs

- Repository and exact base revision: [path and `origin/main` commit]
- Desired visual/interaction/data behavior: [observable before/after]
- Hardware, display, touch, polling, or Finance API contract affected: [details]
- Both intended devices and current reservation identities: [hostnames/IPs;
  hardware identifiers only in an approved private channel]
- Physical observer and maintenance window for both devices: [person/time]
- Current updater full image reference and retained rollback digest: [references]
- Required updater platforms/placement: [discover from helper and cluster]
- Upstream ESPHome/component/font change, if any: [primary references]
- Secret or credential change: [none, or metadata/rotation plan without values]
- Physical/serial recovery availability: [method or explicitly unavailable]
- Acceptance checks for each screen and cross-device behavior: [list]

Never place a plaintext Wi-Fi value, bearer token, OTA password, decrypted Secret,
compiled production firmware, or age identity in this brief.

## Authorization

Fill every line with `yes` or `no` and an exact scope. Blank or ambiguous means
no; one permission never implies another.

- Repository edits: [yes/no; exact CYD/image/Kea/Finance paths]
- Local Docker compile/cache downloads: [yes/no; host and limits]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch; acknowledge automatic GHCR workflow]
- Dispatch or rerun an image workflow: [yes/no; workflow/ref]
- Publish/overwrite a registry tag: [yes/no; exact registry/repository/tag]
- Repin consumer image digests: [yes/no; exact Deployment]
- Open or update a pull request: [yes/no; target and draft/ready]
- Merge to protected `main`: [yes/no; exact PR and required checks]
- Read-only cluster/host/network access: [yes/no; targets]
- Live reconcile, restart, scale, or pod deletion: [yes/no; exact operation]
- Application-state mutation: [yes/no; exact Finance UI/API objects; normally no]
- OTA-write both physical devices: [yes/no; exact reserved identities]
- Change/restart Kea DHCP: [yes/no; desired and live scopes]
- Edit/rotate/revoke a Secret or external credential: [yes/no; exact copies]
- Manual serial/USB flash, erase, or device replacement: [yes/no; identity]

A qualifying branch push may publish a fixed GHCR tag before review. Repository
edit or branch-push authority does not silently authorize that registry side
effect; resolve the authorization conflict before pushing.

## Manuals and skills

Load the actual repo skills:

- [`home-server-safety`](../skills/home-server-safety/SKILL.md)
- [`device-firmware`](../skills/device-firmware/SKILL.md)
- [`custom-image-builds`](../skills/custom-image-builds/SKILL.md)
- [`service-lifecycle`](../skills/service-lifecycle/SKILL.md)
- [`validation`](../skills/validation/SKILL.md)
- [`secrets-sops`](../skills/secrets-sops/SKILL.md) if any Secret metadata or
  value changes
- [`network-services`](../skills/network-services/SKILL.md) if a reservation,
  address, MAC, OTA destination, or Kea state changes

Read [configuration ownership](../docs/configuration-ownership.md),
[service operations](../docs/service-operations.md), and the relevant
[runbook](../docs/runbook.md) sections. Inspect every active file linked from the
device-firmware skill; manuals override prompts.

## Workflow

1. Record the exact revision and worktree status. Prove
   `apps/cyd-ota` and `apps/kea` activity through the root Kustomization and
   preserve unrelated changes.
2. Establish a read-only baseline: current dashboard behavior on each device,
   ConfigMap name/reference, identical updater image pins, init logs/events,
   device reservations and leases, OTA reachability, and current Flux revision.
3. Map coupling before editing:
   - firmware source to generated ConfigMap and Deployment reference;
   - both upload destinations to both exact NetworkPolicy egress peers and Kea
     reservations;
   - device bearer authorization to the Finance service token;
   - both updater containers to one immutable manifest digest.
4. Classify ownership. `apps/cyd-ota/dashboard.yaml` is Git-owned firmware
   configuration, not application UI state. Keep Finance focus state in its
   existing backend. Keep production device inputs only in SOPS.
5. Make the smallest dashboard edit. Preserve hardware pins, display/touch
   calibration, TLS verification, bearer header, JSON error/stale handling, and
   polling unless the requested outcome explicitly changes them.
6. If local Docker work is authorized, compile with the Dockerfile's fake
   build-only inputs. Do not use production Secrets. Record that this proves only
   a local architecture/config compile—not Wi-Fi, OTA, policy, Finance API,
   physical display/touch, pushed digest, SBOM, or provenance.
7. Before any branch push, inspect the current image workflow's branch/path
   filters. If the push qualifies, announce that it will publish to GHCR. Do not
   push without both branch and registry authority.
8. If publication is authorized, use the repository helper through
   `custom-image-builds`, capture the exact pushed manifest digest/platform, and
   repin both init and completion containers to the same full reference. Preserve
   the prior digest. A later `main` rebuild moving the tag does not change the
   reviewed digest; investigate differing output rather than following the tag.
9. Render `apps/cyd-ota` before and after. Prove dashboard content changes the
   generated ConfigMap name and rewrites the Deployment reference. Do not delete
   stale generated ConfigMaps; root pruning is disabled.
10. Run complete `validation`, including Secret, schema, catalog, image-pin,
    high-risk, and Helm stages. If Kea changes, run its reservation tests and
    review the network-critical Recreate rollout separately. A local ESPHome
    compile is not repository validation.
11. Open/merge only within authority. Require protected validation on the exact
    PR revision and a reviewed updater digest before merge. The push-triggered
    image workflow is not an ordinary PR validation trigger.
12. After an authorized merge, wait for Flux to report the exact merged revision.
    The ConfigMap hash should recreate the OTA pod; do not manually restart it
    merely because reconciliation is still in progress.
13. Observe the init compile and both sequential uploads. Both are attempted even
    if the first fails. Any one failure leaves the Deployment unready, but the
    other device may already be running new firmware; retries attempt both again.
14. Verify each device physically: boot, screen layout/readability, finance data
    refresh with no credential disclosure, stale/error behavior, touch action,
    and focus propagation to the other screen. Deployment Ready is not physical
    firmware proof.

## Hard stops

Stop before merge or OTA when:

- either device identity, reservation, address, or physical availability is
  ambiguous;
- upload destinations, NetworkPolicy peers, and Kea reservations disagree;
- a branch push would publish without registry authority;
- the helper's pushed digest or platform cannot be proved and repinned in both
  containers;
- production credentials would enter Git, image context, logs, or local output;
- a bearer/Wi-Fi/OTA rotation lacks a coordinated transition and recovery path;
- the ConfigMap hash/reference does not change with the intended firmware source;
- compile, complete validation, or protected CI fails;
- only one device succeeds and no explicit partial-rollout decision exists;
- Flux is not at the exact merged revision; or
- physical verification or recovery is unavailable.

Do not loosen egress, delete/restart pods repeatedly, follow a mutable image tag,
or bypass protected `main` to make progress.

## Rollback and recovery

Record the prior dashboard Git revision, ConfigMap content source, updater
manifest digest, device credential set, and observed firmware state of each
device. Rollback is a new OTA transaction: restore the prior dashboard and a
compatible pinned updater image through Git, validate, merge, and observe both
uploads.

Reverting only the image digest does not revert dashboard source. Reverting Git
cannot recover a device that no longer boots, joins Wi-Fi, or accepts OTA. Stop
for an explicitly authorized, documented physical recovery rather than inventing
a serial-flash procedure. Do not clean up old generated ConfigMaps incidentally.

## Evidence contract

Return:

- exact base, PR, merged, and Flux revisions;
- ownership/coupling map and changed-file inventory;
- local compile command/result and its stated limitations;
- every branch/workflow/registry action and captured manifest digest/platform;
- rendered ConfigMap hash/reference and identical image pins;
- complete validation and protected-CI results;
- per-device OTA result, including partial/retry history;
- physical acceptance on each screen and cross-device synchronization;
- non-secret Secret/Kea/NetworkPolicy evidence;
- rollback artifacts and every skipped or unauthorized check.

## Acceptance criteria

- [ ] The requested firmware behavior is encoded in the Git-owned dashboard
      without taking ownership of Finance application state.
- [ ] No production credential or compiled secret-bearing artifact leaks.
- [ ] Registry publication and immutable repinning occur only under explicit
      authority; both containers use the reviewed digest.
- [ ] The rendered ConfigMap hash drives the intended rollout and full validation
      passes.
- [ ] Both reserved devices upload, boot, render, refresh, and synchronize as
      specified at the exact merged revision, or deployment is explicitly
      reported incomplete.
- [ ] Rollback accounts for each device independently and does not assume OTA
      remains reachable.
