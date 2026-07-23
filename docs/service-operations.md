# Service lifecycle manual

This manual is for the operator changing an application in the home cluster.
After reading it, you should be able to add, modify, roll back, or retire a
service without creating unmanaged live state, exposing a private interface, or
losing its persistent data.

Use the [cluster operations manual](cluster-operations.md) for node placement,
node lifecycle, and platform maintenance. Use the [runbook](runbook.md) for
incident checks and the recovery procedures that are explicitly documented
there. Do not infer that an application has a production disaster-restore
procedure merely because its backup has an isolated read test; production
Syncthing disaster recovery is one procedure that still needs to be written
and rehearsed.

## Operating rules

1. Git is the desired state. GitHub Actions validates it; Flux deploys it after
   it reaches protected `main`.
2. Do not use Docker Compose for production and do not use a direct
   `kubectl apply`, `kubectl edit`, or `kubectl set image` as a normal change
   path. Flux will normally overwrite overlapping live changes.
3. The root Flux Kustomization has pruning disabled. Removing YAML from Git
   does **not** remove the corresponding live object.
4. Back up and read-test persistent data before changing a PVC, database,
   application encryption key, or storage layout. A replica, retained PV, or
   local snapshot is not an independent backup.
5. Every new network path, privileged setting, host dependency, and high-risk
   baseline change must be intentional and reviewable.

## Operator prerequisites

The documented commands assume the workstation has `kubectl`, Python 3,
`sops`, `jq`, and SSH, and that the repository's age identity is readable at
`$SOPS_AGE_KEY_FILE` or `~/.config/sops/age/keys.txt`. The `beelink` and `pi`
SSH aliases must resolve, and the operator must have non-interactive sudo on the
nodes. Verify the access path without printing any secret:

```bash
set -euo pipefail
command -v kubectl python3 sops jq ssh >/dev/null
SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
export SOPS_AGE_KEY_FILE
test -r "$SOPS_AGE_KEY_FILE"
kubectl kustomize clusters/home-server >/dev/null
sops --decrypt infrastructure/longhorn/backups/backup-credentials.sops.yaml \
  >/dev/null
ssh beelink 'sudo -n k3s kubectl get --raw=/readyz >/dev/null'
ssh pi 'sudo -n true'
```

Stop if any prerequisite fails. Do not work around a missing age identity by
creating a new one: existing Secrets are encrypted to the repository's current
recipient.

## Understand ownership before editing

The cluster has two Kustomization layers:

| Owner | Scope | Pruning |
| --- | --- | --- |
| `flux-system/flux-system` | The main cluster tree, ordinary applications, and most infrastructure | Disabled |
| `flux-system/longhorn-ready` | Longhorn readiness marker | Enabled |
| `flux-system/longhorn-backups` | Longhorn B2 credential and recurring backup job | Enabled |
| `flux-system/syncthing-backups` | Syncthing Restic credential, policy, and CronJobs | Enabled |
| `flux-system/longhorn-snapshot-class` | Repository-owned `VolumeSnapshotClass` | Disabled |
| `flux-system/gateway-api-crds` | Commit-pinned external Gateway API CRDs | Disabled |
| `flux-system/snapshot-api-crds` | Commit-pinned external snapshot API CRDs | Disabled |
| `flux-system/snapshot-controller` | Commit-pinned external snapshot controller | Disabled |

An application directory can contain historical YAML that is not active. Only
resources listed by its `kustomization.yaml`, directly or through a generator,
are desired. Duplicati is the deliberate example: its directory retains
recovery manifests, while its active Kustomization contains only the config
PVC.

Before a change, establish all three facts:

```bash
# What Git renders.
kubectl kustomize clusters/home-server >/tmp/home-server.yaml

# Which Flux objects own independently reconciled children.
ssh beelink 'sudo k3s kubectl -n flux-system get kustomizations -o wide'

# What is currently live.
ssh beelink 'sudo k3s kubectl get \
  deploy,statefulset,daemonset,cronjob,job,pod,service,endpointslice,networkpolicy,configmap,secret,pvc,httproute \
  -A'
ssh beelink 'sudo k3s kubectl get pv,volumeattachment'
```

Do not infer ownership from a filename or label alone. A child Kustomization's
inventory is the authoritative record of what that child last applied:

```bash
ssh beelink 'sudo k3s kubectl -n flux-system get kustomization NAME -o json \
  | jq -r ".status.inventory.entries[]?.id"'
```

## Choose the service shape

Make these decisions before writing manifests.

### Namespace

| Namespace | Intended use | Pod Security enforcement |
| --- | --- | --- |
| `apps` | Identity, home automation, personal applications, and ordinary web services | Baseline; restricted audited and warned |
| `media` | Media, download automation, and VPN-isolated workloads | Privileged; restricted audited and warned |
| `network-services` | DNS, DHCP, VPN, SMB, Syncthing, and LAN protocols | Privileged; restricted audited and warned |
| `monitoring` | Metrics, read-only cluster dashboards, alerting, and event reporting | Baseline; restricted audited and warned |

Prefer an existing namespace. A new namespace needs explicit Pod Security
labels, a default-deny NetworkPolicy, and any namespace-scoped Traefik
middleware or error-page aliases. Creating a namespace merely to avoid an
existing security policy is not acceptable.

### Storage and recovery class

| Data | Use | Off-site coverage | Important limitation |
| --- | --- | --- | --- |
| Small application state, databases, and configuration | Longhorn RWO PVC | Nightly Longhorn B2 backups | Two replicas and block backups do not make a singleton app or multi-PVC database transactionally HA |
| Organized movies, TV, music, books, audiobooks, and podcasts | Namespace-local static JuiceFS RWX claim with the narrowest category `subPath` | Authoritative encrypted payloads in a dedicated B2 bucket; metadata is separately protected by Longhorn and JuiceFS export | B2 is the primary copy, not an independent backup; an internet, B2, or metadata outage can block uncached reads and all new writes |
| Incomplete downloads and active seeding torrents | Static Pi NFS claim for the exact downloads export | None; transient/reproducible | Pi failure interrupts downloads; importing to JuiceFS copies rather than hardlinks, temporarily consuming both local and cloud space |
| Syncthing file data | Pi NFS plus the dedicated Syncthing PVC | Daily encrypted Restic B2 backup | Live-file scan, not an atomic filesystem snapshot |
| Stateless/cache data | `emptyDir` or no PVC | Not backed up | Lost on pod replacement |
| Reproducible observability state | `longhorn-observability` RWO PVC | Deliberately excluded from the default B2 recurring job | Grafana preferences and recent metrics can be lost; dashboards and configuration remain in Git |

A newly added NFS path is **not** automatically covered by either Longhorn or
the Syncthing backup. Do not put application databases or ordinary persistent
state in JuiceFS merely because it is shared: use Longhorn for that class. Use
JuiceFS only for large file libraries whose metadata and object-store recovery
contract is understood. If new data is not reproducible, define its independent
backup and restore test before deployment.

### Placement

Leave a workload unpinned only when its image supports both amd64 and arm64 and
it has no fixed-address, hardware, host-port, broadcast, or local-data
requirement. A hostname selector is a hard availability decision, not a
performance hint. See the placement matrix in the
[cluster operations manual](cluster-operations.md).

### Exposure

Choose one of these deliberately:

- **No HTTP route:** internal-only Service or background worker.
- **Private/admin route:** LAN/WireGuard middleware plus the colocated access
  proxy; the Service targets the proxy, not the application directly.
- **Public route:** no LAN middleware. The application must supply suitable
  authentication and the public exposure must be explicitly reviewed.
- **Host-network admin UI:** use Syncthing's loopback and backend-mTLS pattern.
  Do not expose the loopback service through an ordinary pod Service. Blocky
  and Kea deliberately have no HTTP route; do not add one merely for convenience.

The wildcard certificate normally covers a new `*.reza.network` hostname.

For a user-facing service, use Authentik through the application's built-in
OIDC, OAuth2, or SAML support whenever that support exists. Do not install
third-party authentication code solely to force SSO into an application that
does not support it. In that case, use the application's native authentication,
keep the narrowest practical exposure, and document the exception. Generic
forward-auth is allowed only after proving that it does not break APIs,
webhooks, WebSockets, native clients, or callback flows. Home Assistant is the
current native-auth exception because upstream Home Assistant has no built-in
OIDC provider.

Before implementing authentication for a new user-facing service:

1. Check the current upstream documentation and release for native OIDC,
   OAuth2, or SAML support. Native support is the default when available.
2. Register exact browser, logout, and native/mobile callback URIs in
   Authentik. Use authorization code flow with PKCE where the application
   supports it; do not enable implicit, password, device, or client-credential
   grants unless the application actually requires them.
3. Use a public client with authorization code plus PKCE when the application
   implements PKCE and does not need a client secret. Otherwise, keep the OIDC
   client secret in SOPS-encrypted Secrets. Send only the minimum required
   scopes, prefer stable subject matching, and never grant administrator access
   merely because any Authentik user can authenticate.
4. Add the Authentik issuer path to the workload's NetworkPolicy, including
   the split-horizon Traefik pre- and post-DNAT destinations. Verify discovery,
   login, callback, logout, and any official mobile client before exposure.
5. Keep an uninitialized first-user or first-owner page off the public route.
   Automate a fail-closed bootstrap or complete onboarding through a private
   path before the Service receives public traffic.

Authentik's native-OIDC application state is repository-managed through the
service integration catalog. Declare the fixed `authentik-oidc-v1` profile,
client type, exact callbacks, scopes, and application identity in the
service's colocated descriptor. The catalog compiler generates that
application's separate blueprint document inside the shared ConfigMap.

For a confidential client, add its provider-side secret to the shared encrypted
OIDC client Secret and the same value to the relying application's encrypted
Secret. The compiler derives and generates the worker's required
`secretKeyRef`; a new client therefore changes the pod template, and a missing
key stops the pod instead of silently breaking only its blueprint. A reviewed
PKCE public client has no Secret or worker environment entry. Run `render`,
inspect the generated diffs, and use `explain <service-id>` before `check`.
Never edit the aggregate Authentik blueprint or generated worker patch directly,
and do not add a per-application Authentik manifest or Deployment patch.

For a confidential client, the relying application still needs the same client
secret in its own namespace. Rotate both encrypted copies in one reviewed
change, then restart the Authentik Deployment so the worker receives the new
environment value. Verify that the provider and application blueprint instance
is Successful before rolling the relying application. This duplication is
preferable to adding a cluster-wide Secret replication controller or granting
cross-namespace Secret access.

ISC does not publish supported production Stork container images. Rebuild the
pinned Stork server, non-root agent, and web UI targets only from the reviewed
upstream tag and commit with:

```bash
scripts/build-stork-images.sh
```

The helper refuses a moved tag, applies the repository's minimal non-root
sidecar and read-only lease-list patches, and imports the exact pinned Kea
runtime that Stork must execute to identify the colocated daemon's version. Pass
`server`, `agent`, or `webui` to rebuild one target, or omit the argument to
rebuild all three. It publishes SBOM/provenance attestations and prints the
resulting manifest digests. Review upstream's development-release status and
update the Stork and Kea pins together.

If native integration is unavailable or unsuitable, record what upstream
capability was checked, why it cannot be used, the chosen authentication
boundary, and the narrowest practical exposure. Revisit that exception when
upstream authentication support changes.

## Add a service

Start with the [service integration catalog](service-catalog.md). The
application manifests define runtime behavior; a colocated
`<service-id>.catalog.yaml` records the cross-service decisions that must
accompany them. CI requires an explicit Homepage card or omission,
route/auth/DNS policy, placement, data protection, and observability level for
every active application path.

### 1. Start from the closest security model

Create `apps/<service>/` and compare with an existing service that has the same
exposure and storage model. Actual Budget is the best ordinary private-web-app
example. Blocky and Kea are specialized host-network protocol examples;
Syncthing is the host-network backend-mTLS UI example; the downloads pod is a
specialized shared-network-namespace example. Do not copy a privileged
exception into an ordinary app merely because it is convenient.

A typical application Kustomization explicitly lists:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - access-proxy.yaml    # for the usual private/admin route
  - secrets.sops.yaml   # when needed
  - pvc.yaml            # when stateful
  - deployment.yaml
  - service.yaml        # when networked
  - networkpolicy.yaml
  - route.yaml          # when exposed through Traefik
```

Give every namespaced object an explicit namespace. Use
`app.kubernetes.io/name` consistently across the controller, pod, Service, and
NetworkPolicy selectors.

### 2. Build the workload defensively

Unless the service has a reviewed reason not to, require:

- an immutable image reference in `repository:tag@sha256:digest` form;
- a multi-architecture image when placement is floating;
- `automountServiceAccountToken: false`;
- non-root UID/GID, `RuntimeDefault` seccomp, no privilege escalation, and all
  capabilities dropped;
- a read-only root filesystem when the image supports it;
- explicit CPU and memory requests and limits;
- startup/readiness/liveness probes that test the service rather than merely
  the container process; and
- `Recreate` for a singleton Deployment using an RWO PVC, unless the
  application's update behavior has been proven safe with another strategy.

The following require a specific threat review and a reviewed high-risk
baseline change: root, privileged mode, added capabilities, host networking,
host paths, host ports, broad RBAC, a Kubernetes API token, unsafe sysctls, or
unrestricted ingress/egress.

### 3. Add secrets with SOPS

Secret manifests must end in `.sops.yaml`. Edit them through SOPS so plaintext
is never written to the repository:

```bash
service=SERVICE_NAME
sops "apps/${service}/secrets.sops.yaml"
python3 scripts/ci/validate-secrets.py
```

Inside the editor, create a normal Kubernetes Secret and put secret values only
under `data` or `stringData`; the repository SOPS rule encrypts those fields.
Confirm the saved file contains `ENC[...]` values and SOPS metadata before
staging it. Never commit an age private identity or a temporary plaintext
Secret. Preserve application encryption keys when the existing database was
encrypted with them—generating a replacement can make stored fields
unrecoverable.

A separately reconciled child that contains SOPS resources must configure SOPS
decryption and reference the in-cluster `sops-age` Secret. The root already does
this for ordinary application directories.

### 4. Add storage

For Longhorn state, use a PVC with the default `longhorn` StorageClass and a
realistic requested size. The class has two replicas, delayed binding, and
`Retain` reclaim behavior. Current volumes inherit the `default` recurring-job
group when `spec.recurringJobSelector` is empty; there is no explicit
`b2-nightly` selector on each Volume. A bound PVC therefore proves neither
backup membership nor a completed backup.

Map the PVC to its PV and Longhorn volume, require the target to be available,
and select the newest successful backup created by the recurring job:

```bash
set -euo pipefail
namespace=NAMESPACE
claim=PVC_NAME

pv="$(ssh beelink sudo k3s kubectl -n "$namespace" get pvc "$claim" \
  -o jsonpath='{.spec.volumeName}')"
test -n "$pv"
volume="$(ssh beelink sudo k3s kubectl get pv "$pv" \
  -o jsonpath='{.spec.csi.volumeHandle}')"
test -n "$volume"

ssh beelink sudo k3s kubectl -n longhorn-system \
  get backuptargets.longhorn.io default -o json |
  jq -e '.status.available == true' >/dev/null

ssh beelink sudo k3s kubectl -n longhorn-system \
  get backups.longhorn.io -o json |
  jq -e --arg volume "$volume" '
    [.items[] | select(
      .status.volumeName == $volume and
      .status.state == "Completed" and
      ((.status.error // "") == "") and
      .status.labels.RecurringJob == "b2-nightly"
    )] |
    sort_by(.status.backupCreatedAt) |
    if length == 0 then
      error("no completed b2-nightly backup for this volume")
    else
      last | {
        name: .metadata.name,
        created: .status.backupCreatedAt,
        target: .status.backupTargetName
      }
    end'
```

Before a high-risk data change or final service retirement, stop writers and
[create an on-demand backup](https://longhorn.io/docs/1.12.0/snapshots-and-backups/backup-and-restore/create-a-backup/)
for the exact volume in the Longhorn UI. Give it a
unique backup label such as `change-id=SERVICE-YYYYMMDDTHHMMSSZ`; an on-demand
backup does not have the `RecurringJob=b2-nightly` label and therefore must not
be verified with the recurring-only query above.

The UI has no public route. Open it only through a loopback-bound SSH tunnel;
leave this command running, browse to `http://127.0.0.1:18080`, and stop it with
Ctrl-C when finished:

```bash
ssh -o StrictHostKeyChecking=yes -t \
  -L 127.0.0.1:18080:127.0.0.1:18080 beelink \
  'sudo k3s kubectl -n longhorn-system port-forward \
    --address=127.0.0.1 service/longhorn-frontend 18080:80'
```

Do not add an HTTPRoute, NodePort, or non-loopback `port-forward` merely for UI
convenience.

After initiating the backup, verify exactly one Backup CR matches the captured
volume and unique label:

```bash
set -euo pipefail
volume=LONGHORN_VOLUME_NAME
change_id=SERVICE-YYYYMMDDTHHMMSSZ

ssh beelink sudo k3s kubectl -n longhorn-system \
  get backups.longhorn.io -o json |
  jq -e --arg volume "$volume" --arg change_id "$change_id" '
    [.items[] | select(
      .status.volumeName == $volume and
      .status.labels["change-id"] == $change_id
    )] |
    if length != 1 then
      error("expected exactly one on-demand backup with this change-id")
    else
      first |
      select(
        .status.state == "Completed" and
        ((.status.error // "") == "") and
        (.status.backupCreatedAt | length) > 0 and
        (.status.backupTargetName | length) > 0
      ) |
      {
        name: .metadata.name,
        created: .status.backupCreatedAt,
        target: .status.backupTargetName,
        labels: .status.labels
      }
    end'
```

If this Longhorn UI version cannot add a unique label, capture the newly
created Backup CR's exact metadata name and query only that name, then verify
the same volume/state/error/target/timestamp fields. Never infer that the newest
nightly is the final quiesced backup. A crash-consistent block backup is not a
transactionally consistent multi-PVC database backup; retain the native
application/database export too.

A read-test means an isolated restore, not merely listing the backup. Follow
Longhorn's [restore-from-backup workflow](https://longhorn.io/docs/1.12.0/snapshots-and-backups/backup-and-restore/restore-from-a-backup/)
to restore into a **new, disposable volume name**. Wait until the restored
Longhorn Volume is `detached` and `status.restoreRequired=false` before creating
its PV/PVC. Bind it only to an isolated validation pod or application clone, do
not overwrite or attach it to the production workload, and validate actual
content. Record the disposable PVC/PV/Volume identities before cleanup; delete
only those exact identities.

For Pi NFS data:

1. Create the host directory with the exact UID/GID and mode required by the
   workload.
2. Add the narrowest possible export to the repository-owned Pi export file.
3. Permit only each actual Kubernetes node address that must mount that exact
   path. Use `ro` for read-only consumers and grant `rw` only to nodes that
   contain an intended writer; do not copy all legacy or Syncthing clients onto
   a new export.
4. Add a static PV and namespace-local PVC with `Retain`, NFS 4.2, `hard`, and
   `noatime` following the existing NFS module.
5. Apply the host export separately; Flux does not manage `/etc/exports.d`.
   Record `BASE_MAIN_COMMIT` before editing. After the change is merged, use
   the exact protected-main revision and refuse to overwrite unexplained live
   drift:

   ```bash
   set -euo pipefail
   base_revision=BASE_MAIN_COMMIT
   export_file=infrastructure/hosts/raspberrypi/home-server.exports
   workdir="$(mktemp -d)"
   trap 'rm -rf -- "$workdir"' EXIT

   git fetch origin main
   test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
   test -z "$(git status --porcelain)"
   git cat-file -e "${base_revision}^{commit}"
   git show "${base_revision}:${export_file}" >"$workdir/base"
   ssh -o StrictHostKeyChecking=yes pi \
     'sudo cat /etc/exports.d/home-server.exports' >"$workdir/live"

   if ! cmp -s "$workdir/base" "$workdir/live"; then
     diff -u "$workdir/base" "$workdir/live" || true
     printf '%s\n' 'Refusing to overwrite live NFS export drift.' >&2
     exit 1
   fi

   if command -v sha256sum >/dev/null 2>&1; then
     expected_live_sha256="$(sha256sum "$workdir/live" | awk '{print $1}')"
   else
     expected_live_sha256="$(shasum -a 256 "$workdir/live" | awk '{print $1}')"
   fi
   EXPECTED_LIVE_EXPORTS_SHA256="$expected_live_sha256" \
     scripts/prepare-nfs-media.sh pi
   ssh -o StrictHostKeyChecking=yes pi \
     'sudo cat /etc/exports.d/home-server.exports' >"$workdir/applied"
   diff -u "$export_file" "$workdir/applied"
   ssh -o StrictHostKeyChecking=yes pi 'sudo exportfs -v'
   ```

   The helper independently rechecks that hash and makes a root-only timestamped
   copy before replacement. If the new export set does not reload, it restores
   the previous file (or removes a failed first-install file) and reloads the
   prior export state before returning failure. Review the final `exportfs -v`
   output for the exact path, client addresses, and `ro`/`rw` mode. Test every
   new client and confirm existing NFS consumers remain healthy. A first
   installation with no existing export file may omit
   `EXPECTED_LIVE_EXPORTS_SHA256`; every replacement must provide it.
6. Test only the operations the workload is meant to have as its exact UID
   before enabling the application; a read-only export must reject writes.
7. Record the off-site backup decision.

Do not use multiple PVCs pointing at the same path unless the shared underlying
data and cross-namespace access are deliberate.

Do not share one Longhorn RWO PVC across independent controllers by default.
`Recreate` on each controller does not prevent two different controllers from
landing on different nodes and causing Multi-Attach. If sharing is unavoidable,
record and enforce their same-node placement, and treat the controllers as one
move, upgrade, and retirement unit.

### 5. Add NetworkPolicy

All application namespaces default-deny ingress and egress. Every workload
therefore needs an explicit policy. Permit only:

- DNS to CoreDNS;
- Traefik to the published port;
- named same-namespace dependencies by pod selector;
- the exact Pi/NFS or LAN destination and port when required; and
- narrowly scoped external HTTPS or service-specific ports.

Do not copy an existing empty egress rule (`egress: [{}]`) as a default. For a
pod that calls a split-horizon cluster hostname, test both the MetalLB VIP on
443 and Traefik pod destinations on 8443; policy enforcement may observe the
connection before or after destination NAT.

### 6. Add Service, route, and DNS

Use a ClusterIP Service and a Gateway API HTTPRoute attached to the shared
`traefik/home` Gateway. Private routes require both the custom-error middleware
and the LAN/VPN allow-list middleware. Most private apps also use an access
proxy sidecar so forwarded-header trust terminates next to the application.

Administrative allow-lists deliberately exclude node addresses
`192.168.1.2` and `192.168.1.3`. A private route tested from a node should return
403; test it from an ordinary LAN client through `192.168.1.240`.

For a new hostname, declare `web.hostname`, visibility, exact private-route
middleware, authentication, and both DNS decisions in
`apps/<service>/<service-id>.catalog.yaml`, then run:

```bash
python3 scripts/service_catalog.py render
```

This updates the Homepage service list, the hash-named Cloudflare DDNS domain
ConfigMap input, and Blocky's split-horizon mapping. Do not edit those generated
areas directly. Verify the HTTPRoute is accepted and its backend references
resolve, then test public, direct Pi host-port, and MetalLB VIP paths as
appropriate.

### 7. Connect it to the cluster tree

Add the application directory to the root cluster Kustomization. If you create
a separate Flux child, also add its path to the render bundle in
`.github/workflows/validate-cluster.yml`: rendering the root includes the child
object but not the resources that the child later builds. Run that exact bundle
locally as shown below so schema, secret, and high-risk checks inspect the child
resources themselves.

Do not create a new child solely to obtain automatic pruning. Child ownership,
dependencies, decryption, health checks, and retirement behavior are part of
the service's operational design.

### 8. Validate before the pull request

Run the repository checks after the final manifest edit:

```bash
set -euo pipefail
scripts/ci/validate-shell.sh
python3 -m unittest discover --start-directory scripts/ci --pattern 'test_*.py'
python3 scripts/ci/validate-secrets.py

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
```

The protected GitHub workflow additionally runs pinned strict schema checks and
independently renders every immutable Helm release. A new HelmRelease requires
extending that renderer and its checksum/pinning logic; adding only the
HelmRelease YAML is incomplete.

The high-risk baseline is a review lock, not generated boilerplate. If the
checker reports intentional changes, inspect every finding before updating it:

```bash
python3 scripts/ci/check-high-risk-policy.py \
  /tmp/home-server.yaml scripts/ci/high-risk-baseline.txt --write-baseline
git diff -- scripts/ci/high-risk-baseline.txt
python3 scripts/ci/check-high-risk-policy.py \
  /tmp/home-server.yaml scripts/ci/high-risk-baseline.txt
```

Never regenerate the baseline merely to make CI green; that accepts all current
findings, including unrelated ones.

### 9. Deploy and prove the service

Open a pull request and merge only after the required validation check passes.
Flux normally notices `main` automatically. To request an immediate pull and
root reconciliation:

```bash
ssh beelink 'stamp=$(date +%s); \
  sudo k3s kubectl -n flux-system annotate gitrepository flux-system \
    reconcile.fluxcd.io/requestedAt="$stamp" --overwrite; \
  sudo k3s kubectl -n flux-system annotate kustomization flux-system \
    reconcile.fluxcd.io/requestedAt="$stamp" --overwrite'
```

Verify the exact Git revision, then the service:

```bash
ssh beelink 'sudo k3s kubectl -n flux-system get gitrepository,kustomization -o wide'
ssh beelink 'sudo k3s kubectl -n NAMESPACE rollout status deployment/NAME --timeout=5m'
ssh beelink 'sudo k3s kubectl -n NAMESPACE get pod,svc,endpointslice,pvc,httproute -o wide'
ssh beelink 'sudo k3s kubectl -n NAMESPACE get events --sort-by=.lastTimestamp | tail -n 30'
```

Acceptance is service-specific, but must cover:

- the pod's readiness and restart count;
- expected node placement;
- PVC binding, Longhorn health, or NFS read/write behavior;
- Service endpoints and HTTPRoute `Accepted=True`/`ResolvedRefs=True`;
- private/public access from the correct client network;
- application logs during one real operation; and
- backup inclusion plus a recoverable application-level export when stateful.

## Modify a service

Use the same branch, validation, pull request, reconciliation, and live proof
flow. Add these precautions based on the change type.

### Image or configuration

- Read release notes and verify the pinned digest and target architectures.
- Preserve the previous digest for a Git revert.
- Treat an application schema migration as a storage change, not a routine
  image update.
- A Kustomize `configMapGenerator` creates a new hash-named ConfigMap. Root
  pruning is disabled, so verify no active pod references old hashes before
  deleting them explicitly.

### Secret or identity

- Rotate one integration at a time.
- Reconcile and prove the dependent application before revoking the old value.
- Do not replace a database-coupled encryption key until the old data has been
  decrypted or migrated successfully.

### PVC, database, or application migration

- Produce an application-level export and prove it can be read.
- Confirm the newest Longhorn backup is complete.
- Remember that renaming a PVC provisions or binds a different volume.
- Do not force immutable StatefulSet or PVC changes as a shortcut.
- For a multi-PVC app, block-level backups are not a transactionally consistent
  set; coordinate or quiesce the application where possible.

### Placement or network boundary

- Recheck hardware, architecture, host ports, NFS export permissions, and
  direct-address dependencies on the target node.
- Review route, middleware, access-proxy, Service, and NetworkPolicy changes as
  one boundary.
- Update the high-risk baseline only after reviewing the full rendered diff.

## Roll back a change

Revert the Git change through a pull request, merge it, and reconcile Flux.
For an ordinary modification, Flux reapplies the earlier specification. A
reverted addition is different: because root pruning is disabled, the now
unreferenced live objects remain until explicitly deleted.

Do not blindly roll an image back after a database schema or data-format
migration. First confirm that the old binary supports the migrated data. If it
does not, restore the matching pre-migration database/export into an isolated
target and follow the application's supported rollback procedure, or
forward-fix the application. Reverting only the Deployment can compound the
failure.

Git rollback also does not reverse state outside Flux. Use the original change
record to restore and reapply the previous Pi export or host file, explicitly
reverse Cloudflare records (`DELETE_ON_STOP=false`), router forwards, DHCP
reservations, OAuth/OIDC clients, webhooks, and other provider state, then
verify each system. Do not assume a Git revert or Kubernetes Secret change has
revoked an external credential.

For emergency live recovery only:

1. Suspend the relevant Flux Kustomization.
2. Make the minimum temporary live change.
3. Create and merge matching desired state or a reviewed rollback.
4. Confirm the GitRepository artifact points to that revision.
5. Resume and reconcile Flux.
6. Prove there is no unexplained live drift.

Never leave a service permanently dependent on an uncommitted live patch.

## Retire or remove a service

Retirement is a data-lifecycle operation, not just deletion of manifests.

### 1. Write the retention decision

List exactly what will be retained or destroyed:

- application data and database exports;
- Longhorn PVC/PV/Volume and final B2 backup;
- NFS directories and exports;
- Secrets and application encryption keys;
- remote repositories or provider objects;
- DNS names and router rules; and
- historical manifests needed to interpret retained data.

Create and read-test the application/database export before stopping the last
writer, unless the application documents a supported offline export. The final
quiesced block/file backup comes after the writer inventory reaches zero.

### 2. Remove traffic and stop writers

Use a reviewed Git change to scale controllers to zero or suspend schedules and
remove the route from the active Kustomization. After Flux has applied that
revision, explicitly delete the now-unowned live HTTPRoute because the root will
not prune it. Verify the route is gone before taking the final quiesced backup.

Suspending a CronJob does not stop a Job it already created, and scaling a
Deployment or StatefulSet does not stop standalone pods or another controller.
For every PVC, inspect CronJob templates, live pods, and Job templates, then
wait for or stop each reviewed writer:

```bash
set -euo pipefail
namespace=NAMESPACE
claim=PVC_NAME

ssh beelink sudo k3s kubectl -n "$namespace" get cronjobs -o json |
  jq --arg claim "$claim" '
    [.items[] | select(any(
      .spec.jobTemplate.spec.template.spec.volumes[]?;
      .persistentVolumeClaim.claimName == $claim
    )) | {
      cronjob: .metadata.name,
      suspend: (.spec.suspend // false)
    }]'

ssh beelink sudo k3s kubectl -n "$namespace" \
  get deployments,statefulsets,daemonsets -o json |
  jq --arg claim "$claim" '
    [.items[] | select(any(
      .spec.template.spec.volumes[]?;
      .persistentVolumeClaim.claimName == $claim
    )) | {
      kind: .kind,
      controller: .metadata.name,
      desired: (
        if .kind == "DaemonSet" then "one-per-eligible-node"
        else (.spec.replicas // 1)
        end
      )
    }]'

ssh beelink sudo k3s kubectl -n "$namespace" \
  get horizontalpodautoscalers.autoscaling -o json |
  jq '[.items[] | {
    hpa: .metadata.name,
    targetKind: .spec.scaleTargetRef.kind,
    targetName: .spec.scaleTargetRef.name,
    minReplicas: (.spec.minReplicas // 1),
    maxReplicas: .spec.maxReplicas
  }]'

ssh beelink sudo k3s kubectl -n "$namespace" get pods -o json |
  jq --arg claim "$claim" '
    [.items[] | select(any(.spec.volumes[]?;
      .persistentVolumeClaim.claimName == $claim)) |
      {pod: .metadata.name, phase: .status.phase}]'

ssh beelink sudo k3s kubectl -n "$namespace" get jobs -o json |
  jq --arg claim "$claim" '
    [.items[] | select(any(.spec.template.spec.volumes[]?;
      .persistentVolumeClaim.claimName == $claim)) |
      {job: .metadata.name, active: (.status.active // 0)}]'
```

Repeat the inventory for NFS PVCs and their export paths across every
namespace. Every listed CronJob must report `suspend: true`. Matching
Deployments and StatefulSets must be fixed at zero replicas in reconciled Git;
any HPA targeting them must be absent, because it can rescale a zero-replica
controller. A matching DaemonSet must be removed from desired state and
explicitly deleted—it cannot be scaled to zero. Inventory any service-specific
operator/custom resource that can recreate a writer as well. Require no active
Job, pod, mount, or VolumeAttachment that can write the data, and require a
Longhorn volume to be detached when the service no longer needs it. Re-run all
five inventories immediately before the final backup so a schedule or
controller cannot race an old observation. Only then create the final quiesced
off-site storage backup.

Do not run `kubectl delete -k apps/SERVICE_NAME`: it can delete PVCs and Secrets
that the retention plan intended to preserve.

### 3. Remove desired resources, then live resources

For a root-owned application:

1. Remove the workload, Service, route, and runtime policy from its active
   Kustomization. Remove only destroy-approved ConfigMaps and Secrets. Keep any
   retained PVC, encryption key, Secret, or historical configuration under a
   stable owner.
2. Merge and wait until Flux is on that revision.
3. Explicitly delete each now-unowned live object.
4. Verify no retired runtime pod, Job, endpoint, route, or policy remains, and
   that every surviving ConfigMap, Secret, and PVC matches the written
   retention decision.
5. Remove the application directory from the root only after cleanup is proven
   and it owns no retained objects. Otherwise keep it as a clearly documented
   retention-only module.

For a child with `prune: true`:

1. Keep the child Kustomization live.
2. Classify every inventory entry as retain or destroy. Remove only the
   destroy-approved resources from the child path and reconcile so the child
   prunes those entries.
3. Keep retained PVCs, Secrets, encryption keys, or other resources in the
   child path under their stable owner. The child may remain as a storage-only
   owner after the runtime is retired.
4. Remove the child object only when its inventory is empty, or after a
   separately reviewed and tested ownership-transfer procedure proves another
   stable owner has adopted every retained object. Do not improvise ownership
   transfer during retirement.
5. If the non-pruning root leaves an empty child object behind, explicitly
   delete that exact child after its old path can no longer recreate resources.

Merely removing a child from the root can leave the live child continuously
reconciling its old path.

### 4. Handle storage separately

Deleting a Longhorn PVC leaves a retained PV/Volume by default. Deleting a
static NFS PVC does not delete the Pi directory. Before any storage action,
capture and review the complete identity chain: PVC namespace/name/UID, PV
name/UID and reclaim policy, CSI volume handle/Longhorn Volume name, attachment
state, latest verified backup, and NFS server/path where applicable.

For retention, leave the exact resource under a stable Git/Flux owner and
require it to be detached and backed up. For destruction, write a
change-specific plan whose assertions match every captured UID and handle; this
manual deliberately provides no generic delete command. Never adapt the
Syncthing disposable restore cleanup in the runbook to production data: that
procedure intentionally changes a proven disposable PV from `Retain` to
`Delete`.

If an NFS export is removed, update and apply the Pi host export file, reload
exports, and preserve or delete the directory according to the retention plan.
That host change is outside Flux.

### 5. Remove DNS and external state

- Remove the colocated service descriptor only after its active route and
  workload integration intent is gone, then run
  `python3 scripts/service_catalog.py render`. This removes its generated
  Homepage, Blocky, and Cloudflare DDNS entries together. A retained
  recovery-only app path needs a narrow colocated `CatalogExclusion` reason.
- Allow Blocky's configured five-minute custom-record TTL to expire on clients,
  or flush only the affected client cache when absence must be immediate.
- Explicitly delete the exact Cloudflare record: `DELETE_ON_STOP=false`, so
  removing a generated name from the list does not remove the provider record.
- Remove router forwards only after confirming no retained service uses them.
- Revoke or delete provider-side API keys, OAuth/OIDC clients, webhooks,
  service accounts, and integrations selected for destruction. Record why any
  surviving credential is retained; deleting its Kubernetes Secret does not
  invalidate it.
- Verify authoritative public and Blocky A, AAAA, and CNAME responses are absent.

### 6. Final proof

Confirm Flux is Ready at the intended revision, the retired objects are absent,
retained volumes are detached and backed up, no Released PV was accidentally
orphaned, and no service-specific DNS or host export selected for destruction
remains. Record the recovery artifacts and their restore prerequisites next to
the retained manifests.

## Short checklists

### Add

- [ ] Namespace and Pod Security class selected.
- [ ] Storage, backup, and restore behavior defined.
- [ ] Placement and image architectures proven.
- [ ] Image digest, security context, probes, and resources set.
- [ ] SOPS Secret contains no plaintext.
- [ ] Default-deny NetworkPolicy opened only as required.
- [ ] Route exposure and DNS are deliberate.
- [ ] Service catalog entry and generated integrations are current.
- [ ] App is connected to the root or an explicitly designed child.
- [ ] Local checks and protected CI pass.
- [ ] Flux revision, rollout, access, storage, and backup are proven live.

### Modify

- [ ] Recovery point exists for stateful or identity changes.
- [ ] Rendered and high-risk diffs were reviewed.
- [ ] Rollback preserves the previous image/configuration/data format.
- [ ] Live result was checked at the merged Git revision.
- [ ] Stale generated objects were removed only after reference checks.

### Remove

- [ ] Retain/destroy decision is written for every data and credential class.
- [ ] Traffic is removed and writers are stopped.
- [ ] Final recovery point is read-tested.
- [ ] Desired state no longer owns retired runtime objects.
- [ ] Root-owned objects were explicitly deleted, or child pruning was proven.
- [ ] PVC/PV/Longhorn/NFS cleanup followed an identity-checked plan.
- [ ] Catalog item was removed or replaced by a narrow retention exclusion, and
      generated integrations were reviewed.
- [ ] Cloudflare, Blocky/Kea, router, NFS, and provider credentials/integrations
      were retained or destroyed as documented.
- [ ] Absence and retained recovery artifacts were verified.

## Related material

- [Cluster architecture](architecture.md)
- [Service integration catalog](service-catalog.md)
- [Cluster operations and node lifecycle](cluster-operations.md)
- [Incident and recovery runbook](runbook.md)
- [Flux Kustomization pruning and inventory](https://fluxcd.io/flux/components/kustomize/kustomizations/)
