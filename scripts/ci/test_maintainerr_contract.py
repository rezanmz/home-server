#!/usr/bin/env python3
"""Regression tests for Maintainerr's connection-only integration boundary."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MAINTAINERR_IMAGE = (
    "ghcr.io/maintainerr/maintainerr:3.23.0@"
    "sha256:b6ec7216c5032dd1b8a3aeab8babd167dbeb0794b531fe01fd90b013915db093"
)
NGINX_IMAGE = (
    "nginx:1.31.3-alpine@"
    "sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752"
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


def filter_names(rule: dict) -> list[str]:
    return [
        item["extensionRef"]["name"]
        for item in rule.get("filters", [])
        if item["type"] == "ExtensionRef"
    ]


class MaintainerrContractTests(unittest.TestCase):
    def test_workload_is_singleton_immutable_and_without_host_or_media_access(self) -> None:
        deployment = resource(
            "apps/maintainerr/deployment.yaml", "Deployment", "maintainerr"
        )
        self.assertEqual(deployment["metadata"]["namespace"], "apps")
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")
        pod = deployment["spec"]["template"]
        self.assertEqual(
            pod["metadata"]["labels"]["app.kubernetes.io/name"], "maintainerr"
        )
        self.assertEqual(
            pod["metadata"]["labels"]["app.kubernetes.io/component"], "application"
        )
        pod_spec = pod["spec"]
        self.assertFalse(pod_spec["automountServiceAccountToken"])
        self.assertNotIn("serviceAccountName", pod_spec)
        self.assertFalse(pod_spec.get("hostNetwork", False))
        self.assertFalse(pod_spec.get("hostPID", False))
        self.assertFalse(pod_spec.get("hostIPC", False))
        self.assertNotIn("nodeSelector", pod_spec)
        volumes = {volume["name"]: volume for volume in pod_spec.get("volumes", [])}
        self.assertNotIn("media", volumes)
        self.assertNotIn("media-library", volumes)
        self.assertNotIn("dev-net-tun", volumes)

    def test_maintainerr_image_probes_and_security_context(self) -> None:
        deployment = resource(
            "apps/maintainerr/deployment.yaml", "Deployment", "maintainerr"
        )
        pod = deployment["spec"]["template"]["spec"]
        maintainerr = next(
            container
            for container in pod["containers"]
            if container["name"] == "maintainerr"
        )
        self.assertEqual(maintainerr["image"], MAINTAINERR_IMAGE)
        self.assertEqual(maintainerr["imagePullPolicy"], "IfNotPresent")
        self.assertEqual(
            {entry["name"]: entry["value"] for entry in maintainerr["env"]},
            {"LOG_LEVEL": "info", "TZ": "America/Toronto"},
        )
        self.assertEqual(
            maintainerr["ports"],
            [{"name": "http", "containerPort": 6246, "protocol": "TCP"}],
        )
        self.assertEqual(
            maintainerr["startupProbe"],
            {
                "httpGet": {"path": "/api/health/ready", "port": "http"},
                "periodSeconds": 5,
                "timeoutSeconds": 3,
                "failureThreshold": 18,
            },
        )
        self.assertEqual(
            maintainerr["readinessProbe"],
            {
                "httpGet": {"path": "/api/health/ready", "port": "http"},
                "periodSeconds": 15,
                "timeoutSeconds": 3,
                "failureThreshold": 3,
            },
        )
        self.assertEqual(
            maintainerr["livenessProbe"],
            {
                "httpGet": {"path": "/api/health/live", "port": "http"},
                "periodSeconds": 30,
                "timeoutSeconds": 3,
                "failureThreshold": 3,
            },
        )
        self.assertEqual(
            {mount["name"]: mount["mountPath"] for mount in maintainerr["volumeMounts"]},
            {"config": "/opt/data", "tmp": "/tmp"},
        )

    def test_pod_security_context_is_non_root_and_hardened(self) -> None:
        deployment = resource(
            "apps/maintainerr/deployment.yaml", "Deployment", "maintainerr"
        )
        pod = deployment["spec"]["template"]["spec"]
        self.assertEqual(
            pod["securityContext"],
            {
                "runAsNonRoot": True,
                "runAsUser": 1000,
                "runAsGroup": 1000,
                "fsGroup": 1000,
                "fsGroupChangePolicy": "OnRootMismatch",
                "seccompProfile": {"type": "RuntimeDefault"},
            },
        )
        for container in pod["containers"]:
            security_context = container["securityContext"]
            self.assertFalse(security_context["allowPrivilegeEscalation"])
            self.assertTrue(security_context["readOnlyRootFilesystem"])
            self.assertEqual(security_context["capabilities"]["drop"], ["ALL"])
            self.assertNotIn("add", security_context["capabilities"])

    def test_access_proxy_is_hardened_and_lan_only(self) -> None:
        deployment = resource(
            "apps/maintainerr/deployment.yaml", "Deployment", "maintainerr"
        )
        pod = deployment["spec"]["template"]["spec"]
        proxy = next(
            container
            for container in pod["containers"]
            if container["name"] == "access-proxy"
        )
        self.assertEqual(proxy["image"], NGINX_IMAGE)
        self.assertEqual(
            proxy["ports"],
            [{"name": "access-http", "containerPort": 16246, "protocol": "TCP"}],
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
        volumes = {volume["name"]: volume for volume in pod["volumes"]}
        self.assertEqual(
            volumes["tmp"],
            {"name": "tmp", "emptyDir": {}},
        )
        self.assertEqual(
            volumes["nginx-tmp"],
            {"name": "nginx-tmp", "emptyDir": {}},
        )
        self.assertEqual(
            volumes["nginx-cache"],
            {"name": "nginx-cache", "emptyDir": {}},
        )
        self.assertEqual(
            volumes["config"]["persistentVolumeClaim"],
            {"claimName": "maintainerr-config"},
        )

        config = resource(
            "apps/maintainerr/access-proxy.yaml",
            "ConfigMap",
            "maintainerr-access-proxy",
        )
        nginx = config["data"]["nginx.conf"]
        self.assertIn("pid /tmp/nginx.pid;", nginx)
        self.assertIn("listen 16246;", nginx)
        self.assertIn("proxy_pass http://127.0.0.1:6246;", nginx)
        self.assertIn("proxy_buffering off;", nginx)
        self.assertIn("proxy_read_timeout 3600s;", nginx)
        self.assertIn("allow 192.168.1.0/24;", nginx)
        self.assertIn("allow 10.8.0.0/24;", nginx)
        self.assertIn("allow 10.42.1.0/24;", nginx)
        self.assertIn("deny all;", nginx)

    def test_service_targets_proxy_only(self) -> None:
        services = documents("apps/maintainerr/service.yaml")
        self.assertEqual(len(services), 1)
        service = services[0]
        self.assertEqual(service["kind"], "Service")
        self.assertEqual(service["metadata"]["name"], "maintainerr")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(
            service["spec"]["selector"], {"app.kubernetes.io/name": "maintainerr"}
        )
        self.assertEqual(
            service["spec"]["ports"],
            [{"name": "http", "port": 16246, "targetPort": "access-http", "protocol": "TCP"}],
        )
        # The raw API port must never be exposed as a Service.
        self.assertNotIn(6246, [port["port"] for port in service["spec"]["ports"]])

    def test_network_policy_is_scoped_and_has_no_public_or_open_egress(self) -> None:
        policy = resource(
            "apps/maintainerr/networkpolicy.yaml", "NetworkPolicy", "maintainerr"
        )
        self.assertEqual(policy["metadata"]["namespace"], "apps")
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress", "Egress"])
        self.assertEqual(
            policy["spec"]["podSelector"],
            {"matchLabels": {"app.kubernetes.io/name": "maintainerr"}},
        )
        self.assertEqual(len(policy["spec"]["ingress"]), 1)
        ingress = policy["spec"]["ingress"][0]
        self.assertEqual(
            ingress["from"],
            [
                {
                    "namespaceSelector": {
                        "matchLabels": {"kubernetes.io/metadata.name": "traefik"}
                    }
                }
            ],
        )
        self.assertEqual(
            ingress["ports"], [{"port": 16246, "protocol": "TCP"}]
        )

        egress = policy["spec"]["egress"]
        self.assertNotEqual(egress, [{}])
        self.assertNotIn({}, egress)
        flattened = [
            (to, port)
            for rule in egress
            for to in rule.get("to", [])
            for port in rule.get("ports", [])
        ]
        self.assertEqual(
            flattened,
            [
                (
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                        },
                        "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                    },
                    {"port": 53, "protocol": "UDP"},
                ),
                (
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                        },
                        "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                    },
                    {"port": 53, "protocol": "TCP"},
                ),
                (
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "media"}
                        },
                        "podSelector": {"matchLabels": {"app.kubernetes.io/name": "jellyfin"}},
                    },
                    {"port": 8096, "protocol": "TCP"},
                ),
                (
                    {"ipBlock": {"cidr": "192.168.1.2/32"}},
                    {"port": 8096, "protocol": "TCP"},
                ),
                (
                    {"ipBlock": {"cidr": "192.168.1.3/32"}},
                    {"port": 8096, "protocol": "TCP"},
                ),
                (
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "media"}
                        },
                        "podSelector": {"matchLabels": {"app.kubernetes.io/name": "media-vpn"}},
                    },
                    {"port": 7878, "protocol": "TCP"},
                ),
                (
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "media"}
                        },
                        "podSelector": {"matchLabels": {"app.kubernetes.io/name": "media-vpn"}},
                    },
                    {"port": 8989, "protocol": "TCP"},
                ),
                (
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "apps"}
                        },
                        "podSelector": {"matchLabels": {"app.kubernetes.io/name": "seerr"}},
                    },
                    {"port": 5055, "protocol": "TCP"},
                ),
            ],
        )
        self.assertNotIn("0.0.0.0/0", str(policy))
        self.assertNotIn("10.42.1.0/24", str(policy))

    def test_bilateral_destination_ingress_is_exact(self) -> None:
        jellyfin = resource(
            "apps/jellyfin/networkpolicy.yaml", "NetworkPolicy", "jellyfin"
        )
        jellyfin_api_rule = next(
            rule
            for rule in jellyfin["spec"]["ingress"]
            if [port["port"] for port in rule.get("ports", [])] == [8096]
        )
        maintainerr_from = [
            selector
            for selector in jellyfin_api_rule["from"]
            if selector.get("podSelector", {}).get("matchLabels", {}).get(
                "app.kubernetes.io/name"
            )
            == "maintainerr"
        ]
        self.assertEqual(
            maintainerr_from,
            [
                {
                    "namespaceSelector": {
                        "matchLabels": {"kubernetes.io/metadata.name": "apps"}
                    },
                    "podSelector": {"matchLabels": {"app.kubernetes.io/name": "maintainerr"}},
                }
            ],
        )

        media_vpn = resource(
            "apps/downloads/networkpolicy.yaml", "NetworkPolicy", "media-vpn"
        )
        maintainerr_rule = next(
            rule
            for rule in media_vpn["spec"]["ingress"]
            if any(
                selector.get("podSelector", {}).get("matchLabels", {}).get(
                    "app.kubernetes.io/name"
                )
                == "maintainerr"
                for selector in rule.get("from", [])
            )
        )
        self.assertEqual(
            maintainerr_rule,
            {
                "from": [
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "apps"}
                        },
                        "podSelector": {"matchLabels": {"app.kubernetes.io/name": "maintainerr"}},
                    }
                ],
                "ports": [
                    {"port": 7878, "protocol": "TCP"},
                    {"port": 8989, "protocol": "TCP"},
                ],
            },
        )

        seerr = resource("apps/seerr/networkpolicy.yaml", "NetworkPolicy", "seerr")
        seerr_api_rules = [
            rule
            for rule in seerr["spec"]["ingress"]
            if [port["port"] for port in rule.get("ports", [])] == [5055]
        ]
        self.assertTrue(
            any(
                {
                    "podSelector": {
                        "matchLabels": {"app.kubernetes.io/name": "maintainerr"}
                    }
                }
                in rule["from"]
                for rule in seerr_api_rules
            )
        )

    def test_route_protects_app_after_authentik_callback(self) -> None:
        route_documents = documents("apps/maintainerr/route.yaml")
        middleware = next(
            document
            for document in route_documents
            if document.get("kind") == "Middleware"
        )
        self.assertEqual(middleware["metadata"]["name"], "maintainerr-authentik")
        self.assertEqual(middleware["metadata"]["namespace"], "apps")
        self.assertEqual(
            middleware["spec"]["forwardAuth"]["address"],
            "http://authentik.apps.svc.cluster.local:9000/outpost.goauthentik.io/auth/traefik",
        )
        self.assertTrue(middleware["spec"]["forwardAuth"]["trustForwardHeader"])
        self.assertIn(
            "X-authentik-groups", middleware["spec"]["forwardAuth"]["authResponseHeaders"]
        )

        route = resource("apps/maintainerr/route.yaml", "HTTPRoute", "maintainerr")
        self.assertEqual(
            route["spec"]["parentRefs"], [{"name": "home", "namespace": "traefik"}]
        )
        self.assertEqual(route["spec"]["hostnames"], ["maintainerr.reza.network"])
        self.assertEqual(len(route["spec"]["rules"]), 2)

        callback, protected = route["spec"]["rules"]
        self.assertEqual(
            callback["matches"],
            [{"path": {"type": "PathPrefix", "value": "/outpost.goauthentik.io"}}],
        )
        self.assertEqual(filter_names(callback), ["custom-errors", "lan-vpn-only"])
        self.assertEqual(
            callback["backendRefs"],
            [{"name": "authentik", "namespace": "apps", "port": 9000}],
        )
        self.assertEqual(
            filter_names(protected),
            ["custom-errors", "lan-vpn-only", "maintainerr-authentik"],
        )
        self.assertEqual(
            protected["backendRefs"], [{"name": "maintainerr", "port": 16246}]
        )

    def test_catalog_is_forward_auth_lan_only_with_admin_group(self) -> None:
        catalog = resource(
            "apps/maintainerr/maintainerr.catalog.yaml", "Service", "maintainerr"
        )
        spec = catalog["spec"]
        self.assertEqual(spec["workload"], {"namespace": "apps", "app": "maintainerr"})
        self.assertEqual(
            spec["homepage"]["group"], "Downloads & Automation"
        )
        self.assertEqual(
            spec["web"],
            {
                "hostname": "maintainerr.reza.network",
                "route": "apps/maintainerr/route.yaml",
                "visibility": "private",
                "accessMiddleware": "lan-vpn-only",
                "dns": {"cloudflare": False, "splitHorizon": True},
                "auth": {
                    "mode": "forward-auth",
                    "profile": "authentik-forward-single-v2",
                    "blueprintName": "Maintainerr proxy authentication",
                    "application": {
                        "slug": "maintainerr",
                        "launchUrl": "https://maintainerr.reza.network/",
                    },
                    "middleware": "maintainerr-authentik",
                    "allowedGroups": ["home-admins"],
                },
            },
        )
        self.assertEqual(spec["data"]["class"], "longhorn")
        self.assertEqual(spec["data"]["protection"], "longhorn-b2")
        self.assertEqual(
            spec["data"]["manifests"], ["apps/maintainerr/pvc.yaml"]
        )

    def test_generated_dns_is_split_horizon_only(self) -> None:
        hostname = "maintainerr.reza.network"
        blocky = (REPO_ROOT / "apps/blocky/config.yml").read_text()
        cloudflare = (
            REPO_ROOT / "apps/cloudflare-ddns/kustomization.yaml"
        ).read_text()
        homepage = (
            REPO_ROOT / "apps/homepage/config/services.yaml"
        ).read_text()

        self.assertIn(f"{hostname}: 192.168.1.240", blocky)
        self.assertNotIn(hostname, cloudflare)
        self.assertIn(f"https://{hostname}/", homepage)

    def test_pvc_is_dedicated_one_gib_longhorn(self) -> None:
        pvc = resource(
            "apps/maintainerr/pvc.yaml", "PersistentVolumeClaim", "maintainerr-config"
        )
        self.assertEqual(pvc["metadata"]["namespace"], "apps")
        self.assertEqual(pvc["spec"]["accessModes"], ["ReadWriteOnce"])
        self.assertEqual(
            pvc["spec"]["resources"]["requests"]["storage"], "1Gi"
        )
        self.assertEqual(pvc["spec"]["storageClassName"], "longhorn")

    def test_app_is_referenced_once_from_cluster_kustomization(self) -> None:
        root = (REPO_ROOT / "clusters/home-server/kustomization.yaml").read_text()
        self.assertEqual(root.count("../../apps/maintainerr"), 1)
        self.assertIn("../../apps/maintainerr", root)

    def test_manifests_contain_no_placeholders_or_plaintext_secrets(self) -> None:
        for manifest in [
            "access-proxy.yaml",
            "deployment.yaml",
            "kustomization.yaml",
            "maintainerr.catalog.yaml",
            "networkpolicy.yaml",
            "pvc.yaml",
            "route.yaml",
            "service.yaml",
        ]:
            contents = (REPO_ROOT / f"apps/maintainerr/{manifest}").read_text()
            self.assertNotIn("TODO", contents, manifest)
            self.assertNotIn("REPLACE", contents, manifest)
            self.assertNotIn("PASSWORD", contents, manifest)
            self.assertNotIn("SECRET", contents, manifest)


if __name__ == "__main__":
    unittest.main()
