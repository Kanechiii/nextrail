"""Offline catalog quality, expiry alerts and nonactivation regressions."""
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

from audit_catalog_quality import quality_report
from nextrail_discovery.pipeline import PublicationError
from test_course_pipeline import fixtures


def checked_at_ago(days=0, hours=0):
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).isoformat()


class CatalogQualityAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        base, registry, submissions, reviews, ledger = fixtures()
        self.base = base
        self.registry = registry
        self.snapshot = submissions[registry["sources"][0]["id"]]
        self.reviews = reviews
        self.ledger = ledger
        for row in self.reviews:
            row["checked_at"] = checked_at_ago(hours=1)
        for row in self.ledger["claims"]:
            row["checked_at"] = checked_at_ago(hours=1)
        now = datetime.now(timezone.utc)
        source = registry["sources"][0]
        self.authorization = {
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
                "reviewed_at": checked_at_ago(hours=1),
                "expires_at": (now + timedelta(days=30)).isoformat(),
            }],
        }
        self.manifest = {
            "schema_version": "1.0.0",
            "batches": [{
                "source_id": source["id"],
                "format": "manual",
                "path": "snapshot.json",
            }],
        }
        self.write_all()

    def write(self, filename, value):
        (self.folder / filename).write_text(json.dumps(value), encoding="utf-8")

    def write_all(self):
        for filename, value in (
            ("base.json", self.base),
            ("sources.json", self.registry),
            ("authorizations.json", self.authorization),
            ("manifest.json", self.manifest),
            ("snapshot.json", self.snapshot),
            ("reviews.json", {"schema_version": "1.0.0", "reviews": self.reviews}),
            ("claims.json", self.ledger),
        ):
            self.write(filename, value)

    def cli(self, *extra, sample=False):
        base = ROOT / "data" if sample else self.folder
        if sample:
            filenames = (
                "catalog.sample.json", "sources.sample.json",
                "provider-authorizations.sample.json",
                "course-publication.manifest.sample.json",
                "course-publication.reviews.sample.json", "evidence.sample.json",
            )
        else:
            filenames = (
                "base.json", "sources.json", "authorizations.json",
                "manifest.json", "reviews.json", "claims.json",
            )
        params = [
            sys.executable, str(ROOT / "scripts/audit_catalog_quality.py"),
        ]
        for key, name in zip((
            "--base-catalog", "--sources", "--authorizations",
            "--manifest", "--listing-reviews", "--claims",
        ), filenames):
            params.extend((key, str(base / name)))
        return subprocess.run(
            [*params, *extra], text=True, capture_output=True,
            cwd=ROOT, check=False, timeout=30,
        )

    def test_sample_has_no_real_source_grants_or_courses(self):
        result = self.cli("--expect-empty", sample=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["current_authorization_assertions"], 0)
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["reviewed_course_candidates"], 0)
        self.assertEqual(report["excluded_course_count"], 0)
        self.assertEqual(report["status"], "blocked_no_reviewed_courses")
        self.assertEqual(report["refresh_queue"], [])
        self.assertTrue(report["manual_provider_permission_verification_required"])
        self.assertTrue(report["manual_course_evidence_verification_required"])
        self.assertTrue(report["manual_release_approval_required"])
        self.assertFalse(report["runtime_activation_performed"])
        self.assertEqual(report["remote_requests_performed"], 0)
        self.assertEqual(report["catalog_files_written"], 0)
        self.assertEqual(
            self.cli("--require-reviewed-candidates", sample=True).returncode, 2
        )

    def test_fictional_current_candidate_only_enters_manual_release_review(self):
        result = self.cli("--require-reviewed-candidates")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["current_authorization_assertions"], 1)
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["reviewed_course_candidates"], 1)
        self.assertEqual(report["excluded_course_count"], 0)
        self.assertEqual(report["certificate_cost_unknown_count"], 1)
        self.assertEqual(report["refresh_queue"], [])
        self.assertEqual(report["status"], "manual_release_approval_required")
        self.assertEqual(self.cli("--expect-empty").returncode, 1)
        for sensitive in (
            "https://courses.example.org/learn-html",
            "https://courses.example.org/terms",
            "fictional-reviewer",
        ):
            self.assertNotIn(sensitive, result.stdout)
        self.assertFalse((self.folder / "published.json").exists())

    def test_independent_claims_and_listing_are_scheduled_near_expiry(self):
        self.reviews[0]["checked_at"] = checked_at_ago(days=89, hours=23)
        for row in self.ledger["claims"]:
            if row["claim"] == "availability":
                row["checked_at"] = checked_at_ago(days=6, hours=23)
            if row["claim"] == "access_cost":
                row["checked_at"] = checked_at_ago(days=29, hours=23)
        certificate = copy.deepcopy(self.ledger["claims"][0])
        certificate["claim"] = "certificate_cost"
        certificate["value"] = "paid"
        certificate["checked_at"] = checked_at_ago(days=29, hours=23)
        self.ledger["claims"].append(certificate)
        self.write_all()
        response = self.cli("--refresh-window-hours", "48")
        self.assertEqual(response.returncode, 0, response.stderr)
        report = json.loads(response.stdout)
        self.assertEqual(report["reviewed_course_candidates"], 1)
        self.assertEqual(report["certificate_cost_unknown_count"], 0)
        self.assertEqual(report["refresh_due_counts"], {
            "listing": 1, "availability": 1,
            "access_cost": 1, "certificate_cost": 1,
        })
        self.assertEqual(report["refresh_queue"], [{
            "resource_id": "example-training-intro-html",
            "checks_due": ["access_cost", "availability", "certificate_cost", "listing"],
        }])
        far = self.cli("--refresh-window-hours", "0")
        self.assertEqual(far.returncode, 0, far.stderr)
        self.assertEqual(json.loads(far.stdout)["refresh_queue"], [])

    def test_stale_availability_blocks_course_without_claiming_verified(self):
        for row in self.ledger["claims"]:
            if row["claim"] == "availability":
                row["checked_at"] = checked_at_ago(days=8)
        self.write_all()
        report = json.loads(self.cli().stdout)
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["reviewed_course_candidates"], 0)
        self.assertEqual(report["excluded_course_count"], 1)
        self.assertEqual(report["excluded_reasons"], {"availability_not_verified": 1})
        self.assertEqual(report["refresh_queue"], [])

    def test_stale_access_price_and_listing_are_separate_exclusions(self):
        self.ledger["claims"][0]["checked_at"] = checked_at_ago(days=31)
        self.write_all()
        report = json.loads(self.cli().stdout)
        self.assertEqual(report["excluded_reasons"], {"access_cost_not_verified": 1})
        self.ledger["claims"][0]["checked_at"] = checked_at_ago(hours=1)
        self.reviews[0]["checked_at"] = checked_at_ago(days=91)
        self.write_all()
        report = json.loads(self.cli().stdout)
        self.assertEqual(report["excluded_reasons"], {"listing_review_stale": 1})

    def test_stale_certificate_price_reverts_to_unknown_without_free_claim(self):
        certificate = copy.deepcopy(self.ledger["claims"][0])
        certificate["claim"] = "certificate_cost"
        certificate["value"] = "free"
        certificate["checked_at"] = checked_at_ago(days=31)
        self.ledger["claims"].append(certificate)
        self.write_all()
        response = self.cli()
        self.assertEqual(response.returncode, 0, response.stderr)
        report = json.loads(response.stdout)
        self.assertEqual(report["reviewed_course_candidates"], 1)
        self.assertEqual(report["certificate_cost_unknown_count"], 1)
        self.assertEqual(report["refresh_due_counts"]["certificate_cost"], 0)

    def test_missing_listing_review_is_excluded(self):
        self.reviews = []
        self.write_all()
        report = json.loads(self.cli().stdout)
        self.assertEqual(report["excluded_reasons"], {"missing_listing_review": 1})
        self.assertEqual(report["reviewed_course_candidates"], 0)

    def test_conflicting_duplicate_course_records_fail_closed(self):
        self.snapshot["records"].append(copy.deepcopy(self.snapshot["records"][0]))
        self.snapshot["records"][1]["title"] = "Conflicting name"
        self.write_all()
        response = self.cli()
        self.assertEqual(response.returncode, 1)
        self.assertEqual(response.stdout, "")

    def test_missing_or_expired_authorization_fails_closed(self):
        for mode in ("missing", "expired"):
            with self.subTest(mode=mode):
                original = copy.deepcopy(self.authorization)
                if mode == "missing":
                    self.authorization["authorizations"] = []
                else:
                    self.authorization["authorizations"][0]["expires_at"] = checked_at_ago(days=1)
                self.write_all()
                response = self.cli()
                self.assertEqual(response.returncode, 1)
                self.assertEqual(response.stdout, "")
                self.authorization = original

    def test_invalid_refresh_window_and_naive_clock_rejected(self):
        for value in ("-1", "169", "not-an-hour"):
            with self.subTest(value=value):
                self.assertEqual(
                    self.cli("--refresh-window-hours", value).returncode, 1 if value != "not-an-hour" else 2,
                )
        with self.assertRaises(PublicationError):
            quality_report({"catalog": {"resources": []}}, 0, now=datetime(2026, 11, 3))

    def test_read_only_operator_execution(self):
        before = {p.name: p.read_bytes() for p in self.folder.iterdir() if p.is_file()}
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {p.name: p.read_bytes() for p in self.folder.iterdir() if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
