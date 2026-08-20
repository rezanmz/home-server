#!/usr/bin/env python3
"""Regression tests for Maintainerr's connection-only integration boundary."""

from __future__ import annotations

import re
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
PROXY_IMAGE = (
    "ubuntu/squid:6.6-24.04_beta@"
    "sha256:6a097f68bae708cedbabd6188d68c7e2e7a38cedd05a176e1cc0ba29e3bbe029"
)
PROXY_URL = "http://maintainerr-tmdb-proxy.apps.svc.cluster.local:3128"
PROXY_NO_PROXY = "localhost,127.0.0.1,::1,[::1],.svc,.svc.cluster.local"
PUBLIC_443_EXCLUSIONS = [
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
]


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


def squid_lines() -> list[str]:
    return [
        line.strip()
        for line in (
            REPO_ROOT / "apps/maintainerr-tmdb-proxy/squid.conf"
        ).read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
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
            {
                "LOG_LEVEL": "info",
                "TZ": "America/Toronto",
                "HTTPS_PROXY": PROXY_URL,
                "NO_PROXY": PROXY_NO_PROXY,
            },
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

    def test_maintainerr_proxy_environment_is_uppercase_and_bypass_free(self) -> None:
        deployment = resource(
            "apps/maintainerr/deployment.yaml", "Deployment", "maintainerr"
        )
        maintainerr = next(
            container
            for container in deployment["spec"]["template"]["spec"]["containers"]
            if container["name"] == "maintainerr"
        )
        env = {entry["name"]: entry["value"] for entry in maintainerr["env"]}
        # Only the uppercase proxy variables may exist; lower-case and
        # HTTP/ALL variants would bypass or broaden the egress contract.
        self.assertEqual(set(env), {"LOG_LEVEL", "TZ", "HTTPS_PROXY", "NO_PROXY"})
        self.assertEqual(env["HTTPS_PROXY"], PROXY_URL)
        self.assertEqual(env["NO_PROXY"], PROXY_NO_PROXY)
        no_proxy_entries = env["NO_PROXY"].split(",")
        self.assertTrue(all(no_proxy_entries))
        self.assertNotIn("*", no_proxy_entries)
        self.assertNotIn(".", no_proxy_entries)
        self.assertNotIn("0.0.0.0", no_proxy_entries)
        deployment_text = (REPO_ROOT / "apps/maintainerr/deployment.yaml").read_text()
        for forbidden in (
            "HTTP_PROXY",
            "ALL_PROXY",
            "https_proxy",
            "no_proxy",
            "http_proxy",
            "all_proxy",
        ):
            self.assertNotIn(forbidden, deployment_text)

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
                    },
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "traefik",
                            "app.kubernetes.io/instance": "traefik-traefik",
                        }
                    },
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
                (
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "apps"}
                        },
                        "podSelector": {
                            "matchLabels": {
                                "app.kubernetes.io/name": "maintainerr-tmdb-proxy",
                                "app.kubernetes.io/component": "egress-proxy",
                            }
                        },
                    },
                    {"port": 3128, "protocol": "TCP"},
                ),
            ],
        )
        self.assertNotIn("0.0.0.0/0", str(policy))
        self.assertNotIn("10.42.1.0/24", str(policy))

    def test_proxy_workload_is_singleton_immutable_and_isolated(self) -> None:
        deployment = resource(
            "apps/maintainerr-tmdb-proxy/deployment.yaml",
            "Deployment",
            "maintainerr-tmdb-proxy",
        )
        self.assertEqual(deployment["metadata"]["namespace"], "apps")
        self.assertEqual(
            deployment["metadata"]["labels"]["app.kubernetes.io/name"],
            "maintainerr-tmdb-proxy",
        )
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")
        self.assertEqual(
            deployment["spec"]["selector"]["matchLabels"],
            {
                "app.kubernetes.io/name": "maintainerr-tmdb-proxy",
                "app.kubernetes.io/component": "egress-proxy",
            },
        )
        pod = deployment["spec"]["template"]
        self.assertEqual(
            pod["metadata"]["labels"]["app.kubernetes.io/name"],
            "maintainerr-tmdb-proxy",
        )
        self.assertEqual(
            pod["metadata"]["labels"]["app.kubernetes.io/component"],
            "egress-proxy",
        )
        pod_spec = pod["spec"]
        self.assertFalse(pod_spec["automountServiceAccountToken"])
        self.assertNotIn("serviceAccountName", pod_spec)
        self.assertFalse(pod_spec.get("hostNetwork", False))
        self.assertFalse(pod_spec.get("hostPID", False))
        self.assertFalse(pod_spec.get("hostIPC", False))
        self.assertNotIn("nodeSelector", pod_spec)
        volumes = {volume["name"]: volume for volume in pod_spec["volumes"]}
        self.assertEqual(set(volumes), {"squid-config", "tmp"})
        self.assertEqual(
            volumes["tmp"],
            {"name": "tmp", "emptyDir": {"sizeLimit": "32Mi"}},
        )
        self.assertEqual(
            volumes["squid-config"],
            {
                "name": "squid-config",
                "configMap": {
                    "name": "maintainerr-tmdb-proxy-config",
                    "defaultMode": 0o444,
                },
            },
        )

    def test_proxy_image_command_probes_and_resources(self) -> None:
        deployment = resource(
            "apps/maintainerr-tmdb-proxy/deployment.yaml",
            "Deployment",
            "maintainerr-tmdb-proxy",
        )
        pod = deployment["spec"]["template"]["spec"]
        proxy = next(
            container
            for container in pod["containers"]
            if container["name"] == "maintainerr-tmdb-proxy"
        )
        self.assertEqual(proxy["image"], PROXY_IMAGE)
        self.assertEqual(proxy["imagePullPolicy"], "IfNotPresent")
        self.assertEqual(proxy["command"], ["/usr/sbin/squid"])
        self.assertEqual(proxy["args"], ["-f", "/etc/squid/squid.conf", "-NYC"])
        self.assertEqual(
            proxy["ports"],
            [{"name": "proxy", "containerPort": 3128, "protocol": "TCP"}],
        )
        self.assertEqual(
            proxy["readinessProbe"],
            {"tcpSocket": {"port": "proxy"}, "periodSeconds": 10},
        )
        self.assertEqual(
            proxy["livenessProbe"],
            {"tcpSocket": {"port": "proxy"}, "periodSeconds": 30},
        )
        self.assertNotIn("startupProbe", proxy)
        self.assertEqual(
            proxy["resources"],
            {
                "requests": {
                    "cpu": "10m",
                    "memory": "192Mi",
                    "ephemeral-storage": "8Mi",
                },
                "limits": {
                    "cpu": "200m",
                    "memory": "256Mi",
                    "ephemeral-storage": "64Mi",
                },
            },
        )
        self.assertEqual(
            {mount["name"]: mount["mountPath"] for mount in proxy["volumeMounts"]},
            {"squid-config": "/etc/squid", "tmp": "/tmp"},
        )
        config_mount = next(
            mount
            for mount in proxy["volumeMounts"]
            if mount["name"] == "squid-config"
        )
        self.assertTrue(config_mount["readOnly"])

    def test_proxy_security_context_is_uid_13_and_hardened(self) -> None:
        deployment = resource(
            "apps/maintainerr-tmdb-proxy/deployment.yaml",
            "Deployment",
            "maintainerr-tmdb-proxy",
        )
        pod = deployment["spec"]["template"]["spec"]
        self.assertEqual(
            pod["securityContext"],
            {
                "runAsNonRoot": True,
                "runAsUser": 13,
                "runAsGroup": 13,
                "fsGroup": 13,
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

    def test_proxy_service_is_cluster_ip_only_on_3128(self) -> None:
        services = documents("apps/maintainerr-tmdb-proxy/service.yaml")
        self.assertEqual(len(services), 1)
        service = services[0]
        self.assertEqual(service["kind"], "Service")
        self.assertEqual(service["metadata"]["name"], "maintainerr-tmdb-proxy")
        self.assertEqual(service["metadata"]["namespace"], "apps")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(
            service["spec"]["selector"],
            {
                "app.kubernetes.io/name": "maintainerr-tmdb-proxy",
                "app.kubernetes.io/component": "egress-proxy",
            },
        )
        self.assertEqual(
            service["spec"]["ports"],
            [{"name": "proxy", "port": 3128, "targetPort": "proxy", "protocol": "TCP"}],
        )
        for port in service["spec"]["ports"]:
            self.assertNotIn("nodePort", port)
        self.assertNotIn("externalIPs", service["spec"])
        self.assertNotIn("loadBalancerIP", service["spec"])

    def test_proxy_has_no_route_catalog_pvc_or_secret(self) -> None:
        proxy_dir = REPO_ROOT / "apps/maintainerr-tmdb-proxy"
        self.assertEqual(
            sorted(path.name for path in proxy_dir.iterdir()),
            [
                "deployment.yaml",
                "kustomization.yaml",
                "maintainerr-tmdb-proxy.catalog.yaml",
                "networkpolicy.yaml",
                "service.yaml",
                "squid.conf",
            ],
        )
        exclusion = yaml.safe_load(
            (proxy_dir / "maintainerr-tmdb-proxy.catalog.yaml").read_text()
        )
        self.assertEqual(exclusion["kind"], "CatalogExclusion")
        self.assertIn("no browser-facing service", exclusion["spec"]["reason"])
        for path in proxy_dir.iterdir():
            contents = path.read_text()
            self.assertNotIn("Secret", contents, path.name)
            self.assertNotIn("token", contents, path.name)
            self.assertNotIn("hostPort", contents, path.name)
            self.assertNotIn("hostNetwork", contents, path.name)

    def test_proxy_network_policy_is_maintainerr_only_and_ipv4_public_443(self) -> None:
        policy = resource(
            "apps/maintainerr-tmdb-proxy/networkpolicy.yaml",
            "NetworkPolicy",
            "maintainerr-tmdb-proxy",
        )
        self.assertEqual(policy["metadata"]["namespace"], "apps")
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress", "Egress"])
        self.assertEqual(
            policy["spec"]["podSelector"],
            {
                "matchLabels": {
                    "app.kubernetes.io/name": "maintainerr-tmdb-proxy",
                    "app.kubernetes.io/component": "egress-proxy",
                }
            },
        )
        self.assertEqual(len(policy["spec"]["ingress"]), 1)
        ingress = policy["spec"]["ingress"][0]
        self.assertEqual(
            ingress["from"],
            [
                {
                    "namespaceSelector": {
                        "matchLabels": {"kubernetes.io/metadata.name": "apps"}
                    },
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "maintainerr",
                            "app.kubernetes.io/component": "application",
                        }
                    },
                }
            ],
        )
        self.assertEqual(ingress["ports"], [{"port": 3128, "protocol": "TCP"}])

        egress = policy["spec"]["egress"]
        self.assertEqual(len(egress), 2)
        dns_rule, public_rule = egress
        self.assertEqual(
            dns_rule,
            {
                "to": [
                    {
                        "namespaceSelector": {
                            "matchLabels": {
                                "kubernetes.io/metadata.name": "kube-system"
                            }
                        },
                        "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                    }
                ],
                "ports": [
                    {"port": 53, "protocol": "UDP"},
                    {"port": 53, "protocol": "TCP"},
                ],
            },
        )
        self.assertEqual(len(public_rule["to"]), 1)
        ip_block = public_rule["to"][0]["ipBlock"]
        self.assertEqual(ip_block["cidr"], "0.0.0.0/0")
        self.assertEqual(ip_block["except"], PUBLIC_443_EXCLUSIONS)
        self.assertEqual(public_rule["ports"], [{"port": 443, "protocol": "TCP"}])
        # DNS plus public HTTPS only: no alternate or proxy egress port.
        egress_ports = {
            port["port"] for rule in egress for port in rule.get("ports", [])
        }
        self.assertEqual(egress_ports, {53, 443})
        # Public egress is IPv4-only: no IPv6 rule of any form.
        self.assertNotIn("::", str(policy))

    def test_proxy_config_map_is_generated_with_hash_compatible_name(self) -> None:
        kustomization = yaml.safe_load(
            (REPO_ROOT / "apps/maintainerr-tmdb-proxy/kustomization.yaml").read_text()
        )
        self.assertEqual(
            kustomization["resources"],
            ["deployment.yaml", "service.yaml", "networkpolicy.yaml"],
        )
        self.assertEqual(len(kustomization["configMapGenerator"]), 1)
        self.assertIsNot(
            kustomization.get("generatorOptions", {}).get("disableNameSuffixHash"),
            True,
        )
        generator = kustomization["configMapGenerator"][0]
        self.assertEqual(generator["name"], "maintainerr-tmdb-proxy-config")
        self.assertEqual(generator["namespace"], "apps")
        self.assertEqual(generator["files"], ["squid.conf"])
        # The Deployment references the generator's base name so Kustomize
        # rewrites it to the content-hashed name at build time.
        deployment = resource(
            "apps/maintainerr-tmdb-proxy/deployment.yaml",
            "Deployment",
            "maintainerr-tmdb-proxy",
        )
        volume = next(
            volume
            for volume in deployment["spec"]["template"]["spec"]["volumes"]
            if volume["name"] == "squid-config"
        )
        self.assertEqual(
            volume["configMap"]["name"], "maintainerr-tmdb-proxy-config"
        )

    def test_squid_config_acl_order_allows_only_tmdb_443(self) -> None:
        lines = squid_lines()
        self.assertEqual(
            [line for line in lines if line.startswith("http_port")],
            ["http_port 3128"],
        )
        self.assertIn("acl localnet src 10.42.0.0/16", lines)
        self.assertIn("acl CONNECT method CONNECT", lines)
        self.assertEqual(
            [line for line in lines if line.startswith("acl Safe_ports")],
            ["acl Safe_ports port 443"],
        )
        self.assertEqual(
            [line for line in lines if line.startswith("acl SSL_ports")],
            ["acl SSL_ports port 443"],
        )
        # Security-significant order: reject unsafe ports, then non-CONNECT
        # methods, then CONNECT to any non-443 port, before the single allow
        # rule and the final deny-all. No rule may open a second allow path.
        self.assertEqual(
            [line for line in lines if line.startswith("http_access")],
            [
                "http_access deny !Safe_ports",
                "http_access deny !CONNECT",
                "http_access deny CONNECT !SSL_ports",
                "http_access allow localnet CONNECT TMDB SSL_ports",
                "http_access deny all",
            ],
        )

    def test_squid_config_rejects_raw_ip_suffix_and_trailing_dot_bypass(self) -> None:
        lines = squid_lines()
        tmdb_acl = [line for line in lines if "dstdom_regex" in line]
        self.assertEqual(
            tmdb_acl,
            ["acl TMDB dstdom_regex -n -i ^api\\.themoviedb\\.org$"],
        )
        # No raw-IP (dst) ACL offers an alternate TMDB allow path.
        self.assertEqual(
            [line for line in lines if re.match(r"acl\s+\S+\s+dst\s", line)],
            [],
        )
        # Anchored, case-insensitive hostname match only.
        allowed = re.compile(r"^api\.themoviedb\.org$", re.IGNORECASE)
        self.assertIsNotNone(allowed.fullmatch("api.themoviedb.org"))
        self.assertIsNotNone(allowed.fullmatch("API.TheMovieDB.ORG"))
        for bypass in (
            "api.themoviedb.org.evil.com",  # suffix/superdomain
            "evilapi.themoviedb.org",  # prefix
            "api.themoviedb.org.",  # trailing dot FQDN
            "17.142.68.219",  # raw IP
            "themoviedb.org",  # superdomain
        ):
            self.assertIsNone(allowed.fullmatch(bypass), bypass)

    def test_squid_config_has_no_cache_pid_log_files_or_identity_leak(self) -> None:
        lines = squid_lines()
        self.assertIn("cache deny all", lines)
        self.assertIn("cache_mem 0 MB", lines)
        self.assertIn("maximum_object_size_in_memory 0 KB", lines)
        self.assertIn("memory_pools off", lines)
        self.assertIn("pinger_enable off", lines)
        self.assertNotIn("cache_dir", lines)
        self.assertIn("pid_filename none", lines)
        # Any remaining writable state is explicitly bounded to /tmp or off.
        self.assertIn("coredump_dir /tmp", lines)
        self.assertIn("netdb_filename none", lines)
        self.assertIn("cache_store_log none", lines)
        self.assertIn("access_log stdio:/dev/stdout squid", lines)
        self.assertIn("cache_log stdio:/dev/stderr", lines)
        # Logs go to container streams; nothing is written under /var.
        self.assertNotIn("/var/", lines)
        # The proxy never reveals client or proxy identity to the origin.
        self.assertIn("forwarded_for delete", lines)
        self.assertIn("via off", lines)

    def test_proxy_is_referenced_once_from_cluster_kustomization(self) -> None:
        root = (REPO_ROOT / "clusters/home-server/kustomization.yaml").read_text()
        self.assertEqual(root.count("../../apps/maintainerr-tmdb-proxy"), 1)

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
        # Line-anchored: the proxy entry shares the "maintainerr" name prefix.
        self.assertEqual(root.count("../../apps/maintainerr\n"), 1)
        self.assertIn("../../apps/maintainerr\n", root)

    def test_manifests_contain_no_placeholders_or_plaintext_secrets(self) -> None:
        for manifest in [
            "apps/maintainerr/access-proxy.yaml",
            "apps/maintainerr/deployment.yaml",
            "apps/maintainerr/kustomization.yaml",
            "apps/maintainerr/maintainerr.catalog.yaml",
            "apps/maintainerr/networkpolicy.yaml",
            "apps/maintainerr/pvc.yaml",
            "apps/maintainerr/route.yaml",
            "apps/maintainerr/service.yaml",
            "apps/maintainerr-tmdb-proxy/deployment.yaml",
            "apps/maintainerr-tmdb-proxy/kustomization.yaml",
            "apps/maintainerr-tmdb-proxy/networkpolicy.yaml",
            "apps/maintainerr-tmdb-proxy/service.yaml",
            "apps/maintainerr-tmdb-proxy/squid.conf",
        ]:
            contents = (REPO_ROOT / manifest).read_text()
            self.assertNotIn("TODO", contents, manifest)
            self.assertNotIn("REPLACE", contents, manifest)
            self.assertNotIn("PASSWORD", contents, manifest)
            self.assertNotIn("SECRET", contents, manifest)


if __name__ == "__main__":
    unittest.main()
