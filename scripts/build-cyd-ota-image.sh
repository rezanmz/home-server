#!/usr/bin/env bash
set -euo pipefail

readonly CYD_OTA_VERSION="0.3.1"
readonly IMAGE_NAMESPACE="${CYD_OTA_IMAGE_NAMESPACE:-ghcr.io/rezanmz}"
readonly IMAGE_NAME="cyd-ota-updater"
readonly BUILDER="${CYD_OTA_BUILDX_BUILDER:-cyd-ota-builder}"
readonly PLATFORMS="${CYD_OTA_PLATFORMS:-linux/amd64}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! docker buildx inspect "${BUILDER}" >/dev/null 2>&1; then
  docker buildx create --name "${BUILDER}" --driver docker-container
fi
docker buildx use "${BUILDER}"
docker buildx inspect --bootstrap >/dev/null

docker buildx build \
  --platform "${PLATFORMS}" \
  --file "${repo_root}/images/cyd-ota/Dockerfile" \
  --tag "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${CYD_OTA_VERSION}" \
  --label "org.opencontainers.image.source=https://github.com/rezanmz/home-server" \
  --provenance=mode=max \
  --sbom=true \
  --push \
  "${repo_root}"

docker buildx imagetools inspect \
  "${IMAGE_NAMESPACE}/${IMAGE_NAME}:${CYD_OTA_VERSION}" \
  --format '{{json .Manifest.Digest}}'
