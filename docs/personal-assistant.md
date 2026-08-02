# Personal assistant integrations

MCPHub is the control plane for personal tools. Open WebUI and Hermes Agent each
have one least-privilege connection to MCPHub; MCPHub launches local servers,
connects to remote servers, limits which tools are exposed, and records
activity.

```text
Open WebUI ------> MCPHub
Hermes Agent ----> MCPHub
                |-- official GPT Researcher MCP -> SearXNG + model provider
                |-- Vikunja MCP -> self-hosted Vikunja
                |-- reference filesystem MCP -> Syncthing Obsidian vault
                |-- Google Gmail MCP -> personal Gmail, read only
                |-- Google Calendar MCP -> personal calendar, read/write
                |-- Actual Budget MCP -> primary budget, read only
                |-- Home Assistant native MCP -> exposed home entities
                |-- Seerr MCP -> media search and reviewed requests
                |-- mcp-arr -> Radarr/Sonarr/Prowlarr reads + Lidarr music actions
                |-- Navidrome MCP -> library reads and playlist actions
                |-- Audiobookshelf MCP -> podcast feeds, subscriptions, and downloads
                |-- Grafana MCP -> dashboards, metrics, logs, and alerts, read only
                |-- Kubernetes MCP -> cluster diagnostics, read only
                |-- GitHub MCP -> personal repository context, read only
                |-- mcp-v8 -> stateless, isolated JavaScript calculations
                |-- LlamaCloud MCP -> LlamaParse Agentic document parsing
                `-- Google gcloud MCP -> quota-guarded Vision PDF OCR
```

Server definitions, credentials, OAuth sessions, groups, and tool filters live
in MCPHub's PostgreSQL database. They are changed in MCPHub and protected by
the normal Longhorn and B2 backups. They are not reconciled from Git.

## Hermes Agent

Hermes is the always-on companion and automation runtime. Open WebUI remains
the place for deliberate interactive chats and experimentation; Hermes owns
messaging sessions, persistent companion memory, scheduled jobs, and durable
background work. The proactive mechanism is Hermes cron plus its durable
Kanban dispatcher, not an unbounded magic heartbeat. A bounded recurring
"pulse" may inspect changes and decide whether to stay silent, but it must have
an explicit schedule, tool budget, quiet hours, and mutation limits.

The dashboard is public at `hermes.reza.network` only behind Hermes' native
Authentik OIDC/PKCE gate. The OpenAI-compatible API server is disabled. The
container receives no Kubernetes service-account token, Docker socket, host
filesystem mount, or route to private address space. Upstream requires root PID
1 for its s6 bootstrap; the supervised agent and dashboard processes run as uid
10000, the root filesystem is read-only, and only the capabilities required for
ownership repair and privilege drop remain.

All mutable Hermes state lives on `apps/hermes-agent-data` under `/opt/data` and
is protected by Longhorn's nightly B2 backup. Configure models, provider keys,
Telegram, allowlisted user IDs, `SOUL.md`, memory, skills, MCP connections,
toolsets, schedules, and pulse behavior in Hermes. Do not put them in this
repository. In particular, do not put a person's name in the companion prompt
or `SOUL.md` unless they explicitly ask for it.

Hermes connects only to a dedicated MCPHub group and bearer key. Start from the
same safe capabilities as **Assistant actions**: Gmail read-only, Actual
read-only, Calendar read/create/update, Vikunja read/create/update/complete,
and Obsidian reads plus writes limited by the mounted Inbox/Daily boundary.
Vikunja task deletion may remain available because it was explicitly requested,
but Hermes must ask for confirmation immediately before destructive use.
Calendar deletion and unrelated filesystem mutation remain absent. GPT
Researcher is for explicit research requests, not routine pulse jobs.

For short calculations and data transformations, Hermes uses the maintained
`r33drichards/mcp-js` (`mcp-v8`) server. It exposes one stateless `run_js` tool;
each call starts with a fresh V8 isolate. All upstream sandbox-hardening switches
are enabled, host filesystem reads, subprocesses, external imports, network
fetches, persistent heaps, and calls to other MCP servers remain disabled, and a
Kubernetes NetworkPolicy denies all egress. The pod has no service-account token,
runs non-root with a read-only root filesystem, permits one execution at a time,
and is capped at 250m CPU and 256 MiB memory. The normal execution defaults are
an 8 MiB V8 heap and five seconds. Use it for arithmetic, date calculations,
sorting, filtering, and small JSON transformations—not package installation,
web access, file processing, or background jobs.

Before enabling a messaging channel, use `hermes tools` to replace that
platform's broad defaults with the smallest required set. Keep terminal,
browser, Kubernetes, Docker, host filesystem, outbound messaging-to-third-parties,
and Home Assistant mutation disabled initially. The one code-execution exception
is MCPHub's bounded `mcp-v8` tool described above; it is not a shell and cannot
reach the host, filesystem, network, environment, or other MCP servers.
Enable `tool_loop_guardrails.hard_stop_enabled`, cap repeated failures and
no-progress calls, and verify unknown Telegram users are rejected. Use a
separate Telegram bot from infrastructure alerts.

## Current packages

GPT Researcher uses the official `assafelovic/gptr-mcp` server. It supplies
`deep_research`, `quick_search`, report generation, and source/context lookup.
The runtime image pins the upstream revision, but its models, retriever, limits,
and API keys are editable in MCPHub.

Obsidian uses the MCP project's reference filesystem server. The process sees
the Syncthing vault read-only, with writable over-mounts for `Inbox` and
`Daily`. The operating system enforces that boundary even if a client exposes
a broader filesystem tool. In the MCPHub group used by chat, keep destructive
filesystem tools disabled unless a specific workflow needs them.

Vikunja uses the published `@eargollo/vikunja-mcp` package. Read, additive,
update, completion, and task-deletion operations are available in action-capable
groups. Deletion was explicitly requested but still requires immediate user
confirmation before use. The Vikunja API token should be scoped to the areas
the assistant actually uses.

Gmail uses the published `@klodr/gmail-mcp` package with only the
`gmail.readonly` OAuth scope. The package filters its advertised tools from the
granted scopes, so mail mutation and sending tools are absent rather than
merely discouraged.

Calendar uses the published `@cocal/google-calendar-mcp` package. Its enabled
tool list is limited to calendar discovery, event reads/search, availability,
event creation, and event updates. Event deletion, invitation responses,
calendar-sharing administration, and unrelated Drive scopes remain disabled.

Actual Budget uses a pinned, reviewed revision of the maintained
`s-stefanov/actual-mcp` package and Actual's official `@actual-app/api`. The
runtime build aligns that API with the deployed Actual version and fails when
its production dependency audit reports an advisory. It is launched without
`--enable-write`, so only eight read tools are registered: accounts,
transactions, grouped categories, payees, rules, balance history, monthly
summary, and spending by category. The account tool also returns each account's
last completed reconciliation timestamp and its age in days; this is a small,
tested patch over the pinned maintained package. It joins the ordinary account
result with that read-only field through Actual's supported AQL interface; it is
not a separate MCP server. The
integration targets the active primary budget. Its local API cache belongs in `/tmp/actual-mcp`, not on MCPHub's
persistent volume, to avoid making an unnecessary second backup copy of the
plaintext financial database.

Actual's official headless API cannot complete the browser-based OpenID flow.
The normal Actual UI remains enforced on Authentik OpenID, while the API uses a
separate random password known only to Actual and MCPHub. The server hides the
password method from the browser and accepts it only when a client explicitly
selects it. Keep that credential in MCPHub's application state and never in a
Kubernetes Secret or repository file.

Home Assistant uses its built-in Model Context Protocol Server integration at
`/api/mcp`; it is not wrapped by a custom adapter. Home Assistant remains the
authorization boundary: expose only the entities, scripts, and areas an agent
should be able to inspect or control. The read group receives state/context
tools only. Control belongs only in action-capable groups and still requires an
explicit request for consequential changes such as locks, security devices, or
appliances.

Media automation deliberately separates discovery from mutation. The reviewed
upstream `aserper/jellyseerr-mcp` compatibility package supplies health, search,
request lookup, and media requests; its generic `raw_request` escape hatch is
excluded from every group. The published `mcp-arr-server` package provides
Radarr, Sonarr, Prowlarr, and Lidarr APIs. Read groups may inspect health,
queues, calendars, libraries,
profiles, and indexers. Action-capable groups add only the chosen music
acquisition tools for Lidarr; they do not gain arbitrary Radarr/Sonarr deletion
or queue mutation. The MCP server reaches the raw cluster Services, while the
human-facing Arr UIs remain LAN/WireGuard-only.

Navidrome uses the published `navidrome-mcp` package. It may search and inspect
the library, listening history, and playlists. Action-capable groups may manage
playlists, ratings, and starred items; destructive library or local-playback
tools remain excluded. Its dedicated MCP user authenticates with native
Subsonic credentials stored only in `navidrome-mcp`'s settings file on the
backed-up MCPHub application-data volume; its MCPHub registration stores only
the settings path. Browser traffic uses Authentik
forward authentication, while `/rest/*` and the internal MCP endpoint strip
external identity headers and use native credentials.

Audiobookshelf uses the published `audiobookshelf-mcp` package in verbose-tool
mode. Its dedicated Audiobookshelf administrator account can access only the
Podcasts library, has item deletion disabled, and exists because Audiobookshelf
requires an administrator to create podcast subscriptions. MCPHub exposes only
library discovery, RSS feed inspection, subscription creation, new-episode
checks, download-queue inspection, and episode downloads. Bulk OPML import,
queue clearing, episode removal/update/matching, and every author, series,
email, notification, or library mutation tool stay outside all groups. The
Audiobookshelf URL, token, and tool allow-list are application state in MCPHub;
the repository owns only the pinned executable and network boundary.

Operations tools are read-only at more than one layer. Grafana's official MCP
server starts with `--disable-write` and a Viewer service-account token. The
official Kubernetes MCP server starts with `--read-only` and a dedicated
service account that cannot read Secrets, exec into pods, or mutate resources.
The official GitHub MCP server starts with `--read-only`; use a fine-grained
personal token limited to the personal repositories the assistant actually
needs. None of these tools turns ordinary conversation into authorization to
make a change.

PDF reading has two providers behind the same MCPHub groups. LlamaParse uses
LlamaIndex's published `@llamaindex/llama-cloud-mcp` package and is the primary
provider for layout-heavy documents; request the `agentic` tier and `latest`
parser version when that quality is useful. Google OCR uses Google's published
`@google-cloud/gcloud-mcp` package and `DOCUMENT_TEXT_DETECTION` as a simple OCR
fallback. Both can read only PDFs already inside the Syncthing-backed Obsidian
vault. LlamaCloud receives that vault read-only in its isolated internal pod;
Google's command guard rejects any source outside `/vault`.

The Google integration has three independent cost controls. It runs in the
dedicated `rezanmz-homelab-ocr` project under a service account that can use
Vision and change objects only in the private
`rezanmz-homelab-ocr-staging` bucket. Native Google quotas are five general
Vision requests per minute, five document-OCR requests per minute, and 100
asynchronous pages in processing. Because Vision exposes no monthly quota
dimension, a persistent fail-closed MCPHub-side counter reserves pages before
submission and refuses page 1,001 in a Google billing month. Failed submissions
remain counted. The bucket deletes staging objects after one day and has soft
delete disabled. The 1,000-page guard covers this integration; separate Vision
usage in another project can still consume the billing account's shared free
tier.

Provider choice, the LlamaParse tier/version, credentials, and the Google
monthly page limit are operational settings in MCPHub. Do not add them to a
manifest. A sensible policy is LlamaParse Agentic for a document the user asks
to understand deeply, Google Vision for plain/scanned OCR or when LlamaParse is
unavailable, and no automatic double-processing. Delete the temporary
LlamaCloud upload and Google staging objects after extracting the requested
text.

The shared Google Desktop OAuth client file and the two packages' independent
refresh-token files live under MCPHub's persistent `/app/data/oauth` tree with
owner-only permissions. They are application data covered by Longhorn and B2,
not Kubernetes Secrets or repository content.

## Managing servers

Open MCPHub on the LAN or WireGuard and sign in through Authentik. Use
**Servers** to add, edit, reload, disable, or remove a server. Use **Groups** to
create the curated assistant endpoint and select the tools visible through it.
Use **Activity** to investigate calls and failures.

Changing a model or an experiment parameter is an operational change:

1. edit the GPT Researcher server in MCPHub;
2. change the relevant environment value;
3. save and reload that server;
4. run a small, explicitly requested research query;
5. inspect its sources and MCPHub activity before using the new setting for a
   large report.

No pull request is required. A package upgrade is different: it changes the
executable and therefore goes through image build, validation, review, and
deployment.

## Permission policy

Tool availability is not authorization to create work from ordinary
conversation. The assistant should create a task, event, or note only when the
user explicitly asks or confirms that action.

Use separate MCPHub groups for different risk levels:

- **Assistant read** contains Gmail read-only, calendar reads, Vikunja reads,
  vault reads, Actual Budget reads, media/library reads, Home Assistant state,
  read-only Grafana/Kubernetes/GitHub diagnostics, web research, and both
  document-reading providers.
- **Assistant actions** adds calendar event creation/update, Vikunja additive
  task tools, note creation in Inbox or Daily, reviewed Home Assistant control,
  Seerr requests, Lidarr music acquisition, Navidrome playlist/rating
  operations, and explicitly requested Audiobookshelf podcast subscriptions or
  episode downloads. It may also expose stateless `mcp-v8` execution for
  bounded calculations and transformations.
- Calendar deletion and destructive filesystem tools stay out of both groups.
  Vikunja task deletion is the single reviewed exception in action-capable
  groups and requires explicit confirmation immediately before the call.
  Generic HTTP escape hatches, Arr deletion/queue mutation, Kubernetes/Grafana
  writes, and GitHub writes stay out of every group.

Open WebUI should use the smallest group that fits a profile. A rigorous
fact-checking profile does not need mutation tools. A companion profile can use
the action group but still requires an explicit user instruction before a
mutation.

## Google authorization

Enable the Gmail and Google Calendar APIs in a personal Google Cloud project.
Complete each package's OAuth flow while signed into the personal Google
account. Gmail authorization must explicitly request only `gmail.readonly`.
Calendar authorization is limited to calendar and event access, while its MCP
tool filter excludes delete and invitation-response operations.

Work accounts and work data are out of scope. Never authorize a work account,
copy work mail into chat, or store work content in Open WebUI memory, the
Obsidian vault, Vikunja, or any personal cluster service.

## Recovery and rotation

MCPHub's database is the recovery source. After restore, verify every server is
connected, inspect the curated group's tool list, then perform a harmless read
through Open WebUI. Use a disposable task, event, Inbox note, and Daily entry
for mutation testing and remove them manually afterward.

Rotate upstream tokens and OAuth grants in MCPHub. Reload only the affected
server and test it before revoking the old credential. Do not copy operational
credentials into Kubernetes manifests to make a rotation “automatic.”
