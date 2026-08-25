---
name: node-host-operations
description: Apply or audit repository-owned node OS, SSH, K3s bootstrap, NFS export, package-policy, and JuiceFS host prerequisites. Use for host-layer work, not Kubernetes scheduling or application manifests.
---

# Operate a node host

Use this skill when the target is a node filesystem, system service, package
policy, SSH identity, NFS export, or fresh-host K3s installation. Host work is a
separate deployment plane: a Git merge does not copy a file to a node or restart
its services.

## Required reading

Read:

- [cluster operations and node lifecycle](../../docs/cluster-operations.md);
- [incident and recovery runbook](../../docs/runbook.md);
- [architecture and physical dependencies](../../docs/architecture.md); and
- [JuiceFS host requirements](../../docs/juicefs-media.md) for FUSE, cache,
  AppArmor, or inotify changes.

Inspect the relevant files under `infrastructure/hosts/`,
`infrastructure/k3s/`, and the exact helper under `scripts/`. Do not substitute a
generic host guide for a repository helper's fail-closed checks.

## Authorization boundary

- Read-only SSH inspection is permitted for diagnosis when it is in scope.
- Editing a repository host input does not authorize copying it to a node,
  changing packages, reloading a service, rebooting, or altering exports.
- Authorization to change one host does not apply to the other host or to an
  unknown replacement machine.
- Router, DNS provider, identity provider, and credential revocation are
  separate external operations.

Before any mutation, name the exact host, files, commands, service impact,
rollback source, and maintenance window. Stop if the host identity or scope is
ambiguous.

## Read-only discovery

Start from repository state and compare the installed layer without printing
secrets:

```bash
git status --short --branch
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main

ssh beelink 'hostname; uname -a; systemctl is-system-running'
ssh pi 'hostname; uname -a; systemctl is-system-running'
ssh beelink 'sudo k3s kubectl get nodes -o wide'
```

For a tracked host file, use the documented helper's check mode when available,
or compare a root-readable installed copy to the repository input without
echoing its contents into chat. Inspect services, listeners, mounts, disk space,
package policy, and logs before restarting anything. Preserve the first useful
failure signal.

For a new host, obtain its Ed25519 fingerprint from a physical console or other
authenticated out-of-band channel and compare it character for character
before accepting SSH. Never use `StrictHostKeyChecking=no` or trust an
unauthenticated `ssh-keyscan` result.

## Supported workflows

### Apply a tracked host policy

1. Make the repository change and document how it will be applied.
2. Validate and merge through the protected workflow.
3. Operate only from the exact clean merged revision:

   ```bash
   git fetch origin main
   test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
   test -z "$(git status --porcelain)"
   ```

4. Run the repository's idempotent host helper when one exists. Do not retype a
   partial version of it.
5. Compare the installed file with the repository copy.
6. Verify syntax before reload, then verify service health, listeners, cluster
   impact, and a real client path.

### Provision a fresh agent host

Follow the cluster manual's complete identity, network, architecture, package,
NFS, host-policy, one-time token, taint/cordon, and platform-admission sequence.
The Pi-specific join helper is not a generic new-node script. Create and review
host-specific inputs before the first mutating SSH/SCP command.

Use only the exact pinned installer path and release selected by the repository
helper. Delete the exact short-lived bootstrap token after admission. Never
place a token in Git, command output, or an unprotected file.

### Change NFS exports or JuiceFS prerequisites

Treat an export change as data-boundary work. Resolve every current PV, mount,
writer, backup, client address, UID/GID, and `root_squash` dependency. Prefer
exact child exports; do not introduce a broad parent export around a protected
subtree. Reload exports only after syntax validation, then test from every
intended client and prove unintended clients remain denied.

For JuiceFS, use the repository host-preparation helper to manage `/dev/fuse`,
mount propagation prerequisites, the exact cache location, inotify policy, and
the narrow AppArmor rule. Do not delete cache while a live mount can use it.

### Package or reboot maintenance

Audit effective package origins and dry-run behavior before applying updates.
Do not broaden the Pi's security-only unattended policy, enable automatic
reboots, or copy that OS-specific policy to another host without review. Before
reboot, verify the other failure domain, Longhorn, Flux, and backups, and state
the services expected to disappear.

## Hard stops

Do not:

- run fresh-install, bootstrap, or join helpers against an existing K3s unit or
  data directory;
- use those helpers as a K3s upgrade or recovery mechanism;
- claim Beelink replacement or control-plane restore is supported;
- overwrite `/etc/rancher/k3s/config.yaml` and restart K3s without a complete
  state-aware plan;
- expose or rotate the K3s server token casually; historical recovery material
  may depend on the matching token;
- apply Pi-specific unsafe sysctls, update policy, network identity, or NFS
  trust to a generic node;
- use mutable download/install pipelines such as piping a remote script to a
  shell;
- add a broad NFS export, disable `root_squash`, or delete an NFS tree merely
  because Kubernetes objects no longer reference it; or
- print SOPS identities, JuiceFS keys, repository passwords, or join tokens.

## Rollback and evidence

Before mutation, save a root-readable backup of the exact installed
configuration in the helper-approved location and know the syntax/reload path
for restoring it. Roll back one plane at a time: installed host file and
service first, then Git through a reviewed revert if desired state must also
change. A Git revert alone does not repair a host.

Completion evidence includes the exact Git revision, host fingerprint/identity,
repository-to-installed comparison, helper output, syntax checks, service and
listener status, Kubernetes node/volume impact, client-path tests, rollback
location, and every external action. Never claim host rollout from a merged PR
alone.
