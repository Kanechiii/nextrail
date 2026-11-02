"""Provider onboarding readiness, hostile offline file inputs and no activation."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from publish_course_catalog import (
    PublicationError, input_from_manifest, read_json,
)
from test_course_pipeline import fixtures


class ProviderOnboardingReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        base, registry, submissions, reviews, ledger = fixtures()
        moment = datetime.now(timezone.utc)
        checked = (moment - timedelta(hours=6)).isoformat()
        for row in reviews:
            row["checked_at"] = checked
        for row in ledger["claims"]:
            row["checked_at"] = checked
        source = registry["sources"][0]
        self.permissions = {
            "schema_version": "1.0.0",
            "authorizations": [{
                "source_id": source["id"],
                "provider_id": source["provider_id"],
                "source_url": source["source_url"],
                "method": source["method"],
                "status": "approved",
                "allowed_hosts": source["allowed_hosts"],
                "permission_basis": "published_terms",
                "permission_url": "https://courses.example.org/terms",
                "reviewer": "fictional-reviewer",
                "reviewed_at": checked,
                "expires_at": (moment + timedelta(days=30)).isoformat(),
            }],
        }
        self.write("base.json", base)
        self.write("sources.json", registry)
        self.write("auth.json", self.permissions)
        self.write("manifest.json", {"schema_version": "1.0.0", "batches": [{
            "source_id": source["id"], "format": "manual", "path": "snapshot.json",
        }]})
        self.write("snapshot.json", submissions[source["id"]])
        self.write("reviews.json", {"schema_version": "1.0.0", "reviews": reviews})
        self.write("claims.json", ledger)

    def write(self, name, value):
        (self.folder / name).write_text(
            json.dumps(value), encoding="utf-8",
        )

    def audit(self, *extra):
        command = [
            sys.executable, str(ROOT / "scripts/audit_provider_onboarding.py"),
            "--base-catalog", str(self.folder / "base.json"),
            "--sources", str(self.folder / "sources.json"),
            "--authorizations", str(self.folder / "auth.json"),
            "--manifest", str(self.folder / "manifest.json"),
            "--listing-reviews", str(self.folder / "reviews.json"),
            "--claims", str(self.folder / "claims.json"),
            *extra,
        ]
        return subprocess.run(command, capture_output=True, text=True,
                              cwd=ROOT, check=False, timeout=30)

    def test_current_fictional_review_is_only_manual_signoff_candidate(self):
        result = self.audit("--require-candidates")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["authorized_source_assertions"], 1)
        self.assertEqual(report["course_candidates"], 1)
        self.assertEqual(report["reviewed_course_candidates"], 1)
        self.assertEqual(report["status"], "manual_independent_review_required")
        self.assertEqual(report["remote_requests_performed"], 0)
        self.assertEqual(report["catalog_files_written"], 0)
        self.assertFalse(report["runtime_activation_performed"])
        self.assertTrue(report["manual_release_approval_required"])
        self.assertTrue(report["independent_permission_verification_required"])
        self.assertEqual(report["sources"][0]["status"], "offline_snapshot_submitted")
        self.assertNotIn("permission_url", result.stdout)
        self.assertNotIn("reviewer", report["sources"][0])

    def test_sample_sources_report_zero_real_grants_and_courses(self):
        sample = ROOT / "data"
        args = [
            sys.executable, str(ROOT / "scripts/audit_provider_onboarding.py"),
            "--base-catalog", str(sample / "catalog.sample.json"),
            "--sources", str(sample / "sources.sample.json"),
            "--authorizations", str(sample / "provider-authorizations.sample.json"),
            "--manifest", str(sample / "course-publication.manifest.sample.json"),
            "--listing-reviews", str(sample / "course-publication.reviews.sample.json"),
            "--claims", str(sample / "evidence.sample.json"),
            "--expect-empty",
        ]
        result = subprocess.run(args, capture_output=True, text=True,
                                cwd=ROOT, check=False, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["authorized_source_assertions"], 0)
        self.assertEqual(report["reviewed_course_candidates"], 0)
        self.assertEqual(report["status"], "blocked_no_reviewed_courses")
        self.assertEqual(
            {x["status"] for x in report["sources"]}, {"synthetic_excluded"}
        )

    def test_expected_empty_gate_blocks_unreviewed_activation(self):
        result = self.audit("--expect-empty")
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires zero approved", result.stderr)

    def test_missing_or_expired_permission_fails_closed(self):
        for scenario in ("missing", "expired", "revoked", "wrong_scope"):
            with self.subTest(scenario=scenario):
                permissions = copy.deepcopy(self.permissions)
                row = permissions["authorizations"][0]
                if scenario == "missing":
                    permissions["authorizations"] = []
                elif scenario == "expired":
                    row["expires_at"] = (
                        datetime.now(timezone.utc) - timedelta(hours=1)
                    ).isoformat()
                elif scenario == "revoked":
                    row["status"] = "revoked"
                else:
                    row["source_url"] = "https://courses.example.org/changed"
                self.write("auth.json", permissions)
                result = self.audit()
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(result.stdout, "")
        self.assertFalse((self.folder / "reviewed.json").exists())

    def test_missing_local_snapshot_reports_not_submitted(self):
        self.write("manifest.json", {"schema_version": "1.0.0", "batches": []})
        self.write("reviews.json", {"schema_version": "1.0.0", "reviews": []})
        self.write("claims.json", {"schema_version": "1.0.0", "claims": []})
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["sources"][0]["status"], "authorized_snapshot_missing")
        self.assertEqual(report["reviewed_course_candidates"], 0)
        self.assertEqual(self.audit("--require-candidates").returncode, 2)

    def test_orphan_review_without_snapshot_rejected_before_readiness(self):
        self.write("manifest.json", {"schema_version": "1.0.0", "batches": []})
        response = self.audit()
        self.assertEqual(response.returncode, 1)
        self.assertIn("unknown course", response.stderr)
        self.assertEqual(response.stdout, "")

    def test_stale_availability_or_pending_listing_blocks_candidate(self):
        claims = json.loads((self.folder / "claims.json").read_text())
        for row in claims["claims"]:
            if row["claim"] == "availability":
                row["checked_at"] = "2020-01-01T00:00:00Z"
        self.write("claims.json", claims)
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["reviewed_course_candidates"], 0)
        self.assertEqual(report["excluded_reasons"], {"availability_not_verified": 1})
        self.assertEqual(self.audit("--require-candidates").returncode, 2)

    def test_duplicate_nested_properties_and_nonfinite_values_are_rejected(self):
        snapshot = self.folder / "snapshot.json"
        snapshot.write_text(
            '{"source_id":"example-manual-one","records":[],"records":[]}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(PublicationError, "Duplicate"):
            read_json(snapshot)
        self.assertEqual(self.audit().returncode, 1)
        snapshot.write_text('{"items":[NaN]}', encoding="utf-8")
        with self.assertRaisesRegex(PublicationError, "Non-finite"):
            read_json(snapshot)
        self.assertEqual(self.audit().returncode, 1)

    def test_symlinked_snapshot_and_symlinked_parent_are_rejected(self):
        snapshot = self.folder / "snapshot.json"
        snapshot.unlink()
        target = self.folder / "original.json"
        target.write_text('{"source_id":"example-manual-one","records":[]}',
                          encoding="utf-8")
        try:
            snapshot.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("File symlinks unavailable")
        with self.assertRaisesRegex(PublicationError, "Symlink"):
            input_from_manifest(self.folder, "snapshot.json", suffix=".json")
        self.assertEqual(self.audit().returncode, 1)
        snapshot.unlink()
        directory = self.folder / "real"
        directory.mkdir()
        (directory / "snapshot.json").write_text(target.read_text())
        alias = self.folder / "alias"
        try:
            alias.symlink_to(directory, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Directory symlinks unavailable")
        with self.assertRaisesRegex(PublicationError, "Symlink"):
            input_from_manifest(self.folder, "alias/snapshot.json", suffix=".json")

    def test_oversized_and_out_of_directory_snapshots_are_rejected(self):
        snapshot = self.folder / "snapshot.json"
        snapshot.write_bytes(b"x" * 2_000_001)
        self.assertEqual(self.audit().returncode, 1)
        with self.assertRaises(PublicationError):
            input_from_manifest(self.folder, "../outside.json", suffix=".json")

    def test_existing_publication_output_not_created_by_read_only_audit(self):
        marker = self.folder / "reviewed.json"
        marker.write_text("do not change", encoding="utf-8")
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "do not change")


if __name__ == "__main__":
    unittest.main()
