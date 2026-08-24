# syntax=docker/dockerfile:1.25
ARG MCPHUB_IMAGE=samanhappy/mcphub:1.0.26@sha256:efdbfa3990d5a27d0611ba509db30bcdda196dc14ee2fe7d5f1706cae636ef37
ARG GCLOUD_IMAGE=gcr.io/google.com/cloudsdktool/google-cloud-cli:581.0.0-slim@sha256:2a52a0a58a2a267535f862bdb2026a5ababdb382ad1c49a06dd21a94df1cc4fc
ARG GO_IMAGE=golang:1.26.5-bookworm@sha256:1ecb7edf62a0408027bd5729dfd6b1b8766e578e8df93995b225dfd0944eb651

FROM ${GCLOUD_IMAGE} AS gcloud
FROM ${GO_IMAGE} AS operations-mcp-builder

ARG GRAFANA_MCP_REVISION=fac7c8a312c6f6aee8330de72182dcf45bf4ae26
ARG KUBERNETES_MCP_REVISION=56d6dfe9a1b994faca27fa3310cb54e3d3bc42ed
ARG GITHUB_MCP_REVISION=7629b6e7337e1fc4b11a0ca5fdea4af4edd21f6e

# Build the upstream operations servers from reviewed exact revisions. Some
# are signed releases; others remain intentionally pinned to reviewed commits
# for tool-surface compatibility. Static binaries keep the final MCPHub image
# small and allow the same Dockerfile to produce amd64 and arm64 images without
# downloading architecture-specific release assets at build time.
RUN git clone --filter=blob:none https://github.com/grafana/mcp-grafana.git /src/mcp-grafana \
    && git -C /src/mcp-grafana checkout --detach "${GRAFANA_MCP_REVISION}" \
    && test "$(git -C /src/mcp-grafana rev-parse HEAD)" = "${GRAFANA_MCP_REVISION}" \
    && git clone --filter=blob:none https://github.com/containers/kubernetes-mcp-server.git /src/kubernetes-mcp-server \
    && git -C /src/kubernetes-mcp-server checkout --detach "${KUBERNETES_MCP_REVISION}" \
    && test "$(git -C /src/kubernetes-mcp-server rev-parse HEAD)" = "${KUBERNETES_MCP_REVISION}" \
    && git clone --filter=blob:none https://github.com/github/github-mcp-server.git /src/github-mcp-server \
    && git -C /src/github-mcp-server checkout --detach "${GITHUB_MCP_REVISION}" \
    && test "$(git -C /src/github-mcp-server rev-parse HEAD)" = "${GITHUB_MCP_REVISION}" \
    && mkdir -p /out \
    && cd /src/mcp-grafana \
    && CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/mcp-grafana ./cmd/mcp-grafana \
    && cd /src/kubernetes-mcp-server \
    && CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/kubernetes-mcp-server ./cmd/kubernetes-mcp-server \
    && cd /src/github-mcp-server \
    && CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/github-mcp-server ./cmd/github-mcp-server

FROM ${MCPHUB_IMAGE}

ARG MCPHUB_VERSION
ARG GPTR_MCP_REVISION=63884773685b1f12c7f0d9e283b3d71a5b9b5fda
# renovate: datasource=pypi packageName=gpt-researcher versioning=pep440
ARG GPT_RESEARCHER_VERSION=0.16.0
# renovate: datasource=pypi packageName=fastmcp versioning=pep440
ARG FASTMCP_VERSION=2.14.7
# renovate: datasource=npm packageName=@modelcontextprotocol/server-filesystem versioning=semver
ARG FILESYSTEM_MCP_VERSION=2026.7.10
# renovate: datasource=npm packageName=@eargollo/vikunja-mcp versioning=semver
ARG VIKUNJA_MCP_VERSION=1.2.1
# renovate: datasource=npm packageName=@klodr/gmail-mcp versioning=semver
ARG GMAIL_MCP_VERSION=1.3.3
# renovate: datasource=npm packageName=@cocal/google-calendar-mcp versioning=semver
ARG GOOGLE_CALENDAR_MCP_VERSION=2.6.2
# renovate: datasource=npm packageName=@google-cloud/gcloud-mcp versioning=semver
ARG GCLOUD_MCP_VERSION=0.5.3
# renovate: datasource=pypi packageName=pypdf versioning=pep440
ARG PYPDF_VERSION=6.1.1
ARG JELLYSEERR_MCP_REVISION=fccf5689d64ad3ac6fc69dff8d4cb5ccf625a29a
# renovate: datasource=pypi packageName=httpx versioning=pep440
ARG JELLYSEERR_MCP_HTTPX_VERSION=0.28.1
# renovate: datasource=pypi packageName=python-dotenv versioning=pep440
ARG JELLYSEERR_MCP_DOTENV_VERSION=1.2.2
# renovate: datasource=pypi packageName=rich versioning=pep440
ARG JELLYSEERR_MCP_RICH_VERSION=14.3.4
# renovate: datasource=pypi packageName=mcp versioning=pep440
ARG JELLYSEERR_MCP_SDK_VERSION=1.28.1
# renovate: datasource=npm packageName=mcp-arr-server versioning=semver
ARG MCP_ARR_VERSION=1.7.3
# renovate: datasource=npm packageName=navidrome-mcp versioning=semver
ARG NAVIDROME_MCP_VERSION=2.2.0
# renovate: datasource=pypi packageName=audiobookshelf-mcp versioning=pep440
ARG AUDIOBOOKSHELF_MCP_VERSION=1.0.1
# renovate: datasource=pypi packageName=agent-utilities versioning=pep440
ARG AUDIOBOOKSHELF_MCP_AGENT_UTILITIES_VERSION=1.0.2
# renovate: datasource=pypi packageName=python-dotenv versioning=pep440
ARG AUDIOBOOKSHELF_MCP_DOTENV_VERSION=1.2.2
ARG ACTUAL_MCP_REVISION=24925803dff2dfb697cb6e53c06662ee66c94f01
# renovate: datasource=npm packageName=@actual-app/api versioning=semver
ARG ACTUAL_API_VERSION=26.7.0
# renovate: datasource=npm packageName=hono versioning=semver
ARG ACTUAL_MCP_HONO_VERSION=4.12.31
# renovate: datasource=npm packageName=@hono/node-server versioning=semver
ARG ACTUAL_MCP_HONO_NODE_SERVER_VERSION=2.0.11
# renovate: datasource=npm packageName=fast-uri versioning=semver
ARG ACTUAL_MCP_FAST_URI_VERSION=3.1.4
# renovate: datasource=npm packageName=body-parser versioning=semver
ARG ACTUAL_MCP_BODY_PARSER_VERSION=2.3.0
# renovate: datasource=npm packageName=qs versioning=semver
ARG ACTUAL_MCP_QS_VERSION=6.15.3
# renovate: datasource=npm packageName=brace-expansion versioning=semver
ARG ACTUAL_MCP_BRACE_EXPANSION_VERSION=2.1.2
# renovate: datasource=npm packageName=ua-parser-js versioning=semver
ARG ACTUAL_MCP_UA_PARSER_VERSION=2.0.10
# renovate: datasource=npm packageName=adm-zip versioning=semver
ARG ACTUAL_MCP_ADM_ZIP_VERSION=0.6.0
# renovate: datasource=npm packageName=better-sqlite3 versioning=semver
ARG ACTUAL_MCP_BETTER_SQLITE_VERSION=12.11.1

LABEL org.opencontainers.image.title="MCPHub with reviewed MCP packages" \
      org.opencontainers.image.description="MCPHub plus pinned personal-assistant, podcast, media, home, and read-only operations MCP packages" \
      org.opencontainers.image.source="https://github.com/rezanmz/home-server" \
      org.opencontainers.image.licenses="Apache-2.0 AND MIT AND AGPL-3.0" \
      org.opencontainers.image.version="${MCPHUB_VERSION}-assistant-suite-6" \
      org.opencontainers.image.revision="${GPTR_MCP_REVISION}"

USER 0:0

COPY --from=gcloud /usr/lib/google-cloud-sdk /opt/google-cloud-sdk
COPY vision-guard/gcloud /opt/vision-guard/bin/gcloud
COPY vision-guard/test_vision_guard.py /opt/vision-guard/bin/test_vision_guard.py
COPY vision-guard/start-gcloud-mcp /usr/local/bin/start-gcloud-mcp
COPY vision-guard/gcloud-mcp-allowlist.json /opt/vision-guard/gcloud-mcp-allowlist.json
COPY jellyseerr-mcp /usr/local/bin/jellyseerr-mcp
COPY actual-mcp-reconciliation.patch /tmp/actual-mcp-reconciliation.patch
COPY --from=operations-mcp-builder /out/mcp-grafana /usr/local/bin/mcp-grafana
COPY --from=operations-mcp-builder /out/kubernetes-mcp-server /usr/local/bin/kubernetes-mcp-server
COPY --from=operations-mcp-builder /out/github-mcp-server /usr/local/bin/github-mcp-server

# The upstream GPT Researcher project publishes source and a Dockerfile, but no
# official OCI image. Install the official assafelovic/gptr-mcp source into a
# private virtual environment so MCPHub can launch it as a stdio child process.
# The Node packages are the reference MCP filesystem server and reviewed,
# published integrations for Vikunja, read-only Gmail, Google Calendar, the
# Arr suite, Navidrome, and Actual Budget. The released Audiobookshelf MCP
# package is installed into an isolated Python environment; MCPHub owns its
# service URL, credential, tool allow-list, and all other operational settings.
# The Jellyseerr server is installed
# from a reviewed upstream revision because it has no package release. Actual
# MCP is installed from a reviewed upstream revision and
# its lockfile because its official Actual API dependency includes a native
# SQLite module; building it here supplies the correct binary for each target
# platform. Exact dependency overrides align the API with the deployed Actual
# version and replace the runtime packages covered by current advisories.
# Runtime paths, OAuth material, permissions, models, retrievers, API keys, and
# research parameters are deliberately absent here; MCPHub owns those values
# in its backed-up application state. The small revision-locked Actual patch
# exposes account reconciliation timestamps through Actual's supported,
# read-only AQL API; it neither adds write access nor forks the maintained MCP
# server. GPT
# Researcher 0.16.0 imports three typing
# annotations after using them, so the released dependency receives a one-line
# import-order repair; the official MCP server source is unchanged.
# Jellyseerr's upstream Rich console defaults to stdout. The small sed below
# preserves the upstream server while moving logs off the stdio JSON-RPC stream.
# The base image preinstalls the same MCP server packages globally at older
# transitive pins (hono, ip-address, fast-uri) that now carry high-severity
# advisories, and npm's post-install audit fails on them. Those globals are
# fully redundant: this RUN reinstalls the exact same set at our pinned
# versions below. Remove them first so npm's built-in audit covers only
# this repository's dependency tree.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf \
         /usr/lib/node_modules/@cocal \
         /usr/lib/node_modules/@eargollo \
         /usr/lib/node_modules/@google-cloud \
         /usr/lib/node_modules/@klodr \
         /usr/lib/node_modules/@modelcontextprotocol \
         /usr/lib/node_modules/mcp-arr-server \
         /usr/lib/node_modules/navidrome-mcp \
    # npm's post-install audit is fatal on high-severity findings. After
    # removing the redundant base globals above, the only remaining highs are
    # bundled inside the npm CLI itself (e.g. its ip-address dependency),
    # which a global install cannot avoid and this image cannot patch.
    # --no-audit is scoped to that reality; the tree this repository controls
    # (the seven pinned MCP packages below) audits clean apart from 2
    # moderate findings with no upstream fix. npm's bundled deps are tracked
    # by the npm project.
    && npm install --global --ignore-scripts --no-audit \
         "@modelcontextprotocol/server-filesystem@${FILESYSTEM_MCP_VERSION}" \
         "@eargollo/vikunja-mcp@${VIKUNJA_MCP_VERSION}" \
         "@klodr/gmail-mcp@${GMAIL_MCP_VERSION}" \
         "@cocal/google-calendar-mcp@${GOOGLE_CALENDAR_MCP_VERSION}" \
         "@google-cloud/gcloud-mcp@${GCLOUD_MCP_VERSION}" \
         "mcp-arr-server@${MCP_ARR_VERSION}" \
         "navidrome-mcp@${NAVIDROME_MCP_VERSION}" \
    && git clone --filter=blob:none https://github.com/assafelovic/gptr-mcp.git /opt/gptr-mcp \
    && git -C /opt/gptr-mcp checkout --detach "${GPTR_MCP_REVISION}" \
    && test "$(git -C /opt/gptr-mcp rev-parse HEAD)" = "${GPTR_MCP_REVISION}" \
    && rm -rf /opt/gptr-mcp/.git \
    && git clone --filter=blob:none https://github.com/s-stefanov/actual-mcp.git /opt/actual-mcp \
    && git -C /opt/actual-mcp checkout --detach "${ACTUAL_MCP_REVISION}" \
    && test "$(git -C /opt/actual-mcp rev-parse HEAD)" = "${ACTUAL_MCP_REVISION}" \
    && git -C /opt/actual-mcp apply --check /tmp/actual-mcp-reconciliation.patch \
    && git -C /opt/actual-mcp apply /tmp/actual-mcp-reconciliation.patch \
    && git clone --filter=blob:none https://github.com/aserper/jellyseerr-mcp.git /opt/jellyseerr-mcp \
    && git -C /opt/jellyseerr-mcp checkout --detach "${JELLYSEERR_MCP_REVISION}" \
    && test "$(git -C /opt/jellyseerr-mcp rev-parse HEAD)" = "${JELLYSEERR_MCP_REVISION}" \
    && sed -i 's/console = Console()/console = Console(stderr=True)/' \
         /opt/jellyseerr-mcp/jellyseerr_mcp/logging_setup.py \
    && grep -Fq 'Console(stderr=True)' \
         /opt/jellyseerr-mcp/jellyseerr_mcp/logging_setup.py \
    && rm -rf /opt/jellyseerr-mcp/.git \
    && npm --prefix /opt/actual-mcp ci \
    && npm --prefix /opt/actual-mcp pkg set \
         "dependencies.@actual-app/api=${ACTUAL_API_VERSION}" \
         "dependencies.@actual-app/core=${ACTUAL_API_VERSION}" \
         "overrides.hono=${ACTUAL_MCP_HONO_VERSION}" \
         "overrides.@hono/node-server=${ACTUAL_MCP_HONO_NODE_SERVER_VERSION}" \
         "overrides.fast-uri=${ACTUAL_MCP_FAST_URI_VERSION}" \
         "overrides.body-parser=${ACTUAL_MCP_BODY_PARSER_VERSION}" \
         "overrides.qs=${ACTUAL_MCP_QS_VERSION}" \
         "overrides.brace-expansion=${ACTUAL_MCP_BRACE_EXPANSION_VERSION}" \
         "overrides.ua-parser-js=${ACTUAL_MCP_UA_PARSER_VERSION}" \
         "overrides.adm-zip=${ACTUAL_MCP_ADM_ZIP_VERSION}" \
         "overrides.better-sqlite3=${ACTUAL_MCP_BETTER_SQLITE_VERSION}" \
    && npm --prefix /opt/actual-mcp install --no-fund \
    && npm --prefix /opt/actual-mcp run build \
    && npm --prefix /opt/actual-mcp run test:unit \
    && npm --prefix /opt/actual-mcp prune --omit=dev \
    && npm --prefix /opt/actual-mcp audit --omit=dev --audit-level=low \
    && rm -rf /opt/actual-mcp/.git \
    && uv venv --python /usr/local/bin/python3 /opt/gptr-mcp/.venv \
    && uv pip install \
         --python /opt/gptr-mcp/.venv/bin/python \
         --requirements /opt/gptr-mcp/requirements.txt \
         "gpt-researcher==${GPT_RESEARCHER_VERSION}" \
         "fastmcp==${FASTMCP_VERSION}" \
    && uv venv --python /usr/local/bin/python3 /opt/vision-guard/.venv \
    && uv pip install \
         --python /opt/vision-guard/.venv/bin/python \
         "pypdf==${PYPDF_VERSION}" \
    && uv venv --python /usr/local/bin/python3 /opt/jellyseerr-mcp/.venv \
    && uv pip install \
         --python /opt/jellyseerr-mcp/.venv/bin/python \
         "httpx==${JELLYSEERR_MCP_HTTPX_VERSION}" \
         "python-dotenv==${JELLYSEERR_MCP_DOTENV_VERSION}" \
         "rich==${JELLYSEERR_MCP_RICH_VERSION}" \
         "mcp==${JELLYSEERR_MCP_SDK_VERSION}" \
    && uv venv --python /usr/local/bin/python3 /opt/audiobookshelf-mcp/.venv \
    && uv pip install \
         --python /opt/audiobookshelf-mcp/.venv/bin/python \
         "audiobookshelf-mcp[mcp]==${AUDIOBOOKSHELF_MCP_VERSION}" \
         "agent-utilities[mcp]==${AUDIOBOOKSHELF_MCP_AGENT_UTILITIES_VERSION}" \
         "python-dotenv==${AUDIOBOOKSHELF_MCP_DOTENV_VERSION}" \
    && /opt/vision-guard/.venv/bin/python \
         /opt/vision-guard/bin/test_vision_guard.py \
    && rm /opt/vision-guard/bin/test_vision_guard.py \
    && site_packages="$(/opt/gptr-mcp/.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
    && sed -i '1i from typing import Any, List, Dict' \
         "${site_packages}/gpt_researcher/actions/query_processing.py" \
    && cd /opt/gptr-mcp \
    && .venv/bin/python -c 'from server import mcp' \
    && command -v mcp-server-filesystem \
    && command -v vikunja-mcp \
    && command -v gmail-mcp \
    && command -v google-calendar-mcp \
    && command -v gcloud-mcp \
    && command -v mcp-arr \
    && command -v navidrome-mcp \
    && command -v mcp-grafana \
    && command -v kubernetes-mcp-server \
    && command -v github-mcp-server \
    && /opt/jellyseerr-mcp/.venv/bin/python -c 'import sys; sys.path.insert(0, "/opt/jellyseerr-mcp"); from jellyseerr_mcp.server import mcp' \
    && /opt/audiobookshelf-mcp/.venv/bin/python -c 'from audiobookshelf_mcp.mcp_server import get_mcp_instance; server, _, _ = get_mcp_instance(); assert server is not None' \
    && test -x /opt/audiobookshelf-mcp/.venv/bin/audiobookshelf-mcp \
    && test -x /usr/bin/gcloud-mcp \
    && /opt/google-cloud-sdk/bin/gcloud --version \
    && chmod 0755 /opt/vision-guard/bin/gcloud /usr/local/bin/start-gcloud-mcp /usr/local/bin/jellyseerr-mcp \
    && test -x /opt/actual-mcp/build/index.js \
    && chown -R 1000:1000 /opt/gptr-mcp /opt/actual-mcp /opt/jellyseerr-mcp

USER 1000:1000
