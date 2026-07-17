#!/usr/bin/env bash
set -euo pipefail

readonly STORK_VERSION="2.5.0"
readonly STORK_TAG="v${STORK_VERSION}"
readonly STORK_COMMIT="43f1450d1260ce58c2c6c973b72199b6c6592513"
readonly STORK_REPOSITORY="https://gitlab.isc.org/isc-projects/stork.git"
readonly KEA_VERSION="3.2.0"
readonly IMAGE_NAMESPACE="${STORK_IMAGE_NAMESPACE:-rezanmz}"
readonly BUILDER="${STORK_BUILDX_BUILDER:-stork-builder}"
readonly PLATFORM="linux/amd64"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$(mktemp -d)"
trap 'rm -rf "$source_dir"' EXIT

git clone --branch "$STORK_TAG" --depth 1 "$STORK_REPOSITORY" "$source_dir"
actual_commit="$(git -C "$source_dir" rev-parse HEAD)"
if [[ "$actual_commit" != "$STORK_COMMIT" ]]; then
  printf 'Refusing build: %s resolved to %s, expected %s\n' \
    "$STORK_TAG" "$actual_commit" "$STORK_COMMIT" >&2
  exit 1
fi

git -C "$source_dir" apply "$script_dir/stork-agent-nonroot.patch"

if ! docker buildx inspect "$BUILDER" >/dev/null 2>&1; then
  docker buildx create --name "$BUILDER" --driver docker-container
fi
docker buildx use "$BUILDER"
docker buildx inspect --bootstrap >/dev/null

build_target() {
  local target="$1"
  local image="$2"
  local tag="${3:-$STORK_VERSION}"
  docker buildx build \
    --platform "$PLATFORM" \
    --file "$source_dir/docker/images/stork.Dockerfile" \
    --target "$target" \
    --tag "${IMAGE_NAMESPACE}/${image}:${tag}" \
    --label "org.opencontainers.image.source=https://github.com/rezanmz/home-server" \
    --label "org.opencontainers.image.revision=${STORK_COMMIT}" \
    --label "org.opencontainers.image.version=${STORK_VERSION}" \
    --provenance=mode=max \
    --sbom=true \
    --push \
    "$source_dir"
}

build_target server isc-stork-server
build_target agent-nonroot isc-stork-agent "${STORK_VERSION}-kea${KEA_VERSION}"
build_target webui isc-stork-webui

docker buildx imagetools inspect \
  "${IMAGE_NAMESPACE}/isc-stork-server:${STORK_VERSION}" \
  --format '{{json .Manifest.Digest}}'
docker buildx imagetools inspect \
  "${IMAGE_NAMESPACE}/isc-stork-agent:${STORK_VERSION}-kea${KEA_VERSION}" \
  --format '{{json .Manifest.Digest}}'
docker buildx imagetools inspect \
  "${IMAGE_NAMESPACE}/isc-stork-webui:${STORK_VERSION}" \
  --format '{{json .Manifest.Digest}}'
