#!/usr/bin/env python3
"""Regression tests for SABnzbd's dedicated VPN workload boundary."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SABNZBD_IMAGE = (
    "lscr.io/linuxserver/sabnzbd:5.1.1-ls268@"
    "sha256:78253a5ed379d08c16deba4154a2468875aa25a729c54c59c1199f851f87c29e"
)
GLUETUN_IMAGE = (
    "qmcgaw/gluetun:v3.41.3@"
    "sha256:fa19cc76b2af13d57a8d3dc3066f2ada061b1c761b8aecf989b3877c0486e027"
)
BUSYBOX_IMAGE = (
    "busybox:1.38.0@"
    "sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616"
)
NGINX_IMAGE = (
    "nginx:1.31.4-alpine@"
    "sha256:db35bfc6b2951e7f8a72db5db120288c127ffaeeb4a6d4b95a26fead017d5913"
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
            {
                "PUID": "1000",
                "PGID": "1000",
                "LSIO_NON_ROOT_USER": "1",
                "TZ": "America/Toronto",
            },
        )
        security_context = sabnzbd["securityContext"]
        self.assertFalse(security_context["allowPrivilegeEscalation"])
        self.assertTrue(security_context["runAsNonRoot"])
        self.assertEqual(security_context["runAsUser"], 1000)
        self.assertEqual(security_context["runAsGroup"], 1000)
        self.assertEqual(security_context["capabilities"]["drop"], ["ALL"])
        self.assertNotIn("add", security_context["capabilities"])
        mounts = {mount["name"]: mount["mountPath"] for mount in sabnzbd["volumeMounts"]}
        self.assertEqual(mounts["sabnzbd-config"], "/config")
        self.assertEqual(mounts["media-downloads"], "/media/downloads")
        self.assertEqual(mounts["run"], "/run")
        self.assertNotIn("media-library", mounts)
        self.assertEqual(
            {volume["name"] for volume in pod["volumes"]},
            {
                "dev-net-tun",
                "sabnzbd-config",
                "gluetun-state",
                "media-downloads",
                "tmp",
                "run",
                "sabnzbd-access-config",
                "sabnzbd-nginx-tmp",
                "sabnzbd-nginx-cache",
            },
        )
        volumes = {volume["name"]: volume for volume in pod["volumes"]}
        self.assertEqual(volumes["run"]["emptyDir"], {})

    def test_gluetun_uses_runtime_secret_and_no_lan_bypass(self) -> None:
        deployment = resource(
            "apps/sabnzbd/deployment.yaml", "Deployment", "sabnzbd-vpn"
        )
        pod = deployment["spec"]["template"]["spec"]
        self.assertEqual(
            [container["name"] for container in pod["initContainers"]],
            ["gluetun", "prepare-sabnzbd-run"],
        )
        gluetun = pod["initContainers"][0]
        self.assertEqual(gluetun["name"], "gluetun")
        self.assertEqual(gluetun["image"], GLUETUN_IMAGE)
        self.assertEqual(gluetun["restartPolicy"], "Always")
        self.assertEqual(
            gluetun["securityContext"]["capabilities"]["add"],
            [
                "CHOWN",
                "DAC_OVERRIDE",
                "NET_ADMIN",
                "NET_BIND_SERVICE",
                "NET_RAW",
                "SETGID",
                "SETUID",
            ],
        )
        env = {entry["name"]: entry for entry in gluetun["env"]}
        self.assertEqual(env["VPN_SERVICE_PROVIDER"]["value"], "protonvpn")
        self.assertEqual(env["VPN_TYPE"]["value"], "wireguard")
        self.assertEqual(env["PORT_FORWARD_ONLY"]["value"], "off")
        self.assertEqual(env["VPN_PORT_FORWARDING"]["value"], "off")
        self.assertEqual(env["FIREWALL_INPUT_PORTS"]["value"], "8080,18081")
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
        prepare_run = pod["initContainers"][1]
        self.assertEqual(prepare_run["image"], BUSYBOX_IMAGE)
        self.assertEqual(prepare_run["command"], ["chown", "1000:1000", "/run"])
        self.assertEqual(
            prepare_run["securityContext"],
            {
                "allowPrivilegeEscalation": False,
                "readOnlyRootFilesystem": True,
                "runAsUser": 0,
                "runAsGroup": 0,
                "capabilities": {"drop": ["ALL"], "add": ["CHOWN"]},
            },
        )
        self.assertEqual(
            prepare_run["resources"],
            {
                "requests": {"cpu": "5m", "memory": "8Mi"},
                "limits": {"cpu": "50m", "memory": "32Mi"},
            },
        )
        self.assertEqual(
            prepare_run["volumeMounts"], [{"name": "run", "mountPath": "/run"}]
        )

    def test_access_proxy_is_hardened_and_only_has_dedicated_writable_paths(self) -> None:
        deployment = resource(
            "apps/sabnzbd/deployment.yaml", "Deployment", "sabnzbd-vpn"
        )
        pod = deployment["spec"]["template"]["spec"]
        proxy = next(
            container
            for container in pod["containers"]
            if container["name"] == "sabnzbd-access-proxy"
        )
        self.assertEqual(proxy["image"], NGINX_IMAGE)
        self.assertEqual(proxy["ports"], [{"name": "sab-access", "containerPort": 18081, "protocol": "TCP"}])
        self.assertEqual(
            proxy["readinessProbe"],
            {
                "exec": {"command": ["sh", "-c", "kill -0 1"]},
                "periodSeconds": 10,
                "timeoutSeconds": 3,
            },
        )
        self.assertEqual(
            proxy["livenessProbe"],
            {
                "exec": {"command": ["sh", "-c", "kill -0 1"]},
                "periodSeconds": 30,
                "timeoutSeconds": 3,
            },
        )
        self.assertEqual(
            proxy["resources"],
            {
                "requests": {"cpu": "10m", "memory": "16Mi"},
                "limits": {"cpu": "100m", "memory": "64Mi"},
            },
        )
        self.assertEqual(
            proxy["securityContext"],
            {
                "runAsNonRoot": True,
                "runAsUser": 101,
                "runAsGroup": 101,
                "allowPrivilegeEscalation": False,
                "readOnlyRootFilesystem": True,
                "capabilities": {"drop": ["ALL"]},
            },
        )
        self.assertEqual(
            proxy["volumeMounts"],
            [
                {"name": "sabnzbd-access-config", "mountPath": "/etc/nginx", "readOnly": True},
                {"name": "sabnzbd-nginx-tmp", "mountPath": "/tmp"},
                {"name": "sabnzbd-nginx-cache", "mountPath": "/var/cache/nginx"},
            ],
        )
        volumes = {volume["name"]: volume for volume in pod["volumes"]}
        self.assertEqual(volumes["sabnzbd-nginx-tmp"], {"name": "sabnzbd-nginx-tmp", "emptyDir": {}})
        self.assertEqual(volumes["sabnzbd-nginx-cache"], {"name": "sabnzbd-nginx-cache", "emptyDir": {}})

        config = resource(
            "apps/sabnzbd/access-proxy.yaml", "ConfigMap", "sabnzbd-access-proxy"
        )
        nginx = config["data"]["nginx.conf"]
        self.assertIn("pid /tmp/nginx.pid;", nginx)
        self.assertIn("listen 18081;", nginx)
        self.assertIn("proxy_pass http://127.0.0.1:8080;", nginx)
        self.assertIn("allow 192.168.1.0/24;", nginx)
        self.assertIn("allow 10.8.0.0/24;", nginx)
        self.assertIn("allow 10.42.1.0/24;", nginx)
        self.assertIn("deny all;", nginx)

    def test_service_and_network_policy_are_internal_and_scoped(self) -> None:
        service = resource("apps/sabnzbd/service.yaml", "Service", "sabnzbd")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(
            service["spec"]["selector"], {"app.kubernetes.io/name": "sabnzbd-vpn"}
        )
        self.assertEqual(
            service["spec"]["ports"],
            [{"name": "http", "port": 8080, "targetPort": "sabnzbd"}],
        )

        access_service = resource(
            "apps/sabnzbd/service.yaml", "Service", "sabnzbd-access"
        )
        self.assertEqual(access_service["spec"]["type"], "ClusterIP")
        self.assertEqual(
            access_service["spec"]["selector"],
            {"app.kubernetes.io/name": "sabnzbd-vpn"},
        )
        self.assertEqual(
            access_service["spec"]["ports"],
            [{"name": "http", "port": 80, "targetPort": "sab-access"}],
        )

        policy = resource(
            "apps/sabnzbd/networkpolicy.yaml", "NetworkPolicy", "sabnzbd-vpn"
        )
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress", "Egress"])
        self.assertEqual(len(policy["spec"]["ingress"]), 2)
        self.assertEqual(
            policy["spec"]["ingress"][0]["from"],
            [{"podSelector": {"matchLabels": {"app.kubernetes.io/name": "media-vpn"}}}],
        )
        self.assertEqual(
            policy["spec"]["ingress"][0]["ports"],
            [{"port": 8080, "protocol": "TCP"}],
        )
        self.assertEqual(
            policy["spec"]["ingress"][1],
            {
                "from": [
                    {
                        "namespaceSelector": {
                            "matchLabels": {
                                "kubernetes.io/metadata.name": "traefik"
                            }
                        },
                        "podSelector": {
                            "matchLabels": {"app.kubernetes.io/name": "traefik"}
                        },
                    }
                ],
                "ports": [{"port": 18081, "protocol": "TCP"}],
            },
        )
        self.assertNotIn(
            {"port": 18081, "protocol": "TCP"},
            policy["spec"]["ingress"][0]["ports"],
        )
        self.assertNotIn(
            {"port": 8080, "protocol": "TCP"},
            policy["spec"]["ingress"][1]["ports"],
        )
        self.assertEqual(policy["spec"]["egress"], [{}])

    def test_route_has_no_forward_auth_and_one_protected_backend(self) -> None:
        route_documents = documents("apps/sabnzbd/route.yaml")
        self.assertEqual(len(route_documents), 1)
        self.assertFalse(
            any(document.get("kind") == "Middleware" for document in route_documents)
        )
        route = resource("apps/sabnzbd/route.yaml", "HTTPRoute", "sabnzbd")
        self.assertEqual(
            route["spec"]["parentRefs"], [{"name": "home", "namespace": "traefik"}]
        )
        self.assertEqual(route["spec"]["hostnames"], ["sabnzbd.reza.network"])
        self.assertEqual(len(route["spec"]["rules"]), 1)
        protected = route["spec"]["rules"][0]
        self.assertNotIn("outpost.goauthentik.io", str(route))
        self.assertEqual(
            [
                item["extensionRef"]["name"]
                for item in protected["filters"]
                if item["type"] == "ExtensionRef"
            ],
            ["custom-errors", "lan-vpn-only"],
        )
        self.assertEqual(protected["backendRefs"], [{"name": "sabnzbd-access", "port": 80}])

    def test_catalog_is_private_split_horizon_native_auth_without_public_dns(self) -> None:
        catalog = resource(
            "apps/sabnzbd/sabnzbd.catalog.yaml", "Service", "sabnzbd"
        )
        spec = catalog["spec"]
        self.assertEqual(spec["web"]["hostname"], "sabnzbd.reza.network")
        self.assertEqual(spec["web"]["visibility"], "private")
        self.assertEqual(spec["web"]["accessMiddleware"], "lan-vpn-only")
        self.assertEqual(
            spec["web"]["dns"], {"cloudflare": False, "splitHorizon": True}
        )
        self.assertEqual(
            spec["web"]["auth"],
            {
                "mode": "native",
                "reason": "SABnzbd uses its native application authentication behind the LAN/WireGuard boundary.",
            },
        )

        blocky = (REPO_ROOT / "apps/blocky/config.yml").read_text()
        self.assertIn("sabnzbd.reza.network: 192.168.1.240", blocky)
        cloudflare = (
            REPO_ROOT / "apps/cloudflare-ddns/kustomization.yaml"
        ).read_text()
        self.assertNotIn("sabnzbd.reza.network", cloudflare)


if __name__ == "__main__":
    unittest.main()
