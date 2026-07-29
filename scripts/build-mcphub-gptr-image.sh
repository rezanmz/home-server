#!/usr/bin/env bash
set -euo pipefail

# renovate: datasource=docker depName=samanhappy/mcphub versioning=semver
readonly MCPHUB_VERSION="1.0.26"
readonly GPTR_MCP_REVISION="63884773685b1f12c7f0d9e283b3d71a5b9b5fda"
readonly GPTR_MCP_SHORT_REVISION="${GPTR_MCP_REVISION:0:12}"
readonly ACTUAL_MCP_REVISION="24925803dff2dfb697cb6e53c06662ee66c94f01"
readonly ACTUAL_MCP_SHORT_REVISION="${ACTUAL_MCP_REVISION:0:12}"
readonly GCLOUD_MCP_VERSION="0.5.3"
readonly MCP_ARR_VERSION="1.6.5"
readonly NAVIDROME_MCP_VERSION="2.1.0"
readonly AUDIOBOOKSHELF_MCP_VERSION="1.0.1"
readonly IMAGE_NAMESPACE="${MCPHUB_IMAGE_NAMESPACE:-ghcr.io/rezanmz}"
readonly IMAGE_NAME="mcphub-gptr"
readonly IMAGE_TAG="${MCPHUB_VERSION}-${GPTR_MCP_SHORT_REVISION}-actual-${ACTUAL_MCP_SHORT_REVISION}-assistant-suite-6"
readonly BUILDER="${MCPHUB_BUILDX_BUILDER:-mcphub-gptr-builder}"
readonly PLATFORMS="${MCPHUB_PLATFORMS:-linux/amd64,linux/arm64}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${repo_root}/images/mcphub-gptr"

if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
  docker buildx create --name "$BUILDER" --driver docker-container
fi
docker buildx use "$BUILDER"
docker buildx inspect --bootstrap >/dev/null

docker buildx build \
  --platform "$PLATFORMS" \
  --file "$context/Dockerfile" \
  --tag "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}" \
  --build-arg "MCPHUB_VERSION=${MCPHUB_VERSION}" \
  --label "org.opencontainers.image.source=https://github.com/rezanmz/home-server" \
  --provenance=mode=max \
  --sbom=true \
  --push \
  "$context"

docker buildx imagetools inspect \
  "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}" \
  --format '{{json .Manifest.Digest}}'
