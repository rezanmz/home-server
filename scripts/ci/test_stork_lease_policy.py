#!/usr/bin/env python3
"""Regression tests for Stork's deliberately narrow lease-list access."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
KEA_DEPLOYMENT_PATH = REPO_ROOT / "apps" / "kea" / "deployment.yaml"
STORK_WORKLOADS_PATH = REPO_ROOT / "apps" / "stork" / "workloads.yaml"
STORK_PATCH_PATH = REPO_ROOT / "scripts" / "stork-read-only-lease-list.patch"


def load_object(path: Path, kind: str, name: str) -> dict:
    for document in yaml.safe_load_all(path.read_text()):
        if (
            isinstance(document, dict)
            and document.get("kind") == kind
            and document.get("metadata", {}).get("name") == name
        ):
            return document
    raise AssertionError(f"{kind}/{name} is missing from {path}")


def named(items: list[dict], name: str) -> dict:
    for item in items:
        if item.get("name") == name:
            return item
    raise AssertionError(f"{name} is missing")


class StorkLeasePolicyTests(unittest.TestCase):
    def test_agent_tracks_the_read_only_kea_lease_mount(self) -> None:
        deployment = load_object(KEA_DEPLOYMENT_PATH, "Deployment", "kea-dhcp4")
        pod_spec = deployment["spec"]["template"]["spec"]
        agent = named(pod_spec["containers"], "stork-agent")

        environment = {entry["name"]: entry.get("value") for entry in agent["env"]}
        self.assertEqual(environment["STORK_AGENT_ENABLE_LEASE_TRACKING"], "1")

        lease_mount = named(agent["volumeMounts"], "leases")
        self.assertEqual(lease_mount["mountPath"], "/var/lib/kea")
        self.assertIs(lease_mount["readOnly"], True)

        lease_volume = named(pod_spec["volumes"], "leases")
        self.assertEqual(
            lease_volume["persistentVolumeClaim"]["claimName"],
            "kea-leases",
        )

    def test_oidc_users_remain_in_storks_read_only_group(self) -> None:
        deployment = load_object(STORK_WORKLOADS_PATH, "Deployment", "stork-server")
        server = named(deployment["spec"]["template"]["spec"]["containers"], "server")
        environment = {entry["name"]: entry.get("value") for entry in server["env"]}
        self.assertEqual(environment["STORK_OIDC_MAP_GROUPS"], "false")

    def test_patch_changes_only_the_lease_list_handler_and_its_test(self) -> None:
        patch = STORK_PATCH_PATH.read_text()
        changed_files = [
            line.removeprefix("+++ b/")
            for line in patch.splitlines()
            if line.startswith("+++ b/")
        ]
        self.assertEqual(
            changed_files,
            [
                "backend/server/restservice/leaselist.go",
                "backend/server/restservice/leaselist_test.go",
            ],
        )
        self.assertEqual(
            patch.count("+\t\t!user.InGroup(&dbmodel.SystemGroup{ID: dbmodel.ReadOnlyGroupID})"),
            1,
        )
        self.assertNotIn("PostLease", patch)
        self.assertNotIn("PutLease", patch)
        self.assertNotIn("DeleteLease", patch)


if __name__ == "__main__":
    unittest.main()
