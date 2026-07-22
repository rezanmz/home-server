#!/usr/bin/env bash
set -euo pipefail

readonly MCP_V8_VERSION="0.18.1"
readonly IMAGE_REVISION="1"
readonly IMAGE_NAMESPACE="${MCP_V8_IMAGE_NAMESPACE:-rezanmz}"
readonly IMAGE_NAME="mcp-v8"
readonly IMAGE_TAG="${MCP_V8_VERSION}-${IMAGE_REVISION}"
readonly BUILDER="${MCP_V8_BUILDX_BUILDER:-mcp-v8-builder}"
readonly PLATFORMS="${MCP_V8_PLATFORMS:-linux/amd64,linux/arm64}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${repo_root}/images/mcp-v8"

if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
  docker buildx create --name "$BUILDER" --driver docker-container
fi
docker buildx use "$BUILDER"
docker buildx inspect --bootstrap >/dev/null

docker buildx build \
  --platform "$PLATFORMS" \
  --file "$context/Dockerfile" \
  --build-arg "MCP_V8_VERSION=${MCP_V8_VERSION}" \
  --tag "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}" \
  --label "org.opencontainers.image.source=https://github.com/rezanmz/home-server" \
  --provenance=mode=max \
  --sbom=true \
  --push \
  "$context"

docker buildx imagetools inspect \
  "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}" \
  --format '{{json .Manifest.Digest}}'
