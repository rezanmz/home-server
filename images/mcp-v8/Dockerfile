# syntax=docker/dockerfile:1.7
ARG DEBIAN_IMAGE=debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd
ARG MCP_V8_VERSION=0.18.1

FROM ${DEBIAN_IMAGE} AS mcp-v8
ARG MCP_V8_VERSION
ARG TARGETARCH
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && case "${TARGETARCH}" in \
         amd64) mcp_v8_asset='mcp-v8-linux'; mcp_v8_sha256='05558638bcfc376558ff984aef558eed33d2f4c0a08f39879b6180088c8fca36' ;; \
         arm64) mcp_v8_asset='mcp-v8-linux-arm64'; mcp_v8_sha256='bfc44326584ffcd404d04ebc6205109fc477133f09c7e97b57a2d1123300b179' ;; \
         *) echo "unsupported target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && curl --fail --location --proto '=https' --proto-redir '=https' --retry 3 --show-error --silent \
         "https://github.com/r33drichards/mcp-js/releases/download/v${MCP_V8_VERSION}/${mcp_v8_asset}" \
         --output /mcp-v8 \
    && printf '%s  %s\n' "${mcp_v8_sha256}" /mcp-v8 | sha256sum --check --strict \
    && chmod 0755 /mcp-v8

FROM ${DEBIAN_IMAGE}
ARG MCP_V8_VERSION

LABEL org.opencontainers.image.title="Hardened mcp-v8" \
      org.opencontainers.image.description="Stateless, isolated JavaScript MCP server for bounded agent calculations" \
      org.opencontainers.image.source="https://github.com/r33drichards/mcp-js" \
      org.opencontainers.image.licenses="AGPL-3.0" \
      org.opencontainers.image.version="${MCP_V8_VERSION}"

COPY --from=mcp-v8 --chmod=0755 /mcp-v8 /usr/local/bin/mcp-v8

USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/mcp-v8"]
