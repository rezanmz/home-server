from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pypdf import PdfWriter


GUARD_PATH = Path(__file__).with_name("gcloud")
loader = importlib.machinery.SourceFileLoader("vision_guard", str(GUARD_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
vision_guard = importlib.util.module_from_spec(spec)
loader.exec_module(vision_guard)


class VisionGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.pdf = self.vault / "sample.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_blank_page(width=100, height=100)
        with self.pdf.open("wb") as stream:
            writer.write(stream)

        self.fake_gcloud = self.root / "real-gcloud"
        self.fake_gcloud.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.fake_gcloud.chmod(0o700)
        self.env = {
            "VISION_MONTHLY_PAGE_LIMIT": "3",
            "VISION_QUOTA_DB": str(self.root / "quota.sqlite3"),
            "VISION_REAL_GCLOUD": str(self.fake_gcloud),
            "VISION_STAGING_BUCKET": "test-ocr",
            "VISION_VAULT_ROOT": str(self.vault),
        }

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def call(self, *args: str) -> int:
        with mock.patch.dict(os.environ, self.env, clear=False), mock.patch.object(
            vision_guard.sys, "argv", [str(GUARD_PATH), *args]
        ):
            return vision_guard.main()

    def test_upload_reserves_pages_then_ocr_consumes_them(self) -> None:
        uri = "gs://test-ocr/input/one.pdf"
        self.assertEqual(self.call("storage", "cp", str(self.pdf), uri), 0)
        self.assertEqual(
            self.call("ml", "vision", "detect-text-pdf", uri, "gs://test-ocr/output/one"), 0
        )
        connection = sqlite3.connect(self.root / "quota.sqlite3")
        row = connection.execute("SELECT pages, consumed_at FROM reservations").fetchone()
        self.assertEqual(row[0], 2)
        self.assertIsNotNone(row[1])

    def test_page_limit_is_blocked_before_delegate(self) -> None:
        first_uri = "gs://test-ocr/input/one.pdf"
        second_uri = "gs://test-ocr/input/two.pdf"
        self.assertEqual(self.call("storage", "cp", str(self.pdf), first_uri), 0)
        self.assertEqual(
            self.call("ml", "vision", "detect-text-pdf", first_uri, "gs://test-ocr/output/one"), 0
        )
        self.assertEqual(self.call("storage", "cp", str(self.pdf), second_uri), 0)
        with self.assertRaises(SystemExit) as raised:
            self.call("ml", "vision", "detect-text-pdf", second_uri, "gs://test-ocr/output/two")
        self.assertEqual(raised.exception.code, vision_guard.EXIT_POLICY_DENIED)

    def test_paths_outside_vault_and_bucket_are_blocked(self) -> None:
        outside = self.root / "outside.pdf"
        outside.write_bytes(self.pdf.read_bytes())
        with self.assertRaises(SystemExit):
            self.call("storage", "cp", str(outside), "gs://test-ocr/input/outside.pdf")
        with self.assertRaises(SystemExit):
            self.call("storage", "cat", "gs://another-bucket/output/result.json")

    def test_unknown_gcloud_command_is_blocked(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.call("projects", "delete", "something")
        self.assertEqual(raised.exception.code, vision_guard.EXIT_POLICY_DENIED)


if __name__ == "__main__":
    unittest.main()
