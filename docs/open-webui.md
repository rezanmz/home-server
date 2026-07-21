# Open WebUI operating model

Open WebUI at `chat.reza.network` is the cluster's personal chat client. Its
database owns models, prompts, profiles, automations, memories, retrieval
settings, and tool connections. A Kubernetes restart or an unrelated Flux
deployment must not rewrite those choices.

The deployment manifests own only the runtime boundary: image version,
resources, persistent storage, network access, login wiring, secure defaults,
and the addresses of cluster services such as Tika and SearXNG.

## Profiles and model choice

The current profiles are ordinary application records and remain editable in
**Workspace > Models**:

| Profile | Intended use |
| --- | --- |
| `Companion` | Conversation and explicitly requested personal actions |
| `Rigorous` | Evidence-backed answers with citations and clear uncertainty |
| `Deep Research` | Explicitly requested comprehensive research through GPT Researcher |
| `Model Steward` | Advisory research about current model choices and prices |

The raw provider model catalog remains visible. Profiles may be pinned for
convenience, but provider models are not hidden and no particular raw model is
treated as special.

Change a profile's base model in Open WebUI. Change GPT Researcher's internal
fast, smart, and strategic models in MCPHub. Model Steward may recommend a
change, but it does not apply one. Approval is the administrator making the
change in the relevant UI after reviewing quality, context limits, features,
and price.

Prompts must not include the cluster owner's name or tell a model to impersonate
a named person. Ordinary conversation does not automatically become a task,
calendar event, memory, or note.

## Tools and MCPHub

Open WebUI connects to one curated MCPHub group over the internal service
network. MCPHub owns individual servers, credentials, OAuth sessions, tool
filters, and activity records. Do not add separate Open WebUI connections for
each personal integration.

If a tool should be available by default, add it to the curated MCPHub group
and select that one group for the profile in Open WebUI. Keep mutation tools
out of factual and research-only profiles. Tool availability still requires an
explicit request before an external change.

See the personal-assistant guide for the package choices and permission model.

## Deep Research

Deep Research calls the official GPT Researcher MCP server managed by MCPHub.
The server is the upstream `assafelovic/gptr-mcp` implementation, not a local
replacement.

```text
Deep Research profile -> MCPHub -> official GPT Researcher MCP
                                      |-- internal SearXNG
                                      `-- configured model and embedding APIs
```

Models, retriever choice, depth, breadth, token limits, report style, and API
keys are MCPHub server settings. Experiment there, reload the server, and test
with a small explicit query. Package revision and resource/network boundaries
remain reviewed infrastructure changes.

Deep Research should not duplicate work with Open WebUI's ordinary pre-search.
The research profile uses GPT Researcher; ordinary agentic profiles use
Open WebUI search tools. Model Steward is budgeted to six unique searches and
eight page fetches and stops after two consecutive empty searches. Open WebUI
limits a response to a small number of tool-call iterations rather than an
effectively unbounded loop.

## Search backend

SearXNG is internal-only. It is reachable by Open WebUI and MCPHub so GPT
Researcher can use the same backend. The provider adapter tries one source at a
time and stops at the first usable result set. Free engines are attempted
before the Brave and SerpAPI paid fallbacks, so one successful search does not
consume both paid quotas.

SearXNG is a config-file-only helper, so its engine order and provider wiring
are an intentional declarative exception. Provider secrets remain encrypted
cluster secrets and are never included in request URLs or logs.

## Retrieval, embeddings, and memory

Embedding provider, model, prefixes, chunking, result count, and reranking are
application settings. Change them through Open WebUI, not a startup
reconciler. Embeddings from different models are not interchangeable; changing
the model or dimensions requires a complete, verified re-index of files,
knowledge collections, and memory.

The previous Gemini embedding migration completed and was removed from the pod
startup path. One-time migrations must not remain installed after verification.

Memory is selective, personal, and subordinate to the current conversation.
Store durable facts or preferences only when useful. Never store secrets,
credentials, speculation, or work information. An explicit current statement
overrides conflicting memory.

## Backup and recovery

The Open WebUI Longhorn volume contains the settings described above as well as
conversation and retrieval state. B2 backups protect that volume. Git alone
cannot recreate profiles, prompts, model choices, tool assignments, memories,
or user settings.

After a restore, verify OIDC login, model visibility, each profile's base model,
the single MCPHub connection, one SearXNG search, retrieval over a disposable
document, and a harmless personal-tool read. Do not introduce a reconciler to
make a restore appear complete; repair the backed-up application state through
the supported UI.

## Change workflow

Use Open WebUI for behavior, models, prompts, profiles, automations, memory,
retrieval, and tool assignment. Use MCPHub for MCP servers, tool policy,
credentials, OAuth, and GPT Researcher tuning. Use Git only for images,
resources, storage, network boundaries, shared service addresses, identity
wiring, and other cluster concerns.

The configuration-ownership guide contains the full decision rule and review
checklist.
