#!/usr/bin/env python3
"""Prepare rendered SOPS resources for offline Kubernetes schema validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from yaml_documents import ManifestError, github_error, iter_kubernetes_objects, load_documents


def sanitize_secret(document: dict[str, Any]) -> None:
    document.pop("sops", None)
    data = document.get("data")
    if isinstance(data, dict):
        for key in data:
            # This is base64("schema-placeholder"), not real secret material.
            data[key] = "c2NoZW1hLXBsYWNlaG9sZGVy"
    string_data = document.get("stringData")
    if isinstance(string_data, dict):
        for key in string_data:
            string_data[key] = "schema-placeholder"


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {Path(sys.argv[0]).name} RENDERED_MANIFEST OUTPUT", file=sys.stderr)
        return 2

    source = Path(sys.argv[1])
    destination = Path(sys.argv[2])
    try:
        documents = load_documents(source)
    except ManifestError as error:
        github_error(str(error), path=source)
        return 1

    resources = 0
    with destination.open("w", encoding="utf-8") as output:
        for document in documents:
            if document is None:
                continue
            for resource in iter_kubernetes_objects(document):
                if resource.get("kind") == "Secret":
                    sanitize_secret(resource)
            if resources:
                output.write("---\n")
            json.dump(document, output, separators=(",", ":"), sort_keys=True)
            output.write("\n")
            resources += 1

    if resources == 0:
        github_error("rendered manifest contains no resources", path=source)
        return 1
    print(f"Prepared {resources} resource(s) for schema validation at {destination}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
