#!/usr/bin/env python3
"""Verify that pinned Flux GitRepository commits resolve from their declared tags."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from yaml_documents import ManifestError, github_error, iter_kubernetes_objects, load_documents


FULL_GIT_COMMIT = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
Resolver = Callable[[str, str], str]


def identity(document: dict[str, Any]) -> str:
    metadata = document.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return (
        f"{document.get('apiVersion', 'unknown')}/{document.get('kind', 'unknown')} "
        f"{metadata.get('namespace', 'default')}/{metadata.get('name', 'unnamed')}"
    )


def resolve_remote_tag(url: str, tag: str) -> str:
    if not url.startswith("https://"):
        raise ValueError("only HTTPS Git source URLs can be verified")

    tag_ref = f"refs/tags/{tag}"
    peeled_ref = f"{tag_ref}^{{}}"
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_ALLOW_PROTOCOL": "https",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_PROTOCOL_FROM_USER": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
        completed = subprocess.run(
            ["git", "ls-remote", "--exit-code", url, tag_ref, peeled_ref],
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError(f"timed out resolving tag {tag!r}") from error

    if completed.returncode != 0:
        # Git may repeat a credential-bearing URL in stderr. Keep Actions logs
        # useful without copying remote error text into a public annotation.
        raise ValueError(
            f"could not resolve tag {tag!r}: git ls-remote exited "
            f"{completed.returncode}"
        )

    revisions: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        revision, separator, ref = line.partition("\t")
        if separator and FULL_GIT_COMMIT.fullmatch(revision):
            revisions[ref] = revision.lower()
    resolved = revisions.get(peeled_ref) or revisions.get(tag_ref)
    if resolved is None:
        raise ValueError(f"remote did not return tag {tag!r}")
    return resolved


def validate(documents: list[Any], resolver: Resolver | None = None) -> list[str]:
    resolve = resolver or resolve_remote_tag
    errors: list[str] = []
    for document in documents:
        for resource in iter_kubernetes_objects(document):
            if resource.get("kind") != "GitRepository" or not str(
                resource.get("apiVersion", "")
            ).startswith("source.toolkit.fluxcd.io/"):
                continue
            spec = resource.get("spec")
            ref = spec.get("ref") if isinstance(spec, dict) else None
            tag = ref.get("tag") if isinstance(ref, dict) else None
            if not isinstance(tag, str):
                continue

            source = identity(resource)
            url = spec.get("url") if isinstance(spec, dict) else None
            commit = ref.get("commit")
            if not isinstance(url, str):
                errors.append(f"{source}: tagged source URL is missing")
                continue
            if not isinstance(commit, str) or FULL_GIT_COMMIT.fullmatch(commit) is None:
                errors.append(f"{source}: tag {tag!r} lacks a full immutable commit")
                continue
            try:
                resolved = resolve(url, tag)
            except ValueError as error:
                errors.append(f"{source}: {error}")
                continue
            if resolved != commit.lower():
                errors.append(
                    f"{source}: tag {tag!r} resolves to {resolved}, not declared commit "
                    f"{commit.lower()}"
                )
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        documents = load_documents(args.manifest)
    except ManifestError as error:
        github_error(str(error), path=args.manifest)
        return 1

    errors = validate(documents)
    for error in errors:
        github_error(error, path=args.manifest)
    if errors:
        return 1

    print("Verified all tagged Flux GitRepository commit pins.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
