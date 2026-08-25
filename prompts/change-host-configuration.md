# Task brief: change repository-owned host configuration

Change `[HOST CONFIGURATION]` on `[HOST]` while keeping repository intent,
installed host state, service reload, and rollback as separate controlled
planes. A merged host-file change does not deploy itself.

## Required inputs

- Exact host name, fingerprint/identity, OS, and physical role: [values]
- Repository input and installed destination: [paths]
- Owning helper/script and its check/apply behavior: [path and facts]
- Current installed checksum/effective setting: [evidence]
- Desired behavior and reason: [details]
- Affected systemd service, listener, mount, package, sysctl, or export: [inventory]
- Cluster, workload, NFS, JuiceFS, and network impact: [analysis]
- Syntax/test command and safe client acceptance: [procedure]
- Installed-file backup and service rollback path: [details]
- Window, downtime, and exact target Git revision: [values]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact host input/helper/docs paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and required checks]
- Read-only cluster/host access: [yes/no; host and impact inspection]
- Live cluster/host mutation: [yes/no; copy, package, reload, restart, reboot scope]
- Application-state mutation: [yes/no; exact UI/API objects; normally no]
- External/provider mutation: [yes/no; router, DNS, DHCP, inventory objects]
- Destructive actions: [yes/no; exact host files/data; normally no]

Repository edit, merge, and host apply are independent permissions. Authority
for the Pi does not authorize the Beelink, and vice versa.

## Manuals and skills

Load `home-server-safety`, `node-host-operations`, `cluster-operations`,
`network-services`, `secrets-sops`, `high-risk-review`, and `validation`; add
`juicefs-media`, `storage-recovery`, or `backup-restore` when applicable. Read
cluster-operations configuration ownership, architecture physical dependencies,
the relevant runbook section, and the exact repository helper before acting.

## Workflow

1. Authenticate the exact host and record Git/worktree state. Compare repository
   input, helper logic, installed file, effective service state, listeners,
   mounts, packages, and logs without printing secrets.
2. Classify the setting as host-owned. If Kubernetes, application state, router,
   provider, or K3s-packaged Addon owns it, route to that workflow instead of
   creating competing host configuration.
3. Inventory blast radius across K3s, node DNS, NFS clients/exports, JuiceFS
   FUSE/cache, storage, interfaces, firewall, host-network pods, physical
   services, and the other node.
4. Design the smallest idempotent repository edit. Preserve host-specific
   identity and fail-closed checks. Do not copy Pi-specific sysctls, unattended
   update policy, NFS trust, or network identity to another host.
5. Run syntax/unit checks and the complete applicable repository validation.
   Explain any privileged, sysctl, host-network, broad-trust, package-source, or
   high-risk delta.
6. Merge only through the protected path. Before host application, fetch and
   prove the checkout is clean and exactly equals the merged revision.
7. Save a root-readable backup of the exact installed configuration in the
   helper-approved location. Use the repository helper rather than retyping a
   partial copy/apply procedure.
8. Compare installed content with the repository source, run syntax validation,
   then reload/restart only the exact authorized service. Reboot only when
   explicitly scoped and after planned-node-maintenance preflight.
9. Verify service state, listener/mount/effective settings, node and Longhorn
   health, dependent workloads, and a real intended client path. Prove denied
   clients remain denied for trust-boundary changes.
10. Record the installed revision and any host/external drift. A successful PR or
    Flux status is not evidence that the host file changed.

## Hard stops

Stop for host-identity ambiguity, unexplained installed drift, missing helper or
rollback copy, invalid syntax, secret output, broad NFS export, disabled
root_squash, mutable remote installer, unreviewed sysctl/trust expansion, or
impact on a service without a maintenance plan.

Do not overwrite existing K3s config or data, use fresh-install helpers for an
upgrade/recovery, casually rotate the server token, or claim Beelink restoration
is supported. Do not delete host data because Git no longer references it.

## Rollback and recovery

- Installed host state: restore the exact saved file/package setting and use its
  validated reload/restart path.
- Repository: revert through protected review if desired intent must also move
  back; this does not repair the host by itself.
- Kubernetes/Flux: reverse only separately authorized workload changes and prove
  the exact owner/revision.
- Storage/NFS/JuiceFS: preserve data and mounts; do not use deletion or cache
  clearing as config rollback.
- Network/provider: restore exact external objects separately and verify both
  intended and denied clients.
- Application state: reverse through the supported application interface.

## Evidence contract

Return exact host identity, base/merged revision, ownership decision, before/after
checksums and effective state, files/helper changed, syntax and repository
validation, installed backup location, apply/reload result, node/storage impact,
listener/mount/client tests, all external/live actions, and rollback readiness.

## Acceptance criteria

- [ ] The setting is correctly classified as host-owned and narrowly scoped.
- [ ] Repository and installed state match the exact reviewed revision.
- [ ] Syntax, service, node, storage, and client-path checks pass.
- [ ] Host-specific security and physical boundaries remain intact.
- [ ] Git, host, cluster, provider, and application rollback are distinguished.
- [ ] No unsupported K3s upgrade or Beelink recovery path is attempted.
