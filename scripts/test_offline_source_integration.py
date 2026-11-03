"""Offline adapter integration and zero-activation regression tests."""
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

from test_course_pipeline import fixtures


class OfflineSourceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        catalog, registry, submissions, _reviews, _claims = fixtures()
        now = datetime.now(timezone.utc)
        reviewed = (now - timedelta(hours=1)).isoformat()
        expires = (now + timedelta(days=30)).isoformat()
        source = registry["sources"][0]
        self.source_id = source["id"]
        self.catalog = catalog
        self.registry = registry
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
                "reviewed_at": reviewed,
                "expires_at": expires,
            }],
        }
        self.manifest = {
            "schema_version": "1.0.0",
            "batches": [{"source_id": source["id"], "format": "manual",
                         "path": "snapshot.json"}],
        }
        self.snapshot = submissions[source["id"]]
        self.flush()

    def write(self, name, value):
        (self.folder / name).write_text(json.dumps(value), encoding="utf-8")

    def flush(self):
        self.write("base.json", self.catalog)
        self.write("sources.json", self.registry)
        self.write("auth.json", self.authorization)
        self.write("manifest.json", self.manifest)
        self.write("snapshot.json", self.snapshot)

    def run_preflight(self, *flags, sample=False):
        directory = ROOT / "data" if sample else self.folder
        if sample:
            names = (
                "catalog.sample.json", "sources.sample.json",
                "provider-authorizations.sample.json",
                "course-publication.manifest.sample.json",
            )
        else:
            names = ("base.json", "sources.json", "auth.json", "manifest.json")
        command = [
            sys.executable, str(ROOT / "scripts/verify_offline_source_integration.py"),
            "--base-catalog", str(directory / names[0]),
            "--sources", str(directory / names[1]),
            "--authorizations", str(directory / names[2]),
            "--manifest", str(directory / names[3]), *flags,
        ]
        return subprocess.run(command, text=True, capture_output=True,
                              check=False, cwd=ROOT, timeout=30)

    def test_checked_in_sample_has_no_authorized_sources_or_candidates(self):
        response = self.run_preflight("--expect-empty", sample=True)
        self.assertEqual(response.returncode, 0, response.stderr)
        report = json.loads(response.stdout)
        self.assertEqual(report["status"], "blocked_no_authorized_sources")
        self.assertEqual(report["current_authorization_assertions"], 0)
        self.assertEqual(report["submitted_snapshot_count"], 0)
        self.assertEqual(report["normalized_course_candidates"], 0)
        self.assertTrue(report["manual_provider_rights_review_required"])
        self.assertFalse(report["course_publication_permitted"])
        self.assertFalse(report["runtime_activation_performed"])
        self.assertEqual(report["remote_requests_performed"], 0)
        self.assertEqual(report["catalog_files_written"], 0)
        self.assertEqual(self.run_preflight("--require-candidates", sample=True).returncode, 2)

    def test_fictional_manual_snapshot_needs_independent_course_review(self):
        response = self.run_preflight("--require-candidates")
        self.assertEqual(response.returncode, 0, response.stderr)
        report = json.loads(response.stdout)
        self.assertEqual(report["current_authorization_assertions"], 1)
        self.assertEqual(report["submitted_snapshot_count"], 1)
        self.assertEqual(report["normalized_course_candidates"], 1)
        self.assertEqual(report["status"], "manual_course_evidence_review_required")
        self.assertEqual(report["sources"][0]["integration_method"], "manual")
        self.assertEqual(report["sources"][0]["status"],
                         "snapshot_normalized_pending_course_review")
        self.assertFalse(report["permissions_independently_verified"])
        self.assertFalse(report["listing_claims_independently_verified"])
        self.assertFalse(report["course_publication_permitted"])
        self.assertNotIn("permission_url", response.stdout)
        self.assertNotIn("fictional-reviewer", response.stdout)
        self.assertEqual(self.run_preflight("--expect-empty").returncode, 1)
        self.assertFalse((self.folder / "published.json").exists())

    def test_local_official_api_export_uses_curated_manual_contract(self):
        self.registry["sources"][0]["method"] = "official_api"
        self.authorization["authorizations"][0]["method"] = "official_api"
        self.flush()
        response = self.run_preflight()
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)["sources"][0]["integration_method"],
                         "official_api")

    def test_local_rss_feed_requires_curated_annotations(self):
        self.registry["sources"][0]["method"] = "rss"
        self.authorization["authorizations"][0]["method"] = "rss"
        self.manifest["batches"][0] = {
            "source_id": self.source_id,
            "format": "rss", "feed_path": "feed.xml",
            "annotations_path": "annotations.json",
        }
        self.write("annotations.json", {
            "intro-html": {"skills": ["html"], "prerequisites": []},
        })
        (self.folder / "feed.xml").write_bytes(
            b"<rss><channel><item><guid>intro-html</guid>"
            b"<title>Fictional HTML</title>"
            b"<link>https://courses.example.org/learn-html</link>"
            b"</item></channel></rss>"
        )
        self.flush()
        self.assertEqual(self.run_preflight().returncode, 0)
        self.assertEqual(json.loads(self.run_preflight().stdout)
                         ["normalized_course_candidates"], 1)
        (self.folder / "feed.xml").write_bytes(
            b'<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b"<rss><channel><item><guid>&xxe;</guid></item></channel></rss>"
        )
        response = self.run_preflight()
        self.assertEqual(response.returncode, 1)
        self.assertEqual(response.stdout, "")

    def test_missing_expired_revoked_or_scope_mismatched_permission_rejected(self):
        original = copy.deepcopy(self.authorization)
        for mode in ("missing", "expired", "revoked", "wrong-method"):
            with self.subTest(mode=mode):
                self.authorization = copy.deepcopy(original)
                row = self.authorization["authorizations"][0]
                if mode == "missing":
                    self.authorization["authorizations"] = []
                elif mode == "expired":
                    row["expires_at"] = "2020-01-01T00:00:00Z"
                elif mode == "revoked":
                    row["status"] = "revoked"
                else:
                    row["method"] = "official_api"
                self.flush()
                response = self.run_preflight()
                self.assertEqual(response.returncode, 1, response.stdout)
                self.assertEqual(response.stdout, "")

    def test_approved_source_without_snapshot_reports_missing_evidence(self):
        self.manifest["batches"] = []
        self.flush()
        response = self.run_preflight()
        self.assertEqual(response.returncode, 0, response.stderr)
        report = json.loads(response.stdout)
        self.assertEqual(report["status"], "awaiting_offline_snapshot")
        self.assertEqual(report["normalized_course_candidates"], 0)
        self.assertEqual(report["sources"][0]["status"], "awaiting_offline_snapshot")
        self.assertEqual(self.run_preflight("--require-candidates").returncode, 2)

    def test_unapproved_snapshot_is_blocked_before_read(self):
        self.registry["sources"][0]["authorization"] = "pending"
        self.authorization["authorizations"] = []
        self.flush()
        response = self.run_preflight()
        self.assertEqual(response.returncode, 1)
        self.assertEqual(response.stdout, "")

    def test_unknown_skill_and_duplicate_source_record_fail_closed(self):
        original = copy.deepcopy(self.snapshot)
        self.snapshot["records"][0]["skills"] = ["not-reviewed"]
        self.flush()
        self.assertEqual(self.run_preflight().returncode, 1)
        self.snapshot = copy.deepcopy(original)
        self.snapshot["records"].append(copy.deepcopy(self.snapshot["records"][0]))
        self.flush()
        self.assertEqual(self.run_preflight().returncode, 1)

    def test_unsafe_manifest_path_and_duplicate_json_fail_closed(self):
        self.manifest["batches"][0]["path"] = "../outside.json"
        self.flush()
        self.assertEqual(self.run_preflight().returncode, 1)
        self.manifest["batches"][0]["path"] = "snapshot.json"
        self.flush()
        (self.folder / "snapshot.json").write_text(
            '{"source_id":"x","records":[],"records":[]}', encoding="utf-8"
        )
        self.assertEqual(self.run_preflight().returncode, 1)

    def test_preflight_is_read_only_and_does_not_create_a_release(self):
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()
                  if p.is_file()}
        response = self.run_preflight()
        self.assertEqual(response.returncode, 0, response.stderr)
        after = {p.name: p.read_bytes() for p in self.folder.iterdir()
                 if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
