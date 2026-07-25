from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "apps/downloads/storage-guard.sh"
GUARD_TAG = "storage-guard-paused"


def torrent(
    hash_value: str,
    state: str,
    *,
    progress: float = 0.5,
    amount_left: int = 500,
    tags: str = "",
) -> dict[str, object]:
    return {
        "hash": hash_value,
        "state": state,
        "progress": progress,
        "amount_left": amount_left,
        "tags": tags,
    }


class ApiState:
    def __init__(self, torrents: list[dict[str, object]]) -> None:
        self.torrents = torrents
        self.requests: list[tuple[str, dict[str, list[str]]]] = []
        self.allow_start = True

    def apply(self, endpoint: str, form: dict[str, list[str]]) -> None:
        self.requests.append((endpoint, form))
        hashes = set(form.get("hashes", [""])[0].split("|"))
        tag = form.get("tags", [GUARD_TAG])[0]
        for item in self.torrents:
            if item["hash"] not in hashes:
                continue
            current_tags = {
                value.strip()
                for value in str(item.get("tags", "")).split(",")
                if value.strip()
            }
            if endpoint == "addTags":
                current_tags.add(tag)
                item["tags"] = ", ".join(sorted(current_tags))
            elif endpoint == "removeTags":
                current_tags.discard(tag)
                item["tags"] = ", ".join(sorted(current_tags))
            elif endpoint == "stop":
                item["state"] = "stoppedDL"
            elif endpoint == "start" and self.allow_start:
                item["state"] = "downloading"


class MockApiHandler(BaseHTTPRequestHandler):
    state: ApiState

    def log_message(self, *_args: object) -> None:
        return

    def send_json(self, value: object) -> None:
        payload = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/qbt/api/v2/app/version":
            self.send_json("5.2.3")
        elif path == "/qbt/api/v2/torrents/info":
            self.send_json(self.state.torrents)
        else:
            self.send_json({"error": f"unhandled path: {path}"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        endpoint = path.rsplit("/", 1)[-1]
        length = int(self.headers.get("Content-Length", "0"))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        self.state.apply(endpoint, form)
        self.send_response(200)
        self.end_headers()


class StorageGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        if not shutil.which("curl") or not shutil.which("jq"):
            self.skipTest("curl and jq are required")

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.downloads = self.root / "downloads"
        self.downloads.mkdir()
        self.state_path = self.root / "state"
        self.state_path.mkdir()
        self.cleaner_ready = self.root / "import-cleaner-ready"

        self.bin_directory = self.root / "bin"
        self.bin_directory.mkdir()
        stat_command = self.bin_directory / "stat"
        stat_command.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  *%T*) echo nfs ;;\n"
            "  *) echo \"1000 ${FAKE_FREE_BLOCKS} 1\" ;;\n"
            "esac\n"
        )
        stat_command.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    def run_guard(
        self,
        torrents: list[dict[str, object]],
        *,
        free_blocks: int,
        cleaner_ready: bool = False,
        allow_start: bool = True,
    ) -> tuple[subprocess.CompletedProcess[str], ApiState]:
        api_state = ApiState(torrents)
        api_state.allow_start = allow_start
        handler = type("Handler", (MockApiHandler,), {"state": api_state})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        if cleaner_ready:
            self.cleaner_ready.touch()
        elif self.cleaner_ready.exists():
            self.cleaner_ready.unlink()

        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin_directory}:{environment['PATH']}",
                "QBITTORRENT_URL": (
                    f"http://127.0.0.1:{server.server_address[1]}/qbt"
                ),
                "DOWNLOADS_PATH": str(self.downloads),
                "STATE_PATH": str(self.state_path),
                "IMPORT_CLEANER_READY_PATH": str(self.cleaner_ready),
                "MIN_FREE_BYTES": "200",
                "MIN_FREE_PERCENT": "10",
                "RESUME_FREE_BYTES": "400",
                "RESUME_FREE_PERCENT": "20",
                "VERIFY_DELAY_SECONDS": "0",
                "FAKE_FREE_BLOCKS": str(free_blocks),
                "RUN_ONCE": "true",
            }
        )
        result = subprocess.run(
            ["sh", str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )
        return result, api_state

    def test_low_space_tags_and_stops_only_active_incomplete_torrents(self) -> None:
        torrents = [
            torrent("active", "downloading"),
            torrent("stalled", "stalledDL"),
            torrent("manual", "stoppedDL"),
            torrent("error", "error"),
            torrent("complete", "uploading", progress=1, amount_left=0),
        ]
        result, state = self.run_guard(torrents, free_blocks=50)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            state.requests,
            [
                (
                    "addTags",
                    {"hashes": ["active|stalled"], "tags": [GUARD_TAG]},
                ),
                ("stop", {"hashes": ["active|stalled"]}),
            ],
        )
        self.assertEqual(torrents[0]["state"], "stoppedDL")
        self.assertEqual(torrents[2]["tags"], "")

    def test_recovered_space_resumes_only_guard_owned_torrents(self) -> None:
        torrents = [
            torrent("guarded", "stoppedDL", tags=f"other, {GUARD_TAG}"),
            torrent("manual", "stoppedDL"),
            torrent("broken", "error", tags=GUARD_TAG),
        ]
        result, state = self.run_guard(
            torrents,
            free_blocks=500,
            cleaner_ready=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            state.requests,
            [
                ("start", {"hashes": ["guarded"]}),
                (
                    "removeTags",
                    {"hashes": ["guarded"], "tags": [GUARD_TAG]},
                ),
            ],
        )
        self.assertEqual(torrents[0]["state"], "downloading")
        self.assertEqual(torrents[0]["tags"], "other")
        self.assertEqual(torrents[1]["state"], "stoppedDL")
        self.assertEqual(torrents[2]["tags"], GUARD_TAG)

    def test_resume_waits_for_successful_cleaner_storage_check(self) -> None:
        torrents = [torrent("guarded", "stoppedDL", tags=GUARD_TAG)]
        result, state = self.run_guard(torrents, free_blocks=500)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state.requests, [])
        self.assertIn("automatic resume deferred", result.stdout)

    def test_failed_start_keeps_guard_ownership_tag(self) -> None:
        torrents = [torrent("guarded", "stoppedDL", tags=GUARD_TAG)]
        result, state = self.run_guard(
            torrents,
            free_blocks=500,
            cleaner_ready=True,
            allow_start=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state.requests, [("start", {"hashes": ["guarded"]})])
        self.assertEqual(torrents[0]["tags"], GUARD_TAG)
        self.assertIn("ownership tags retained", result.stdout)

    def test_hysteresis_band_leaves_all_states_unchanged(self) -> None:
        torrents = [
            torrent("active", "downloading"),
            torrent("guarded", "stoppedDL", tags=GUARD_TAG),
        ]
        result, state = self.run_guard(
            torrents,
            free_blocks=300,
            cleaner_ready=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state.requests, [])


if __name__ == "__main__":
    unittest.main()
