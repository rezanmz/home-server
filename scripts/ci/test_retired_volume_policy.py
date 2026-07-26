#!/usr/bin/env python3
"""Regression checks for frozen Longhorn recovery volumes."""

from pathlib import Path
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


class RetiredVolumePolicyTests(unittest.TestCase):
    def test_duplicati_archive_does_not_inherit_nightly_backups(self) -> None:
        claim = yaml.safe_load(
            (REPO_ROOT / "apps/duplicati/storage.yaml").read_text(encoding="utf-8")
        )
        labels = claim["metadata"]["labels"]

        self.assertEqual(labels["recurring-job.longhorn.io/source"], "enabled")
        self.assertEqual(
            labels["recurring-job-group.longhorn.io/default"], "disabled"
        )


if __name__ == "__main__":
    unittest.main()
