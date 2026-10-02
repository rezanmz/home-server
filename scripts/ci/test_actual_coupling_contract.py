#!/usr/bin/env python3
"""Regression tests for the Actual Budget server/client schema coupling.

`@actual-app/api` embeds the budget-file schema of the `actualbudget/actual-server`
release line it ships with. When the server's schema moves ahead of an embedded
client, every sync fails with `SyncError: invalid-schema` and never recovers
while the pods still look healthy (see docs/lessons-learned.md). Renovate groups
the packages but does not move every consumer together, so the three source pins
must agree and the identifying image tags must match their content.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def server_version() -> str:
    text = (REPO_ROOT / "apps/actual-budget/deployment.yaml").read_text()
    match = re.search(r"actualbudget/actual-server:([^@]+)@sha256:", text)
    if match is None:
        raise AssertionError("actual-server image pin is missing from the deployment")
    return match.group(1)


class ActualCouplingContractTests(unittest.TestCase):
    def test_finance_display_api_pin_matches_server(self) -> None:
        package = json.loads((REPO_ROOT / "images/finance-display/package.json").read_text())
        self.assertEqual(package["dependencies"]["@actual-app/api"], server_version())

    def test_finance_display_lockfile_matches_server(self) -> None:
        lock = json.loads((REPO_ROOT / "images/finance-display/package-lock.json").read_text())
        entry = lock["packages"]["node_modules/@actual-app/api"]
        self.assertEqual(entry["version"], server_version())

    def test_finance_display_helper_tag_matches_package_version(self) -> None:
        helper = (REPO_ROOT / "scripts/build-finance-display-image.sh").read_text()
        package = json.loads((REPO_ROOT / "images/finance-display/package.json").read_text())
        match = re.search(r'FINANCE_DISPLAY_VERSION="([^"@]+)"', helper)
        self.assertIsNotNone(match, "FINANCE_DISPLAY_VERSION is missing from the helper")
        self.assertEqual(match.group(1), package["version"])

    def test_mcphub_gptr_api_pin_matches_server(self) -> None:
        dockerfile = (REPO_ROOT / "images/mcphub-gptr/Dockerfile").read_text()
        match = re.search(r"ARG ACTUAL_API_VERSION=(\S+)", dockerfile)
        self.assertIsNotNone(match, "ACTUAL_API_VERSION is missing from the Dockerfile")
        self.assertEqual(match.group(1), server_version())

    def test_mcphub_gptr_suite_tag_matches_version_label(self) -> None:
        dockerfile = (REPO_ROOT / "images/mcphub-gptr/Dockerfile").read_text()
        helper = (REPO_ROOT / "scripts/build-mcphub-gptr-image.sh").read_text()
        label = re.search(
            r'org\.opencontainers\.image\.version="\$\{MCPHUB_VERSION\}-(assistant-suite-\d+)"',
            dockerfile,
        )
        tag = re.search(r'IMAGE_TAG="\$\{MCPHUB_VERSION\}-[^"]*-(assistant-suite-\d+)"', helper)
        self.assertIsNotNone(label, "suite revision is missing from the OCI version label")
        self.assertIsNotNone(tag, "suite revision is missing from the helper image tag")
        self.assertEqual(label.group(1), tag.group(1))


if __name__ == "__main__":
    unittest.main()
