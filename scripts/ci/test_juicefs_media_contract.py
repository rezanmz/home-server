#!/usr/bin/env python3
"""Regression tests for the JuiceFS library/local-downloads boundary."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def documents(relative_path: str) -> list[dict]:
    with (REPO_ROOT / relative_path).open() as stream:
        return [doc for doc in yaml.safe_load_all(stream) if isinstance(doc, dict)]


def deployment(relative_path: str, name: str) -> dict:
    for doc in documents(relative_path):
        if doc.get("kind") == "Deployment" and doc.get("metadata", {}).get("name") == name:
            return doc
    raise AssertionError(f"Deployment {name!r} not found in {relative_path}")


def pod_spec(resource: dict) -> dict:
    return resource["spec"]["template"]["spec"]


def named(items: list[dict], name: str) -> dict:
    for item in items:
        if item.get("name") == name:
            return item
    raise AssertionError(f"item {name!r} not found")


class JuiceFSMediaStorageContractTests(unittest.TestCase):
    def test_migration_can_safely_reset_stale_checkpoints(self) -> None:
        script = (REPO_ROOT / "scripts/run-juicefs-media-migration.sh").read_text()
        self.assertIn("--reset-checkpoint", script)
        self.assertIn("sync_args+=(--checkpoint-force-reset)", script)
        self.assertIn("--check-change", script)
        self.assertIn("--max-failure=0", script)

    def test_encrypted_direct_sync_cannot_checksum_remote_payloads(self) -> None:
        script = (REPO_ROOT / "scripts/run-juicefs-media-migration.sh").read_text()
        self.assertNotIn("--check-new", script)
        self.assertNotIn("--check-all", script)
        self.assertIn("JUICEFS_MIGRATION_MAX_INGRESS_BASE_BYTES", script)
        self.assertIn("IPIngressBytes", script)
        self.assertIn("IPAccounting", script)
        self.assertIn("juicefs_sync_copied_bytes", script)
        self.assertIn("kill -TERM", script)

    def test_download_stack_keeps_torrents_outside_juicefs(self) -> None:
        spec = pod_spec(deployment("apps/downloads/deployment.yaml", "downloads"))
        volumes = {item["name"]: item for item in spec["volumes"]}
        self.assertEqual(
            volumes["media-library"]["persistentVolumeClaim"]["claimName"],
            "media-library-juicefs",
        )
        self.assertEqual(
            volumes["media-downloads"]["persistentVolumeClaim"]["claimName"],
            "media-downloads",
        )

        containers = {item["name"]: item for item in spec["containers"]}
        qb_mounts = {item["name"]: item for item in containers["qbittorrent"]["volumeMounts"]}
        self.assertEqual(qb_mounts["media-library"]["mountPath"], "/media")
        self.assertTrue(qb_mounts["media-library"]["readOnly"])
        self.assertEqual(qb_mounts["media-library"]["mountPropagation"], "HostToContainer")
        self.assertEqual(qb_mounts["media-downloads"]["mountPath"], "/media/downloads")
        self.assertFalse(qb_mounts["media-downloads"].get("readOnly", False))

        for importer_name in ("radarr", "sonarr", "lidarr"):
            mounts = {
                item["name"]: item
                for item in containers[importer_name]["volumeMounts"]
            }
            self.assertFalse(mounts["media-library"].get("readOnly", False))
            self.assertEqual(mounts["media-library"]["mountPath"], "/media")
            self.assertEqual(mounts["media-library"]["mountPropagation"], "HostToContainer")
            self.assertEqual(mounts["media-downloads"]["mountPath"], "/media/downloads")

        for downloader_name in ("slskd", "soularr", "shelfmark"):
            mount_names = {
                item["name"] for item in containers[downloader_name]["volumeMounts"]
            }
            self.assertIn("media-downloads", mount_names)
            self.assertNotIn("media-library", mount_names)

    def test_pi_nfs_claims_export_only_the_downloads_subdirectory(self) -> None:
        for relative_path, pv_name in (
            ("infrastructure/nfs-media/media.yaml", "media-downloads-media"),
            ("infrastructure/nfs-media/apps.yaml", "media-downloads-apps"),
        ):
            resources = documents(relative_path)
            pv = next(
                doc
                for doc in resources
                if doc.get("kind") == "PersistentVolume"
                and doc.get("metadata", {}).get("name") == pv_name
            )
            self.assertEqual(pv["spec"]["nfs"]["path"], "/home/reza/media/downloads")

    def test_read_only_consumers_cannot_write_the_cloud_library(self) -> None:
        consumers = (
            ("apps/jellyfin/deployment.yaml", "jellyfin", "jellyfin", "media"),
            ("apps/navidrome/deployment.yaml", "navidrome", "navidrome", "music"),
            ("apps/homepage/deployment.yaml", "homepage", "homepage", "media"),
            (
                "infrastructure/observability/media-storage-exporter.yaml",
                "media-storage-exporter",
                "exporter",
                "media",
            ),
        )
        for relative_path, deployment_name, container_name, volume_name in consumers:
            spec = pod_spec(deployment(relative_path, deployment_name))
            volume = named(spec["volumes"], volume_name)
            self.assertEqual(
                volume["persistentVolumeClaim"]["claimName"],
                "media-library-juicefs",
            )
            mount = named(named(spec["containers"], container_name)["volumeMounts"], volume_name)
            self.assertTrue(mount["readOnly"])
            self.assertEqual(mount["mountPropagation"], "HostToContainer")

    def test_exporter_inventory_excludes_local_downloads_from_cloud_categories(self) -> None:
        config = next(
            doc
            for doc in documents("infrastructure/observability/media-storage-exporter.yaml")
            if doc.get("kind") == "ConfigMap"
        )["data"]["collect.sh"]
        self.assertIn(
            'readonly CATEGORIES="movies tv music books audiobooks podcasts"',
            config,
        )
        self.assertNotIn('CATEGORIES="movies tv downloads', config)
        self.assertIn('readonly DOWNLOADS_ROOT="${DOWNLOADS_ROOT:-/downloads}"', config)

    def test_dashboard_covers_cloud_cache_download_and_cost_layers(self) -> None:
        config_map = next(
            doc
            for doc in documents("infrastructure/observability/media-storage-dashboard.yaml")
            if doc.get("kind") == "ConfigMap"
        )
        dashboard = json.loads(config_map["data"]["media-storage.json"])
        panels = {panel["title"]: panel for panel in dashboard["panels"]}
        required_titles = {
            "Cloud library data",
            "Downloads footprint",
            "JuiceFS cache by mount pod",
            "JuiceFS cache hit ratio",
            "Cache eviction rate",
            "B2 client traffic",
            "B2 request latency p95",
            "JuiceFS service health",
            "Estimated media storage / month",
            "Rolling 30-day B2 reads",
            "Estimated 30-day egress overage",
        }
        self.assertTrue(required_titles.issubset(panels))
        traffic_expr = panels["B2 client traffic"]["targets"][0]["expr"]
        self.assertIn("sum by (pod, method)", traffic_expr)
        self.assertIn('vol_name="media"', traffic_expr)

    def test_juicefs_alerts_are_scoped_to_the_media_volume(self) -> None:
        rule = next(
            doc
            for doc in documents("infrastructure/juicefs/monitoring.yaml")
            if doc.get("kind") == "PrometheusRule"
        )
        rules = {
            item["alert"]: item["expr"]
            for group in rule["spec"]["groups"]
            for item in group["rules"]
        }
        for alert_name in (
            "JuiceFSObjectStoreErrors",
            "JuiceFSMetadataBackupStale",
            "JuiceFSCapacity75Percent",
            "JuiceFSCapacity85Percent",
            "JuiceFSCapacity95Percent",
            "JuiceFSUnexpectedWritebackStaging",
            "JuiceFSAbnormalB2ReadGrowth",
        ):
            self.assertIn('vol_name="media"', rules[alert_name])
        self.assertIn("absent(", rules["JuiceFSMetadataBackupStale"])


if __name__ == "__main__":
    unittest.main()
