# Open WebUI operating model

Open WebUI at `chat.reza.network` is the personal chat client for this cluster.
It is not an autonomous administrator. Conversations may search and analyze,
but changes to the cluster, accounts, calendar, tasks, notes, or other external
systems still require an explicit request and the normal confirmation rules of
the relevant tool.

The reconciler in `apps/open-webui/config/reconcile.py` applies the reviewed
baseline on every pod start. It creates missing managed objects, repairs
security-sensitive settings, and preserves the administrator's later choice of
base model for managed profiles. This split keeps policy declarative without
making fast-moving model choices require a Git change.

## Choosing a profile

| Profile | Use it for | Evidence and tools | Cost behavior |
| --- | --- | --- | --- |
| Ordinary provider model | Conversation, writing, lightweight questions, and personal assistance | Native web, notes, knowledge, memory, and personal tools are available according to the model's reviewed defaults | One normal provider request plus any explicitly used tool |
| `Companion` | A stable conversational preset whose provider model can be changed without changing its behavior or tools | Personal companion prompt plus the reviewed ordinary-chat tools | One normal provider request plus any explicitly used tool |
| `Rigorous` | Important factual answers where unsupported claims would be harmful | Requires claim-level evidence, distinguishes source statements from inference, reports uncertainty, and refuses to invent citations. It is read-only: no memory or external-action tools | Normal model and search cost; it does not call GPT Researcher |
| `Deep Research` | An explicitly requested comprehensive research report | Calls the internal GPT Researcher tool once, returns the report with sources and reported estimated cost, and does not duplicate the work with native web search | Multiple model, embedding, search, and page-processing calls; materially more expensive |
| `Model Steward` | Reviewing whether the current role-to-model assignments should change | Native web only. Produces recommendations with exact model IDs, current pricing, availability status, evidence, and trade-offs | Advisory only; no paid benchmark or automatic configuration change |

The personal companion prompt deliberately does not turn ordinary conversation
into a task, note, memory, or calendar item. Such actions require an explicit
request. Managed prompts never use the cluster owner's name or tell a model to
impersonate a named person.

## Model selection and approval

Rapid model turnover is handled through two layers:

1. The managed profile is stable and defines behavior, permissions, and tool
   boundaries.
2. Its base provider model remains editable in **Workspace > Models**.

The reconciler seeds a safe default only when a profile is first created. A
later administrator selection is retained across restarts. GPT Researcher's
three internal roles are the exception because they run outside Open WebUI;
review `FAST_LLM`, `SMART_LLM`, and `STRATEGIC_LLM` in
`apps/gpt-researcher/config/researcher.json`, then change them through a pull
request.

The administrator's chat model selector contains the complete live provider
catalog. `Companion`, `Rigorous`, `Deep Research`, and `Model Steward` are
pinned and sorted first; raw models such as GLM or provider aliases remain
ordinary unpinned choices. The admin-only access-control bypass is enabled for
catalog browsing, while global model-access bypass remains disabled, so normal
users do not inherit unrestricted model access.

The weekly `Model Steward` automation runs Monday at 09:00
`America/Toronto`. It creates a visible advisory chat. Open WebUI does not
guarantee that an automation result will be pinned, so pin a useful report
manually. The report is a recommendation, not an approval request with an
executable **Approve** button. Approval means either:

- select a new base model in **Workspace > Models** for an Open WebUI profile;
  or
- review and merge a Git change to GPT Researcher's role mapping.

Replying “approve” in the report chat does not mutate configuration. The
steward may recommend no change and may not spend money on comparative
benchmarks.

### GPT Researcher model-update pipeline

The scheduled **GPT Researcher model maintenance** workflow checks the current
`FAST_LLM`, `SMART_LLM`, and `STRATEGIC_LLM` mappings against OpenRouter's
public catalog each Monday. It verifies availability, text output, context and
completion limits, required parameters, expiration metadata, and published
pricing. It performs no inference, benchmark, recommendation, issue creation,
or PR creation during a healthy scheduled check.

To apply a Model Steward recommendation:

1. Open **GitHub Actions > GPT Researcher model maintenance > Run workflow**.
2. Enter one or more exact OpenRouter IDs. Leave a role blank to keep it.
3. The workflow validates the requested mapping, runs the repository tests,
   pushes a candidate branch, dispatches the complete cluster validation, and
   opens a pull request only if the configuration changed and validation
   passed.
4. Review the steward's evidence, pricing, and the exact JSON diff. Merging the
   PR is the approval and Flux performs the rollout.

The updater cannot change `EMBEDDING`. Embedding-model changes require a full
vector migration and rollback plan. Locally, the same catalog-only validation
is available with:

```bash
python3 scripts/update_gpt_researcher_models.py
```

## Deep Research architecture

```text
Deep Research profile
        |
        | authenticated internal OpenAPI call
        v
GPT Researcher service ----> SearXNG ----> public search engines
        |
        +-------------------> OpenRouter models and embeddings
```

GPT Researcher has no HTTPRoute and is not reachable from the LAN or Internet.
A bearer token shared only by its encrypted Secret and the Open WebUI
reconciler authenticates the OpenAPI endpoint. NetworkPolicy accepts requests
only from Open WebUI and Prometheus, blocks private and reserved destinations,
and permits only SearXNG plus public HTTP/HTTPS egress. The pod has no
Kubernetes API token, runs non-root with a read-only root filesystem, and keeps
temporary reports in a size-limited `emptyDir`.

Only one job may run at a time. Jobs have a 15-minute hard timeout. The service
accepts a self-contained question and one of three report depths; it does not
accept arbitrary URLs, files, provider configuration, MCP servers, deletion
requests, or shell commands. Reports persist in the originating Open WebUI
chat, not in GPT Researcher.

GPT Researcher is for an explicit request such as “do deep research on this.”
Ordinary chat and ordinary factual lookups must not call it. Its returned
`estimated_cost_usd` is best-effort telemetry rather than a provider invoice.
Use the **AI Services** Grafana dashboard to inspect use, success, latency,
busy responses, resource use, and the 30-day estimated cost.

## Retrieval and embeddings

Open WebUI uses the OpenAI-compatible OpenRouter endpoint with
`google/gemini-embedding-2` at its native 3,072 dimensions. The reconciler
reuses the existing encrypted OpenRouter provider credential; no duplicate API
key is stored in Git.

The retrieval baseline uses:

- asynchronous embeddings with three concurrent single-item requests;
- a document prefix of `title: none | text: `;
- a query prefix of `task: question answering | query: `;
- hybrid search with BM25 weight `0.4`;
- six initial results and four reranked results;
- Tika for document extraction.

An embedding-model change requires a complete rebuild because vectors produced
by different models are not interchangeable. The
`migrate-gemini-embeddings` init container performs that migration before the
main application starts:

1. retain the policy database backup;
2. make a lossless local copy of the previous Chroma directory;
3. start Open WebUI on pod loopback only;
4. reprocess every non-empty persisted file and knowledge collection through
   Open WebUI's own API;
5. generate replacement vectors for every SQLite memory row with Open WebUI's
   own embedding helper, then replace the per-user memory collections while the
   main application is stopped;
6. verify file model metadata and verify the exact memory IDs, documents,
   metadata, collection ownership, and 3,072-dimensional vectors;
7. record independent file and memory completion markers and allow the main
   container to start.

The temporary server disables Automations through a startup-only database
override and restores the exact prior value afterward, so a due personal
automation cannot be claimed during maintenance.

If the initial migration fails, the init container restores the entire old
Chroma directory and previous retrieval configuration. If file migration
already completed but the separate memory marker is absent, it takes
`vector-db-pre-gemini-memory-v4`, rebuilds only memory, and preserves the
working file index and target configuration on rollback. The next restart
retries after the underlying error is corrected. Local remediation backups
retain only the three newest policy database snapshots. They are rollback aids
on the same Longhorn volume, not off-site backups.

## Personal memory

Memory is selective, personal, and subordinate to the current conversation.
The preferred durable structure is:

```text
/profile             stable personal facts
/preferences         durable interaction and lifestyle preferences
/people              relationships useful to personal context
/home                household and homelab context
/projects/personal   active personal projects
```

Do not save every message. Do not save secrets, credentials, speculative
inferences, or information merely because it appeared once. The current
explicit statement overrides conflicting memory. Work data must remain on
work-controlled systems and must never enter this personal Open WebUI memory,
knowledge base, notes, or tools.

## SearXNG

SearXNG is internal-only and exists solely as Open WebUI and GPT Researcher's
search backend. It has no external route. Its reviewed engine set is kept
small—Brave, DuckDuckGo, Google CSE, and Startpage—to reduce duplicate and
low-quality results. Open WebUI continues to apply its own result limits and
document-fetch protections.

## Secrets and change workflow

The OpenRouter key remains in Open WebUI's encrypted persistent configuration.
`apps/gpt-researcher/secrets.sops.yaml` contains the GPT Researcher copy and
its independent service token. Never decrypt either into a tracked file or
print the values in logs.

For behavioral or permission changes, edit the reconciler and its tests. Use
the model-maintenance workflow for GPT Researcher LLM role changes; edit
`researcher.json` directly only when changing reviewed research depth or cost
limits. For search-engine changes, edit
`apps/open-webui/config/searxng-settings.yml`. Render, validate, review cost and
tool-boundary changes, and deploy through the normal pull request and Flux
workflow.

Operational commands and recovery procedures are in the
[incident runbook](runbook.md#open-webui-security-policy-and-extensions) and
[GPT Researcher runbook](runbook.md#gpt-researcher).
