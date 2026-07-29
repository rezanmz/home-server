#!/usr/bin/env bash

set -euo pipefail

[[ $# == 2 ]] || {
  echo "usage: render-helm-releases.sh <rendered-cluster.yaml> <output.yaml>" >&2
  exit 2
}

for command in awk diff git grep helm mktemp sort tr wc yq; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "required command is not installed: ${command}" >&2
    exit 1
  }
done

cluster_manifest="$1"
output="$2"
[[ -s "${cluster_manifest}" ]] || {
  echo "rendered cluster manifest is missing or empty: ${cluster_manifest}" >&2
  exit 1
}
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
rendered_releases="${tmp}/rendered-releases.txt"
expected_releases="${tmp}/expected-releases.txt"
: >"${rendered_releases}"

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "neither sha256sum nor shasum is installed" >&2
    return 1
  fi
}

extract_resource() {
  local kind="$1"
  local namespace="$2"
  local name="$3"
  local destination="$4"
  local expression count

  expression="select(.kind == \"${kind}\" and .metadata.namespace == \"${namespace}\" and .metadata.name == \"${name}\")"
  if ! count="$(
    yq -r "${expression} | .metadata.name" "${cluster_manifest}" |
      awk -v expected="${name}" '$0 == expected { count += 1 } END { print count + 0 }'
  )"; then
    echo "could not search rendered cluster for ${kind} ${namespace}/${name}" >&2
    return 1
  fi
  [[ "${count}" == 1 ]] || {
    echo "expected exactly one rendered ${kind} ${namespace}/${name}; found ${count}" >&2
    return 1
  }
  yq -o=yaml "${expression}" "${cluster_manifest}" >"${destination}"
}

validate_release_reference() {
  local release_file="$1"
  local source_kind="$2"
  local source_namespace="$3"
  local source_name="$4"
  local chart_path="${5:-}"
  local expression identity

  identity="$(yq -r '.metadata.namespace + "/" + .metadata.name' "${release_file}")"
  if [[ "${source_kind}" == "OCIRepository" ]]; then
    expression="
      .spec.chart == null and
      .spec.chartRef.kind == \"${source_kind}\" and
      .spec.chartRef.namespace == \"${source_namespace}\" and
      .spec.chartRef.name == \"${source_name}\"
    "
  else
    expression="
      .spec.chartRef == null and
      .spec.chart.spec.chart == \"${chart_path}\" and
      .spec.chart.spec.sourceRef.kind == \"${source_kind}\" and
      .spec.chart.spec.sourceRef.namespace == \"${source_namespace}\" and
      .spec.chart.spec.sourceRef.name == \"${source_name}\"
    "
  fi
  if ! yq -e "${expression}" "${release_file}" >/dev/null 2>&1; then
    printf '%s does not reference the immutable %s %s/%s artifact rendered by CI\n' \
      "${identity}" "${source_kind}" "${source_namespace}" "${source_name}" >&2
    return 1
  fi
}

pull_oci_chart() {
  local source_file="$1"
  local expected_package_sha256="$2"
  local url tag digest name package pull_output actual_package_sha256

  url="$(yq -r '.spec.url' "${source_file}")"
  tag="$(yq -r '.spec.ref.tag' "${source_file}")"
  digest="$(yq -r '.spec.ref.digest' "${source_file}")"
  name="$(yq -r '.metadata.name' "${source_file}")"
  package="${tmp}/${name}-${tag}.tgz"

  pull_output="$(helm pull "${url}" --version "${tag}" --destination "${tmp}" 2>&1)" || {
    printf '%s\n' "${pull_output}" >&2
    return 1
  }
  grep -Fqx "Digest: ${digest}" <<<"${pull_output}" || {
    printf 'OCI digest mismatch for %s:%s; expected %s\n' "${url}" "${tag}" "${digest}" >&2
    printf '%s\n' "${pull_output}" >&2
    return 1
  }
  [[ -f "${package}" ]] || {
    echo "Helm did not create expected chart package: ${package}" >&2
    return 1
  }
  actual_package_sha256="$(sha256_file "${package}")"
  [[ "${actual_package_sha256}" == "${expected_package_sha256}" ]] || {
    printf 'chart package checksum mismatch for %s: expected %s, got %s\n' \
      "${name}" "${expected_package_sha256}" "${actual_package_sha256}" >&2
    return 1
  }

  printf '%s\n' "${package}"
}

render_release() {
  local release_file="$1"
  local chart="$2"
  local name namespace values_file

  name="$(yq -r '.metadata.name' "${release_file}")"
  namespace="$(yq -r '.metadata.namespace' "${release_file}")"
  values_file="${tmp}/${name}-values.yaml"
  yq '.spec.values // {}' "${release_file}" >"${values_file}"
  helm template "${name}" "${chart}" \
    --namespace "${namespace}" \
    --kube-version 1.36.2 \
    --include-crds \
    --values "${values_file}" >>"${output}"
  printf '\n' >>"${output}"
  printf '%s/%s\n' "${namespace}" "${name}" >>"${rendered_releases}"
}

checkout_git_chart() {
  local source_file="$1"
  local display_name="$2"
  local url tag commit name checkout resolved_commit

  url="$(yq -r '.spec.url' "${source_file}")"
  tag="$(yq -r '.spec.ref.tag' "${source_file}")"
  commit="$(yq -r '.spec.ref.commit' "${source_file}")"
  name="$(yq -r '.metadata.name' "${source_file}")"
  checkout="${tmp}/${name}"
  git -C "${tmp}" init -q "${name}"
  git -C "${checkout}" remote add origin "${url}"
  git -C "${checkout}" fetch -q --depth=1 origin "refs/tags/${tag}"
  resolved_commit="$(git -C "${checkout}" rev-parse 'FETCH_HEAD^{commit}')"
  [[ "${resolved_commit}" == "${commit}" ]] || {
    printf '%s tag/commit mismatch: expected %s, got %s\n' \
      "${display_name}" "${commit}" "${resolved_commit}" >&2
    return 1
  }
  git -C "${checkout}" checkout -q --detach FETCH_HEAD
  printf '%s\n' "${checkout}"
}

: >"${output}"

cert_manager_release="${tmp}/cert-manager-release.yaml"
cert_manager_source="${tmp}/cert-manager-source.yaml"
extract_resource HelmRelease cert-manager cert-manager "${cert_manager_release}"
extract_resource OCIRepository flux-system cert-manager "${cert_manager_source}"
validate_release_reference \
  "${cert_manager_release}" OCIRepository flux-system cert-manager
cert_manager_chart="$(pull_oci_chart \
  "${cert_manager_source}" \
  c27101f3f3e2349fb4a9e704316105bf7b52ad73b8c8257d3498ef7f2f6a4adc)"
render_release \
  "${cert_manager_release}" \
  "${cert_manager_chart}"

traefik_release="${tmp}/traefik-release.yaml"
traefik_source="${tmp}/traefik-source.yaml"
extract_resource HelmRelease traefik traefik "${traefik_release}"
extract_resource OCIRepository flux-system traefik "${traefik_source}"
validate_release_reference "${traefik_release}" OCIRepository flux-system traefik
traefik_chart="$(pull_oci_chart \
  "${traefik_source}" \
  a84ec5eae9f5507c8f0632d58a7eb10c9b7fd2a277b77740ee7460c55ecde49a)"
render_release "${traefik_release}" "${traefik_chart}"

metallb_release="${tmp}/metallb-release.yaml"
metallb_source="${tmp}/metallb-source.yaml"
extract_resource HelmRelease metallb-system metallb "${metallb_release}"
extract_resource OCIRepository flux-system metallb "${metallb_source}"
validate_release_reference "${metallb_release}" OCIRepository flux-system metallb
metallb_chart="$(pull_oci_chart \
  "${metallb_source}" \
  fb06bb584fcb7856f15733b2a6a2aff5b61b5c350687e341c163ae24a5938adc)"
render_release "${metallb_release}" "${metallb_chart}"

longhorn_source="${tmp}/longhorn-source.yaml"
longhorn_release="${tmp}/longhorn-release.yaml"
extract_resource HelmRelease longhorn-system longhorn "${longhorn_release}"
extract_resource GitRepository flux-system longhorn "${longhorn_source}"
validate_release_reference \
  "${longhorn_release}" GitRepository flux-system longhorn ./chart
longhorn_checkout="$(checkout_git_chart "${longhorn_source}" Longhorn)"
longhorn_chart_path="$(yq -r '.spec.chart.spec.chart' "${longhorn_release}")"
render_release "${longhorn_release}" "${longhorn_checkout}/${longhorn_chart_path#./}"

juicefs_source="${tmp}/juicefs-source.yaml"
juicefs_release="${tmp}/juicefs-release.yaml"
extract_resource HelmRelease kube-system juicefs-csi-driver "${juicefs_release}"
extract_resource GitRepository flux-system juicefs-csi-driver "${juicefs_source}"
validate_release_reference \
  "${juicefs_release}" GitRepository flux-system juicefs-csi-driver \
  ./charts/juicefs-csi-driver
juicefs_checkout="$(checkout_git_chart "${juicefs_source}" 'JuiceFS CSI')"
juicefs_chart_path="$(yq -r '.spec.chart.spec.chart' "${juicefs_release}")"
render_release "${juicefs_release}" "${juicefs_checkout}/${juicefs_chart_path#./}"

observability_release="${tmp}/observability-release.yaml"
observability_source="${tmp}/observability-source.yaml"
extract_resource HelmRelease monitoring observability "${observability_release}"
extract_resource OCIRepository flux-system kube-prometheus-stack "${observability_source}"
validate_release_reference \
  "${observability_release}" OCIRepository flux-system kube-prometheus-stack
observability_chart="$(pull_oci_chart \
  "${observability_source}" \
  05eae98df0ff6c21877a26a4400780e4bbff248bc3b88694ef8d08b273ed6815)"
render_release "${observability_release}" "${observability_chart}"

: >"${expected_releases}"
release_output="${tmp}/release-output.txt"
yq -r '
  select(.kind == "HelmRelease") |
  ((.metadata.namespace // "default") + "/" + .metadata.name)
' "${cluster_manifest}" >"${release_output}"
while IFS= read -r release; do
  [[ -n "${release}" && "${release}" != "---" ]] || continue
  printf '%s\n' "${release}" >>"${expected_releases}"
done <"${release_output}"
sort -u -o "${expected_releases}" "${expected_releases}"
sort -u -o "${rendered_releases}" "${rendered_releases}"
if ! diff -u "${expected_releases}" "${rendered_releases}"; then
  echo "immutable Helm renderer does not cover every rendered-cluster HelmRelease" >&2
  exit 1
fi

resource_count="$(
  yq 'select(.kind != null) | .kind' "${output}" |
    grep -Fvx -- '---' |
    wc -l |
    tr -d ' '
)"
printf 'Rendered %s immutable Helm chart resource(s) at %s.\n' "${resource_count}" "${output}"
