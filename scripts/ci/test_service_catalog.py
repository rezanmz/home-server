#!/usr/bin/env python3
"""Regression tests for the repository service-integration catalog."""

from __future__ import annotations

import sys
import tempfile
import unittest
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
