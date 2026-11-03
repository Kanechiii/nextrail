"""Provider-rights review is evidence-only and never grants source access."""
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

from audit_provider_rights import RightsReviewError, audit_dossier

SAMPLE = ROOT / "data/provider-rights-review.sample.json"


class ProviderRightsAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "rights.json"
        self.document = json.loads(SAMPLE.read_text(encoding="utf-8"))
        self.write()

    def write(self, raw=None):
        self.path.write_text(
            json.dumps(self.document if raw is None else raw), encoding="utf-8"
        )

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/audit_provider_rights.py"),
             "--dossier", str(self.path), *args],
            capture_output=True, text=True, cwd=ROOT, check=False, timeout=30,
        )

    def submitted_fictional_dossier(self):
        now = datetime.now(timezone.utc)
        checked = (now - timedelta(hours=2)).isoformat()
        expires = (now + timedelta(days=30)).isoformat()
        fictional = copy.deepcopy(self.document["providers"][0])
        fictional.update({
            "provider_id": "fictional-test-school",
            "provider_name": "Fictional Test School",
            "official_website": "https://courses.example.org",
            "review_state": "evidence_submitted",
            "proposed_method": "manual",
        })
        fictional["rights"] = {
            "metadata_collection": "permitted",
            "metadata_display": "permitted",
            "metadata_caching": "permitted",
            "commercial_use": "permitted",
            "attribution_requirements": "documented",
        }
        fictional["evidence"] = {
            "permission_basis": "published_terms",
            "permission_url": "https://courses.example.org/terms",
            "reviewer_id": "fictional-reviewer",
            "reviewed_at": checked,
            "expires_at": expires,
        }
        fictional["course_claims"] = {
            "availability": "reviewed",
            "access_cost": "reviewed",
            "certificate_cost": "reviewed",
            "student_eligibility": "reviewed",
        }
        self.document["providers"] = [fictional]
        self.write()
        return fictional

    def test_sample_all_eight_providers_remain_pending_and_unapproved(self):
        result = self.cli("--expect-pending")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["provider_count"], 8)
        self.assertEqual(report["pending_provider_reviews"], 8)
        self.assertEqual(report["evidence_dossiers_for_signoff"], 0)
        self.assertEqual(report["status"], "blocked_no_provider_rights")
        self.assertEqual(report["authorization_records_written"], 0)
        self.assertEqual(report["remote_requests_performed"], 0)
        self.assertFalse(report["runtime_activation_performed"])
        self.assertFalse(report["rights_independently_verified"])
        self.assertTrue(report["manual_source_approval_required"])
        self.assertEqual(
            {row["status"] for row in report["providers"]}, {"pending"}
        )
        self.assertEqual(self.cli("--require-review-ready").returncode, 2)

    def test_fictional_evidence_only_requests_signoff_not_authorization(self):
        provider = self.submitted_fictional_dossier()
        response = self.cli("--require-review-ready")
        self.assertEqual(response.returncode, 0, response.stderr)
        report = json.loads(response.stdout)
        self.assertEqual(report["status"], "manual_independent_review_required")
        self.assertEqual(report["evidence_dossiers_for_signoff"], 1)
        self.assertEqual(report["authorization_records_written"], 0)
        self.assertEqual(report["providers"][0]["status"], "requires_independent_signoff")
        self.assertEqual(self.cli("--expect-pending").returncode, 1)
        for secret in (
            provider["evidence"]["reviewer_id"],
            provider["evidence"]["permission_url"],
            provider["provider_name"],
        ):
            self.assertNotIn(secret, response.stdout)
        self.assertFalse((self.path.parent / "authorization.json").exists())

    def test_missing_right_or_claim_blocks_signoff(self):
        for field in ("metadata_collection", "metadata_display",
                      "metadata_caching", "commercial_use"):
            with self.subTest(field=field):
                self.submitted_fictional_dossier()
                self.document["providers"][0]["rights"][field] = "unknown"
                self.write()
                report = json.loads(self.cli().stdout)
                self.assertEqual(report["providers"][0]["status"], "rights_review_incomplete")
        self.submitted_fictional_dossier()
        self.document["providers"][0]["course_claims"]["certificate_cost"] = "unknown"
        self.write()
        report = json.loads(self.cli().stdout)
        self.assertEqual(report["providers"][0]["status"], "course_claim_review_incomplete")

    def test_prohibited_collection_or_display_blocks_signoff(self):
        for right in ("metadata_collection", "metadata_display", "metadata_caching"):
            with self.subTest(right=right):
                self.submitted_fictional_dossier()
                self.document["providers"][0]["rights"][right] = "prohibited"
                self.write()
                report = json.loads(self.cli().stdout)
                self.assertEqual(report["providers"][0]["status"], "rights_prohibit_planned_use")

    def test_stale_or_future_review_cannot_be_signoff_ready(self):
        self.submitted_fictional_dossier()
        dossier = self.document["providers"][0]["evidence"]
        dossier["expires_at"] = "2020-01-01T00:00:00Z"
        self.write()
        self.assertEqual(json.loads(self.cli().stdout)["providers"][0]["status"],
                         "permission_evidence_stale")
        self.submitted_fictional_dossier()
        dossier = self.document["providers"][0]["evidence"]
        dossier["reviewed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.write()
        self.assertEqual(json.loads(self.cli().stdout)["providers"][0]["status"],
                         "permission_evidence_stale")

    def test_missing_permission_and_undetermined_method_do_not_pass(self):
        self.submitted_fictional_dossier()
        self.document["providers"][0]["evidence"]["permission_basis"] = "unverified"
        for field in ("permission_url", "reviewer_id", "reviewed_at", "expires_at"):
            self.document["providers"][0]["evidence"][field] = None
        self.write()
        self.assertEqual(json.loads(self.cli().stdout)["providers"][0]["status"],
                         "permission_evidence_missing")
        self.submitted_fictional_dossier()
        self.document["providers"][0]["proposed_method"] = "undetermined"
        self.write()
        self.assertEqual(json.loads(self.cli().stdout)["providers"][0]["status"],
                         "collection_method_unverified")

    def test_untrusted_json_duplicate_and_overflow_fail_closed(self):
        self.path.write_text('{"providers":[],"providers":[]}', encoding="utf-8")
        self.assertEqual(self.cli().returncode, 1)
        self.path.write_text('{"value":1e999}', encoding="utf-8")
        self.assertEqual(self.cli().returncode, 1)
        self.path.write_text('{"value":NaN}', encoding="utf-8")
        self.assertEqual(self.cli().returncode, 1)

    def test_pending_record_cannot_smuggle_permissions(self):
        provider = self.document["providers"][0]
        provider["rights"]["metadata_display"] = "permitted"
        self.write()
        self.assertEqual(self.cli("--expect-pending").returncode, 1)
        with self.assertRaises(RightsReviewError):
            audit_dossier(self.document)

    def test_unknown_extra_fields_and_duplicate_ids_rejected(self):
        self.document["providers"][0]["token"] = "never-commit"
        self.write()
        self.assertEqual(self.cli().returncode, 1)
        self.assertNotIn("never-commit", self.cli().stderr)
        self.document = json.loads(SAMPLE.read_text(encoding="utf-8"))
        self.document["providers"][1]["provider_id"] = self.document["providers"][0]["provider_id"]
        self.write()
        self.assertEqual(self.cli().returncode, 1)

    def test_unsafe_evidence_urls_and_unverified_metadata_rejected(self):
        self.submitted_fictional_dossier()
        for url in (
            "http://courses.example.org/terms",
            "https://user:password@courses.example.org/terms",
            "https://courses.example.org/terms?token=secret",
            "https://127.0.0.1/terms",
        ):
            with self.subTest(url=url):
                self.document["providers"][0]["evidence"]["permission_url"] = url
                self.write()
                self.assertEqual(self.cli().returncode, 1)
        self.submitted_fictional_dossier()
        self.document["providers"][0]["evidence"]["permission_basis"] = "unverified"
        self.write()
        self.assertEqual(self.cli().returncode, 1)

    def test_existing_local_file_not_modified_by_read_only_audit(self):
        before = self.path.read_bytes()
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(before, self.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
