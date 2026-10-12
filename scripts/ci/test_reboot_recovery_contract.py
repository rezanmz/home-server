#!/usr/bin/env python3
"""Regression tests for cross-service recovery after a full cluster reboot."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CLUSTER_KUSTOMIZATION = REPO_ROOT / "clusters" / "home-server" / "kustomization.yaml"
COREDNS_SPLIT_DNS = REPO_ROOT / "infrastructure" / "coredns" / "split-dns.yaml"
AUTHENTIK_WORKLOADS = REPO_ROOT / "apps" / "authentik" / "workloads.yaml"


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

    def test_longhorn_b2_endpoint_cannot_select_unrouted_ipv6(self) -> None:
        config = load_object(COREDNS_SPLIT_DNS, "ConfigMap", "coredns-custom")
        corefile = config["data"]["backblaze-b2-ipv4.server"]

        self.assertIn("s3.ca-east-006.backblazeb2.com:53", corefile)
        self.assertIn("template IN AAAA", corefile)
        self.assertIn("rcode NOERROR", corefile)
        self.assertIn("forward . /etc/resolv.conf", corefile)
        self.assertNotIn("104.153.236.", corefile)

    def test_authentik_postgresql_has_oom_headroom(self) -> None:
        stateful_set = load_object(
            AUTHENTIK_WORKLOADS, "StatefulSet", "authentik-postgresql"
        )
        postgresql = named(
            stateful_set["spec"]["template"]["spec"]["containers"], "postgresql"
        )

        self.assertEqual(postgresql["resources"]["requests"]["memory"], "256Mi")
        self.assertEqual(postgresql["resources"]["limits"]["memory"], "512Mi")

if __name__ == "__main__":
    unittest.main()
