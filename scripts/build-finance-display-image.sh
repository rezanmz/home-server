#!/usr/bin/env bash
set -euo pipefail

readonly FINANCE_DISPLAY_VERSION="0.1.0"
readonly IMAGE_NAMESPACE="${FINANCE_DISPLAY_IMAGE_NAMESPACE:-ghcr.io/rezanmz}"
readonly IMAGE_NAME="finance-display"
readonly IMAGE_TAG="${FINANCE_DISPLAY_VERSION}"
readonly BUILDER="${FINANCE_DISPLAY_BUILDX_BUILDER:-finance-display-builder}"
readonly PLATFORMS="${FINANCE_DISPLAY_PLATFORMS:-linux/amd64,linux/arm64}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
context="${repo_root}/images/finance-display"

if ! docker buildx inspect "${BUILDER}" >/dev/null 2>&1; then
  docker buildx create --name "${BUILDER}" --driver docker-container
fi
docker buildx use "${BUILDER}"
docker buildx inspect --bootstrap >/dev/null

docker buildx build \
  --platform "${PLATFORMS}" \
  --file "${context}/Dockerfile" \
  --tag "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}" \
  --label "org.opencontainers.image.source=https://github.com/rezanmz/home-server" \
  --provenance=mode=max \
  --sbom=true \
  --push \
  "${context}"

docker buildx imagetools inspect \
  "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}" \
  --format '{{json .Manifest.Digest}}'
