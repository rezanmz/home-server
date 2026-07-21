#!/usr/bin/env bash
set -euo pipefail

readonly LLAMA_CLOUD_MCP_VERSION="2.11.0"
readonly IMAGE_NAMESPACE="${LLAMACLOUD_IMAGE_NAMESPACE:-rezanmz}"
readonly IMAGE_NAME="llamacloud-mcp"
readonly IMAGE_TAG="${LLAMA_CLOUD_MCP_VERSION}"
readonly BUILDER="${LLAMACLOUD_BUILDX_BUILDER:-llamacloud-mcp-builder}"
readonly PLATFORMS="${LLAMACLOUD_PLATFORMS:-linux/amd64,linux/arm64}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${repo_root}/images/llamacloud-mcp"

if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
  docker buildx create --name "$BUILDER" --driver docker-container
fi
docker buildx use "$BUILDER"
docker buildx inspect --bootstrap >/dev/null

docker buildx build \
  --platform "$PLATFORMS" \
  --file "$context/Dockerfile" \
  --tag "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}" \
  --label "org.opencontainers.image.source=https://github.com/rezanmz/home-server" \
  --provenance=mode=max \
  --sbom=true \
  --push \
  "$context"

docker buildx imagetools inspect \
  "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}" \
  --format '{{json .Manifest.Digest}}'
