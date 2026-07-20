#!/usr/bin/env bash
set -euo pipefail

readonly GPT_RESEARCHER_VERSION="0.16.0"
readonly ADAPTER_REVISION="4"
readonly IMAGE_NAMESPACE="${GPT_RESEARCHER_IMAGE_NAMESPACE:-rezanmz}"
readonly IMAGE_NAME="gpt-researcher-service"
readonly IMAGE_TAG="${GPT_RESEARCHER_VERSION}-${ADAPTER_REVISION}"
readonly BUILDER="${GPT_RESEARCHER_BUILDX_BUILDER:-gpt-researcher-builder}"
readonly PLATFORMS="${GPT_RESEARCHER_PLATFORMS:-linux/amd64,linux/arm64}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${repo_root}/images/gpt-researcher-service"

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
