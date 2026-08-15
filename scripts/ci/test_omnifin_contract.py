#!/usr/bin/env python3
"""Regression tests for Omnifin's web/gateway trust and storage boundaries."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE = (
    "ghcr.io/rezanmz/omnifin@"
    "sha256:0bb736ae7ce6ae6b0fa9c3b823a96a044824a523b7bd96518f462f79ea5eeda8"
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
        self.assertNotIn("fsGroup", pod["securityContext"])
        self.assertNotIn("fsGroupChangePolicy", pod["securityContext"])

        prepare = named(pod["initContainers"], "prepare-data-directory")
        self.assertFalse(prepare["securityContext"]["runAsNonRoot"])
        self.assertEqual(prepare["securityContext"]["runAsUser"], 0)
        self.assertEqual(
            prepare["securityContext"]["capabilities"]["add"],
            ["CHOWN", "FOWNER", "DAC_OVERRIDE"],
        )
        self.assert_strict_sqlite_repair(prepare)

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
            environment["OMNIFIN_GATEWAY_HEALTH_URL"]["value"],
            "http://127.0.0.1:4000/healthz",
        )
        self.assertEqual(
            environment["OMNIFIN_GATEWAY_READY_URL"]["value"],
            "http://127.0.0.1:4000/readyz",
        )
        self.assertEqual(environment["OMNIFIN_IMAGE_REF"]["value"], IMAGE)
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
        self.assertEqual(volumes["encryption-key"]["secret"]["defaultMode"], 0o444)
        self.assertEqual(volumes["recovery-secret"]["secret"]["defaultMode"], 0o444)
        gateway_mounts = {item["name"] for item in gateway["volumeMounts"]}
        self.assertEqual(
            gateway_mounts,
            {"data", "tmp", "encryption-key", "recovery-secret"},
        )

    def test_web_is_stateless_and_only_proxies_to_private_gateway(self) -> None:
        deployment = resource(
            "apps/omnifin/deployment.yaml", "Deployment", "omnifin-web"
        )
        pod = deployment["spec"]["template"]["spec"]
        self.assertNotIn("nodeSelector", pod)
        self.assertEqual(pod["securityContext"]["fsGroup"], 65532)
        self.assertEqual(
            pod["securityContext"]["fsGroupChangePolicy"], "OnRootMismatch"
        )
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
        self.assertNotIn("encryption-key", volume_names)
        self.assertNotIn("recovery-secret", volume_names)

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

    def test_daily_maintenance_is_local_and_hardened(self) -> None:
        cronjob = resource(
            "apps/omnifin/maintenance.yaml", "CronJob", "omnifin-maintenance"
        )
        spec = cronjob["spec"]
        self.assertEqual(spec["schedule"], "17 3 * * *")
        self.assertEqual(spec["concurrencyPolicy"], "Forbid")

        job = spec["jobTemplate"]["spec"]
        self.assertLessEqual(job["activeDeadlineSeconds"], 1800)
        pod = job["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["securityContext"]["runAsUser"], 65532)
        self.assertEqual(pod["securityContext"]["runAsGroup"], 65532)
        self.assertNotIn("fsGroup", pod["securityContext"])
        self.assertNotIn("fsGroupChangePolicy", pod["securityContext"])
        # The required same-node gateway affinity supplies the ownership and
        # privacy guarantees; maintenance must not remount or repair the PVC.
        self.assertNotIn("initContainers", pod)
        affinity = pod["affinity"]["podAffinity"][
            "requiredDuringSchedulingIgnoredDuringExecution"
        ]
        self.assertEqual(len(affinity), 1)
        self.assertEqual(
            affinity[0]["labelSelector"]["matchLabels"],
            {
                "app.kubernetes.io/name": "omnifin",
                "app.kubernetes.io/component": "gateway",
            },
        )
        self.assertEqual(affinity[0]["namespaces"], ["apps"])
        self.assertEqual(affinity[0]["topologyKey"], "kubernetes.io/hostname")

        maintenance = named(pod["containers"], "maintenance")
        self.assertEqual(maintenance["image"], IMAGE)
        self.assertEqual(
            maintenance["command"],
            ["/nodejs/bin/node", "/opt/omnifin/bin/entrypoint.mjs", "maintenance"],
        )
        self.assertEqual(
            maintenance["args"], ["backup-retained", "--retain", "14"]
        )
        self.assertTrue(maintenance["securityContext"]["runAsNonRoot"])
        self.assertTrue(maintenance["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(maintenance["securityContext"]["capabilities"]["drop"], ["ALL"])
        environment = {item["name"]: item["value"] for item in maintenance["env"]}
        self.assertEqual(
            environment,
            {
                "OMNIFIN_BASE_URL": "https://omnifin.reza.network",
                "OMNIFIN_DATABASE_URL": "/data/omnifin.db",
                "OMNIFIN_BACKUP_DIRECTORY": "/data/backups",
                "OMNIFIN_IMAGE_REF": IMAGE,
            },
        )
        volume_names = {item["name"] for item in pod["volumes"]}
        self.assertEqual(volume_names, {"data", "tmp"})
        self.assertEqual(
            next(item for item in pod["volumes"] if item["name"] == "data")[
                "persistentVolumeClaim"
            ]["claimName"],
            "omnifin-data",
        )
        mounts = {item["name"]: item for item in maintenance["volumeMounts"]}
        self.assertEqual(mounts["data"]["mountPath"], "/data")
        self.assertEqual(mounts["tmp"]["mountPath"], "/tmp")
        self.assertEqual(set(mounts), {"data", "tmp"})
        self.assertNotIn("OMNIFIN_ENCRYPTION_KEY_FILE", environment)
        self.assertNotIn("recovery-secret", volume_names)

        policy = resource(
            "apps/omnifin/networkpolicy.yaml", "NetworkPolicy", "omnifin-maintenance"
        )
        self.assertEqual(
            policy["spec"]["podSelector"]["matchLabels"][
                "app.kubernetes.io/component"
            ],
            "maintenance",
        )
        self.assertEqual(policy["spec"]["policyTypes"], ["Egress"])
        self.assertEqual(policy["spec"]["egress"], [])

    def assert_strict_sqlite_repair(self, init_container: dict) -> None:
        command = " ".join(init_container["command"])
        data_guard = command.index("if [ -L /data ] || [ ! -d /data ]; then")
        backups_symlink_guard = command.index(
            "if [ -L /data/backups ]; then"
        )
        backups_type_guard = command.index(
            "if [ -e /data/backups ] && [ ! -d /data/backups ]; then"
        )
        database_validation = command.index(
            "for database_file in /data/omnifin.db /data/omnifin.db-wal /data/omnifin.db-shm"
        )
        self.assertEqual(
            command.count(
                "for database_file in /data/omnifin.db /data/omnifin.db-wal /data/omnifin.db-shm"
            ),
            2,
        )
        mkdir = command.index("mkdir /data/backups")
        backup_chown = command.index("chown 65532:65532 /data/backups")
        backup_chmod = command.index("chmod 0700 /data/backups")
        database_loop = command.rindex(
            "for database_file in /data/omnifin.db /data/omnifin.db-wal /data/omnifin.db-shm"
        )
        database_chown = command.index('chown 65532:65532 "$database_file"')
        database_chmod = command.index('chmod 0600 "$database_file"')
        data_chown = command.index("chown 65532:65532 /data\n")
        data_chmod = command.index("chmod 0700 /data\n")
        self.assertIn("if [ ! -e /data/backups ]; then", command)
        self.assertIn('if [ -L "$database_file" ]; then', command)
        self.assertIn(
            'if [ -e "$database_file" ] && [ ! -f "$database_file" ]; then',
            command,
        )
        self.assertIn('if [ -f "$database_file" ]; then', command)
        self.assertNotIn("mkdir -p", command)
        self.assertNotIn("find ", command)
        self.assertLess(data_guard, mkdir)
        self.assertLess(backups_symlink_guard, mkdir)
        self.assertLess(backups_type_guard, mkdir)
        self.assertLess(database_validation, mkdir)
        self.assertLess(mkdir, backup_chown)
        self.assertLess(backup_chown, backup_chmod)
        self.assertLess(backup_chmod, database_loop)
        self.assertLess(database_loop, database_chown)
        self.assertLess(database_chown, database_chmod)
        self.assertLess(database_chmod, data_chown)
        self.assertLess(data_chown, data_chmod)
        for database_file in ("omnifin.db", "omnifin.db-wal", "omnifin.db-shm"):
            self.assertIn(f"/data/{database_file}", command)
        self.assertIn("if [ -e \"$database_file\" ]", command)
        self.assertNotIn("*", command)


if __name__ == "__main__":
    unittest.main()
