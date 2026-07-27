#!/usr/bin/env python3
"""Regression tests for cross-service recovery after a full cluster reboot."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CLUSTER_KUSTOMIZATION = REPO_ROOT / "clusters" / "home-server" / "kustomization.yaml"
COREDNS_SPLIT_DNS = REPO_ROOT / "infrastructure" / "coredns" / "split-dns.yaml"
HERMES_DEPLOYMENT = REPO_ROOT / "apps" / "hermes-agent" / "deployment.yaml"
KEA_DEPLOYMENT = REPO_ROOT / "apps" / "kea" / "deployment.yaml"


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


class RebootRecoveryContractTests(unittest.TestCase):
    def test_cluster_routes_public_service_names_through_blocky(self) -> None:
        cluster = yaml.safe_load(CLUSTER_KUSTOMIZATION.read_text())
        self.assertIn("../../infrastructure/coredns", cluster["resources"])

        config = load_object(COREDNS_SPLIT_DNS, "ConfigMap", "coredns-custom")
        corefile = config["data"]["reza-network.server"]
        self.assertIn("reza.network:53", corefile)
        self.assertIn("forward . 192.168.1.2 192.168.1.3", corefile)
        self.assertNotIn("65.95.92.124", corefile)

    def test_hermes_waits_for_a_stable_nonempty_mcp_registry(self) -> None:
        deployment = load_object(HERMES_DEPLOYMENT, "Deployment", "hermes-agent")
        pod_spec = deployment["spec"]["template"]["spec"]
        wait = named(pod_spec["initContainers"], "wait-for-mcphub-tools")
        command = wait["args"][0]

        self.assertIn("hermes mcp test mcphub", command)
        self.assertIn("Tools discovered:", command)
        self.assertIn('count" = "$previous_count', command)
        self.assertNotIn("gmail", command.lower())
        self.assertNotIn("authorization", command.lower())
        self.assertEqual(named(wait["volumeMounts"], "data")["mountPath"], "/opt/data")

    def test_stork_agent_probes_require_the_grpc_listener(self) -> None:
        deployment = load_object(KEA_DEPLOYMENT, "Deployment", "kea-dhcp4")
        agent = named(deployment["spec"]["template"]["spec"]["containers"], "stork-agent")

        for probe_name in ("startupProbe", "readinessProbe", "livenessProbe"):
            command = agent[probe_name]["exec"]["command"][-1]
            self.assertIn("/proc/net/tcp", command)
            self.assertIn('01002A0A:1F90', command)
            self.assertIn('$4 == "0A"', command)


if __name__ == "__main__":
    unittest.main()
