#!/usr/bin/env python3
"""Regression tests for Syncthing's default-include backup policy."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import textwrap
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "apps" / "syncthing" / "backups" / "backup.sh"
APPROVED_REPOSITORY = (
    "s3:https://s3.ca-east-006.backblazeb2.com/"
    "rezanmz-home-server-syncthing-backups/syncthing"
)
REPOSITORY_ID = "c" * 64
CANDIDATE_ID = "a" * 64
PROMOTED_ID = "b" * 64


class SyncthingBackupPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source"
        self.policy = self.root / "excluded-folder-ids.txt"
        self.config = self.root / "config.xml"
        self.work = self.root / "work"
        self.work.mkdir()
        for folder in ("vault", "Family Notes"):
            (self.source / folder / ".stfolder").mkdir(parents=True)

        self.canary_content = b"test-source-canary\n"
        (self.source / ".restic-source-canary").write_bytes(self.canary_content)
        self.write_config(
            ("vault-id", "/data/vault"),
            ("family-notes-id", "/data/Family Notes"),
        )

    def write_config(self, *folders: tuple[str, str]) -> None:
        folder_lines = "\n".join(
            f'    <folder id="{folder_id}" label="test" path="{path}" type="sendreceive">\n'
            "        <markerName>.stfolder</markerName>\n"
            "    </folder>"
            for folder_id, path in folders
        )
        self.config.write_text(
            f"<configuration>\n{folder_lines}\n"
            "    <defaults>\n"
            '        <folder id="" label="" path="" type="sendreceive">\n'
            "            <markerName>.stfolder</markerName>\n"
            "        </folder>\n"
            "    </defaults>\n"
            "</configuration>\n",
            encoding="utf-8",
        )

    def run_validation(self, policy: str) -> subprocess.CompletedProcess[str]:
        self.policy.write_text(policy, encoding="utf-8")
        environment = os.environ.copy()
        environment.update(
            {
                "SOURCE_ROOT": str(self.source),
                "SYNCTHING_CONFIG_FILE": str(self.config),
                "POLICY_FILE": str(self.policy),
                "WORK_DIR": str(self.work),
                "SOURCE_CANARY_SHA256": hashlib.sha256(self.canary_content).hexdigest(),
            }
        )
        return subprocess.run(
            [str(SCRIPT), "validate-policy"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def exclusions(self) -> list[str]:
        exclude_file = self.work / "restic-excludes.txt"
        return exclude_file.read_text(encoding="utf-8").splitlines()

    def test_empty_policy_includes_every_configured_folder(self) -> None:
        result = self.run_validation("# Everything is included by default.\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.exclusions(), [])

    def test_folder_ids_resolve_to_current_exact_paths(self) -> None:
        result = self.run_validation("vault-id\nfamily-notes-id\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.exclusions(),
            [str(self.source / "vault"), str(self.source / "Family Notes")],
        )

    def test_unknown_invalid_and_duplicate_ids_fail_closed(self) -> None:
        for policy in ("missing-id\n", "bad id\n", "vault-id\nvault-id\n"):
            with self.subTest(policy=policy):
                result = self.run_validation(policy)
                self.assertNotEqual(result.returncode, 0)

    def test_outside_traversing_pattern_and_backslash_paths_fail_closed(self) -> None:
        fixtures = (
            ("outside", "/config/private"),
            ("traversal", "/data/../config"),
            ("dot-component", "/data/./vault"),
            ("trailing-slash", "/data/vault/"),
            ("pattern", "/data/vault*"),
            ("backslash", "/data/literal\\name"),
        )
        for folder_id, path in fixtures:
            with self.subTest(path=path):
                self.write_config((folder_id, path))
                result = self.run_validation("")
                self.assertNotEqual(result.returncode, 0)

    def test_overlapping_folder_paths_fail_closed(self) -> None:
        (self.source / "vault" / "nested" / ".stfolder").mkdir(parents=True)
        self.write_config(
            ("vault-id", "/data/vault"),
            ("nested-id", "/data/vault/nested"),
        )
        result = self.run_validation("")
        self.assertNotEqual(result.returncode, 0)

    def test_symlinked_folder_or_marker_fails_closed(self) -> None:
        external = self.root / "external"
        (external / ".stfolder").mkdir(parents=True)
        (self.source / "linked").symlink_to(external, target_is_directory=True)
        self.write_config(("linked-id", "/data/linked"))
        result = self.run_validation("")
        self.assertNotEqual(result.returncode, 0)

        (self.source / "linked").unlink()
        (self.source / "linked").mkdir()
        (self.source / "linked" / ".stfolder").symlink_to(
            external / ".stfolder", target_is_directory=True
        )
        result = self.run_validation("")
        self.assertNotEqual(result.returncode, 0)

    def test_missing_or_changed_durable_canary_fails_closed(self) -> None:
        canary = self.source / ".restic-source-canary"
        canary.unlink()
        result = self.run_validation("")
        self.assertNotEqual(result.returncode, 0)

        canary.write_bytes(b"wrong\n")
        result = self.run_validation("")
        self.assertNotEqual(result.returncode, 0)


class SyncthingBackupStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source"
        self.policy = self.root / "excluded-folder-ids.txt"
        self.config = self.root / "config.xml"
        self.work = self.root / "work"
        self.credentials = self.root / "credentials"
        self.bin = self.root / "bin"
        self.restic_log = self.root / "restic.log"
        self.repo_state = self.root / "repo-initialized"
        for directory in (self.work, self.credentials, self.bin):
            directory.mkdir()
        (self.source / "vault" / ".stfolder").mkdir(parents=True)
        self.canary_content = b"test-source-canary\n"
        (self.source / ".restic-source-canary").write_bytes(self.canary_content)
        self.policy.write_text("# Include everything by default.\n", encoding="utf-8")
        self.config.write_text(
            "<configuration>\n"
            '  <folder id="vault-id" label="Vault" path="/data/vault" '
            'type="sendreceive">\n'
            "    <markerName>.stfolder</markerName>\n"
            "  </folder>\n"
            "  <defaults>\n"
            '    <folder id="" label="" path="" type="sendreceive" />\n'
            "  </defaults>\n"
            "</configuration>\n",
            encoding="utf-8",
        )
        for name, value in (
            ("aws-access-key-id", "test-access-key"),
            ("aws-secret-access-key", "test-secret-key"),
            ("repository-password", "test-repository-password"),
        ):
            (self.credentials / name).write_text(value, encoding="utf-8")

        fake_restic = self.bin / "restic"
        fake_restic.write_text(
            textwrap.dedent(
                """\
                #!/bin/sh
                set -eu

                while [ "${1:-}" = "--retry-lock" ]; do
                  shift 2
                done
                command_name="${1:-}"
                [ "$#" -gt 0 ] && shift
                {
                  printf '%s' "$command_name"
                  for argument in "$@"; do
                    printf '\t%s' "$argument"
                  done
                  printf '\n'
                } >> "$FAKE_RESTIC_LOG"

                case "$command_name" in
                  cat)
                    if [ "${FAKE_PROBE_MISSING:-false}" = true ] && \
                       [ ! -f "$FAKE_REPO_STATE" ]; then
                      exit 10
                    fi
                    printf '{"id":"%s"}\n' "$FAKE_REPOSITORY_ID"
                    ;;
                  init)
                    : > "$FAKE_REPO_STATE"
                    ;;
                  backup)
                    printf '{"message_type":"summary","snapshot_id":"%s"}\n' \
                      "$FAKE_CANDIDATE_ID"
                    exit "${FAKE_BACKUP_STATUS:-0}"
                    ;;
                  tag)
                    printf '{"message_type":"changed","old_snapshot_id":"%s","new_snapshot_id":"%s"}\n' \
                      "${FAKE_TAG_OLD_ID:-$FAKE_CANDIDATE_ID}" "$FAKE_PROMOTED_ID"
                    printf '{"message_type":"summary","changed":1}\n'
                    ;;
                  snapshots)
                    printf '[{"id":"%s","time":"%s","hostname":"home-server-syncthing-nfs","paths":["%s"],"tags":%s}]\n' \
                      "$FAKE_PROMOTED_ID" "$FAKE_SNAPSHOT_TIME" \
                      "$FAKE_SOURCE_ROOT" "$FAKE_SNAPSHOT_TAGS_JSON"
                    ;;
                  check|forget|prune)
                    ;;
                  *)
                    printf 'unexpected fake restic command: %s\n' "$command_name" >&2
                    exit 90
                    ;;
                esac
                """
            ),
            encoding="utf-8",
        )
        fake_restic.chmod(0o755)

        fake_date = self.bin / "date"
        fake_date.write_text(
            textwrap.dedent(
                """\
                #!/bin/sh
                set -eu
                [ "${1:-}" = "-u" ] || exit 91
                case "${2:-}" in
                  +%u) printf '2\n' ;;
                  +%d) printf '14\n' ;;
                  +%m) printf '07\n' ;;
                  +%s) printf '%s\n' "$FAKE_NOW_EPOCH" ;;
                  *) exit 92 ;;
                esac
                """
            ),
            encoding="utf-8",
        )
        fake_date.chmod(0o755)

        self.environment = os.environ.copy()
        self.environment.update(
            {
                "PATH": f"{self.bin}:{self.environment['PATH']}",
                "SOURCE_ROOT": str(self.source),
                "SYNCTHING_CONFIG_FILE": str(self.config),
                "POLICY_FILE": str(self.policy),
                "WORK_DIR": str(self.work),
                "CREDENTIALS_DIR": str(self.credentials),
                "SOURCE_CANARY_SHA256": hashlib.sha256(
                    self.canary_content
                ).hexdigest(),
                "RESTIC_REPOSITORY": APPROVED_REPOSITORY,
                "EXPECTED_REPOSITORY_ID": REPOSITORY_ID,
                "FAKE_RESTIC_LOG": str(self.restic_log),
                "FAKE_REPO_STATE": str(self.repo_state),
                "FAKE_REPOSITORY_ID": REPOSITORY_ID,
                "FAKE_CANDIDATE_ID": CANDIDATE_ID,
                "FAKE_PROMOTED_ID": PROMOTED_ID,
                "FAKE_SOURCE_ROOT": str(self.source),
                "FAKE_SNAPSHOT_TIME": "2026-07-14T16:08:50Z",
                "FAKE_SNAPSHOT_TAGS_JSON": '["syncthing-nfs"]',
                "FAKE_NOW_EPOCH": str(
                    int(
                        datetime(
                            2026, 7, 14, 16, 8, 50, tzinfo=timezone.utc
                        ).timestamp()
                    )
                    + 3600
                ),
            }
        )

    def run_script(
        self, mode: str, **environment_updates: str
    ) -> subprocess.CompletedProcess[str]:
        environment = self.environment.copy()
        environment.update(environment_updates)
        return subprocess.run(
            [str(SCRIPT), mode],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def logged_commands(self) -> list[str]:
        if not self.restic_log.exists():
            return []
        return self.restic_log.read_text(encoding="utf-8").splitlines()

    def test_success_uses_quiet_json_and_validates_tag_id_rewrite(self) -> None:
        result = self.run_script("backup")
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.logged_commands()
        backup = next(command for command in commands if command.startswith("backup\t"))
        self.assertIn("\t--json\t--quiet", backup)
        self.assertTrue(any(command.startswith("tag\t") for command in commands))
        self.assertIn(f"trusted snapshot id={PROMOTED_ID}", result.stdout)

    def test_partial_backup_is_not_promoted_and_bounds_candidates(self) -> None:
        result = self.run_script("backup", FAKE_BACKUP_STATUS="3")
        self.assertNotEqual(result.returncode, 0)
        commands = self.logged_commands()
        self.assertFalse(any(command.startswith("tag\t") for command in commands))
        cleanup = [command for command in commands if command.startswith("forget\t")]
        self.assertEqual(len(cleanup), 1)
        self.assertIn("\t--tag\tsyncthing-nfs-candidate", cleanup[0])
        self.assertIn("\t--keep-last\t3", cleanup[0])

    def test_repository_id_mismatch_fails_before_backup(self) -> None:
        result = self.run_script("backup", FAKE_REPOSITORY_ID="d" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(
            any(command.startswith("backup\t") for command in self.logged_commands())
        )

    def test_initialization_requires_explicit_approval(self) -> None:
        result = self.run_script(
            "init-repository",
            EXPECTED_REPOSITORY_ID="PENDING",
            FAKE_PROBE_MISSING="true",
            ALLOW_REPOSITORY_INIT="false",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(command.startswith("init\t") for command in self.logged_commands()))

        self.restic_log.unlink()
        result = self.run_script(
            "init-repository",
            EXPECTED_REPOSITORY_ID="PENDING",
            FAKE_PROBE_MISSING="true",
            ALLOW_REPOSITORY_INIT="true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(command.startswith("init\t") for command in self.logged_commands()))
        self.assertIn(REPOSITORY_ID, result.stdout)

    def test_promotion_must_report_the_exact_candidate(self) -> None:
        result = self.run_script("backup", FAKE_TAG_OLD_ID="e" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("trusted snapshot id=", result.stdout)

    def test_freshness_accepts_a_recent_exact_trusted_snapshot(self) -> None:
        result = self.run_script("check-freshness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("freshness check passed", result.stdout)
        self.assertIn("age=3600s", result.stdout)

        result = self.run_script(
            "check-freshness",
            FAKE_SNAPSHOT_TIME="2026-07-14T12:08:50.123456-04:00",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("age=3600s", result.stdout)

    def test_freshness_rejects_stale_or_candidate_metadata(self) -> None:
        snapshot_epoch = int(
            datetime(2026, 7, 14, 16, 8, 50, tzinfo=timezone.utc).timestamp()
        )
        result = self.run_script(
            "check-freshness", FAKE_NOW_EPOCH=str(snapshot_epoch + 129601)
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snapshot is stale", result.stderr)

        result = self.run_script(
            "check-freshness",
            FAKE_SNAPSHOT_TAGS_JSON=(
                '["syncthing-nfs","syncthing-nfs-candidate"]'
            ),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a trusted Syncthing recovery point", result.stderr)


if __name__ == "__main__":
    unittest.main()
