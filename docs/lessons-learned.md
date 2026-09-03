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
