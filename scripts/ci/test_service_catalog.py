#!/usr/bin/env python3
"""Regression tests for the repository service-integration catalog."""

from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import service_catalog  # noqa: E402


class ServiceCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = service_catalog.load_catalog()

    def test_catalog_structure_is_valid(self) -> None:
        errors: list[str] = []
        service_catalog.validate_catalog_structure(self.catalog, errors)
        self.assertEqual(errors, [])

    def test_generated_aggregate_files_are_current(self) -> None:
        errors: list[str] = []
        service_catalog.validate_generated_outputs(self.catalog, errors)
        self.assertEqual(errors, [])

    def test_catalog_is_decentralized_and_versioned(self) -> None:
        self.assertFalse((REPO_ROOT / "catalog" / "services.yaml").exists())
        entries = service_catalog.services(self.catalog)
        self.assertEqual(len(entries), 33)
        sources = [entry["_source"] for entry in entries]
        self.assertEqual(len(sources), len(set(sources)))
        self.assertTrue(all(source.endswith(".catalog.yaml") for source in sources))
        for source in sources:
            text = (REPO_ROOT / source).read_text()
            self.assertIn(
                "apiVersion: catalog.reza.network/v1alpha1",
                text,
            )

    def test_catalog_json_schemas_are_closed_and_valid_json(self) -> None:
        for name in ("cluster.schema.json", "service.schema.json"):
            schema = json.loads((REPO_ROOT / "catalog" / name).read_text())
            self.assertEqual(
                schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
            )
        service_schema = json.loads(
            (REPO_ROOT / "catalog" / "service.schema.json").read_text()
        )
        self.assertFalse(
            service_schema["$defs"]["service"]["additionalProperties"]
        )
        self.assertFalse(
            service_schema["$defs"]["service"]["properties"]["spec"][
                "additionalProperties"
            ]
        )

    def test_authentik_blueprints_are_generated_from_service_descriptors(self) -> None:
        document = service_catalog.load_single_document(
            REPO_ROOT / "apps" / "authentik" / "application-blueprints.yaml"
        )
        data = document["data"]
        self.assertEqual(
            sorted(data),
            [
                "actual-budget.yaml",
                "audiobookshelf.yaml",
                "grafana.yaml",
                "headlamp.yaml",
                "homepage.yaml",
                "open-webui.yaml",
                "stork.yaml",
            ],
        )
        self.assertIn(
            "actual-budget-60d8e2eef4cf4c928ee18cd2",
            data["actual-budget.yaml"],
        )
        self.assertIn(
            '"preferred_username": request.user.email',
            data["actual-budget.yaml"],
        )
        self.assertIn(
            "https://audiobooks.reza.network/auth/openid/mobile-redirect",
            data["audiobookshelf.yaml"],
        )
        self.assertIn("mode: forward_single", data["homepage.yaml"])

    def test_authentik_worker_patch_contains_only_confidential_clients(self) -> None:
        patch = service_catalog.load_single_document(
            REPO_ROOT
            / "apps"
            / "authentik"
            / "generated-oidc-worker-env.yaml"
        )
        env = patch["spec"]["template"]["spec"]["containers"][0]["env"]
        names = [entry["name"] for entry in env]
        self.assertEqual(
            names,
            [
                "AUTHENTIK_OIDC_ACTUAL_BUDGET_CLIENT_SECRET",
                "AUTHENTIK_OIDC_AUDIOBOOKSHELF_CLIENT_SECRET",
                "AUTHENTIK_OIDC_GRAFANA_CLIENT_SECRET",
                "AUTHENTIK_OIDC_HEADLAMP_CLIENT_SECRET",
                "AUTHENTIK_OIDC_OPEN_WEBUI_CLIENT_SECRET",
            ],
        )
        self.assertNotIn("AUTHENTIK_OIDC_STORK_CLIENT_SECRET", names)

    def test_public_oidc_client_requires_verified_pkce(self) -> None:
        stork = next(
            service
            for service in service_catalog.services(self.catalog)
            if service["id"] == "stork"
        )
        client = stork["web"]["auth"]["client"]
        self.assertEqual(client["type"], "public")
        self.assertTrue(client["pkce"]["verified"])
        self.assertNotIn("secret", client)

    def test_authentik_profile_is_version_pinned(self) -> None:
        for service in service_catalog.services(self.catalog):
            auth = service.get("web", {}).get("auth", {})
            if auth.get("mode") == "oidc":
                self.assertEqual(auth["profile"], "authentik-oidc-v1")
            elif auth.get("mode") == "forward-auth":
                self.assertEqual(
                    auth["profile"], "authentik-forward-single-v1"
                )

    def test_homepage_order_survives_decentralized_discovery(self) -> None:
        groups = {
            group: [next(iter(card)) for card in cards]
            for document in service_catalog.homepage_document(self.catalog)
            for group, cards in document.items()
        }
        self.assertEqual(
            groups["Home & Identity"],
            ["Home Assistant", "Authentik", "Actual Budget", "Speedtest Tracker"],
        )
        self.assertEqual(
            groups["AI & Data"],
            ["Open WebUI", "GPT Researcher", "MCPHub", "Argilla"],
        )
        self.assertEqual(
            groups["Operations"],
            ["Grafana", "Headlamp", "ISC Stork", "Syncthing", "WireGuard"],
        )

    def test_unknown_nested_field_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["services"][0]["homepage"]["typo"] = True
        errors: list[str] = []
        service_catalog.validate_catalog_structure(catalog, errors)
        self.assertTrue(
            any("homepage contains unknown field: typo" in error for error in errors)
        )

    def test_cross_host_oidc_redirect_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        service = next(
            item for item in catalog["services"] if item["id"] == "open-webui"
        )
        service["web"]["auth"]["client"]["redirectUris"][0]["url"] = (
            "https://evil.example/callback"
        )
        errors: list[str] = []
        service_catalog.validate_catalog_structure(catalog, errors)
        self.assertTrue(
            any("must be an exact https URL on chat.reza.network" in error for error in errors)
        )

    def test_cross_host_authentik_launch_url_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        service = next(
            item for item in catalog["services"] if item["id"] == "open-webui"
        )
        service["web"]["auth"]["application"]["launchUrl"] = (
            "https://evil.example/"
        )
        errors: list[str] = []
        service_catalog.validate_catalog_structure(catalog, errors)
        self.assertTrue(
            any(
                "application.launchUrl must be an HTTPS URL on chat.reza.network"
                in error
                for error in errors
            )
        )

    def test_generated_identifiers_reject_yaml_syntax(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        service = next(
            item for item in catalog["services"] if item["id"] == "open-webui"
        )
        service["web"]["auth"]["application"]["slug"] = "open-webui\nentries"
        errors: list[str] = []
        service_catalog.validate_catalog_structure(catalog, errors)
        self.assertTrue(
            any("application.slug must be a DNS label" in error for error in errors)
        )

    def test_invalid_catalog_does_not_partially_render(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        before = {
            path: path.read_text()
            for path in service_catalog.generated_outputs(self.catalog)
        }
        catalog["services"][0]["placement"]["mode"] = "undecided"
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(service_catalog.CatalogError):
            service_catalog.render(catalog)
        self.assertIn("placement.mode must be one of", output.getvalue())
        after = {path: path.read_text() for path in before}
        self.assertEqual(before, after)

    def test_explain_separates_generated_and_manual_responsibilities(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            service_catalog.explain(self.catalog, "actual-budget")
        text = output.getvalue()
        self.assertIn("Reachable from: LAN and WireGuard only", text)
        self.assertIn("Generated by the catalog compiler:", text)
        self.assertIn("Authentik application/provider blueprint", text)
        self.assertIn(
            "Validated but still explicitly owned by manifests:", text
        )
        self.assertIn("Relying application's OIDC settings", text)

    def test_homepage_self_omission_is_explicit(self) -> None:
        entries = {
            service["id"]: service
            for service in service_catalog.services(self.catalog)
        }
        self.assertFalse(entries["homepage"]["homepage"]["enabled"])
        rendered_names = {
            next(iter(card))
            for group in service_catalog.homepage_document(self.catalog)
            for cards in group.values()
            for card in cards
        }
        self.assertNotIn("Homepage", rendered_names)

    def test_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(service_catalog.CatalogError):
            service_catalog.repo_path("../outside")

    def validate_rendered_text(
        self, catalog: dict[str, object], rendered: str
    ) -> list[str]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as manifest:
            manifest.write(rendered)
            manifest.flush()
            errors: list[str] = []
            service_catalog.validate_rendered_cluster(
                catalog, Path(manifest.name), errors
            )
        return errors

    def test_private_route_requires_declared_ip_allowlist(self) -> None:
        catalog = {
            "services": [
                {
                    "web": {
                        "hostname": "example.reza.network",
                        "visibility": "private",
                        "accessMiddleware": "lan-only",
                        "auth": {"mode": "native"},
                    }
                }
            ]
        }
        rendered = """
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: {name: example, namespace: apps}
spec:
  hostnames: [example.reza.network]
  rules: [{}]
"""
        errors = self.validate_rendered_text(catalog, rendered)
        self.assertTrue(
            any(
                "does not reference access middleware lan-only" in item
                for item in errors
            )
        )

    def test_public_route_rejects_hidden_ip_allowlist(self) -> None:
        catalog = {
            "services": [
                {
                    "web": {
                        "hostname": "example.reza.network",
                        "visibility": "public",
                        "auth": {"mode": "native"},
                    }
                }
            ]
        }
        rendered = """
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata: {name: lan-only, namespace: apps}
spec:
  ipAllowList:
    sourceRange: [192.168.1.0/24]
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: {name: example, namespace: apps}
spec:
  hostnames: [example.reza.network]
  rules:
    - filters:
        - type: ExtensionRef
          extensionRef:
            group: traefik.io
            kind: Middleware
            name: lan-only
"""
        errors = self.validate_rendered_text(catalog, rendered)
        self.assertTrue(
            any("cataloged public" in item and "lan-only" in item for item in errors)
        )


if __name__ == "__main__":
    unittest.main()
