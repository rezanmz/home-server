# Task brief: design control-plane recovery

Design and review a consistency-safe, encrypted, off-host backup and bare-metal
restore procedure for the single K3s server. The default outcome is a procedure,
automation/test design, and isolated rehearsal plan. It is not authorization to
stop, replace, restore, or rebuild the production Beelink.

This capability is currently unsupported. Do not describe it as supported until
an isolated restoration of a matched SQLite datastore and historical server
token has passed the defined acceptance tests.

## Required inputs

- Repository and exact reference revision: [path and commit]
- Current server identity, architecture, disks, LAN identity, and failure roles: [facts]
- Current K3s version, immutable binary/source checksum, install method, and config: [evidence]
- SQLite data location, filesystem, size, and current integrity observations: [facts]
- Current server-token location and historical token lineage: [locations/fingerprints only]
- Existing local archives and why they do or do not survive server-disk loss: [inventory]
- Off-host destination, trust boundary, retention, immutability, and capacity: [design inputs]
- Backup encryption mechanism and independently recoverable key custodians: [design inputs]
- Host bootstrap/config, SSH identity, certificates, and network prerequisites: [inventory]
- Required recovery point and recovery time objectives: [targets]
- Isolated rehearsal hardware/VM, bare-metal equivalence matrix, network
  isolation, and test owner: [details/evidence]
- Existing Pi agent certificate, node identity/password state, and isolated
  rejoin-clone method: [locations/fingerprints and test design; no values]
- Production services affected by Beelink loss, including DHCP and storage: [inventory]

Never put a server token, age private identity, encryption key, kubeconfig, or
decrypted archive content into this prompt.

## Authorization

Fill every line. Blank or ambiguous means no. The suggested default for live,
host, external, and destructive scopes is no.

- Repository edits: [yes/no; procedure, scripts, tests, SOPS metadata, CI paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target and draft/ready]
- Merge: [yes/no; exact PR and required checks]
- Remote workflow dispatch or rerun: [yes/no; exact workflow and ref]
- Registry or artifact publication: [yes/no; exact registry/repository/tag or artifact]
- Read-only cluster/host access: [yes/no; Beelink, agent, backup, and log scope]
- Live cluster mutation: [yes/no; exact production Kubernetes objects; default no]
- Host mutation: [yes/no; exact disposable or production hosts; production default no]
- Application-state mutation: [yes/no; exact disposable or production application data]
- External/provider mutation: [yes/no; exact off-host storage, DNS, DHCP, or key objects]
- Credential or secret-material action: [yes/no; exact create/read/write/rotate/revoke scope; never include values]
- Destructive actions: [yes/no; exact disposable artifacts; production default no]

Research and design permission does not authorize taking the production API
offline, copying plaintext secrets, rotating a token, restoring a datastore, or
starting a replacement server on the production network.

A pull-request deliverable requires separate authority to create its commit,
push its branch, and open or update the pull request. Before a push or merge,
inspect current branch/path filters and authorize every inevitable remote
workflow, registry, or artifact-publication effect. If such an effect is denied,
use a proven non-triggering path or stop before the triggering action.

## Manuals, skills, and primary research

Load `home-server-safety`, `cluster-operations`, `node-host-operations`,
`backup-restore`, `storage-recovery`, `secrets-sops`, `incident-response`,
`high-risk-review`, and `validation`.

Read the current repository [cluster operations manual](../docs/cluster-operations.md),
[architecture](../docs/architecture.md), and [runbook](../docs/runbook.md).
Reconfirm active K3s host configuration and helper behavior from the reference
revision; the fresh-agent installer is not a recovery tool.

Research the current primary upstream documentation at task time:

- [K3s backup and restore](https://docs.k3s.io/datastore/backup-restore)
- [K3s token lifecycle](https://docs.k3s.io/cli/token)
- [K3s datastore types](https://docs.k3s.io/datastore)

Record access date and relevant upstream release/doc revision. Reconcile any
conflict between upstream guidance and the repository's actual single-server
SQLite topology. Do not replace primary sources with blogs or remembered steps.

## Threat and failure model

Cover at least:

- total Beelink system-disk loss, not merely deletion of one Kubernetes object;
- torn or inconsistent SQLite copies while K3s is writing;
- datastore corruption that remains unnoticed until older backups expire;
- a valid database paired with the wrong server token;
- token rotation: every pre-rotation backup requires its matching old token;
- theft of the backup set or full-administrator token;
- backup encryption keys stored only on the failed host or inside the cluster;
- stale, truncated, silently replaced, or unauthenticated off-host archives;
- wrong K3s binary/config, hostname, address, clock, certificates, or filesystem;
- a surviving agent rejected by the restored datastore because certificate,
  node identity, or node-password state does not match;
- two servers accidentally active with the same cluster identity;
- restored Flux/controllers contacting real providers during a rehearsal;
- restored storage bindings whose underlying volumes or NFS paths are absent; and
- Beelink-only DHCP/compute responsibilities that datastore recovery does not restore.

Distinguish confidentiality, integrity, availability, operator-error, and
rollback risks. State which risks the design accepts rather than claiming zero
risk.

## Design workflow

1. Establish the current server as a single K3s server using SQLite. Inventory
   exact binary, config, service unit, data directory, token lineage, host
   prerequisites, Git revision, Flux revision, and external physical roles.
2. Select a consistency mechanism supported by the current K3s/SQLite behavior.
   Define whether K3s must be stopped or quiesced and how the procedure proves
   that copied database files form one coherent point. A recursive file copy
   during writes is not accepted without primary-source proof and a test.
3. Define one immutable backup-set manifest that couples:
   - SQLite database/directory content and cryptographic checksums;
   - the matching historical server token, stored encrypted and identified by a
     non-secret fingerprint;
   - exact K3s binary/source checksum and architecture;
   - effective K3s/host config and service-unit checksum;
   - Git and Flux revisions, timestamp, host identity, and backup schema version;
   - encryption format, off-host object identity, and restore prerequisites.
4. Design encryption before transport. The off-host copy must reveal neither
   datastore secrets nor token. Recovery keys must be independently available
   after loss of the Beelink, Kubernetes, Git credentials, and ordinary network
   services. Document custodians and a non-secret key-loss test.
5. Design authenticated off-host transfer, atomic publication, checksum
   verification after upload, retention by complete backup set, failed-upload
   quarantine, capacity alerts, and protection from accidental overwrite.
   Never retain a database after deleting its matching token.
6. Define a fresh bare-metal restoration path for server OS identity, disks,
   pinned K3s artifact, host config, SQLite data, matching token, ownership/mode,
   network, and service startup. Keep it distinct from agent admission and from
   a new-cluster GitOps rebuild.
7. Define how a surviving Pi agent rejoins the restored cluster with its
   existing certificate and node identity/password state. Rehearse that path on
   an isolated clone of the agent state, or retain agent rejoin as unsupported;
   deleting identity state and silently treating it as a fresh node is not proof.
8. Define fencing that proves the old server cannot return before a replacement
   starts. Separate control-plane recovery from Kea DHCP, Longhorn data,
   application databases, NFS, router, and provider recovery.
9. Create fail-closed automation and tests only when repository edits are
   authorized. It must reject an unmatched token fingerprint, failed checksum,
   incomplete manifest, unexpected host identity, wrong architecture/version,
   existing K3s state, or production target during rehearsal.
10. Run repository validation and security review. Treat scripts handling server
   tokens, root host paths, remote storage, or replacement startup as high risk.
11. Produce an operator decision record: backup frequency, acceptable API
    outage, RPO/RTO, recovery key custody, rehearsal cadence, and criteria for
    promoting the gap from unsupported to supported.

## Isolated rehearsal

Use disposable hardware or a VM with no route to production LAN services,
agents, B2 write credentials, router, DHCP, or public providers. Before calling
a VM rehearsal bare-metal-equivalent, map and test the Beelink's architecture,
boot/service manager, disk layout and filesystem semantics, permissions,
hostname/address/clock identity, K3s config, and required host interfaces. Any
unrepresented layer stays explicitly unsupported. Never reuse the production
server address or allow both servers to become reachable.

Restore one exact backup set with its matching token and pinned K3s binary/config.
Prove archive checksums before decryption and database identity after startup.
Verify API availability, cluster/object UIDs, namespaces, encrypted Secrets,
service accounts, CRDs, Flux objects, storage bindings, and expected degraded
dependencies without permitting reconcilers to mutate external systems.

Attach an isolated clone of the current agent identity/state and prove its
certificate and node-password path can rejoin the restored datastore without
contacting production. Verify node UID/identity expectations, CNI state, and the
documented fallback if the existing agent state is irrecoverable. A fresh-agent
join alone does not test survival of the Pi.

Repeat negative tests for wrong token, corrupted database, truncated archive,
missing manifest, wrong K3s binary/config, unavailable encryption key, and
accidental production-network reachability. The harness must fail before
starting K3s in each unsafe case.

Record restore duration and every manual prerequisite. Dispose only exact
rehearsal artifacts under destructive authority; preserve the evidence report.

## Hard stops and abort gates

Stop when no consistency-safe snapshot mechanism is justified, the historical
token cannot be matched, encryption depends on the failed cluster, off-host
integrity cannot be authenticated, production and rehearsal networks can
collide, recovery would start two servers, or external side effects cannot be
blocked.

Do not rotate the production token as part of design, generate a new token for
an old database, use the agent installer, expose the token in logs/process
arguments, or call a local-on-Beelink archive disaster recovery.

## Rollback and recovery

- Design/repository: revert scripts and documentation through protected review;
  no production state should have changed.
- Rehearsal host: keep it isolated and stopped, preserve diagnostics, then remove
  only its exact disposable disk, credentials, and provider objects.
- Backup repository: publish new formats alongside old readable sets until the
  new restore passes; never rewrite historical sets in place.
- Token/encryption: retain matching historical tokens and old decryptors for all
  retained databases. Rotation is a separate, supported, rehearsed project.
- Future production cutover: fence the failed/old server, preserve its disk,
  allow only one control plane, and define a return-to-old-server boundary before
  any replacement startup.
- Physical services: recover DHCP, Longhorn, workloads, DNS, and external state
  through their own rollback plans.

## Evidence contract

Report every commit, push, pull-request, merge, workflow, registry, and
artifact-publication action in addition to the task-specific evidence below.

Return repository and upstream research revisions, topology/identity inventory,
failure model, consistency rationale, backup-set schema, checksums/fingerprints,
encryption and custody design, off-host publication/retention, fail-closed tests,
isolated restore observations, negative-test results, measured RPO/RTO, validation
and security findings, all authorized mutations, and remaining unsupported gaps.
Never include secret values.

## Acceptance criteria

- [ ] Durable behavior is documented; affected manuals, agent guidance, and examples are updated, or non-applicability is justified.
- [ ] The design atomically couples a consistency-safe SQLite backup with its
      exact historical server token and immutable K3s/host identity.
- [ ] Complete encrypted sets are authenticated, checksummed, and recoverable
      from off-host storage without the production cluster.
- [ ] Failure, threat, fencing, rollback, and physical-service models are explicit.
- [ ] Automation fails closed on token, checksum, identity, version, and network errors.
- [ ] Hardware/VM equivalence is explicit, and unrepresented bare-metal layers
      remain unsupported rather than being inferred from a VM boot.
- [ ] An isolated restore, surviving-agent identity/rejoin path, and negative
      tests are specified and rehearsed before support is claimed.
- [ ] Production execution remains out of scope unless separately authorized.
- [ ] The gap is called supported only after an authorized rehearsal passes and
      the reviewed manual records reproducible evidence.
