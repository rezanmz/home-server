#!/usr/bin/env python3
"""Reject plaintext or malformed Kubernetes Secret manifests anywhere in the repo."""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from yaml_documents import ManifestError, github_error, iter_kubernetes_objects, load_documents


SOPS_VALUE = re.compile(
    r"^ENC\[AES256_GCM,data:(?P<data>[A-Za-z0-9+/]*={0,2}),"
    r"iv:(?P<iv>[A-Za-z0-9+/]+={0,2}),"
    r"tag:(?P<tag>[A-Za-z0-9+/]+={0,2}),type:str\]$"
)
SOPS_FILENAME = re.compile(r"\.sops\.ya?ml$")
AGE_RECIPIENT = re.compile(r"^age1[023456789acdefghjklmnpqrstuvwxyz]{58}$")
MANIFEST_SUFFIXES = (".yaml", ".yml", ".json")


def tracked_files() -> list[Path]:
    process = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    paths = (Path(os.fsdecode(raw)) for raw in process.stdout.split(b"\0") if raw)
    # Model the prospective worktree: include non-ignored new files, but do not
    # try to open indexed paths that have been deleted locally.
    return sorted(path for path in paths if path.exists())


def is_probably_text(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return b"\0" not in stream.read(8192)
    except OSError:
        return False


def valid_sops_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    match = SOPS_VALUE.fullmatch(value)
    if match is None:
        return False
    decoded: dict[str, bytes] = {}
    try:
        for field in ("data", "iv", "tag"):
            decoded[field] = base64.b64decode(match.group(field), validate=True)
    except (ValueError, binascii.Error):
        return False
    return len(decoded["iv"]) == 32 and len(decoded["tag"]) == 16


def is_encrypted_or_null(value: Any) -> bool:
    # A null carries no plaintext. It is retained for the one existing optional
    # Secret key; kubeconform receives a schema-safe placeholder separately.
    return value is None or valid_sops_value(value)


def valid_age_envelope(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lines = value.strip().splitlines()
    if len(lines) < 3:
        return False
    if lines[0] != "-----BEGIN AGE ENCRYPTED FILE-----":
        return False
    if lines[-1] != "-----END AGE ENCRYPTED FILE-----":
        return False
    payload = "".join(lines[1:-1])
    try:
        decoded = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        return False
    return decoded.startswith(b"age-encryption.org/v1\n")


def parse_age_values(value: Any) -> set[str]:
    values: list[str] = []
    if isinstance(value, str):
        values = re.split(r"[,\s]+", value.strip())
    elif isinstance(value, list):
        values = [entry for entry in value if isinstance(entry, str)]
    return {entry for entry in values if entry}


def load_creation_rules(path: Path = Path(".sops.yaml")) -> list[tuple[re.Pattern[str], set[str]]]:
    documents = load_documents(path)
    if len(documents) != 1 or not isinstance(documents[0], dict):
        raise ManifestError(f"{path}: expected exactly one SOPS configuration document")
    raw_rules = documents[0].get("creation_rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ManifestError(f"{path}: creation_rules must be a non-empty list")

    rules: list[tuple[re.Pattern[str], set[str]]] = []
    for index, rule in enumerate(raw_rules):
        if not isinstance(rule, dict) or not isinstance(rule.get("path_regex"), str):
            raise ManifestError(f"{path}: creation_rules[{index}] has no path_regex")
        try:
            pattern = re.compile(rule["path_regex"])
        except re.error as error:
            raise ManifestError(
                f"{path}: creation_rules[{index}].path_regex is invalid: {error}"
            ) from error
        recipients = parse_age_values(rule.get("age"))
        if not recipients or any(AGE_RECIPIENT.fullmatch(value) is None for value in recipients):
            raise ManifestError(f"{path}: creation_rules[{index}] has invalid age recipients")
        if rule.get("encrypted_regex") != "^(data|stringData)$":
            raise ManifestError(
                f"{path}: creation_rules[{index}] must encrypt exactly data and stringData"
            )
        rules.append((pattern, recipients))
    return rules


def validate_secret(
    document: dict[str, Any],
    path: Path,
    *,
    require_sops_filename: bool = True,
    expected_recipient_sets: list[set[str]] | None = None,
) -> list[str]:
    errors: list[str] = []
    metadata = document.get("metadata")
    name = metadata.get("name") if isinstance(metadata, dict) else None
    identity = str(name or "<unnamed>")

    if require_sops_filename and not SOPS_FILENAME.search(path.name):
        errors.append(f"Secret {identity} must use a .sops.yaml or .sops.yml filename")

    sops = document.get("sops")
    if not isinstance(sops, dict):
        errors.append(f"Secret {identity} is missing top-level SOPS metadata")
        sops = {}

    if sops.get("encrypted_regex") != "^(data|stringData)$":
        errors.append(
            f"Secret {identity} must encrypt exactly data and stringData via sops.encrypted_regex"
        )
    if not is_encrypted_or_null(sops.get("mac")) or sops.get("mac") is None:
        errors.append(f"Secret {identity} has no encrypted SOPS MAC")

    age = sops.get("age")
    actual_recipients: list[str] = []
    if not isinstance(age, list) or not age:
        errors.append(f"Secret {identity} has no SOPS age recipient metadata")
    else:
        for index, recipient in enumerate(age):
            if not isinstance(recipient, dict):
                errors.append(f"Secret {identity} has malformed sops.age[{index}] metadata")
                continue
            recipient_value = recipient.get("recipient")
            if not isinstance(recipient_value, str) or AGE_RECIPIENT.fullmatch(recipient_value) is None:
                errors.append(f"Secret {identity} has invalid sops.age[{index}].recipient")
            else:
                actual_recipients.append(recipient_value)
            if not valid_age_envelope(recipient.get("enc")):
                errors.append(f"Secret {identity} has invalid sops.age[{index}].enc armor")

    if len(actual_recipients) != len(set(actual_recipients)):
        errors.append(f"Secret {identity} has duplicate SOPS age recipients")
    if expected_recipient_sets is not None:
        actual_set = set(actual_recipients)
        if not expected_recipient_sets:
            errors.append(f"Secret {identity} is not covered by any .sops.yaml creation rule")
        elif actual_set not in expected_recipient_sets:
            errors.append(f"Secret {identity} age recipients do not match .sops.yaml")

    payload_seen = False
    for field in ("data", "stringData"):
        payload = document.get(field)
        if payload is None:
            continue
        payload_seen = True
        if not isinstance(payload, dict):
            errors.append(f"Secret {identity} field {field} must be a mapping")
            continue
        for key, value in payload.items():
            if not is_encrypted_or_null(value):
                errors.append(f"Secret {identity} contains plaintext or malformed {field}.{key}")

    if "binaryData" in document:
        errors.append(
            f"Secret {identity} uses unsupported binaryData; put encrypted values in data instead"
        )

    if not payload_seen and document.get("type") != "kubernetes.io/service-account-token":
        errors.append(f"Secret {identity} has neither data nor stringData")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rendered",
        type=Path,
        help="validate a rendered multi-document bundle instead of tracked source files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        creation_rules = load_creation_rules()
    except ManifestError as error:
        github_error(str(error), path=Path(".sops.yaml"))
        return 1
    candidates = [args.rendered] if args.rendered else tracked_files()
    if not candidates:
        github_error("no files were found for Secret validation")
        return 1

    secret_count = 0
    failures = 0
    parsed_count = 0
    for path in candidates:
        standard_manifest = path.suffix.lower() in MANIFEST_SUFFIXES
        if not args.rendered and not standard_manifest and not is_probably_text(path):
            continue
        try:
            documents = load_documents(path)
        except ManifestError as error:
            # Normal manifest extensions and the rendered bundle must always be
            # syntactically valid. Other tracked text files are opportunistically
            # parsed so an extensionless or oddly named Secret cannot hide.
            if args.rendered or standard_manifest:
                github_error(str(error), path=path)
                failures += 1
            continue
        parsed_count += 1

        for document in documents:
            for resource in iter_kubernetes_objects(document):
                if resource.get("kind") != "Secret":
                    continue
                secret_count += 1
                if args.rendered:
                    expected_recipients = [recipients for _, recipients in creation_rules]
                else:
                    expected_recipients = [
                        recipients
                        for pattern, recipients in creation_rules
                        if pattern.search(path.as_posix())
                    ]
                for error in validate_secret(
                    resource,
                    path,
                    require_sops_filename=not bool(args.rendered),
                    expected_recipient_sets=expected_recipients,
                ):
                    github_error(error, path=path)
                    failures += 1

    if failures:
        print(
            f"Secret validation failed with {failures} error(s) across {parsed_count} parsed file(s).",
            file=sys.stderr,
        )
        return 1

    print(
        f"Validated {secret_count} encrypted Kubernetes Secret document(s) "
        f"across {parsed_count} parsed file(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
