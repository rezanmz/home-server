# Personal assistant integrations

MCPHub is the control plane for personal tools. Open WebUI has one connection
to MCPHub; MCPHub launches local servers, connects to remote servers, limits
which tools are exposed, and records activity.

```text
Open WebUI -> MCPHub
                |-- official GPT Researcher MCP -> SearXNG + model provider
                |-- Vikunja MCP -> self-hosted Vikunja
                |-- reference filesystem MCP -> Syncthing Obsidian vault
                |-- Google Gmail MCP -> personal Gmail, read only
                |-- Google Calendar MCP -> personal calendar, read/write
                `-- Actual Budget MCP -> primary budget, read only
```

Server definitions, credentials, OAuth sessions, groups, and tool filters live
in MCPHub's PostgreSQL database. They are changed in MCPHub and protected by
the normal Longhorn and B2 backups. They are not reconciled from Git.

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

Vikunja uses the published `@eargollo/vikunja-mcp` package. Read and additive
operations are available by default. Its optional write tier and delete tier
remain off until deliberately enabled. The Vikunja API token should be scoped
to the areas the assistant actually uses.

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
summary, and spending by category. The integration targets the active primary
budget. Its local API cache belongs in `/tmp/actual-mcp`, not on MCPHub's
persistent volume, to avoid making an unnecessary second backup copy of the
plaintext financial database.

Actual's official headless API cannot complete the browser-based OpenID flow.
The normal Actual UI remains enforced on Authentik OpenID, while the API uses a
separate random password known only to Actual and MCPHub. The server hides the
password method from the browser and accepts it only when a client explicitly
selects it. Keep that credential in MCPHub's application state and never in a
Kubernetes Secret or repository file.

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
  vault reads, Actual Budget reads, and web research.
- **Assistant actions** adds calendar event creation/update, Vikunja additive
  task tools, and note creation in Inbox or Daily.
- Destructive task, calendar, and filesystem tools stay out of both groups.

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
