#!/usr/bin/env bash

set -euo pipefail

checked=0
failed=0

while IFS= read -r -d '' file; do
  checked=$((checked + 1))
  if ! bash -n "$file"; then
    printf '::error file=%s,title=Invalid shell syntax::bash -n failed\n' "$file" >&2
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
