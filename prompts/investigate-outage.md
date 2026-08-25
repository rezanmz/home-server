# Task brief: investigate an outage

Diagnose `[SYMPTOM/SERVICE]` and return evidence-backed cause, scope, and next
action. Investigation is read-only by default; do not silently turn diagnosis
into repair, restart, rollback, reconcile, credential rotation, or failover.

## Required inputs

- Symptom, affected users/clients, and first observed time: [facts/time zone]
- Service, namespace, hostname, protocol, and expected behavior: [values]
- Last known-good time and recent Git/PR/provider/application changes: [facts]
- Blast radius and safety impact: [single service/network/storage/cluster]
- Current alerts, error text, and reproduction: [redacted evidence]
- Stateful/storage/encryption dependencies: [inventory]
- Maintenance window or urgency: [constraints]
- Desired outcome: [diagnosis only/proposed fix/authorized recovery]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; exact diagnostic/fix paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Read-only cluster/host access: [yes/no; namespaces/hosts/log scope]
- Live cluster/host mutation: [yes/no; exact suspend/restart/reconcile/repair]
- Application-state mutation: [yes/no; exact diagnostic/repair UI/API objects]
- External/provider mutation: [yes/no; exact DNS/auth/storage/provider action]
- Destructive actions: [yes/no; exact objects; normally no]

Read-only access allows observation, not annotations, exec that writes state,
rollout restart, scale, job creation, token refresh, or Flux reconciliation.

## Manuals and skills

Load `home-server-safety` and `incident-response`; add `network-auth`,
`network-services`, `observability`, `storage-recovery`, `backup-restore`,
`secrets-sops`, or `validation` according to the failing boundary. Read the
runbook top-down triage and exact service section,
architecture traffic/storage boundaries, and cluster-operations for node or Flux
issues. Manuals override remembered fixes.

## Workflow

1. Record exact repository `HEAD`, `origin/main`, worktree state, incident timeline,
   and the first useful failure signal. Avoid making the evidence disappear.
2. When read access is authorized, establish node health and prove the Flux
   GitRepository, relevant root/child Kustomization, and HelmRelease revisions and
   conditions. Distinguish desired-state failure, reconciliation failure, and an
   application failure at a successfully reconciled revision.
3. Walk the request path from the affected client: DNS answer, certificate,
   Gateway/route conditions, middleware/auth, Service endpoints, proxy, pod,
   dependency, storage, and external provider. Test both intended and forbidden
   paths when access control is implicated.
4. Inspect pods/controllers, placement, probes, restarts, recent events, logs,
   Jobs/CronJobs, NetworkPolicy, PVC/PV/volume/attachment, node filesystem or NFS
   only as required. Redact secrets and sensitive application data.
5. Build a short hypothesis table: evidence for, evidence against, safe next test,
   and blast radius. Run discriminating read-only tests before selecting a cause.
6. Identify known live/repository drift separately. Do not normalize documented
   Longhorn EngineImage or live-only CoreDNS exceptions as an incident shortcut.
7. State the best-supported cause or the narrowed unknowns. Propose the smallest
   repair, recovery, or rollback with risk and recovery prerequisites.
8. Implement only if the corresponding repository/live/external/destructive
   fields authorize it. Normal repairs go through protected Git/Flux. Emergency
   live recovery requires suspending the exact owner, the minimum authorized
   change, matching Git, resume, and proof of no unexplained drift.

## Hard stops

Stop before mutation when evidence is insufficient, the owner is unclear, a
stateful repair lacks backup/read test, a secret would be disclosed, a provider
change is unauthorized, or the proposed action expands blast radius. The current
manuals do not establish routine Beelink/control-plane replacement, consistency-
safe off-host K3s datastore restoration, state-aware K3s upgrade, or production
Syncthing disaster recovery; do not improvise those from adjacent procedures.

## Rollback and recovery

For any authorized mitigation, define the exact pre-change state, time-box,
success/failure signal, and reversal before acting. Preserve logs/events first.
Live changes must either be represented in reviewed desired state or fully
reversed before Flux resumes. Do not call a restart a rollback when data or
external state changed.

## Evidence contract

Return a timestamped timeline, exact Git/Flux revisions, affected/unaffected
scope, request-path observations, relevant redacted events/logs, hypotheses and
tests, root cause/confidence, drift found, actions taken, recovery prerequisites,
and a prioritized next step. Separate observed fact from inference.

## Acceptance criteria

- [ ] The blast radius and failing boundary are evidenced, not guessed.
- [ ] Desired revision, reconciliation state, and runtime state are distinguished.
- [ ] The result provides a supported cause or a minimal set of discriminating
      next tests.
- [ ] No mutation exceeded its explicit authorization or erased needed evidence.
- [ ] Any repair has rollback/recovery gates and remaining uncertainty stated.
