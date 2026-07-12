#!/usr/bin/env bash
set -euo pipefail

host="${1:-beelink}"
flux_version="${FLUX_VERSION:-v2.9.1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sync_manifest="${repo_root}/clusters/home-server/flux-system/gotk-sync.yaml"

# The repository is public, so the in-cluster source needs no Git credential.
ssh "${host}" \
  "curl -fsSL 'https://github.com/fluxcd/flux2/releases/download/${flux_version}/install.yaml' | sudo k3s kubectl apply -f -"
ssh "${host}" sudo k3s kubectl -n flux-system rollout status \
  deployment/source-controller --timeout=180s
ssh "${host}" sudo k3s kubectl -n flux-system rollout status \
  deployment/kustomize-controller --timeout=180s
ssh "${host}" sudo k3s kubectl apply -f - < "${sync_manifest}"
ssh "${host}" sudo k3s kubectl -n flux-system wait \
  gitrepository/flux-system --for=condition=Ready --timeout=180s
ssh "${host}" sudo k3s kubectl -n flux-system wait \
  kustomization/flux-system --for=condition=Ready --timeout=180s
