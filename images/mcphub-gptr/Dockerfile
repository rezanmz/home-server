# syntax=docker/dockerfile:1.7
ARG MCPHUB_IMAGE=samanhappy/mcphub:1.0.24@sha256:2a1d22d636b437194b68ff30dd333b52e17da25492abe1e6ac5976653ae383a1

FROM ${MCPHUB_IMAGE}

ARG GPTR_MCP_REVISION=63884773685b1f12c7f0d9e283b3d71a5b9b5fda
ARG GPT_RESEARCHER_VERSION=0.16.0
ARG FASTMCP_VERSION=2.14.7
ARG FILESYSTEM_MCP_VERSION=2026.7.10
ARG VIKUNJA_MCP_VERSION=1.2.0

LABEL org.opencontainers.image.title="MCPHub with reviewed MCP packages" \
      org.opencontainers.image.description="MCPHub plus pinned GPT Researcher, filesystem, and Vikunja MCP packages" \
      org.opencontainers.image.source="https://github.com/rezanmz/home-server" \
      org.opencontainers.image.licenses="Apache-2.0 AND MIT" \
      org.opencontainers.image.version="1.0.24-gptr-mcp" \
      org.opencontainers.image.revision="${GPTR_MCP_REVISION}"

USER 0:0

# The upstream GPT Researcher project publishes source and a Dockerfile, but no
# official OCI image. Install the official assafelovic/gptr-mcp source into a
# private virtual environment so MCPHub can launch it as a stdio child process.
# The two Node packages are the reference MCP filesystem server and a small,
# independently maintained Vikunja adapter. Runtime paths, permissions, models,
# retrievers, API keys, and research parameters are deliberately absent here;
# MCPHub owns those values in its database. GPT Researcher 0.16.0 imports three
# typing annotations after using them, so the released dependency receives a
# one-line import-order repair; the official MCP server source is unchanged.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --ignore-scripts \
         "@modelcontextprotocol/server-filesystem@${FILESYSTEM_MCP_VERSION}" \
         "@eargollo/vikunja-mcp@${VIKUNJA_MCP_VERSION}" \
    && git clone --filter=blob:none https://github.com/assafelovic/gptr-mcp.git /opt/gptr-mcp \
    && git -C /opt/gptr-mcp checkout --detach "${GPTR_MCP_REVISION}" \
    && test "$(git -C /opt/gptr-mcp rev-parse HEAD)" = "${GPTR_MCP_REVISION}" \
    && rm -rf /opt/gptr-mcp/.git \
    && uv venv --python /usr/local/bin/python3 /opt/gptr-mcp/.venv \
    && uv pip install \
         --python /opt/gptr-mcp/.venv/bin/python \
         --requirements /opt/gptr-mcp/requirements.txt \
         "gpt-researcher==${GPT_RESEARCHER_VERSION}" \
         "fastmcp==${FASTMCP_VERSION}" \
    && site_packages="$(/opt/gptr-mcp/.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
    && sed -i '1i from typing import Any, List, Dict' \
         "${site_packages}/gpt_researcher/actions/query_processing.py" \
    && cd /opt/gptr-mcp \
    && .venv/bin/python -c 'from server import mcp' \
    && command -v mcp-server-filesystem \
    && command -v vikunja-mcp \
    && chown -R 1000:1000 /opt/gptr-mcp

USER 1000:1000
