#!/usr/bin/env python3
"""Regression tests for SABnzbd's dedicated VPN workload boundary."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SABNZBD_IMAGE = (
    "lscr.io/linuxserver/sabnzbd:5.1.0-ls266@"
    "sha256:341b91c31403e46aff0ac640d9889092649f168a5f1edb8bb26d61abee62643a"
)
GLUETUN_IMAGE = (
    "qmcgaw/gluetun:v3.41.3@"
    "sha256:fa19cc76b2af13d57a8d3dc3066f2ada061b1c761b8aecf989b3877c0486e027"
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


class SabnzbdContractTests(unittest.TestCase):
    def test_workload_is_singleton_and_dedicated(self) -> None:
        deployment = resource(
            "apps/sabnzbd/deployment.yaml", "Deployment", "sabnzbd-vpn"
        )
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")
        pod = deployment["spec"]["template"]
        self.assertFalse(pod["spec"]["automountServiceAccountToken"])
        self.assertEqual(
            pod["metadata"]["labels"]["app.kubernetes.io/name"], "sabnzbd-vpn"
        )
        self.assertNotIn("media-library", pod["spec"].get("volumes", []))

    def test_sabnzbd_storage_image_and_security(self) -> None:
        deployment = resource(
            "apps/sabnzbd/deployment.yaml", "Deployment", "sabnzbd-vpn"
        )
        pod = deployment["spec"]["template"]["spec"]
        sabnzbd = next(
            container for container in pod["containers"] if container["name"] == "sabnzbd"
        )
        self.assertEqual(sabnzbd["image"], SABNZBD_IMAGE)
        self.assertEqual(
            {entry["name"]: entry["value"] for entry in sabnzbd["env"]},
            {"PUID": "1000", "PGID": "1000", "TZ": "America/Toronto"},
        )
        self.assertFalse(sabnzbd["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(sabnzbd["securityContext"]["capabilities"]["drop"], ["ALL"])
        mounts = {mount["name"]: mount["mountPath"] for mount in sabnzbd["volumeMounts"]}
        self.assertEqual(mounts["sabnzbd-config"], "/config")
        self.assertEqual(mounts["media-downloads"], "/media/downloads")
        self.assertNotIn("media-library", mounts)
        self.assertEqual(
            {volume["name"] for volume in pod["volumes"]},
            {"dev-net-tun", "sabnzbd-config", "gluetun-state", "media-downloads", "tmp"},
        )

    def test_gluetun_uses_runtime_secret_and_no_lan_bypass(self) -> None:
        deployment = resource(
            "apps/sabnzbd/deployment.yaml", "Deployment", "sabnzbd-vpn"
        )
        pod = deployment["spec"]["template"]["spec"]
        self.assertEqual(len(pod["initContainers"]), 1)
        gluetun = pod["initContainers"][0]
        self.assertEqual(gluetun["name"], "gluetun")
        self.assertEqual(gluetun["image"], GLUETUN_IMAGE)
        self.assertEqual(gluetun["restartPolicy"], "Always")
        env = {entry["name"]: entry for entry in gluetun["env"]}
        self.assertEqual(env["VPN_SERVICE_PROVIDER"]["value"], "protonvpn")
        self.assertEqual(env["VPN_TYPE"]["value"], "wireguard")
        self.assertEqual(env["PORT_FORWARD_ONLY"]["value"], "off")
        self.assertEqual(env["VPN_PORT_FORWARDING"]["value"], "off")
        self.assertEqual(env["FIREWALL_INPUT_PORTS"]["value"], "8080")
        self.assertEqual(
            env["FIREWALL_OUTBOUND_SUBNETS"]["value"], "10.42.0.0/16,10.43.0.0/16"
        )
        self.assertNotIn("192.168.1.0/24", env["FIREWALL_OUTBOUND_SUBNETS"]["value"])
        self.assertEqual(
            env["WIREGUARD_PRIVATE_KEY"]["valueFrom"]["secretKeyRef"],
            {"name": "sabnzbd-vpn", "key": "wireguard-private-key"},
        )
        self.assertEqual(
            {mount["name"]: mount["mountPath"] for mount in gluetun["volumeMounts"]},
            {"dev-net-tun": "/dev/net/tun", "gluetun-state": "/gluetun"},
        )

    def test_service_and_network_policy_are_internal_and_scoped(self) -> None:
        service = resource("apps/sabnzbd/service.yaml", "Service", "sabnzbd")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(
            service["spec"]["selector"], {"app.kubernetes.io/name": "sabnzbd-vpn"}
        )
        self.assertEqual(service["spec"]["ports"], [{"name": "http", "port": 8080, "targetPort": "sabnzbd"}])

        policy = resource(
            "apps/sabnzbd/networkpolicy.yaml", "NetworkPolicy", "sabnzbd-vpn"
        )
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress", "Egress"])
        self.assertEqual(len(policy["spec"]["ingress"]), 1)
        self.assertEqual(
            policy["spec"]["ingress"][0]["from"],
            [{"podSelector": {"matchLabels": {"app.kubernetes.io/name": "media-vpn"}}}],
        )
        self.assertEqual(
            policy["spec"]["ingress"][0]["ports"],
            [{"port": 8080, "protocol": "TCP"}],
        )
        self.assertEqual(policy["spec"]["egress"], [{}])


if __name__ == "__main__":
    unittest.main()
