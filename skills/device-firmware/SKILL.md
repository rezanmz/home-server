---
name: device-firmware
description: Change, publish, roll out, diagnose, or recover the Git-owned CYD ESPHome dashboard firmware and its in-cluster OTA controller. Use for apps/cyd-ota dashboard behavior, updater image pins, reserved-device addressing, OTA failures, or coordinated device credentials; do not use for unrelated Home Assistant dashboards or generic container rollouts.
---

# CYD dashboard firmware and OTA

Treat every updater pod start as a possible write to both physical devices. A
Kubernetes rollout is not merely infrastructure churn here: the init container
compiles firmware and performs authenticated OTA uploads before the long-running
container can start.

## Load the companion skills

Always load [home-server-safety](../home-server-safety/SKILL.md),
[service-lifecycle](../service-lifecycle/SKILL.md), and
[validation](../validation/SKILL.md).

Also load:

- [custom-image-builds](../custom-image-builds/SKILL.md) before building,
  dispatching, publishing, or repinning the updater image;
- [secrets-sops](../secrets-sops/SKILL.md) before viewing metadata for, editing,
  or rotating the projected device or Finance API Secrets; and
- [network-services](../network-services/SKILL.md) before changing a Kea
  reservation, device address, DHCP state, or the Beelink-hosted network path.

Read [configuration ownership](../../docs/configuration-ownership.md), the
[service lifecycle manual](../../docs/service-operations.md), and the relevant
[runbook](../../docs/runbook.md) sections. Manuals override this skill; flag
drift instead of choosing the easier rule.

## Authoritative surfaces

Read these files in full and discover current values from them:

- [firmware source](../../apps/cyd-ota/dashboard.yaml)
- [Kustomize generator](../../apps/cyd-ota/kustomization.yaml)
- [OTA Deployment](../../apps/cyd-ota/deployment.yaml)
- [OTA NetworkPolicy](../../apps/cyd-ota/networkpolicy.yaml)
- [encrypted production inputs](../../apps/cyd-ota/secrets.sops.yaml)
- [placeholder key contract](../../apps/cyd-ota/secrets.example.yaml)
- [catalog exclusion](../../apps/cyd-ota/cyd-ota.catalog.yaml)
- [updater Dockerfile](../../images/cyd-ota/Dockerfile)
- [build-only dummy inputs](../../images/cyd-ota/secrets.yaml)
- [publishing helper](../../scripts/build-cyd-ota-image.sh)
- [publishing workflow](../../.github/workflows/build-cyd-ota-image.yml)
- [Kea reservation inventory](../../apps/kea/iot-reservations.json)
- [Kea reservation tests](../../scripts/ci/test_kea_iot_policy.py)
- [Finance service Secret](../../apps/finance-display/secrets.sops.yaml)
- [Finance service environment](../../apps/finance-display/deployment.yaml)
- [Finance bearer/API implementation](../../images/finance-display/server.js)

Follow [the root Kustomization](../../clusters/home-server/kustomization.yaml) to
prove both the OTA and Kea paths are active. Do not infer ownership from files
existing alone.

## Ownership model

`apps/cyd-ota/dashboard.yaml` is not a user-edited application dashboard. It is
the configuration-file-only source for device firmware, hardware pins, display,
touch behavior, polling, and the Finance API client, so Git owns it. The
cataloged Finance service owns its durable focus state; do not create a second
Git reconciliation loop for that application data.

The production Wi-Fi values, Finance endpoint and bearer authorization, and OTA
password are Kubernetes startup/delivery inputs in the SOPS-encrypted projected
file. Only ciphertext belongs in Git. The example file contains placeholders,
and the image's `secrets.yaml` contains deliberately fake build-only values.
Never replace either with production data.

The published updater image prewarms the ESPHome/ESP-IDF build environment using
the fake inputs. At runtime, the init container copies that cache, overlays the
Git-generated dashboard and decrypted projected Secret, recompiles, and uploads.
Never deploy the build-cache firmware artifact as if it contained production
configuration. Treat runtime firmware binaries and build workspaces as
secret-bearing because compiled firmware embeds credentials.

## Coupled identities and rollouts

Before editing, map these exact couplings with `rg`:

1. Both reserved device addresses and identities must agree across the OTA
   upload commands, NetworkPolicy OTA destinations, and Kea reservation
   inventory. Do not change only one surface.
2. The Finance bearer integration has a device-side `Bearer ...` value in the
   CYD projected file and a server-side token in the Finance service's encrypted
   Secret. They are one credential with separately deployed consumers.
3. The updater image reference appears in both the init container and the
   completion container. Preserve identical full `repository:tag@sha256:digest`
   references.
4. `configMapGenerator` hashes dashboard content and rewrites the Deployment's
   ConfigMap reference. A dashboard change therefore changes the pod template,
   uses `Recreate`, and runs OTA again.
5. A Secret content change does not receive this ConfigMap name hash and does not
   by itself guarantee a pod-template rollout. Never claim a credential reached
   firmware without proving a new init execution and both device uploads.
6. Any other pod-template edit or pod recreation can run the uploader even when
   dashboard content is unchanged. Node maintenance, manual pod deletion, image
   repinning, and recovery restarts are device-write events.

Root pruning is disabled. Old generated ConfigMaps can remain live after their
references change; do not delete them as incidental cleanup.

## Authorization boundaries

- Review, planning, Git inspection, live status, logs, and non-secret
  connectivity checks are read-only.
- Repository edit authority covers only the named files. It does not authorize
  a commit, branch push, workflow dispatch, registry publication, PR, merge,
  reconcile, pod restart/deletion, OTA upload, DHCP restart, credential rotation,
  or physical/serial flashing.
- A local Docker compile mutates local cache and may download tools. Confirm it
  is in scope; it does not authorize use of the publishing helper.
- Every repository image helper pushes. A qualifying branch push can also run
  the GitHub workflow and mutate GHCR automatically. State the exact branch,
  path filter, registry tag, and overwrite risk before pushing.
- Registry publication, consumer repinning, protected merge, Flux deployment,
  and physical-device OTA are distinct permissions. Permission for one does not
  imply the next.
- Changing Kea desired state and restarting the live DHCP service are separate
  network-critical permissions.
- Rotating a bearer, Wi-Fi, or OTA credential and revoking the old value are
  separate permissions.
- Manual serial/USB recovery, erasure, or physical replacement is destructive
  device work and requires an exact recovery procedure and explicit authority.

Do not use direct `kubectl apply`, `edit`, or `set image` as the normal path.

## Preflight

Record without exposing credentials:

1. exact Git revision, branch, worktree state, and active Flux owner;
2. current rendered ConfigMap name/reference and both updater image references;
3. current SOPS Secret metadata and resource reference, never its value;
4. both intended device reservations, observed Kea lease/MAC agreement, OTA
   address/port reachability, and device power/physical availability;
5. current pod/init status, restarts, events, and complete current/previous init
   logs, identifying the result for each device separately;
6. current dashboard behavior and a physical acceptance check for each screen;
7. prior dashboard Git revision, prior updater manifest digest, and whether each
   device can still accept OTA;
8. physical recovery availability if firmware boots without networking or OTA.

Do not print the lease inventory broadly when a bounded lookup suffices; it
contains hardware identifiers. Do not print Secret data, environment values,
compiled firmware, or command lines containing credentials.

## Change and compile

Make the smallest change to `apps/cyd-ota/dashboard.yaml`. Preserve the hardware
board, framework, pins, display rotation, touch calibration, API schema, TLS
verification, stale/error behavior, and polling contract unless the requested
change explicitly covers them. A visual compile cannot prove touch geometry or
physical readability.

`kubectl kustomize` does not invoke ESPHome. A local container build using the
Dockerfile and fake build-only Secret can prove that the selected ESPHome image
parses and compiles the source for the local target architecture. It cannot prove:

- production SOPS values or Wi-Fi association;
- OTA authentication/reachability;
- the updater NetworkPolicy;
- finance endpoint TLS, bearer authorization, or response semantics;
- boot success, display colors/fonts/readability, touch calibration, or
  cross-device focus synchronization; or
- the exact pushed manifest digest, other architectures, SBOM, or provenance.

The repository helper is not a local compile command because it always uses
`--push`. Do not invoke it without registry publication authority.

## Publish and repin the updater image

A dashboard path change is included in the image workflow's push filters. Read
the current branch filters first. Pushing a qualifying branch can publish the
fixed updater tag before PR review; merging to `main` can publish that tag again.
The validation workflow does not make this an ordinary pull-request image check.

When publication is authorized:

1. Follow `custom-image-builds`; verify a clean context contains no plaintext or
   untracked secret material.
2. Build/push only the exact authorized registry tag and capture the returned
   manifest digest.
3. Inspect the pushed architecture against the updater's constrained placement
   and the build helper's current platform declaration.
4. Repin both Deployment containers to the same captured full reference and
   preserve the prior digest.
5. If the `main` push rebuild moves the mutable tag to a different digest, do not
   silently repin “latest.” Compare inputs/results and retain the exact reviewed
   digest as deployment identity.

SBOM and provenance attestations do not prove signatures, vulnerability
acceptance, reproducibility, or that physical firmware works.

## Render and validate

Render `apps/cyd-ota` before and after. For a dashboard change, prove that the
generated ConfigMap content/name and the Deployment reference change together.
Verify both image references, both upload destinations, both NetworkPolicy
destinations, and both Kea reservations remain consistent.

Run the full repository validation through `validation`, not only Kustomize or a
local compile. If reservations change, run the Kea reservation tests and review
the resulting Kea ConfigMap/Deployment rollout and high-risk boundaries. If
NetworkPolicy changes, review its existing DNS, HTTPS build dependency, and
exact OTA-only egress; do not broaden it to restore connectivity.

## Understand one-device failure semantics

The init script compiles once, then attempts both device uploads sequentially.
It continues to the second device when the first fails. Any failed upload leaves
the init container nonzero, so the completion container does not start and the
Deployment is not Ready.

This is not an atomic fleet transaction:

- the successful device may already run new firmware while the other remains on
  old firmware;
- init restart/backoff re-runs compile and attempts both devices again, including
  one that already succeeded;
- the final exit code does not by itself describe both results; retain the
  per-device log evidence;
- deleting/restarting the pod is another attempt against both devices, not a
  harmless retry.

If repeated uploads could cause harm, stop and request explicit emergency
authority for the documented minimum live mitigation. Do not repeatedly delete
pods or loosen NetworkPolicy. Preserve partial-state evidence and identify each
device's observed behavior.

## Secrets and coordinated rotation

Use `secrets-sops` and rotate one integration at a time.

- The bearer token must be coordinated with the Finance service. The current
  server consumes one token, while the firmware embeds the device-side
  authorization. Define an order that handles the interval where old and new
  consumers disagree; do not switch the server after only one device updates.
- A CYD Secret-only commit does not prove a firmware rollout. Define an
  authorized pod-template rollout and prove both uploads.
- Wi-Fi rotation can remove OTA reachability after flashing. Require physical
  recovery and verify both devices join the intended network before retiring the
  old network.
- OTA password rotation must authenticate to the currently installed password
  while embedding the replacement. The current single projected value and
  command do not document that transition. Stop and establish a tested
  transition or serial recovery procedure; do not assume a one-value Secret edit
  can rotate it safely.
- Do not revoke the old server token, network, or password until the replacement
  path is proven under an explicitly approved overlap or maintenance plan.

## Kea and NetworkPolicy coupling

For an address, device, or MAC change, load `network-services`. Verify the real
lease identity, public-repository disclosure, uniqueness, address ordering, DHCP
pool membership, and the current reservation test. Update the reservation,
uploader destination, and exact `/32` OTA egress together.

Kea's generator hash can recreate the network-critical DHCP Deployment. That
side effect requires its own maintenance and verification authority. A Kea
reservation does not create DNS; OTA intentionally uses reserved addresses.

## Protected rollout and verification

Merge only through the protected PR path after full validation and the reviewed
image digest are present. After merge, verify Flux reports the exact merged
revision before interpreting the rollout.

Collect:

- rendered and live ConfigMap name/reference;
- identical live updater image references and pulled image IDs;
- Deployment, pod, init-container, restart, and event state;
- complete per-device compile/upload results without secrets;
- both Kea reservation/lease identities and bounded OTA reachability;
- physical boot and screen behavior on each device;
- successful authenticated finance refresh on each device;
- a touch focus change and propagation to the other device within the firmware's
  documented polling behavior; and
- expected denial of unneeded updater ingress/egress paths if policy changed.

Deployment readiness proves the upload commands exited successfully. It does not
prove that either device booted, rendered correctly, retained connectivity, or
accepted touch input. Physical verification is mandatory for a completion claim.

## Rollback and hard stops

Rollback is another OTA deployment. Restore the prior dashboard source and a
compatible prior updater digest through Git, validate, merge, and observe both
uploads. Reverting only the image digest does not restore firmware source because
runtime compilation overlays the current ConfigMap. Reverting Git cannot reach a
device that no longer boots, joins Wi-Fi, or accepts OTA.

Stop when an exact device identity is ambiguous, either device is unavailable
without an accepted partial-rollout plan, registry publication is unauthorized,
the pushed digest/platform is unproved, the ConfigMap/reference does not hash
together, a Secret would be exposed, credential transition is untested, Kea/
NetworkPolicy destinations disagree, compile or full validation fails, Flux is
not at the merged revision, or physical recovery is required but undocumented.

Report exact revisions and non-secret identities, changed files, local compile
limits, registry side effects/digest, rendered hash coupling, validation/CI,
per-device OTA outcome, physical acceptance, credential/reservation actions,
rollback readiness, and every unverified step.
