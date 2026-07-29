#!/usr/bin/env bash
set -euo pipefail

host="${1:-beelink}"
flux_version="${FLUX_VERSION:-v2.9.3}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sync_manifest="${repo_root}/clusters/home-server/flux-system/gotk-sync.yaml"
install_sha256="aa0bd71dbc4bed916b9cafa850c4618f341c74c580832c613dca04a067ee7281"
install_manifest="$(mktemp)"
pinned_install_manifest="$(mktemp)"
trap 'rm -f -- "${install_manifest}" "${pinned_install_manifest}"' EXIT

if [[ "${flux_version}" != "v2.9.3" ]]; then
  printf 'Unsupported FLUX_VERSION %s; review the install checksum and all controller digests first.\n' \
    "${flux_version}" >&2
  exit 1
fi

flux_images=(
  "helm-controller=ghcr.io/fluxcd/helm-controller:v1.6.3@sha256:16ada99456385100698a5d7adf90aba8a2089d987ab541c9566b6d7b0e897038"
  "image-automation-controller=ghcr.io/fluxcd/image-automation-controller:v1.2.3@sha256:81128adfd127601530d3dffc1deaf7c9eeec5b9aa555b3ab80cab37fa5d909a4"
  "image-reflector-controller=ghcr.io/fluxcd/image-reflector-controller:v1.2.3@sha256:a47e09e024a9ff2ea4f3878a1b90c2850134cfdc8b292ec52268dbc1e57e1a4c"
  "kustomize-controller=ghcr.io/fluxcd/kustomize-controller:v1.9.4@sha256:2b8bec54ffb6caf421bd2a6c005d27f567d5dd4db7feb55794fb51fcabd69b8f"
  "notification-controller=ghcr.io/fluxcd/notification-controller:v1.9.2@sha256:9ce503e7bcb8493fafe2aaef0c2ac4396df4f6890256acf9cd444a2dcd2a69ed"
  "source-controller=ghcr.io/fluxcd/source-controller:v1.9.3@sha256:ff8f3c92f1bcb433e858c948040c3a3393fe73f5dd72048a4502bfaf0a4c26cd"
  "source-watcher=ghcr.io/fluxcd/source-watcher:v2.2.2@sha256:1d59f752ecf520d1dc56ca413749dfab507497dd363639b6fbaf5036850e05c7"
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
