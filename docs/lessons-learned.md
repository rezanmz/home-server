# Operational lessons learned

This ledger records durable, non-obvious knowledge from real incidents so that
future agents and operators do not rediscover it the hard way. `AGENTS.md`
makes reviewing for lessons a standing step after any non-trivial fix.

## What belongs here

Record only knowledge that is specific to this repository, cluster, or its
external integrations and that would change future behavior:

- failure signatures that look like something else (silent failures, misleading
  logs, whole-integration symptoms);
- hidden couplings between separately updated components;
- recovery quirks and undocumented device or vendor behavior; and
- diagnostic recipes that materially shortened an investigation.

## What does not belong here

General engineering knowledge, obvious troubleshooting steps, one-off command
output, and task-specific evidence (those live in the commit, pull request, or
task record). If a lesson can be prevented mechanically, add that mechanism
(Renovate grouping, test, CI check, schema) in the same change and note it
here. Never record secret values.

---

## 2026-09-03 — Actual client/server schema drift freezes CYD finance data

Source: PR #300 (`finance-display` 0.3.3).

`finance-display` embeds `@actual-app/api`, whose schema must track the running
`actualbudget/actual-server` release line. After the server alone was upgraded
to 26.9.0, every sync failed with `SyncError: invalid-schema — SqliteError: no
such column: account_group_id` and never recovered: the CYD showed financial
data frozen at the last good sync while every pod looked healthy.

- **Watch for:** a CYD screen that is merely stale is an upstream data-path
  failure; check `finance-display` sync logs before suspecting the OTA path.
- **Prevention:** `renovate.json` groups `actualbudget/actual-server` with
  `@actual-app/api`. When adding a service that embeds a client library
  mirroring a server product, pair them in one Renovate group from day one.

### Second consumer found 2026-09-05

Source: MCPHub `assistant-suite-8` fix (actual-mcp API bump).

The MCPHub image (`images/mcphub-gptr/Dockerfile`) embeds the same client
library (`@actual-app/api`, built into `s-stefanov/actual-mcp` at pinned
revision) via `ARG ACTUAL_API_VERSION`, and #300 fixed only the
`finance-display` consumer. Hermes' Actual MCP tools stayed broken with the
same schema error even after the CYD fix. The `renovate:` ARG comment and the
"Actual Budget" group did not move the pin when the server upgraded — do not
assume Renovate caught every consumer. When bumping `actualbudget/actual-server`,
manually verify every `@actual-app/api` pin: `finance-display/package.json`,
`images/mcphub-gptr/Dockerfile` `ACTUAL_API_VERSION`, and the suite tag bump
(tag must change with content per the coupling gate).

## 2026-09-03 — TP-Link firmware update silently breaks Kasa local control

Source: incident investigation on 2026-09-03 (all seven KL125 bulbs
unavailable in Home Assistant while HS103 plugs kept working).

KL125 firmware `1.1.1 Build 260710 Rel.082646` (the July 2026 security fix for
local-communication interception) closed the legacy unauthenticated protocol:
TCP 9999 refused connections and UDP 9999 discovery went silent. It also
changed the KLAP handshake on TCP 80 so that `python-kasa` 0.10.2 — the newest
release, bundled in Home Assistant — fails with `AuthenticationError: Device
response did not match our challenge` even with cloud-valid credentials. Home
Assistant logs contain nothing about this: python-kasa swallows the errors and
entities simply flip to `unavailable`. Recovery is undocumented: opening the
Kasa app's Me → Settings → Third-Party Compatibility page re-enables the
legacy TCP 9999 channel, after which the integration reconnects on its own
retry cycle.

- **Watch for:** every entity of one integration unavailable at once is an
  integration/firmware/protocol problem, not a per-device failure. Absence of
  Home Assistant log errors proves nothing; query entity states directly
  (`/api/states/<entity>` with a token, or the UI).
- **Diagnostics that worked:** ARP from the Beelink node to confirm device
  identity at reserved IPs (bulbs answer ICMP only intermittently); direct
  TCP/UDP port probes from inside the Home Assistant pod; the TP-Link cloud
  API (`use1-wap.tplinkcloud.com` login → `getDeviceList` → passthrough
  `get_sysinfo`) to validate account binding, credentials, and firmware
  versions without exposing device secrets.
- **Durable fix:** reconfigure the `tplink` entries to encrypted local control
  once python-kasa supports the new handshake. Until then, control rides the
  unauthenticated legacy channel and can break again silently; re-read this
  entry before re-diagnosing.

## 2026-09-03 — Debugging LAN devices from the cluster

Source: the same incident.

- Pod-network sources cannot use UDP broadcast/multicast discovery against the
  LAN even when a NetworkPolicy explicitly allows the unicast port; broadcast
  does not traverse the pod→LAN path. Probe devices from the node (SSH to
  Beelink) when discovery seems dead.
- Consumer IoT devices answer ICMP and ARP unreliably (Wi-Fi power save). A
  missing ARP entry is not proof a device is offline; sweep the subnet once
  (ping each address, then read `ip neigh`) and compare MACs against the Kea
  reservation inventory.
- Live Kea reservations live in the hash-suffixed ConfigMap
  `kea-dhcp4-config-*` in the `network-services` namespace, not in `apps`.
- Home Assistant's entity→integration mapping is readable without the UI via
  `kubectl exec` into the pod using `/config/.storage/core.entity_registry`
  and `core.config_entries`. Read key names, domains, and titles only; never
  print credential values.

## 2026-09-03 — SABnzbd `bandwidth_max` is bytes/s: "20000" caps downloads at ~20 KB/s

Source: Eweka/Usenet slow-download incident on 2026-09-03 (queue pinned at
~30 KB/s for ~18 hours across all 190 items; an Eweka account lock was a
second, separate layer, fixed by a portal password reset).

`bandwidth_max = 20000` in `sabnzbd.ini` reads as "20000 KB/s" but SABnzbd
interprets the value as **bytes/s** — a ~20 KB/s hard cap. The downloader's
throttle loop (`downloader.py`: sleep-loop whenever `BPSMeter.bps >
bandwidth_limit`) pins throughput at exactly the ceiling: BPS meter debug
showed a steady 20–40 KB/s while queue items reported "Downloading" with zero
`mb` progress for hours. SABnzbd UI/API show `speedlimit_abs: 20000`, which
looks like a percentage-derived value and gives no hint of the unit.

The incident produced two wrong hypotheses before the real cause: an Eweka
per-IP throttle (disproven — raw probes got 5–55 MB/s through the same
tunnel), and the #293/#297 image bump (disproven — rolling back
`5.1.2-ls270` to `5.1.1-ls268` changed nothing, so the digest was restored).

- **Watch for:** any "everything crawls at one exact number" symptom in
  SABnzbd. A rock-steady KB/s ceiling that survives restarts, reconnects,
  pipelining changes, and connection-count changes is a configured limit, not
  a network fault. Check `bandwidth_max` first; its unit is bytes/s, and the
  BPS-meter debug lines (`[bpsmeter:356] Speed: …`) sit exactly at it.
- **Diagnostics that worked:** comparing BPS debug lines against
  `bandwidth_max` (matching numbers = the cap), then raw NNTP clients in the
  same container (fetching the exact stalled article IDs) to exonerate line,
  VPN exit, provider backends (all 5 Eweka IPs individually), NFS/Longhorn
  fsync writes, DNS, pipelining, and flow age (a single flow held 7.4 MB/s for
  25 minutes).
- **Durable fix:** express the intended cap with explicit units
  (`20971520` = 20 MiB/s) rather than a bare 20000; the value now lives as
  `bandwidth_max = 20971520`. Provider-side note: Eweka locks accounts
  (NNTP `502 Authentication Failed` with unchanged credentials, from any IP)
  after heavy volume from a shared VPN exit; a portal password reset clears
  it.

## 2026-09-10 — Library print() corrupts FastMCP stdio JSON-RPC; MCP tool calls hang silently

Source: MCPHub `assistant-suite-9` fix (gpt-researcher `deep_research`).

Open WebUI's `gpt-researcher-deep_research` calls produced no answer, no
error, and no tool result, while MCPHub's own upstream stderr log showed the
research *completing successfully* minutes earlier (correct cost, context,
sources). Every `quick_search` worked. The loss was between the stdio child
and MCPHub: FastMCP 3.x's stdio writer binds the process stdout buffer
directly, and gpt-researcher's `curator.py` dumps its entire source blob via
bare `print()` during every curated run. Interleaved non-protocol lines
corrupt the response frame; MCPHub's MCP SDK client drops unparseable stdout
lines through an `onerror` hook it never sets, so the pending `callTool`
promise simply hangs forever (upstream timeout is effectively infinite).
MCPHub forwards only child *stderr*, so the stdout pollution is invisible in
its logs.

- **Watch for:** any MCPHub tool whose server-side completion log exists but
  whose `Tool call result` line never follows — that combination means lost
  stdio frames or a killed child, not an LLM or retriever failure.
- **Diagnostic recipe:** grep MCPHub logs for the upstream's completion line,
  then for the paired `Tool call result` / activities-row absence; compare
  against a tool that does deliver on the same child.
- **Prevention:** `images/mcphub-gptr/Dockerfile` now redirects `sys.stdout`
  to stderr at server import and rebinds the pinned mcp SDK's writer to
  fd 1, both grep-verified fail-closed. When adding any stdio-transport MCP
  child, check the dependency tree for stdout writers first (same pattern as
  the Jellyseerr Rich-console patch).
- **Related quirk:** `PUT /api/servers/…` (and `/reload`) in MCPHub kill the
  stdio child; any in-flight long-running tool call dies with
  `McpError -32000: Connection closed` and its paid result is discarded.
  Edit server config only when nothing long-running is in flight.

## 2026-09-13 — CronJob DeadlineExceeded with zero pod logs means Pending, not slow

The nightly Syncthing Restic backup failed with `DeadlineExceeded` after its full
12-hour window for seven consecutive days. Every investigation instinct pointed
at restic, B2, or the NFS source — all healthy: the tree is ~6 MB, the repo reads
fine, and network from the job's node is normal. `kube_pod_status_unschedulable`
in Prometheus showed the truth: every backup pod had been stuck **Pending** the
entire time; `activeDeadlineSeconds` also bounds scheduling wait, and a pod that
never starts produces no logs anywhere. The Pi had crossed 99% of allocatable CPU
**requests** (3990m/4000m) when the Sep 7 JuiceFS Helm upgrade restarted its mount
pod with a 250m request; the backup job needed 50m and could not be scheduled or
preempt anything. Native sidecars (init containers with `restartPolicy: Always`)
are counted additively in node request totals — the `gluetun` sidecar accounts
for 50m of the ledger.

- **Watch for:** `DeadlineExceeded`/`BackoffLimitExceeded` on any CronJob whose
  pods leave no container logs — query `kube_pod_status_unschedulable` for the
  pod before touching the application.
- **Prevention:** `apps/syncthing/backups/cronjob.yaml` reserves only 10m CPU;
  burst (limits) still gets a full core.
- **Diagnostic recipe:** `sum(kube_pod_container_resource_requests{resource="cpu",
  node="..."})` plus `kubectl describe node` Allocated-resources ledger against
  the pending pod's request answers capacity rejections in one query.
- **Related drift:** the same incident family included `message length exceeds
  Telegram limits` failures: kube-state-metrics joins scrape-target labels
  (pod/instance/container/endpoint/service) into recording-rule series, so
  `SyncthingBackupStale` fired one duplicate alert instance per target label set
  into a single grouped Telegram message over 4096 characters. The recording
  rules in `infrastructure/observability/backup-health-rules.yaml` now aggregate
  `max by (namespace, cronjob)` to one series per job.

## 2026-09-13 — Kubelet restart triggers a permanent Longhorn FailedMount storm on healthy volumes

Two `systemctl restart k3s` operations on beelink (K3s config change) produced a
stream of Telegram alerts: `MountVolume.SetUp failed … Aborted desc = no Pending
workload pods for volume … to be mounted: map[Failed:[<old pods>] Running:[<live
pod>]]` for `open-webui`, `actual-horizon`, and `finance-display`, repeating every
~2 minutes per pod with counts climbing past 20. Every volume was `attached` +
`healthy` and every application was fully functional — the live bind mounts
survive the kubelet restart; only the *replayed* `NodePublish` for an
already-`Running` pod is rejected by Longhorn's CSI plugin (upstream
longhorn/longhorn#8072), and kubelet's retry loop re-emits the Warning forever.

- **Watch for:** `FailedMount … no Pending workload pods` where the listed
  `Running:` pod is the current serving pod and the volume reports
  `state=attached robust=healthy`. It is not data corruption.
- **Remedy:** restart each affected pod once (`kubectl delete pod`); the
  replacement mounts cleanly as a `Pending` workload and the event loop dies
  with the old pod. Then delete the stale `Failed`/`Evicted` pod leftovers the
  message's `Failed:[…]` list names — they persist for days and appear in every
  later alert for the same volume.
- **Verification pitfall:** probing the mount at the manifest's nominal path
  (`/app/data`) failed while the real container `mountPath` (`/app/backend/data`)
  was healthy — read `.spec.containers[*].volumeMounts` before declaring a mount
  broken.
- **Prevention:** expect this alert storm in the minutes after any kubelet/k3s
  service restart on a Longhorn node; it is self-inflicted noise, not an outage.

## 2026-09-14 — Alertmanager's default Telegram template silently degrades oversized groups

When a grouped alert notification rendered from Alertmanager's built-in
`telegram.default.message` exceeds Telegram's 4096-character limit under
`parse_mode: HTML`, the notifier does NOT fail: it sends the literal placeholder
`Alertmanager notification could not be sent: message length exceeds Telegram
limits…` instead of the alert content and returns success
(`prometheus/alertmanager` `notify/telegram/telegram.go`, the HTML branch).
`alertmanager_notifications_failed_total` stays at zero, so dashboards and
alert-on-alerting rules see nothing. During the Sep 7–13 backup gap this is how
`SyncthingBackupStale` notifications vanished while the operator believed
delivery was healthy; the operator only ever saw the placeholder itself.

- **Watch for:** the placeholder arriving as a normal-looking Telegram message
  from the alert bot — it is not an informational relay, it is a lost
  notification. Correlate with the firing alert list, not with delivery
  counters.
- **Diagnostic recipe:** `increase(alertmanager_notifications_failed_total
  {integration="telegram"}[N])` cannot prove delivery health for this failure
  mode; query the receivers' message template instead
  (`/api/v2/status` → `config.original`).
- **Prevention:** make the message length-bounded by construction. Two
  apparent shortcuts do NOT work in this stack: (a) custom templates are only
  auto-truncated on the notifier's non-HTML branch — with the default
  `parse_mode: HTML` even custom templates hit the same placeholder path; and
  (b) removing `parse_mode` (or setting it to `""`) is silently undone by the
  prometheus-operator: `provisionAlertmanagerConfiguration` parses the secret's
  config into alertmanager's structs and re-marshals it, and Telegram's
  `ParseMode` is `parse_mode,omitempty`, so an empty string round-trips away
  (verified live: `/api/v2/status` re-showed `parse_mode: HTML` after both
  #324 and #326). The durable fix is a template bounded by construction — cap
  alert instances per message (first 6 of N, alertname + description) — landed
  in `infrastructure/observability/alertmanager-config.sops.yaml` (#327); the
  instance-count duplication that fed the oversize was fixed by #320.

## 2026-09-15 — Silent MCP response streams are dropped at 300 s; long tool work must be job-plus-poll

A `deep_research` call completed successfully in 8m33s and MCPHub logged a
valid result, yet the Open WebUI chat kept its "in progress" state forever
and stored no answer (assistant row remained a 2-byte placeholder). The mcp
1.27.2 Python client in Open WebUI drops any MCP stream that stays silent
for 300 seconds — its GET stream disconnect logged at exactly +300 s after
session init — and a streamable-HTTP `tools/call` response that produces no
bytes until completion is exactly such a stream. MCPHub 1.0.37 registers no
progress or logging callback for stdio children (grep `setProgressCallback`
/ `loggingMessage` in `/app/src` returns nothing), so child-side
notifications cannot heartbeat the call, and completed results are never
replayed to a reconnected session. The earlier 2026-09-10 fix addressed
frame corruption on the same path; this is the timeout leg of the same
failure family.

- **Watch for:** any MCP tool whose server-side completion log exists but
  whose result never lands in the chat, with the call duration above
  ~300 s. Check the client's `GET stream disconnected` timestamp against
  session init before suspecting the LLM or retriever.
- **Diagnostic recipe:** Open WebUI stores nothing for an unfinished
  assistant turn — compare `chat_message` content length against the
  MCPHub `Tool call result` log time to prove delivery loss vs. generation
  failure.
- **Prevention:** `assistant-suite-10` carries
  `images/mcphub-gptr/gptr-mcp-async-research.patch`, which adds
  `start_research` (returns a research ID immediately, runs the research as
  a background task, records phases through the library's `log_handler`
  contract) and `research_status` (server-side long-poll clamped to 120 s,
  returning phase/progress/cost while running and the full deep_research
  payload on completion). Every MCP call stays bounded, and the chat shows
  the user periodic progress instead of silence. Do not reintroduce a
  single blocking call for minute-scale tool work on this transport chain.
- **Related quirk:** the run's 8-minute tail was entirely the source-curation
  LLM call (`curator.py`) on a reasoning model with a huge candidate set;
  tuning breadth or the curation model reduces duration but cannot make any
  fixed-timeout design safe for open-ended research.

## 2026-09-18 — Shared /dev/shm lets the worker's Rust core steal the server's socket

The durable root cause of the recurring "forward-auth host serves Authentik's
404" wedge (see the superseded 2026-09-15 entry below). The image runs one
Rust core per container: the `server` core binds `$TMPDIR/authentik.sock` to
serve the full router, and the `worker` core binds the *same path* to serve a
healthcheck-only router. `TMPDIR` is `/dev/shm` in this image, `run_unix()`
unlinks the path before binding, and our manifest mounted one `emptyDir` at
`/dev/shm` into both containers. So both binds succeeded and whichever core
started last owned the directory entry.

When the worker won, the embedded outpost's `get_outpost` call hit the
healthcheck router (which registers only `/-/health/*` plus a 404 fallback),
so it 404'd forever and every forward-auth host served the branded 404, while
native-OIDC apps stayed healthy. It is a startup race, not an upgrade defect:
the same code path exists in 2026.8.0/.8.1/.8.2, and any unrelated pod
recreate can flip the winner — which is why an image bump and a
`rollout restart` each appeared to "fix" it.

- **Fix:** give each container its own memory-backed `emptyDir` at `/dev/shm`
  (`server-shm` / `worker-shm`, 256Mi each so total tmpfs is unchanged). Pinned
  by `scripts/ci/test_authentik_contract.py`.
- **Discriminating check:** the two sockets answer differently. Probe the unix
  socket directly — a `404` on `/api/v3/outposts/instances/` (and on
  `/outpost.goauthentik.io/ping`) while the same path over TCP
  `localhost:9000` returns `200` proves the worker's router owns the path.
  `/dev/shm/authentik-mode` reading `worker` inside the `server` container is
  the same tell, because both containers share the volume.
- **Watch for:** do not accept "restart fixes it" as resolution. Confirm which
  router owns the socket before declaring the incident closed.

## 2026-09-15 — Wedged embedded outpost serves Authentik 404 for every forward-auth host

**Root cause corrected by the 2026-09-18 entry above; this entry records the
original symptom and its misleading first diagnosis.**

After the 2026.8.2 upgrade, the embedded Rust proxy outpost appeared to wedge:
every `/outpost.goauthentik.io/auth/traefik` subrequest returned Authentik's
404 page, so every forward-auth app (Homepage, Maintainerr, slskd, and the new
llm-gateway) showed a Not-Found page instead of a login redirect, while
native-OIDC apps (Open WebUI, MCPHub) and the IdP flows stayed healthy. The
server container logged `authentik::outpost get_outpost ... 404 Not Found`
every 5 seconds.

The 2026.8.2 upgrade was blamed and `kubectl -n apps rollout restart
deploy/authentik` appeared to restore provider matching. Both were wrong: the
upgrade was incidental and the restart merely re-rolled the socket race.
`#306` (2026-09-04) had "fixed" the identical symptom the same way by bumping
to 2026.8.1. Treat this entry's remedy as a band-aid only.

- **Watch for:** a *new* forward-auth service "returning 404 from the
  identity provider" — probe an existing forward-auth host
  (`homepage.reza.network`) first; if both 404, the shared outpost is the
  victim, not the new manifest.
- **Diagnostic recipe:** compare forward-auth vs native-OIDC apps, count
  repeated `get_outpost` warns (`... | grep -c get_outpost`), then apply the
  2026-09-18 discriminating check to identify which router owns the socket.

## 2026-09-15 — 9Router image entrypoint needs root setgroups; unprivileged pod must bypass it

Source: first deployment of `apps/9router`.

The upstream image runs its server through `/entrypoint.sh` = `chown -R
node:node /app/data; su-exec node …`, which presumes a root-start container.
Our pod is deliberately unprivileged (`runAsUser: 1000`, `capabilities:
drop: [ALL]`), so `su-exec` aborts with `setgroups: Operation not
permitted` and the pod crash-loops before the process starts.

- **Fix:** set `command: ["node"] args: ["custom-server.js"]` to exec the
  same process the entrypoint would, skipping chown and `su-exec`;
  `fsGroup: 1000` already owns the Longhorn volume, so the chown was
  always redundant for us.
- **Watch for:** any Node "non_root"-style image whose entrypoint chains a
  privilege drop; the CrashLoopBackOff signature is the single line
  `su-exec: setgroups: Operation not permitted` with no application output.

## 2026-09-15 — cloudflare-ddns only deletes records that vanish mid-session

Source: retiring `llm-gateway.reza.network`.

`favonia/cloudflare-ddns` deletes a record when it drops out of `DOMAINS`
during that container's uptime. When the list change also restarts the pod
(the normal Flux path), the new session never knew the removed domain, so
the A record persisted after merge, rollout, and several 5-minute sync
cycles — and split-DNS removal made it *look* healthy from inside the LAN.

- **Watch for:** a retired service whose route/workloads are gone but the
  public record still answers `dig … @1.1.1.1 +tcp` / Cloudflare DoH.
- **Recipe:** decrypt `apps/cloudflare-ddns/secrets.sops.yaml` in memory
  only, then `DELETE /zones/{id}/dns_records?name=…` via the API; the
  controller never recreates a name absent from its current list.

## 2026-09-16 — Default-deny workloads need BOTH egress and the target's ingress admission; a one-sided fix still refuses connections

Source: 9Router consumer wiring (Open WebUI, Hermes, gpt-researcher → 9Router `/v1`).

Adding an egress rule to a consumer's NetworkPolicy is not enough when the
target workload is itself default-deny. 9Router's own
`9router-application` ingress allowlist admitted only open-webui, mcphub,
and the traefik route — so after hermes' egress was allowed, every model
call still failed with `Connection refused` (even against the pod IP,
not just the Service). The failure looks like an app bug or a port issue
but is a dropped-by-policy TCP connect.

- **Watch for:** `Errno 111 Connection refused` from a pod that just got a
  new egress rule, where the target demonstrably listens on the port
  (verified with `netstat` inside the target).
- **Recipe:** check BOTH policies: the consumer's `egress` for the target
  and the target's `ingress` allowlist for the consumer. Verify with a raw
  `socket.create_connection` from the consumer pod, then confirm live
  policy with `kubectl get netpol -o yaml | grep <port>`.
- **Related trap:** the high-risk policy tracks some findings by egress
  rule *index* (internet-wide egress) and by whole-`spec` *hash* (ingress
  boundaries). Inserting an egress rule before the internet-wide rule
  shifts indexes and reads as new constructs; adding an ingress peer
  changes the spec hash and requires a reviewed baseline hash update.
- **Prevention:** when wiring a new consumer to a default-deny service,
  change both netpols in the same PR and note that mcphub deliberately
  has `egress: - {}` (arbitrary MCP servers), so it needs no counterpart.

## 2026-09-16 — A gateway migration can leave an embedding model id valid for one base URL and invalid for another

Source: Open WebUI retrieval after the LiteLLM → 9Router cutover.

Open WebUI's embedding config is split across two independent fields:
`rag.embedding_model` (the model id) and `rag.openai.api_base_url` (where the
request goes). 9Router spells provider-qualified models as
`<providerAlias>/<model>`, so `openrouter/google/gemini-embedding-2` is correct
against 9Router but is *not* a valid OpenRouter model id. Moving the chat
connection to 9Router while `rag.openai.api_base_url` still pointed at
`https://openrouter.ai/api/v1` left retrieval embeddings returning HTTP 400
`"Model openrouter/google/gemini-embedding-2 does not exist"` on every new
embed, while chat, rerank, STT, and TTS stayed healthy — so the failure is
invisible unless retrieval is exercised.

- **Watch for:** retrieval or memory that silently stops indexing or recalling
  while chat works. Embeddings are a separate code path from chat with their
  own base URL, key, and model id.
- **Recipe:** call Open WebUI's own `get_embedding_function` in the pod with the
  stored values, or `POST /api/v1/retrieval/embedding/update` and read back the
  stored `openai_config.url`. Compare the id against the base URL's own model
  listing: `GET <base>/v1/models`.
- **Related trap:** `chat.context_compaction.model` must also be a model the
  connection serves. When it is not, `_generate_summary` silently falls back to
  the chat model (`context_compaction.py`: the configured id is used only when
  it is already in the model map), so context compaction keeps "working" on the
  wrong model instead of erroring.
- **Prevention:** when repointing a consumer at 9Router, change the base URL and
  every model id in the same operation, and verify with a real request rather
  than the saved form values.

## 2026-09-16 — 9Router's admin API needs a signed session cookie; router keys only reach /v1

Source: pruning broken model ids from 9Router's catalog.

9Router's `/api/*` admin routes reject both the per-app router keys used for
`/v1` and unauthenticated requests with `401 {"error":"Unauthorized"}`. The
dashboard authenticates with an HS256 JWT in the `auth_token` cookie, signed
with the `JWT_SECRET` environment variable; the payload is `{authenticated:
true, iat, exp}` and needs no server-side session row.

- **Watch for:** `401` from `/api/combos`, `/api/models/disabled`, or
  `/api/settings` while `/v1` works fine with the same key.
- **Recipe:** mint the cookie inside the pod from `JWT_SECRET` — HMAC-SHA256
  over `base64url(header).base64url(payload)` — then send
  `Cookie: auth_token=…`.
- **Related trap:** disabled models live in the `kv` table under scope
  `disabledModels`, keyed by provider alias, with **bare** model names (the
  `ocg/` prefix appears only when listing). `POST /api/models/disabled` unions
  additively, so a later narrow POST can never re-enable a model; removal
  requires the `DELETE` method.

## 2026-09-16 — 9Router's container clock is UTC and its dashboard has no timezone setting

Source: dashboard times reported as not EST.

The 9Router image ships no tzdata and runs with an empty `TZ`, so the process
clock is UTC. Some times are formatted server-side — the Console Log line
prefix, and the `usageDaily` day key built from `getFullYear()`, `getMonth()`,
and `getDate()` — and those showed UTC wall-clock. Other dashboard times are
rendered in the browser with a bare `toLocaleString()`, so they follow the
client. No timezone control exists in the app's settings.

- **Watch for:** dashboard times that are exactly the local time plus the UTC
  offset, while another page looks correct.
- **Recipe:** run `date` and
  `node -e 'console.log(Intl.DateTimeFormat().resolvedOptions().timeZone)'`
  inside the pod. Node's bundled ICU resolves `America/New_York` even with no
  `/usr/share/zoneinfo`, so a `TZ` environment variable is sufficient — no
  tzdata package or zoneinfo mount is needed.
- **Note:** the same day-key bucketing means UTC day boundaries also shift the
  Usage page's daily totals; setting `TZ` corrects both.

## 2026-09-16 — Only chat completions accept a 9Router combo; other /v1 surfaces need a raw model id

Source: consolidating Open WebUI model pins onto the `chat`/`smart` combos.

9Router's combos are the failover unit, but combo expansion is implemented on
the chat route only. Probing `/v1` with `model: "chat"` gives
`Invalid model format` on `/v1/embeddings`, `/v1/audio/transcriptions`, and
`/v1/audio/speech` (and 404 on `/v1/rerank`, which has no route at all).
`/v1/images/generations` does expand a combo name, but resolves it against
image models the chat combo does not contain — `model: "smart"` returned
`No model found for "qwen/qwen3.8-max-0902"`.

- **Watch for:** a `model` pin that *looks* combo-backed but silently targets a
  single upstream model, so it loses failover without any error.
- **Recipe:** before pinning, send one real request with the combo name to the
  exact surface. A combo-eligible surface accepts it; the others reject with
  `Invalid model format`.
- **Consequence:** Open WebUI's embedding model, speech engines, and external
  reranker cannot be combo-backed and stay on their documented direct-provider
  exceptions. `chat.context_compaction.model` and `task.model.*` can and should
  name `chat`.

## 2026-09-17 — CPU-request saturation is not CPU exhaustion

Source: investigating why nothing new could be scheduled on `raspberrypi`.

The Pi reported 99% of allocatable CPU *requested* while actually using about
17% of its cores. Because the scheduler admits pods on requests, the node was
effectively full for placement while sitting idle in reality. The cause was a
copy-pasted `cpu: 250m` request applied to every workload, including services
measured at 1-13m.

- **Watch for:** `kubectl describe node` showing high request percentage next to
  a low `kubectl top` figure, and a `Pending` pod with `Insufficient cpu`
  while the node's own utilization looks low. Requests reserve scheduling
  capacity; they do not describe load.
- **Recipe:** size requests from a 14-day Prometheus peak per
  `namespace/pod/container`, not from a single sample. Two aggregation bugs
  produce false safety: grouping by container name merges unrelated pods that
  share a name (`postgresql`, `server`, `manager`), and dead ReplicaSet
  generations inflate the peak. Filter to pods that are currently live.
- **Hidden coupling:** one shared Helm value can serve several pods. Traefik's
  single `resources` block feeds both DaemonSet instances, and the
  `raspberrypi` instance peaks higher (58m) than the Beelink one (3m) — sizing
  from the Beelink sample would have put the internet-facing ingress below its
  own measured peak. JuiceFS mount pods share one `mountPodPatch` the same way;
  their measured peaks (341m CPU / 1161Mi memory) already exceed the reviewed
  request, so that patch must not be reduced.
- **Related setting:** Longhorn's `guaranteedInstanceManagerCPU` reserves a
  percentage of *each* node's allocatable CPU per instance-manager pod. A
  percentage is not a portable unit across differently sized nodes: 12%
  reserves 1440m on the 12-core Beelink but only 480m on the 4-core Pi. An
  attempt to lower it to 6% was reverted after measurement; see the entry below.
- **Consequence:** requests must stay above each workload's observed peak so a
  busy pod is not competing from outside its own reservation. Reclaim capacity
  by lowering over-sized requests, not by lowering a request below the load it
  is sized to carry.

## 2026-09-17 — Longhorn records a Danger Zone setting but refuses to apply it

Source: investigating why `guaranteedInstanceManagerCPU` had no live effect.

`Setting/guaranteed-instance-manager-cpu` accepted `{"v1":"6","v2":"6"}` but its
live instance-manager pods kept their original 1440m and 480m requests. The
setting was **not ignored**: it is a Danger Zone setting that Longhorn applies
only when the target instance-manager has no running engine or replica
processes. `longhorn-manager` logged the refusal 40 times in six hours via
`setting_controller.go:200`:

```
failed to sync setting for longhorn-system/guaranteed-instance-manager-cpu:
  current state prevents this: failed to apply guaranteed-instance-manager-cpu
  setting for data engine v1 to Longhorn components when there are running
  engine instances. It will be eventually applied
```

- **Watch for:** a Helm value that is visibly correct in Git and in the CR, yet
  has no effect on the running pods. Check `Setting.status.applied`, not just
  `Setting.value`.
- **Recipe:** `kubectl -n longhorn-system get setting <name> -o json` and read
  `status.applied`; `kubectl get settings -n longhorn-system -o json` and filter
  `status.applied==false` to list every unapplied Danger Zone setting at once.
  The value becomes live at the next instance-manager recreation, e.g. a
  Longhorn upgrade.
- **Hidden coupling:** an unapplied setting is an *armed* change, not an inert
  one. It applied to nobody when written, but it silently applies to every
  instance-manager that is later recreated — typically during a Longhorn
  upgrade, far from the original change and its review.
- **Consequence:** treat Danger Zone settings as scheduled deployments. A
  percentage that is safe on the largest node can under-provision a smaller
  one; here 6% reserved 720m on the Beelink but only 240m on the Pi, whose
  instance-manager both peaks at 614m and exceeds 240m in 6.9% of sampled
  5-minute windows. Use the per-node millicore override
  (`Node.spec.instanceManagerCPURequest`) when node sizes differ.

## 2026-09-17 — A missing NFS subdirectory blocks pod start behind root_squash

Source: MCPHub failed to start during the request right-sizing rollout.

Restarting MCPHub produced `failed to create subPath directory for volumeMount
"obsidian-vault" of container "mcphub"`, and the pod never left `Pending`.
Hermes then failed behind it, because its `wait-for-mcphub-tools` init
container requires MCPHub's tool registry to answer. The service-level symptom
was "MCPHub is down", not a storage error.

The cause was a missing directory on the Pi's NFS export. `apps/mcphub` mounts
`vault`, `vault/Inbox`, and `vault/Daily` as `subPath` over-mounts, but
`vault/Daily` did not exist. kubelet creates a missing subPath directory as
root, and `/etc/exports.d/home-server.exports` exports the Syncthing tree with
`root_squash`, so the creating uid maps to `nobody` and cannot write inside
`vault/` (owned by `reza`, mode 755). Creation failed and the mount sequence
aborted.

- **Watch for:** a workload that runs fine for weeks and then cannot start
  after an unrelated restart. The old pod had been holding its mounts since
  before the directory disappeared, so the manifest was latent-broken the whole
  time. A restart is a real test of a NFS subPath contract; a long-running pod
  proves nothing about it.
- **Recipe:** when a pod reports a subPath creation failure, check that every
  `subPath` directory exists on the exporting host with a mode the squashed
  uid can traverse, then recheck:
  `sudo k3s kubectl -n apps exec deploy/mcphub -c mcphub -- sh -lc 'test -r /vault && test -w /vault/Inbox && test -w /vault/Daily'`.
- **Cause of this instance:** `/home/reza/persistent/syncthing/data/vault/Daily`
  was absent. It was recreated as `reza:reza` mode 700, matching `Inbox`.
- **Consequence:** any `subPath` under a `root_squash` NFS export depends on a
  directory that kubelet cannot create for you. Create it out of band on the
  Pi, and treat a pod restart as the moment to verify the boundary rather than
  assume a previously running mount still resolves.
