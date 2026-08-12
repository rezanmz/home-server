#!/usr/bin/env bash
set -euo pipefail

host="${1:-beelink}"
# renovate: datasource=github-releases depName=fluxcd/flux2 versioning=semver
supported_flux_version="v2.9.4"
flux_version="${FLUX_VERSION:-${supported_flux_version}}"
verify_only="${FLUX_VERIFY_ONLY:-false}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sync_manifest="${repo_root}/clusters/home-server/flux-system/gotk-sync.yaml"
install_sha256="9eb86c5f9d606b2ac2cfe71223ab2f23faa2d59ccb21df4e08e5610e54d535f8"
install_manifest="$(mktemp)"
pinned_install_manifest="$(mktemp)"
trap 'rm -f -- "${install_manifest}" "${pinned_install_manifest}"' EXIT

if [[ "${flux_version}" != "${supported_flux_version}" ]]; then
  printf 'Unsupported FLUX_VERSION %s; review the install checksum and all controller digests first.\n' \
    "${flux_version}" >&2
  exit 1
fi

flux_images=(
  "helm-controller=ghcr.io/fluxcd/helm-controller:v1.6.3@sha256:16ada99456385100698a5d7adf90aba8a2089d987ab541c9566b6d7b0e897038"
  "image-automation-controller=ghcr.io/fluxcd/image-automation-controller:v1.2.4@sha256:0286cbba95a2606a006e370052cb642f4370cb42ceea8353b5cba922cf47770c"
  "image-reflector-controller=ghcr.io/fluxcd/image-reflector-controller:v1.2.4@sha256:d63550296dc9a6c2b7c9246cb7ef6e52d7469d5b104cd329622301b46971e255"
  "kustomize-controller=ghcr.io/fluxcd/kustomize-controller:v1.9.4@sha256:2b8bec54ffb6caf421bd2a6c005d27f567d5dd4db7feb55794fb51fcabd69b8f"
  "notification-controller=ghcr.io/fluxcd/notification-controller:v1.9.3@sha256:071c351a0fb163eeb6a2bb82f1e894f51b6b0734216d2e97d3d99c9ab9d710b9"
  "source-controller=ghcr.io/fluxcd/source-controller:v1.9.4@sha256:8a8ed0a57b8b86f561d5a4309a69f65e62f0cebe4de8801593c5ff35a3bc3c23"
  "source-watcher=ghcr.io/fluxcd/source-watcher:v2.2.3@sha256:40f35415a78f4514aea41cf4d6dd299d59bc646eb4a73365eac831c8ced2445a"
)

# The repository is public, so the in-cluster source needs no Git credential.
curl --proto '=https' --tlsv1.2 -fsSLo "${install_manifest}" \
  "https://github.com/fluxcd/flux2/releases/download/${flux_version}/install.yaml"
printf '%s  %s\n' "${install_sha256}" "${install_manifest}" | shasum -a 256 -c -

# The checksum covers the unmodified upstream manifest. Rewrite its seven
# controller images locally so a tag-only controller is never applied, even
# briefly, then verify the transformed manifest before sending it to the node.
sed_args=()
for pin in "${flux_images[@]}"; do
  deployment="${pin%%=*}"
  image="${pin#*=}"
  tagged_image="${image%@*}"
  repository="${tagged_image%:*}"
  upstream_count="$(awk -v prefix="${repository}:" \
    '$1 == "image:" && index($2, prefix) == 1 { count++ } END { print count + 0 }' \
    "${install_manifest}")"
  if [[ "${upstream_count}" -ne 1 ]]; then
    printf 'Expected exactly one upstream image for %s; found %s.\n' \
      "${deployment}" "${upstream_count}" >&2
    exit 1
  fi
  upstream_image="$(awk -v prefix="${repository}:" \
    '$1 == "image:" && index($2, prefix) == 1 { print $2 }' \
    "${install_manifest}")"
  escaped_upstream_image="${upstream_image//./\\.}"
  sed_args+=( -e "s#${escaped_upstream_image}#${image}#g" )
done
sed "${sed_args[@]}" "${install_manifest}" > "${pinned_install_manifest}"

for pin in "${flux_images[@]}"; do
  deployment="${pin%%=*}"
  image="${pin#*=}"
  pinned_count="$(awk -v image="${image}" \
    '$1 == "image:" && $2 == image { count++ } END { print count + 0 }' \
    "${pinned_install_manifest}")"
  if [[ "${pinned_count}" -ne 1 ]]; then
    printf 'Expected exactly one pinned image %s for %s; found %s.\n' \
      "${image}" "${deployment}" "${pinned_count}" >&2
    exit 1
  fi
done

tag_only_controllers="$(awk '
  $1 == "image:" &&
  $2 ~ /^ghcr\.io\/fluxcd\/(helm-controller|image-automation-controller|image-reflector-controller|kustomize-controller|notification-controller|source-controller|source-watcher):/ &&
  $2 !~ /@sha256:/ { print $2 }
' "${pinned_install_manifest}")"
if [[ -n "${tag_only_controllers}" ]]; then
  printf 'Refusing to apply Flux manifest with tag-only controller images:\n%s\n' \
    "${tag_only_controllers}" >&2
  exit 1
fi

if [[ "${verify_only}" == "true" ]]; then
  printf 'Verified Flux %s install checksum and %d controller image pins.\n' \
    "${flux_version}" "${#flux_images[@]}"
  exit 0
fi
if [[ "${verify_only}" != "false" ]]; then
  printf 'FLUX_VERIFY_ONLY must be true or false, got %s.\n' "${verify_only}" >&2
  exit 2
fi

ssh "${host}" sudo k3s kubectl apply -f - < "${pinned_install_manifest}"

for pin in "${flux_images[@]}"; do
  deployment="${pin%%=*}"
  ssh "${host}" sudo k3s kubectl -n flux-system rollout status \
    "deployment/${deployment}" --timeout=180s
done
ssh "${host}" sudo k3s kubectl apply -f - < "${sync_manifest}"
ssh "${host}" sudo k3s kubectl -n flux-system wait \
  gitrepository/flux-system --for=condition=Ready --timeout=180s
ssh "${host}" sudo k3s kubectl -n flux-system wait \
  kustomization/flux-system --for=condition=Ready --timeout=180s
