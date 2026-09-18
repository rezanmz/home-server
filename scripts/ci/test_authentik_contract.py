#!/usr/bin/env python3
"""Regression tests for Authentik's embedded-outpost socket isolation.

The server and worker containers each run the same Rust core. That core binds
`$TMPDIR/authentik.sock`, `TMPDIR` is `/dev/shm` in this image, and
`run_unix()` unlinks the path before binding. If both containers share one
`/dev/shm`, the two cores race for a single socket path: the loser's router
still answers, and whichever bound last owns it.

When the worker's healthcheck-only router owns `/dev/shm/authentik.sock`, the
embedded outpost's `get_outpost` call 404s forever, so every forward-auth host
(Homepage, Actual Horizon, Maintainerr, Navidrome, slskd, Soularr) serves
Authentik's Not-Found page while native-OIDC apps stay healthy.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHENTIK_WORKLOADS = "apps/authentik/workloads.yaml"
SHM_PATH = "/dev/shm"


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


def shm_volumes(pod_spec: dict) -> dict[str, list[str]]:
    """Map each container that mounts /dev/shm to the volume names it mounts."""
    mounted: dict[str, list[str]] = {}
    for container in pod_spec.get("containers", []):
        names = [
            mount.get("name")
            for mount in container.get("volumeMounts", [])
            if mount.get("mountPath") == SHM_PATH
        ]
        if names:
            mounted[container["name"]] = names
    return mounted


class AuthentikContractTests(unittest.TestCase):
    def setUp(self) -> None:
        deployment = resource(AUTHENTIK_WORKLOADS, "Deployment", "authentik")
        self.pod = deployment["spec"]["template"]["spec"]
        self.volumes = {volume["name"]: volume for volume in self.pod["volumes"]}

    def test_containers_do_not_share_one_dev_shm_volume(self) -> None:
        """Both cores bind $TMPDIR/authentik.sock, so /dev/shm must be private."""
        mounted = shm_volumes(self.pod)
        self.assertEqual(
            set(mounted),
            {"server", "worker"},
            "/dev/shm must be mounted into both the server and worker containers",
        )

        server_volumes = mounted["server"]
        worker_volumes = mounted["worker"]
        self.assertEqual(len(server_volumes), 1)
        self.assertEqual(len(worker_volumes), 1)
        self.assertNotEqual(
            server_volumes[0],
            worker_volumes[0],
            "server and worker must not share a /dev/shm volume: their Rust "
            "cores would race for the same authentik.sock",
        )

    def test_each_dev_shm_mount_is_a_bounded_memory_volume(self) -> None:
        mounted = shm_volumes(self.pod)
        for container, names in mounted.items():
            for name in names:
                volume = self.volumes[name]
                self.assertIn(
                    "emptyDir",
                    volume,
                    f"{container} mounts non-emptyDir volume {name} at /dev/shm",
                )
                self.assertEqual(volume["emptyDir"].get("medium"), "Memory")
                self.assertTrue(
                    volume["emptyDir"].get("sizeLimit"),
                    f"{name} must bound its memory-backed size",
                )


if __name__ == "__main__":
    unittest.main()
