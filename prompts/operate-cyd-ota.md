# Task brief: operate or recover CYD OTA delivery

Inspect, retry, pause, or recover the in-cluster CYD updater without confusing a
Kubernetes pod action with a harmless restart. Every init execution compiles and
attempts OTA writes to both reserved devices.

## Required inputs

- Requested mode: [read-only diagnosis / retry current firmware / complete a
  partial rollout / credential transition / address change / rollback]
- Exact repository, merged, and Flux revisions: [commits]
- Current Deployment, pod, generated ConfigMap, and updater image digest: [IDs]
- Current and previous init outcomes for each device: [redacted logs/status]
- Both intended Kea reservations and observed lease/reachability: [identities]
- Physical state of each screen: [boot/display/data/touch/Wi-Fi/OTA]
- Last known-good dashboard revision and updater digest: [rollback identities]
- Suspected failure domain: [compile/image/Secret/DNS-HTTPS egress/OTA policy/
  reservation/device power or firmware]
- Maintenance window and physical observer: [details]
- Credential change or compromise: [none or type/copies, never values]
- Physical/serial recovery availability: [method or explicitly unavailable]

Do not paste Secret data, bearer headers, Wi-Fi or OTA passwords, decrypted
firmware, broad lease dumps, or age identities.

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact paths]
- Local compile/cache mutation: [yes/no; scope]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; branch/tag and acknowledged automatic GHCR publication]
- Dispatch or rerun an image workflow: [yes/no; exact workflow/ref]
- Publish or overwrite a registry artifact: [yes/no; exact registry/tag]
- Open or update a pull request: [yes/no; target and state]
- Merge protected `main`: [yes/no; exact PR and required checks]
- Read-only cluster/host/network access: [yes/no; exact resources]
- Read non-secret pod logs/events and bounded lease entries: [yes/no]
- Live cluster/host mutation (reconcile, scale, restart, or delete updater resources): [yes/no; operation]
- Application-state mutation: [yes/no; exact Finance UI/API objects; normally no]
- External/provider mutation not otherwise listed: [yes/no; exact objects and operations]
- Re-attempt OTA to both devices: [yes/no; exact reserved identities]
- Pause repeated OTA attempts through exceptional live mitigation: [yes/no;
  exact Flux/workload scope]
- Change or restart Kea DHCP: [yes/no; exact desired/live operations]
- Edit/rotate/revoke bearer, Wi-Fi, or OTA credentials: [yes/no; exact copies]
- Destructive actions not otherwise listed: [yes/no; exact resource, data, or device identities]
- Manual serial/USB recovery, erase, or replacement: [yes/no; exact device]

Read-only diagnosis does not authorize a pod deletion. Deleting or restarting the
pod retries both physical devices. Git edit, registry, merge, live-cluster, DHCP,
credential, and device-write permissions remain separate.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals and skills

Load:

- [`home-server-safety`](../skills/home-server-safety/SKILL.md)
- [`device-firmware`](../skills/device-firmware/SKILL.md)
- [`service-lifecycle`](../skills/service-lifecycle/SKILL.md)
- [`validation`](../skills/validation/SKILL.md)
- [`custom-image-builds`](../skills/custom-image-builds/SKILL.md) for image build,
  workflow, registry, digest, or repin work
- [`secrets-sops`](../skills/secrets-sops/SKILL.md) for any credential work
- [`network-services`](../skills/network-services/SKILL.md) for reservation,
  DHCP, address, or LAN reachability work

Read the [service operations manual](../docs/service-operations.md), relevant
[runbook](../docs/runbook.md) sections, and every active CYD/Finance/Kea file
linked by `device-firmware` before mutation.

## Read-only diagnosis

1. Record Git/worktree state and prove the active root Kustomization paths. Verify
   Flux's exact applied revision before attributing symptoms to the latest commit.
2. Inspect Deployment generation/conditions, pod phase, init state, restart count,
   events, generated ConfigMap reference, both container image references/image
   IDs, and Secret metadata/resource version without reading Secret values.
3. Preserve complete current and previous init logs. Separate:
   - dashboard compile outcome;
   - first reserved-device upload outcome; and
   - second reserved-device upload outcome.
   The final exit code alone is insufficient.
4. Correlate both upload destinations with exact `/32` NetworkPolicy egress and
   Kea reservations. Inspect only the matching lease rows. Check device power and
   bounded OTA-port reachability from the updater's actual network vantage point.
5. Distinguish failure domains before changing anything:
   - image pull or architecture;
   - ESPHome/ESP-IDF compile or public HTTPS dependency;
   - missing/malformed projected Secret;
   - OTA password/authentication;
   - NetworkPolicy or reservation/address drift;
   - device offline/Wi-Fi failure;
   - upload success followed by boot/display/touch/application failure.
6. Inspect each physical device separately. One may already run the candidate
   even while the Deployment remains unready.

Do not expose the updater to broad LAN/internet egress, dump environment/Secret
contents, or restart components as a diagnostic shortcut.

## One-device failure and retry semantics

The init container compiles, attempts both uploads sequentially, retains a
nonzero status if either fails, and prevents the completion container from
starting. Kubernetes init backoff retries the whole sequence, so a previously
successful device can be flashed again.

Therefore:

- mark the fleet state as partial until each device is physically identified;
- do not report “nothing deployed” because the Deployment is unready;
- do not report “both deployed” from a single successful log line;
- do not delete/restart the pod to retry one device—the current command retries
  both;
- preserve logs before any retry;
- if repeated flashing presents risk, stop and request authority for the
  documented minimum emergency pause rather than fighting Flux;
- define what happens if the unavailable device cannot be recovered during the
  maintenance window.

An authorized retry must name both device side effects, use the exact reviewed
ConfigMap and pinned digest, and be observed from compile through physical boot.

## Choose the corrective path

### Current desired state is correct; one device was transiently unavailable

First repair power, reservation, Wi-Fi, or exact policy reachability without
broadening access. If retry is authorized, acknowledge that both devices will be
uploaded again. Verify both physically afterward.

### Dashboard or updater content is wrong

Use [change-cyd-dashboard.md](change-cyd-dashboard.md). Do not patch the live
ConfigMap or set the Deployment image directly. Preserve the prior dashboard and
digest and use protected Git/Flux rollout.

### Updater image is unavailable or wrong

Use `custom-image-builds`. Every repository helper pushes; workflow dispatch and
qualifying branch pushes are registry mutations. Capture a reviewed manifest
digest, repin both containers identically, validate, and deploy through Git.

### Device address or reservation drifted

Use `network-services`. Prove the real MAC/lease, then update Kea inventory,
upload commands, and exact NetworkPolicy peers together. A Kea generator change
can Recreate the live DHCP service and needs separate network-critical authority.
A reservation does not create DNS.

### Bearer token changes

Use `secrets-sops`. Inventory both encrypted copies: the device-side `Bearer ...`
authorization and the Finance server token. The server currently consumes one
token, so define a bounded maintenance sequence. Do not switch the server after
only one device receives the replacement. A CYD Secret edit alone does not roll
the hashed dashboard ConfigMap or prove the new value reached firmware.

### Wi-Fi or OTA password changes

Wi-Fi rotation can strand both devices outside OTA reachability; require physical
recovery and verify each device before old-network retirement. OTA password
rotation must authenticate with the installed credential while embedding the
new one. The current single-value projected configuration does not document that
transition. Stop for a tested transition or explicit serial recovery plan rather
than treating it as a normal one-file Secret update.

## Validation and protected deployment

For any repository correction, render the active CYD path and verify generated
ConfigMap/reference coupling, both image pins, both destinations, NetworkPolicy,
and Kea agreement. Run complete `validation`; a compile, narrowed unit test, or
successful one-device upload is not enough.

Push, publish, open a PR, merge, or reconcile only within the authorization
matrix. After merge, wait for the exact Flux revision. Observe init behavior
without manually restarting a still-progressing rollout.

Completion requires physical proof for both devices: boot, intended screen,
fresh authenticated Finance data, expected stale/error behavior, touch action,
and cross-device focus synchronization. Deployment Ready proves both upload
commands exited zero, not that firmware booted or the UI works.

## Hard stops

Stop if:

- exact Git/Flux/config/image/device identities do not agree;
- logs for one device are missing or a partial flash cannot be classified;
- a retry, pause, DHCP change, credential change, or physical flash lacks its
  separate authority;
- a proposed fix broadens NetworkPolicy or bypasses immutable image pins;
- a Secret or compiled production firmware would be exposed;
- registry publication would occur as an unacknowledged branch-push side effect;
- an OTA/Wi-Fi/bearer transition lacks a two-device sequence and recovery plan;
- full validation or protected CI fails;
- either device cannot be physically verified; or
- a device requires undocumented serial recovery.

Preserve evidence and state the minimum safe operator decision. Do not loop
restarts or improvise destructive device recovery.

## Rollback and evidence

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Rollback is another two-device write. Restore the prior dashboard source and a
compatible prior updater digest through Git; reverting only the image leaves the
current ConfigMap source in place. Verify both upload and physical behavior.
If OTA is lost, Git rollback cannot repair the device; require the separately
authorized physical procedure.

Return:

- exact Git, Flux, Deployment, ConfigMap, image, and device identities;
- current/previous per-device init results and restart history;
- non-secret reservation, policy, reachability, and Secret-metadata evidence;
- diagnosed failure domain and why alternatives were rejected;
- every Git/GitHub/registry/live/DHCP/credential/device action taken;
- complete validation and protected-CI results;
- physical outcome for each device and any partial state;
- retained rollback revision/digest and physical recovery gap.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] The failure is classified without leaking credentials or broadening access.
- [ ] No pod action is mislabeled as harmless; both OTA side effects are authorized.
- [ ] Dashboard, image, Secret, NetworkPolicy, and Kea identities agree.
- [ ] Any correction passes complete validation and protected deployment rules.
- [ ] Both devices are physically verified, or the task is explicitly incomplete
      with a safe partial-state/recovery plan.
- [ ] Rollback preserves the prior Git source and immutable digest and recognizes
      when OTA cannot perform recovery.
