#!/usr/bin/env bash

set -euo pipefail

checked=0
failed=0

escape_workflow_property() {
  local value="$1"
  value="${value//'%'/'%25'}"
  value="${value//$'\r'/'%0D'}"
  value="${value//$'\n'/'%0A'}"
  value="${value//':'/'%3A'}"
  value="${value//','/'%2C'}"
  printf '%s' "${value}"
}

while IFS= read -r -d '' file; do
  checked=$((checked + 1))
  if ! bash -n -- "$file"; then
    escaped_file="$(escape_workflow_property "${file}")"
    printf '::error file=%s,title=Invalid shell syntax::bash -n failed\n' \
      "${escaped_file}" >&2
    failed=1
  fi
done < <(git ls-files -z -- '*.sh')

if ((checked == 0)); then
  printf '::error title=Shell validation::No tracked shell scripts were found\n' >&2
  exit 1
fi

if ((failed != 0)); then
  exit 1
fi

printf 'Validated shell syntax in %d tracked script(s).\n' "$checked"
