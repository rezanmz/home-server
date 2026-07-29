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

    def test_backup_alerts_exclude_pvcs_that_disable_nightly_backups(self) -> None:
        release_documents = list(
            yaml.safe_load_all(
                (REPO_ROOT / "infrastructure/observability/release.yaml").read_text(
                    encoding="utf-8"
                )
            )
        )
        release = next(
            document
            for document in release_documents
            if document and document.get("kind") == "HelmRelease"
        )
        kube_state_metrics = release["spec"]["values"]["kube-state-metrics"]
        self.assertIn(
            "persistentvolumeclaims=[recurring-job-group.longhorn.io/default]",
            kube_state_metrics["metricLabelsAllowlist"],
        )

        rules_document = yaml.safe_load(
            (REPO_ROOT / "infrastructure/observability/backup-health-rules.yaml").read_text(
                encoding="utf-8"
            )
        )
        rules = {
            rule["record"]: rule["expr"]
            for group in rules_document["spec"]["groups"]
            for rule in group["rules"]
            if "record" in rule
        }
        eligibility = rules["home_server_longhorn_backup_eligible_pvc_info"]
        self.assertIn("kube_persistentvolumeclaim_info", eligibility)
        self.assertIn("kube_persistentvolumeclaim_labels", eligibility)
        self.assertIn(
            'label_recurring_job_group_longhorn_io_default="disabled"',
            eligibility,
        )
        self.assertIn("unless on (namespace, persistentvolumeclaim)", eligibility)

        for recording_rule in (
            "home_server_longhorn_backup_age_seconds",
            "home_server_longhorn_backup_eligible_pvcs",
            "home_server_longhorn_backup_covered_pvcs",
        ):
            self.assertIn(
                "home_server_longhorn_backup_eligible_pvc_info",
                rules[recording_rule],
            )


if __name__ == "__main__":
    unittest.main()
