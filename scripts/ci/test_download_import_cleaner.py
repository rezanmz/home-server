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
SCRIPT = REPO_ROOT / "apps/downloads/import-cleaner.sh"
TORRENT_HASH = "0123456789abcdef0123456789abcdef01234567"


class ApiState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.arr_removal_enabled = False
        self.sonarr_history_status = 200
        self.delete_requests: list[dict[str, list[str]]] = []
        self.history_queries: list[dict[str, list[str]]] = []

        self.downloads = root / "downloads"
        self.tv = root / "tv"
        self.movies = root / "movies"
        self.music = root / "music"
        self.state = root / "state"
        self.release = self.downloads / "release"
        self.episode_file = self.tv / "Series" / "episode.mkv"
        for path in (
            self.release,
            self.episode_file.parent,
            self.movies,
            self.music,
            self.state,
        ):
            path.mkdir(parents=True, exist_ok=True)
        (self.release / "episode.mkv").write_bytes(b"download")
        self.episode_file.write_bytes(b"juicefs-library")

    def qbit_torrents(self) -> list[dict[str, object]]:
        return [
            {
                "hash": TORRENT_HASH,
                "category": "tv-sonarr",
                "state": "stoppedUP",
                "progress": 1,
                "amount_left": 0,
                "size": 8,
                "name": "release",
                "content_path": str(self.release),
            }
        ]

    def sonarr_history(self) -> dict[str, object]:
        return {
            "records": [
                {
                    "downloadId": TORRENT_HASH.upper(),
                    "eventType": "downloadFolderImported",
                    "episodeId": 1,
                    "data": {
                        "importedPath": str(self.episode_file),
                        "droppedPath": str(self.release / "episode.mkv"),
                    },
                }
            ]
        }


class MockApiHandler(BaseHTTPRequestHandler):
    state: ApiState

    def log_message(self, *_args: object) -> None:
        return

    def send_json(self, value: object, status_code: int = 200) -> None:
        payload = json.dumps(value).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/qbt/api/v2/app/version":
            self.send_json("5.2.3")
        elif path == "/qbt/api/v2/app/preferences":
            self.send_json(
                {
                    "max_ratio_act": 0,
                    "max_seeding_time_enabled": True,
                    "max_seeding_time": 1,
                }
            )
        elif path == "/qbt/api/v2/torrents/info":
            self.send_json(self.state.qbit_torrents())
        elif path.endswith("/ping"):
            self.send_json({"status": "OK"})
        elif path.endswith("/downloadclient"):
            self.send_json(
                [
                    {
                        "name": "qBittorrent",
                        "enable": True,
                        "removeCompletedDownloads": self.state.arr_removal_enabled,
                    }
                ]
            )
        elif path == "/sonarr/api/v3/history":
            self.state.history_queries.append(
                urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            )
            self.send_json(
                self.state.sonarr_history(),
                self.state.sonarr_history_status,
            )
        elif path in ("/radarr/api/v3/history", "/lidarr/api/v1/history"):
            self.send_json({"records": []})
        elif path == "/sonarr/api/v3/episode/1":
            self.send_json({"hasFile": True, "episodeFileId": 10})
        elif path == "/sonarr/api/v3/episodefile/10":
            self.send_json({"path": str(self.state.episode_file), "size": 15})
        else:
            self.send_json({"error": f"unhandled path: {path}"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode()
        if path == "/qbt/api/v2/torrents/delete":
            self.state.delete_requests.append(urllib.parse.parse_qs(body))
            self.send_response(200)
            self.end_headers()
        else:
            self.send_json({"error": f"unhandled path: {path}"}, 404)


class ImportCleanerTest(unittest.TestCase):
    def setUp(self) -> None:
        if not shutil.which("curl") or not shutil.which("jq"):
            self.skipTest("curl and jq are required")

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.api_state = ApiState(self.root)

        handler = type("Handler", (MockApiHandler,), {"state": self.api_state})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.server_thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

        self.bin_directory = self.root / "bin"
        self.bin_directory.mkdir()
        stat_command = self.bin_directory / "stat"
        stat_command.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  *downloads*) echo nfs ;;\n"
            "  *) echo fuse ;;\n"
            "esac\n"
        )
        stat_command.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

        self.config_directories: dict[str, Path] = {}
        for application in ("sonarr", "radarr", "lidarr"):
            directory = self.root / f"{application}-config"
            directory.mkdir()
            (directory / "config.xml").write_text(
                "<Config><ApiKey>test-api-key</ApiKey></Config>"
            )
            self.config_directories[application] = directory

        (self.api_state.state / f"confirm-{TORRENT_HASH}").write_text("1\n")

    def run_cleaner(self) -> subprocess.CompletedProcess[str]:
        port = self.server.server_address[1]
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin_directory}:{environment['PATH']}",
                "QBITTORRENT_URL": f"http://127.0.0.1:{port}/qbt",
                "SONARR_URL": f"http://127.0.0.1:{port}/sonarr",
                "RADARR_URL": f"http://127.0.0.1:{port}/radarr",
                "LIDARR_URL": f"http://127.0.0.1:{port}/lidarr",
                "DOWNLOADS_PATH": str(self.api_state.downloads),
                "TV_PATH": str(self.api_state.tv),
                "MOVIES_PATH": str(self.api_state.movies),
                "MUSIC_PATH": str(self.api_state.music),
                "SONARR_CONFIG_PATH": str(self.config_directories["sonarr"]),
                "RADARR_CONFIG_PATH": str(self.config_directories["radarr"]),
                "LIDARR_CONFIG_PATH": str(self.config_directories["lidarr"]),
                "STATE_PATH": str(self.api_state.state),
                "CONFIRMATIONS_REQUIRED": "2",
                "DELETE_ENABLED": "true",
                "RUN_ONCE": "true",
            }
        )
        return subprocess.run(
            ["sh", str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )

    def test_deletes_only_after_current_library_file_and_second_confirmation(self) -> None:
        result = self.run_cleaner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.api_state.delete_requests,
            [{"hashes": [TORRENT_HASH], "deleteFiles": ["true"]}],
        )
        self.assertIn("deleted verified import", result.stdout)
        self.assertEqual(
            self.api_state.history_queries[0]["downloadId"],
            [TORRENT_HASH.upper()],
        )

    def test_missing_current_library_file_fails_closed(self) -> None:
        self.api_state.episode_file.unlink()
        result = self.run_cleaner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.api_state.delete_requests, [])
        self.assertFalse(
            (self.api_state.state / f"confirm-{TORRENT_HASH}").exists()
        )

    def test_arr_builtin_removal_must_be_disabled(self) -> None:
        self.api_state.arr_removal_enabled = True
        result = self.run_cleaner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.api_state.delete_requests, [])
        self.assertIn("ownership policy failed", result.stdout)

    def test_failed_history_fetch_breaks_confirmation_chain(self) -> None:
        self.api_state.sonarr_history_status = 500
        result = self.run_cleaner()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.api_state.delete_requests, [])
        self.assertFalse(
            (self.api_state.state / f"confirm-{TORRENT_HASH}").exists()
        )
        self.assertIn("history fetch failed", result.stdout)
        self.assertNotIn("cycle failed", result.stdout)


if __name__ == "__main__":
    unittest.main()
