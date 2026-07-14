#!/usr/bin/env python3
"""Small yq-backed helpers shared by repository CI checks."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from collections.abc import Iterator
from typing import Any


class ManifestError(RuntimeError):
    """Raised when a manifest cannot be converted to JSON documents."""


def require_command(command: str) -> None:
    if shutil.which(command) is None:
        raise ManifestError(f"required command is not installed: {command}")


def load_documents(path: Path) -> list[Any]:
    """Load every YAML/JSON document from path using pinned yq in CI."""

    require_command("yq")
    process = subprocess.run(
        ["yq", "eval", "--output-format=json", "--indent=0", ".", str(path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or "unknown yq error"
        raise ManifestError(f"{path}: {detail}")

    documents: list[Any] = []
    for line_number, line in enumerate(process.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            documents.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ManifestError(
                f"{path}: yq produced invalid JSON on output line {line_number}: {error}"
            ) from error
    return documents


def iter_kubernetes_objects(document: Any) -> Iterator[dict[str, Any]]:
    """Expand Kubernetes List objects without inspecting arbitrary embedded data."""

    if not isinstance(document, dict):
        return
    yield document
    if document.get("kind") not in {"List", "SecretList"}:
        return
    items = document.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        yield from iter_kubernetes_objects(item)


def github_error(message: str, *, path: Path | None = None) -> None:
    """Emit a GitHub Actions error annotation without command injection."""

    escaped = (
        message.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )
    if path is None:
        print(f"::error title=Cluster validation::{escaped}")
        return

    escaped_path = (
        str(path)
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )
    print(f"::error file={escaped_path},title=Cluster validation::{escaped}")
