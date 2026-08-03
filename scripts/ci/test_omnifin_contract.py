#!/usr/bin/env python3
"""Regression tests for Omnifin's web/gateway trust and storage boundaries."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE = (
    "ghcr.io/rezanmz/omnifin:0.7.2@"
    "sha256:5dd2b685594cf15c85f9d055dc8290c105575a7c7ab59d9394cf6f1e566df16b"
)


def documents(relative_path: str) -> list[dict]:
    return [
        document
        for document in yaml.safe_load_all((REPO_ROOT / relative_path).read_text())
        if isinstance(document, dict)
    ]


def resource(relative_path: str, kind: str, name: str) -> dict:
    for document in documents(relative_path):
        if (
            document.get("kind") == kind
            and document.get("metadata", {}).get("name") == name
        ):
            return document
    raise AssertionError(f"{kind}/{name} is missing from {relative_path}")


def named(items: list[dict], name: str) -> dict:
    for item in items:
        if item.get("name") == name:
            return item
    raise AssertionError(f"{name!r} is missing")


class OmnifinContractTests(unittest.TestCase):
    def test_gateway_is_single_writer_floating_and_file_secret_backed(self) -> None:
        deployment = resource(
            "apps/omnifin/deployment.yaml", "Deployment", "omnifin-gateway"
        )
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")

        pod = deployment["spec"]["template"]["spec"]
        self.assertNotIn("nodeSelector", pod)
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["securityContext"]["runAsUser"], 65532)

        prepare = named(pod["initContainers"], "prepare-data-directory")
        self.assertFalse(prepare["securityContext"]["runAsNonRoot"])
        self.assertEqual(prepare["securityContext"]["runAsUser"], 0)
        self.assertEqual(
            prepare["securityContext"]["capabilities"]["add"],
            ["CHOWN", "FOWNER"],
        )
        prepare_command = " ".join(prepare["command"])
        self.assertIn("mkdir -p /data/backups", prepare_command)
        self.assertIn("chmod 0700 /data/backups", prepare_command)
        self.assertIn("chown 65532:65532 /data/backups", prepare_command)
        self.assertIn("chmod 0700 /data", prepare_command)
        self.assertIn("chown 65532:65532 /data", prepare_command)

        gateway = named(pod["containers"], "gateway")
        self.assertEqual(gateway["image"], IMAGE)
        self.assertTrue(gateway["securityContext"]["readOnlyRootFilesystem"])
        environment = {item["name"]: item for item in gateway["env"]}
        self.assertEqual(
            environment["OMNIFIN_DATABASE_URL"]["value"], "/data/omnifin.db"
        )
        self.assertEqual(
            environment["OMNIFIN_BACKUP_DIRECTORY"]["value"], "/data/backups"
        )
        self.assertEqual(
            environment["OMNIFIN_JELLYFIN_URL"]["value"],
            "http://jellyfin.media.svc.cluster.local:8096",
        )
        self.assertEqual(
            environment["OMNIFIN_JELLYFIN_INSECURE_HTTP_APPROVED"]["value"],
            "true",
        )
        self.assertEqual(
            environment["OMNIFIN_ENCRYPTION_KEY_FILE"]["value"],
            "/run/secrets/omnifin_encryption_key",
        )
        self.assertEqual(
            environment["OMNIFIN_RECOVERY_SECRET_FILE"]["value"],
            "/run/secrets/omnifin_recovery_secret",
        )
        self.assertNotIn("OMNIFIN_ENCRYPTION_KEY", environment)
        self.assertNotIn("OMNIFIN_RECOVERY_SECRET", environment)
        self.assertEqual(gateway["readinessProbe"]["httpGet"]["path"], "/readyz")

        volumes = {item["name"]: item for item in pod["volumes"]}
        self.assertEqual(
            volumes["data"]["persistentVolumeClaim"]["claimName"],
            "omnifin-data",
        )
        self.assertEqual(volumes["encryption-key"]["secret"]["defaultMode"], 0o440)
        self.assertEqual(volumes["recovery-secret"]["secret"]["defaultMode"], 0o440)

    def test_web_is_stateless_and_only_proxies_to_private_gateway(self) -> None:
        deployment = resource(
            "apps/omnifin/deployment.yaml", "Deployment", "omnifin-web"
        )
        pod = deployment["spec"]["template"]["spec"]
        self.assertNotIn("nodeSelector", pod)
        web = named(pod["containers"], "web")
        self.assertEqual(web["image"], IMAGE)
        environment = {item["name"]: item["value"] for item in web["env"]}
        self.assertEqual(
            environment["OMNIFIN_GATEWAY_URL"],
            "http://omnifin-gateway.apps.svc.cluster.local:4000",
        )
        self.assertTrue(web["securityContext"]["readOnlyRootFilesystem"])
        volume_names = {item["name"] for item in pod["volumes"]}
        self.assertNotIn("data", volume_names)

        route = resource("apps/omnifin/route.yaml", "HTTPRoute", "omnifin")
        backend = route["spec"]["rules"][0]["backendRefs"][0]
        self.assertEqual(backend, {"name": "omnifin", "port": 3000})
        gateway_service = resource(
            "apps/omnifin/service.yaml", "Service", "omnifin-gateway"
        )
        self.assertEqual(gateway_service["spec"]["type"], "ClusterIP")
        self.assertEqual(gateway_service["spec"]["ports"][0]["port"], 4000)

    def test_network_policies_preserve_the_gateway_boundary(self) -> None:
        web_policy = resource(
            "apps/omnifin/networkpolicy.yaml", "NetworkPolicy", "omnifin-web"
        )
        gateway_policy = resource(
            "apps/omnifin/networkpolicy.yaml", "NetworkPolicy", "omnifin-gateway"
        )
        self.assertEqual(
            web_policy["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/component"],
            "web",
        )
        self.assertEqual(
            gateway_policy["spec"]["podSelector"]["matchLabels"][
                "app.kubernetes.io/component"
            ],
            "gateway",
        )
        gateway_ingress = gateway_policy["spec"]["ingress"]
        self.assertEqual(len(gateway_ingress), 1)
        source = gateway_ingress[0]["from"][0]["podSelector"]["matchLabels"]
        self.assertEqual(source["app.kubernetes.io/name"], "omnifin")
        self.assertEqual(source["app.kubernetes.io/component"], "web")

        for rule in gateway_policy["spec"]["egress"]:
            for peer in rule.get("to", []):
                self.assertNotEqual(
                    peer.get("ipBlock", {}).get("cidr"), "0.0.0.0/0"
                )

        jellyfin_rules = [
            rule
            for rule in gateway_policy["spec"]["egress"]
            if rule.get("ports") == [{"port": 8096, "protocol": "TCP"}]
        ]
        self.assertEqual(len(jellyfin_rules), 1)
        jellyfin_cidrs = {
            peer["ipBlock"]["cidr"]
            for peer in jellyfin_rules[0]["to"]
            if "ipBlock" in peer
        }
        self.assertEqual(jellyfin_cidrs, {"192.168.1.2/32", "192.168.1.3/32"})


if __name__ == "__main__":
    unittest.main()
