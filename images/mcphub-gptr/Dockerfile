# syntax=docker/dockerfile:1.7
ARG MCPHUB_IMAGE=samanhappy/mcphub:1.0.24@sha256:2a1d22d636b437194b68ff30dd333b52e17da25492abe1e6ac5976653ae383a1
ARG GCLOUD_IMAGE=gcr.io/google.com/cloudsdktool/google-cloud-cli:571.0.0-slim@sha256:61cdaee8f89a2500c8e93fac2499d98a5b7692fcc3d7d69abbef48200477cb71

FROM ${GCLOUD_IMAGE} AS gcloud
FROM ${MCPHUB_IMAGE}

ARG GPTR_MCP_REVISION=63884773685b1f12c7f0d9e283b3d71a5b9b5fda
ARG GPT_RESEARCHER_VERSION=0.16.0
ARG FASTMCP_VERSION=2.14.7
ARG FILESYSTEM_MCP_VERSION=2026.7.10
ARG VIKUNJA_MCP_VERSION=1.2.0
ARG GMAIL_MCP_VERSION=1.3.1
ARG GOOGLE_CALENDAR_MCP_VERSION=2.6.2
ARG GCLOUD_MCP_VERSION=0.5.3
ARG PYPDF_VERSION=6.1.1
ARG ACTUAL_MCP_REVISION=24925803dff2dfb697cb6e53c06662ee66c94f01
ARG ACTUAL_API_VERSION=26.7.0
ARG ACTUAL_MCP_HONO_VERSION=4.12.31
ARG ACTUAL_MCP_BODY_PARSER_VERSION=2.3.0
ARG ACTUAL_MCP_QS_VERSION=6.15.3
ARG ACTUAL_MCP_BRACE_EXPANSION_VERSION=2.1.2
ARG ACTUAL_MCP_UA_PARSER_VERSION=2.0.10
ARG ACTUAL_MCP_ADM_ZIP_VERSION=0.6.0
ARG ACTUAL_MCP_BETTER_SQLITE_VERSION=12.11.1

LABEL org.opencontainers.image.title="MCPHub with reviewed MCP packages" \
      org.opencontainers.image.description="MCPHub plus pinned GPT Researcher, filesystem, Vikunja, Gmail, Google Calendar, Google Cloud, and Actual Budget MCP packages" \
      org.opencontainers.image.source="https://github.com/rezanmz/home-server" \
      org.opencontainers.image.licenses="Apache-2.0 AND MIT" \
      org.opencontainers.image.version="1.0.24-gptr-mcp-actual" \
      org.opencontainers.image.revision="${GPTR_MCP_REVISION}"

USER 0:0

COPY --from=gcloud /usr/lib/google-cloud-sdk /opt/google-cloud-sdk
COPY vision-guard/gcloud /opt/vision-guard/bin/gcloud
COPY vision-guard/test_vision_guard.py /opt/vision-guard/bin/test_vision_guard.py
COPY vision-guard/start-gcloud-mcp /usr/local/bin/start-gcloud-mcp
COPY vision-guard/gcloud-mcp-allowlist.json /opt/vision-guard/gcloud-mcp-allowlist.json

# The upstream GPT Researcher project publishes source and a Dockerfile, but no
# official OCI image. Install the official assafelovic/gptr-mcp source into a
# private virtual environment so MCPHub can launch it as a stdio child process.
# The Node packages are the reference MCP filesystem server and reviewed,
# published integrations for Vikunja, read-only Gmail, Google Calendar, and
# Actual Budget. Actual MCP is installed from a reviewed upstream revision and
# its lockfile because its official Actual API dependency includes a native
# SQLite module; building it here supplies the correct binary for each target
# platform. Exact dependency overrides align the API with the deployed Actual
# version and replace the runtime packages covered by current advisories.
# Runtime paths, OAuth material, permissions, models, retrievers, API keys, and
# research parameters are deliberately absent here; MCPHub owns those values
# in its backed-up application state. GPT Researcher 0.16.0 imports three typing
# annotations after using them, so the released dependency receives a one-line
# import-order repair; the official MCP server source is unchanged.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --ignore-scripts \
         "@modelcontextprotocol/server-filesystem@${FILESYSTEM_MCP_VERSION}" \
         "@eargollo/vikunja-mcp@${VIKUNJA_MCP_VERSION}" \
         "@klodr/gmail-mcp@${GMAIL_MCP_VERSION}" \
         "@cocal/google-calendar-mcp@${GOOGLE_CALENDAR_MCP_VERSION}" \
         "@google-cloud/gcloud-mcp@${GCLOUD_MCP_VERSION}" \
    && git clone --filter=blob:none https://github.com/assafelovic/gptr-mcp.git /opt/gptr-mcp \
    && git -C /opt/gptr-mcp checkout --detach "${GPTR_MCP_REVISION}" \
    && test "$(git -C /opt/gptr-mcp rev-parse HEAD)" = "${GPTR_MCP_REVISION}" \
    && rm -rf /opt/gptr-mcp/.git \
    && git clone --filter=blob:none https://github.com/s-stefanov/actual-mcp.git /opt/actual-mcp \
    && git -C /opt/actual-mcp checkout --detach "${ACTUAL_MCP_REVISION}" \
    && test "$(git -C /opt/actual-mcp rev-parse HEAD)" = "${ACTUAL_MCP_REVISION}" \
    && npm --prefix /opt/actual-mcp ci \
    && npm --prefix /opt/actual-mcp pkg set \
         "dependencies.@actual-app/api=${ACTUAL_API_VERSION}" \
         "dependencies.@actual-app/core=${ACTUAL_API_VERSION}" \
         "overrides.hono=${ACTUAL_MCP_HONO_VERSION}" \
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
    && /opt/google-cloud-sdk/bin/gcloud --version \
    && chmod 0755 /opt/vision-guard/bin/gcloud /usr/local/bin/start-gcloud-mcp \
    && test -x /opt/actual-mcp/build/index.js \
    && chown -R 1000:1000 /opt/gptr-mcp /opt/actual-mcp

USER 1000:1000
