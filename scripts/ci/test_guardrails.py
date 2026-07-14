#!/usr/bin/env python3
"""Regression tests for security-sensitive CI detection logic."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

from yaml_documents import github_error, iter_kubernetes_objects


def load_script(module_name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy = load_script("high_risk_policy", "check-high-risk-policy.py")
schema = load_script("prepare_schema_manifest", "prepare-schema-manifest.py")
secrets = load_script("validate_secrets", "validate-secrets.py")


def encrypted_secret() -> dict:
    encrypted = (
        "ENC[AES256_GCM,data:dmFsdWU=,"
        "iv:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=,"
        "tag:AAAAAAAAAAAAAAAAAAAAAA==,type:str]"
    )
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "fixture"},
        "data": {"password": encrypted, "optional": None},
        "sops": {
            "age": [
                {
                    "recipient": "age1" + ("q" * 58),
                    "enc": (
                        "-----BEGIN AGE ENCRYPTED FILE-----\n"
                        "YWdlLWVuY3J5cHRpb24ub3JnL3YxCmZpeHR1cmU=\n"
                        "-----END AGE ENCRYPTED FILE-----\n"
                    ),
                }
            ],
            "encrypted_regex": "^(data|stringData)$",
            "mac": encrypted,
        },
    }


class SecretValidationTests(unittest.TestCase):
    def test_tracked_non_utf8_filename_uses_filesystem_surrogate_decoding(self) -> None:
        completed = mock.Mock(stdout=b"normal.yaml\0invalid-\xff.yaml\0")
        with (
            mock.patch.object(secrets.subprocess, "run", return_value=completed) as run,
            mock.patch.object(Path, "exists", return_value=True),
        ):
            paths = secrets.tracked_files()
        self.assertIn(b"invalid-\xff.yaml", {os.fsencode(path) for path in paths})
        run.assert_called_once_with(
            [
                "git",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            check=True,
            stdout=secrets.subprocess.PIPE,
        )

    def test_tracked_files_skip_deleted_worktree_paths(self) -> None:
        completed = mock.Mock(stdout=b"present.yaml\0deleted.yaml\0")
        with (
            mock.patch.object(secrets.subprocess, "run", return_value=completed),
            mock.patch.object(
                Path,
                "exists",
                autospec=True,
                side_effect=lambda path: path.name == "present.yaml",
            ),
        ):
            self.assertEqual(secrets.tracked_files(), [Path("present.yaml")])

    def test_github_annotation_safely_prints_surrogates_and_delimiters(self) -> None:
        output = io.StringIO()
        path = Path("invalid-\udcff,colon:name%line\n.yaml")
        with contextlib.redirect_stdout(output):
            github_error("bad\r\nmessage", path=path)
        annotation = output.getvalue()
        self.assertEqual(annotation.count("\n"), 1)
        self.assertIn(r"invalid-\udcff%2Ccolon%3Aname%25line%0A.yaml", annotation)
        self.assertIn("bad%0D%0Amessage", annotation)

    def test_valid_encrypted_secret_passes(self) -> None:
        self.assertEqual(secrets.validate_secret(encrypted_secret(), Path("fixture.sops.yaml")), [])

    def test_plaintext_secret_is_found_without_filename_convention(self) -> None:
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "plaintext"},
            "stringData": {"password": "not-encrypted"},
        }
        errors = secrets.validate_secret(secret, Path("secrets/no-extension"))
        self.assertTrue(any("plaintext" in error for error in errors))
        self.assertTrue(any("SOPS metadata" in error for error in errors))

    def test_rendered_plaintext_secret_fails_without_filename_requirement(self) -> None:
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "generated-plaintext"},
            "data": {"password": "cGxhaW50ZXh0"},
        }
        errors = secrets.validate_secret(
            secret, Path("rendered-bundle.yaml"), require_sops_filename=False
        )
        self.assertTrue(any("plaintext" in error for error in errors))
        self.assertFalse(any("filename" in error for error in errors))

    def test_obvious_fake_sops_wrapper_and_age_metadata_fail(self) -> None:
        secret = encrypted_secret()
        secret["data"]["password"] = "ENC[AES256_GCM,data:literal-password]"
        secret["sops"]["age"] = [{"recipient": "x", "enc": "y"}]
        errors = secrets.validate_secret(secret, Path("fixture.sops.yaml"))
        self.assertTrue(any("plaintext or malformed" in error for error in errors))
        self.assertTrue(any("recipient" in error for error in errors))
        self.assertTrue(any("armor" in error for error in errors))

    def test_list_resources_are_expanded(self) -> None:
        resources = list(
            iter_kubernetes_objects(
                {"apiVersion": "v1", "kind": "List", "items": [encrypted_secret()]}
            )
        )
        self.assertEqual([resource["kind"] for resource in resources], ["List", "Secret"])

    def test_schema_sanitization_removes_sops_and_ciphertext(self) -> None:
        secret = encrypted_secret()
        schema.sanitize_secret(secret)
        self.assertNotIn("sops", secret)
        self.assertEqual(secret["data"]["password"], "c2NoZW1hLXBsYWNlaG9sZGVy")


class HighRiskPolicyTests(unittest.TestCase):
    def test_name_hashed_access_proxy_configmap_is_a_boundary(self) -> None:
        resource = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "pihole-access-proxy-abc123", "namespace": "test"},
            "data": {"nginx.conf": "deny all;"},
        }
        findings = policy.resource_findings(resource)
        self.assertTrue(any(item.startswith("access-proxy-boundary|") for item in findings))

    def test_traefik_backend_transport_and_service_are_hashed_boundaries(self) -> None:
        for kind in ("ServersTransport", "TraefikService"):
            resource = {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": kind,
                "metadata": {"name": "backend", "namespace": "test"},
                "spec": {"serverName": "backend.test.svc"},
            }
            findings = policy.resource_findings(resource)
            self.assertTrue(
                any(item.startswith("traefik-backend-boundary|") for item in findings)
            )

    def test_privileged_latest_image_and_host_path_are_detected(self) -> None:
        workload = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "unsafe", "namespace": "test"},
            "spec": {
                "template": {
                    "spec": {
                        "shareProcessNamespace": True,
                        "securityContext": {
                            "runAsUser": 0,
                            "seccompProfile": {"type": "Unconfined"},
                            "sysctls": [{"name": "kernel.example", "value": "1"}],
                        },
                        "containers": [
                            {
                                "name": "unsafe",
                                "image": "example.invalid/unsafe:latest",
                                "securityContext": {
                                    "privileged": True,
                                    "capabilities": {"add": ["ALL"]},
                                },
                            }
                        ],
                        "volumes": [{"name": "host", "hostPath": {"path": "/"}}],
                    }
                }
            },
        }
        rules = {item.split("|", 1)[0] for item in policy.detect([workload])}
        self.assertTrue(
            {
                "host-path",
                "added-capability",
                "explicit-root-user",
                "mutable-image-tag",
                "pod-sysctl",
                "privileged-container",
                "service-account-token-mounted",
                "shared-process-namespace",
                "unconfined-seccomp",
                "unpinned-image",
            }.issubset(rules)
        )

    def test_digest_pinned_unprivileged_workload_has_no_findings(self) -> None:
        workload = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "safe", "namespace": "test"},
            "spec": {
                "template": {
                    "spec": {
                        "automountServiceAccountToken": False,
                        "containers": [
                            {
                                "name": "safe",
                                "image": "example.invalid/safe@sha256:" + ("a" * 64),
                            }
                        ],
                    }
                }
            },
        }
        self.assertEqual(policy.detect([workload]), set())

    def test_unpinned_image_value_is_part_of_baseline_finding(self) -> None:
        workload = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "image-lock", "namespace": "test"},
            "spec": {
                "template": {
                    "spec": {
                        "automountServiceAccountToken": False,
                        "containers": [{"name": "app", "image": "example.invalid/app:1.0"}],
                    }
                }
            },
        }
        before = policy.detect([workload])
        workload["spec"]["template"]["spec"]["containers"][0]["image"] = (
            "evil.invalid/payload:1.0"
        )
        after = policy.detect([workload])
        self.assertNotEqual(before, after)
        self.assertTrue(any("evil.invalid/payload:1.0" in item for item in after))

    def test_images_passed_in_arguments_must_be_digest_pinned(self) -> None:
        workload = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "dynamic-image", "namespace": "test"},
            "spec": {
                "template": {
                    "spec": {
                        "automountServiceAccountToken": False,
                        "containers": [
                            {
                                "name": "controller",
                                "image": "example.invalid/controller@sha256:" + ("a" * 64),
                                "args": [
                                    "--solver-image=example.invalid/solver:latest",
                                    "--helper-image",
                                    "example.invalid/helper:1.2.3@sha256:" + ("b" * 64),
                                ],
                            }
                        ],
                    }
                }
            },
        }
        findings = policy.detect([workload])
        rules = {item.split("|", 1)[0] for item in findings}
        self.assertIn("unpinned-image-argument", rules)
        self.assertIn("mutable-image-argument", rules)
        self.assertFalse(any("helper" in item and "unpinned" in item for item in findings))

    def test_images_passed_in_environment_must_be_digest_pinned(self) -> None:
        workload = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "image-env", "namespace": "test"},
            "spec": {
                "template": {
                    "spec": {
                        "automountServiceAccountToken": False,
                        "containers": [
                            {
                                "name": "controller",
                                "image": "example.invalid/controller@sha256:" + ("a" * 64),
                                "env": [
                                    {
                                        "name": "CSI_ATTACHER_IMAGE",
                                        "value": "example.invalid/attacher:latest",
                                    },
                                    {
                                        "name": "HELPER_IMAGE",
                                        "value": "example.invalid/helper:1.2.3@sha256:"
                                        + ("b" * 64),
                                    },
                                    {
                                        "name": "SECRET_IMAGE",
                                        "valueFrom": {
                                            "secretKeyRef": {"name": "images", "key": "worker"}
                                        },
                                    },
                                ],
                            }
                        ],
                    }
                }
            },
        }
        findings = policy.detect([workload])
        rules = {item.split("|", 1)[0] for item in findings}
        self.assertIn("unpinned-image-environment", rules)
        self.assertIn("mutable-image-environment", rules)
        self.assertIn("indirect-image-environment", rules)
        self.assertFalse(any("HELPER_IMAGE" in item for item in findings))

    def test_development_suffix_is_mutable(self) -> None:
        self.assertTrue(policy.mutable_tag("example.invalid/app:1.2.3-develop"))
        self.assertFalse(policy.mutable_tag("example.invalid/app:1.2.3"))

    def test_secret_reading_rbac_is_detected(self) -> None:
        role = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {"name": "secret-reader", "namespace": "test"},
            "rules": [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get"]}],
        }
        rules = {item.split("|", 1)[0] for item in policy.detect([role])}
        self.assertIn("rbac-secret-or-token-access", rules)

    def test_git_tag_and_helm_range_are_mutable(self) -> None:
        git_source = {
            "apiVersion": "source.toolkit.fluxcd.io/v1",
            "kind": "GitRepository",
            "metadata": {"name": "source", "namespace": "flux-system"},
            "spec": {
                "url": "https://example.invalid/repository.git",
                "ref": {"tag": "v1.2.3"},
                "verify": {"mode": "HEAD"},
            },
        }
        helm_release = {
            "apiVersion": "helm.toolkit.fluxcd.io/v2",
            "kind": "HelmRelease",
            "metadata": {"name": "chart", "namespace": "test"},
            "spec": {"chart": {"spec": {"version": "1.2.3 - 2.0.0"}}},
        }
        rules = {item.split("|", 1)[0] for item in policy.detect([git_source, helm_release])}
        self.assertIn("mutable-git-ref", rules)
        self.assertIn("mutable-helm-chart", rules)

    def test_helm_chart_ref_does_not_require_an_inline_chart_version(self) -> None:
        release = {
            "apiVersion": "helm.toolkit.fluxcd.io/v2",
            "kind": "HelmRelease",
            "metadata": {"name": "chart", "namespace": "test"},
            "spec": {
                "chartRef": {
                    "apiVersion": "source.toolkit.fluxcd.io/v1",
                    "kind": "OCIRepository",
                    "name": "chart",
                    "namespace": "flux-system",
                }
            },
        }
        rules = {item.split("|", 1)[0] for item in policy.detect([release])}
        self.assertNotIn("mutable-helm-chart", rules)

    def test_git_chart_path_does_not_require_ignored_helm_version(self) -> None:
        release = {
            "apiVersion": "helm.toolkit.fluxcd.io/v2",
            "kind": "HelmRelease",
            "metadata": {"name": "chart", "namespace": "test"},
            "spec": {
                "chart": {
                    "spec": {
                        "chart": "./chart",
                        "sourceRef": {
                            "kind": "GitRepository",
                            "name": "immutable-source",
                        },
                    }
                }
            },
        }
        rules = {item.split("|", 1)[0] for item in policy.detect([release])}
        self.assertNotIn("mutable-helm-chart", rules)

    def test_helm_release_without_chart_or_chart_ref_is_detected(self) -> None:
        release = {
            "apiVersion": "helm.toolkit.fluxcd.io/v2",
            "kind": "HelmRelease",
            "metadata": {"name": "chart", "namespace": "test"},
            "spec": {},
        }
        rules = {item.split("|", 1)[0] for item in policy.detect([release])}
        self.assertIn("mutable-helm-chart", rules)

    def test_helm_post_renderer_and_exposed_service_are_detected(self) -> None:
        release = {
            "apiVersion": "helm.toolkit.fluxcd.io/v2",
            "kind": "HelmRelease",
            "metadata": {"name": "chart", "namespace": "test"},
            "spec": {
                "chart": {"spec": {"version": "1.2.3"}},
                "postRenderers": [{"kustomize": {"patches": [{"patch": "unsafe"}]}}],
                "values": {"service": {"type": "LoadBalancer"}},
            },
        }
        rules = {item.split("|", 1)[0] for item in policy.detect([release])}
        self.assertIn("helm-post-renderer", rules)
        self.assertIn("helm-externally-exposed-service", rules)

    def test_universal_egress_peers_are_detected(self) -> None:
        policy_document = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": "egress", "namespace": "test"},
            "spec": {
                "podSelector": {},
                "policyTypes": ["Egress"],
                "egress": [
                    {"to": [{}]},
                    {"to": [{"namespaceSelector": {}}]},
                    {"to": [{"ipBlock": {"cidr": "0.0.0.0/0"}}]},
                ],
            },
        }
        rules = {item.split("|", 1)[0] for item in policy.detect([policy_document])}
        self.assertIn("universal-egress-destination", rules)
        self.assertIn("cluster-wide-egress-destination", rules)
        self.assertIn("internet-wide-egress-destination", rules)

    def test_traefik_pod_cidr_allowlist_is_detected(self) -> None:
        middleware = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "Middleware",
            "metadata": {"name": "internal", "namespace": "test"},
            "spec": {
                "ipAllowList": {
                    "sourceRange": ["192.168.1.0/24", "10.42.1.0/24"]
                }
            },
        }
        findings = policy.detect([middleware])
        self.assertTrue(any(item.startswith("pod-cidr-ip-allowlist|") for item in findings))
        self.assertTrue(any(item.endswith("/10.42.1.0/24") for item in findings))

    def test_route_and_middleware_changes_alter_exact_boundaries(self) -> None:
        route = {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "HTTPRoute",
            "metadata": {"name": "admin", "namespace": "test"},
            "spec": {
                "hostnames": ["admin.example.invalid"],
                "rules": [
                    {
                        "filters": [
                            {
                                "type": "ExtensionRef",
                                "extensionRef": {
                                    "group": "traefik.io",
                                    "kind": "Middleware",
                                    "name": "lan-only",
                                },
                            }
                        ],
                        "backendRefs": [{"name": "admin", "port": 8080}],
                    }
                ],
            },
        }
        middleware = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "Middleware",
            "metadata": {"name": "lan-only", "namespace": "test"},
            "spec": {"ipAllowList": {"sourceRange": ["192.168.1.0/24"]}},
        }
        before = policy.detect([route, middleware])
        route["spec"]["rules"][0]["filters"] = []
        middleware["spec"]["ipAllowList"]["sourceRange"] = ["0.0.0.0/0"]
        after = policy.detect([route, middleware])
        self.assertNotEqual(before, after)
        self.assertTrue(any(item.startswith("route-boundary|") for item in after))
        self.assertTrue(any(item.startswith("middleware-boundary|") for item in after))

    def test_all_supported_route_kinds_have_exact_boundaries(self) -> None:
        route_kinds = {
            "Gateway": "gateway.networking.k8s.io/v1",
            "HTTPRoute": "gateway.networking.k8s.io/v1",
            "GRPCRoute": "gateway.networking.k8s.io/v1",
            "TCPRoute": "gateway.networking.k8s.io/v1alpha2",
            "TLSRoute": "gateway.networking.k8s.io/v1alpha2",
            "UDPRoute": "gateway.networking.k8s.io/v1alpha2",
            "Ingress": "networking.k8s.io/v1",
            "IngressRoute": "traefik.io/v1alpha1",
            "IngressRouteTCP": "traefik.io/v1alpha1",
            "IngressRouteUDP": "traefik.io/v1alpha1",
        }
        for kind, api_version in route_kinds.items():
            with self.subTest(kind=kind):
                route = {
                    "apiVersion": api_version,
                    "kind": kind,
                    "metadata": {"name": kind.lower(), "namespace": "test"},
                    "spec": {"fixture": "reviewed-boundary"},
                }
                findings = policy.detect([route])
                self.assertTrue(
                    any(item.startswith("route-boundary|") for item in findings)
                )

    def test_universal_ingress_and_missing_default_deny_are_detected(self) -> None:
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "apps"},
        }
        ingress = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": "unsafe", "namespace": "apps"},
            "spec": {
                "podSelector": {},
                "policyTypes": ["Ingress"],
                "ingress": [{"from": [{}]}],
            },
        }
        rules = {item.split("|", 1)[0] for item in policy.detect([namespace, ingress])}
        self.assertIn("universal-ingress-source", rules)
        self.assertIn("network-policy-ingress-boundary", rules)
        self.assertIn("missing-default-deny", rules)

    def test_exact_helm_release_change_alters_boundary(self) -> None:
        release = {
            "apiVersion": "helm.toolkit.fluxcd.io/v2",
            "kind": "HelmRelease",
            "metadata": {"name": "chart", "namespace": "test"},
            "spec": {
                "chart": {
                    "spec": {
                        "chart": "example",
                        "version": "1.2.3",
                        "sourceRef": {"kind": "HelmRepository", "name": "example"},
                    }
                }
            },
        }
        before = policy.detect([release])
        release["spec"]["chart"]["spec"]["version"] = "9.9.9"
        after = policy.detect([release])
        self.assertNotEqual(before, after)
        self.assertTrue(any(item.startswith("helm-release-boundary|") for item in after))


if __name__ == "__main__":
    unittest.main()
