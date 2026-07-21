# syntax=docker/dockerfile:1.7
ARG DENO_IMAGE=denoland/deno:debian-2.7.1@sha256:76702d3ee36524d8e8e4195798fc3263e42d860df9fb597230b8cfc48bcf2077
FROM ${DENO_IMAGE}

ARG LLAMA_CLOUD_MCP_VERSION=2.11.0

LABEL org.opencontainers.image.title="Official LlamaCloud MCP runtime" \
      org.opencontainers.image.description="Unmodified LlamaIndex LlamaCloud MCP package with Deno code sandbox" \
      org.opencontainers.image.source="https://github.com/rezanmz/home-server" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${LLAMA_CLOUD_MCP_VERSION}"

USER 0:0
RUN apt-get update \
    && apt-get install --yes --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/node_modules/@llamaindex/vault \
    && cd /app \
    && npm init --yes \
    && npm install --omit=dev --ignore-scripts "@llamaindex/llama-cloud-mcp@${LLAMA_CLOUD_MCP_VERSION}" \
    && npm audit --omit=dev --audit-level=high \
    && npm cache clean --force \
    && apt-get purge --yes --auto-remove npm \
    && chown -R 1000:1000 /app

WORKDIR /app
USER 1000:1000
EXPOSE 3000

ENTRYPOINT ["node", "/app/node_modules/@llamaindex/llama-cloud-mcp/index.js"]
CMD ["--transport=http", "--port=3000", "--log-format=json", "--code-allowed-methods=^files\\.(create|delete)$", "--code-allowed-methods=^parsing\\.(create|get)$"]
