"""Phase 19: pinned release activation, freshness, owner isolation and offline gates."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_api import create_app
from nextrail_api.release import ReleaseError, load_reviewed_bundle, validate_reviewed_bundle
from nextrail_api.settings import ConfigurationError, reviewed_catalog_from_env
from nextrail_auth import AccountStore
from nextrail_auth.preferences import AccountPreferencesStore
from nextrail_discovery.pipeline import build_reviewed_catalog
from nextrail_storage import open_database
from test_course_pipeline import NOW, fixtures

PASSWORD = "test-local-release-password123"


def snapshot():
    return build_reviewed_catalog(*fixtures(), now=NOW)


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.path = self.parent / "reviewed.json"
        self.data = snapshot()
        self.clock = [NOW]

    def write(self, value=None):
        payload = self.data if value is None else value
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def load(self, data=None):
        digest = self.write(data)
        return load_reviewed_bundle(self.path, digest, now=self.clock[0])

    def test_valid_reviewed_bundle_passes(self):
        release = self.load()
        self.assertEqual(release.reviewed_course_count, 1)
        self.assertEqual(release.current_catalog(now=NOW)["resources"][0]["access_cost"], "free")
        self.assertGreater(release.expires_at, NOW)

    def test_existing_phase16_output_accepted_unchanged(self):
        release = self.load()
        self.assertEqual(release.current_catalog(now=NOW), self.data["catalog"])

    def test_sha256_mismatch_rejected(self):
        self.write()
        with self.assertRaises(ReleaseError):
            load_reviewed_bundle(self.path, "0" * 64, now=NOW)

    def test_sha256_uppercase_and_invalid_rejected(self):
        self.write()
        for sha in ("A" * 64, "abc", "", None):
            with self.subTest(sha=sha), self.assertRaises(ReleaseError):
                load_reviewed_bundle(self.path, sha, now=NOW)

    def test_mutated_file_rejected_with_original_pin(self):
        digest = self.write()
        self.path.write_bytes(self.path.read_bytes() + b" ")
        with self.assertRaises(ReleaseError):
            load_reviewed_bundle(self.path, digest, now=NOW)

    def test_missing_or_symlinked_input_rejected(self):
        digest = self.write()
        missing = self.parent / "missing.json"
        with self.assertRaises(ReleaseError):
            load_reviewed_bundle(missing, digest, now=NOW)
        link = self.parent / "linked.json"
        try:
            link.symlink_to(self.path)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink unavailable on this operating system")
        with self.assertRaises(ReleaseError):
            load_reviewed_bundle(link, digest, now=NOW)

    def test_oversized_snapshot_rejected(self):
        self.path.write_bytes(b" " * 2_000_001)
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaises(ReleaseError):
            load_reviewed_bundle(self.path, digest, now=NOW)

    def test_duplicate_json_keys_rejected_even_when_hash_matches(self):
        raw = b'{"schema_version":"1.0.0","schema_version":"1.0.0"}'
        self.path.write_bytes(raw)
        with self.assertRaises(ReleaseError):
            load_reviewed_bundle(
                self.path, hashlib.sha256(raw).hexdigest(), now=NOW
            )

    def test_invalid_bundle_document_rejected(self):
        doc = copy.deepcopy(self.data)
        doc["unknown"] = "metadata"
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_synthetic_resource_rejected(self):
        doc = copy.deepcopy(self.data)
        doc["catalog"]["resources"][0]["synthetic"] = True
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_unapproved_provider_rejected(self):
        doc = copy.deepcopy(self.data)
        doc["catalog"]["providers"][0]["authorization"] = "pending"
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_tampered_catalog_resource_rejected(self):
        doc = copy.deepcopy(self.data)
        doc["catalog"]["resources"][0]["id"] = "another-course"
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_unofficial_resource_host_rejected(self):
        doc = copy.deepcopy(self.data)
        doc["catalog"]["resources"][0]["url"] = "https://other.example.net/course"
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_missing_provenance_rejected(self):
        doc = copy.deepcopy(self.data)
        doc["provenance"] = {}
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_missing_required_claim_rejected(self):
        doc = copy.deepcopy(self.data)
        rid = doc["catalog"]["resources"][0]["id"]
        item = doc["provenance"][rid]
        item["verified_claims"].remove("access_cost")
        item["claim_evidence"].pop("access_cost")
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_unknown_certificate_fee_is_preserved(self):
        release = self.load()
        resource = release.current_catalog(now=NOW)["resources"][0]
        self.assertEqual(resource["certificate_cost"], "unknown")

    def test_fabricated_certificate_claim_rejected(self):
        doc = copy.deepcopy(self.data)
        doc["catalog"]["resources"][0]["certificate_cost"] = "free"
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_listing_age_limit_enforced(self):
        doc = copy.deepcopy(self.data)
        rid = doc["catalog"]["resources"][0]["id"]
        doc["provenance"][rid]["listing_reviewed_at"] = "2026-01-01T00:00:00Z"
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_access_cost_age_limit_enforced(self):
        doc = copy.deepcopy(self.data)
        rid = doc["catalog"]["resources"][0]["id"]
        doc["provenance"][rid]["claim_evidence"]["access_cost"]["checked_at"] = (
            "2026-09-01T00:00:00Z"
        )
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_availability_age_limit_enforced(self):
        doc = copy.deepcopy(self.data)
        rid = doc["catalog"]["resources"][0]["id"]
        doc["provenance"][rid]["claim_evidence"]["availability"]["checked_at"] = (
            "2026-10-01T00:00:00Z"
        )
        doc["catalog"]["resources"][0]["evidence"]["checked_at"] = (
            "2026-10-01T00:00:00Z"
        )
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_future_dated_claim_rejected(self):
        doc = copy.deepcopy(self.data)
        rid = doc["catalog"]["resources"][0]["id"]
        doc["provenance"][rid]["listing_reviewed_at"] = "2026-11-03T00:00:00Z"
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_conflicting_availability_provenance_rejected(self):
        doc = copy.deepcopy(self.data)
        doc["catalog"]["resources"][0]["evidence"]["source_url"] = (
            "https://courses.example.org/other"
        )
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_report_count_mismatch_rejected(self):
        doc = copy.deepcopy(self.data)
        doc["review_report"]["published"] = 0
        with self.assertRaises(ReleaseError):
            self.load(doc)

    def test_release_expires_after_startup(self):
        release = self.load()
        with self.assertRaises(ReleaseError):
            release.current_catalog(now=NOW + timedelta(days=8))

    def test_naive_clock_rejected(self):
        with self.assertRaises(ReleaseError):
            validate_reviewed_bundle(self.data, now=datetime(2026, 11, 1))

    def test_empty_phase16_dry_run_allowed_without_releasing_courses(self):
        base = json.loads((ROOT / "data/catalog.sample.json").read_text())
        registry = json.loads((ROOT / "data/sources.sample.json").read_text())
        empty = build_reviewed_catalog(
            base, registry, {}, [], {"schema_version": "1.0.0", "claims": []}, now=NOW
        )
        release = self.load(empty)
        self.assertEqual(release.reviewed_course_count, 0)
        self.assertEqual(release.current_catalog(now=NOW)["resources"], [])


class ReviewedRuntimeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "reviewed.json"
        raw = json.dumps(snapshot(), sort_keys=True).encode("utf-8")
        self.path.write_bytes(raw)
        self.sha = hashlib.sha256(raw).hexdigest()
        self.clock = [NOW]
        self.app = create_app(
            reviewed_catalog_path=self.path,
            reviewed_catalog_sha256=self.sha,
            release_clock=lambda: self.clock[0],
        )
        self.ctx = TestClient(self.app)
        self.client = self.ctx.__enter__()
        self.addCleanup(lambda: self.ctx.__exit__(None, None, None))

    def test_ready_reports_reviewed_mode_without_private_records(self):
        result = self.client.get("/ready")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {
            "status": "ready", "catalog_mode": "reviewed_snapshot",
            "reviewed_course_count": 1,
        })
        self.assertNotIn("reviewer", result.text)
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_guest_course_discovery_serves_reviewed_course_without_account(self):
        result = self.client.get("/v1/courses", params={"query": "HTML"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual([x["id"] for x in result.json()["items"]],
                         ["example-training-intro-html"])

    def test_guest_preview_uses_verified_free_course_from_reviewed_release(self):
        res = self.client.post("/v1/pathways/preview", json={
            "career_goal": "Frontend developer", "target_skill_ids": ["html"],
            "zero_budget": True,
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json()["milestones"][0]["resource_ids"],
            ["example-training-intro-html"],
        )

    def test_saved_zero_budget_pathway_retains_reviewed_free_course(self):
        registration = self.client.post("/v1/auth/register", json={
            "email": "student-path@example.org", "password": PASSWORD,
        })
        self.assertEqual(registration.status_code, 201)
        token = self.client.post("/v1/auth/login", json={
            "email": "student-path@example.org", "password": PASSWORD,
        }).json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        result = self.client.post("/v1/me/pathways", headers=headers, json={
            "career_goal": "Frontend developer",
            "target_skill_ids": ["html"],
            "zero_budget": True,
        })
        self.assertEqual(result.status_code, 201, result.text)
        milestone = result.json()["pathway"]["milestones"][0]
        self.assertEqual(milestone["resource_ids"], ["example-training-intro-html"])
        fetched = self.client.get(
            "/v1/me/pathways/" + result.json()["id"], headers=headers,
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(
            fetched.json()["milestones"][0]["resource_ids"],
            ["example-training-intro-html"],
        )

    def test_existing_auth_and_saved_courses_work_with_reviewed_catalog(self):
        register = self.client.post("/v1/auth/register", json={
            "email": "release@example.org", "password": PASSWORD,
        })
        self.assertEqual(register.status_code, 201)
        token = self.client.post("/v1/auth/login", json={
            "email": "release@example.org", "password": PASSWORD,
        }).json()["access_token"]
        h = {"Authorization": "Bearer " + token}
        saved = self.client.put(
            "/v1/me/courses/example-training-intro-html", headers=h
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get("/v1/me/courses", headers=h).json()["resource_ids"],
                         ["example-training-intro-html"])

    def test_freshness_expiry_blocks_catalog_routes_not_account_login(self):
        self.clock[0] += timedelta(days=8)
        self.assertEqual(self.client.get("/ready").status_code, 503)
        self.assertEqual(self.client.get("/v1/courses").status_code, 503)
        self.assertEqual(self.client.get("/v1/skills").status_code, 503)
        self.assertEqual(self.client.post("/v1/pathways/preview", json={
            "career_goal": "Frontend", "target_skill_ids": ["html"],
        }).status_code, 503)
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.post("/v1/auth/register", json={
            "email": "still@example.org", "password": PASSWORD,
        }).status_code, 201)

    def test_missing_catalog_config_pair_rejected(self):
        with self.assertRaises(ReleaseError):
            create_app(reviewed_catalog_path=self.path)

    def test_injected_catalog_cannot_override_reviewed_bundle(self):
        catalog = json.loads((ROOT / "data/catalog.sample.json").read_text())
        with self.assertRaises(ReleaseError):
            create_app(
                catalog=catalog,
                reviewed_catalog_path=self.path, reviewed_catalog_sha256=self.sha,
            )

    def test_default_app_remains_guest_first_and_sample_mode(self):
        with TestClient(create_app()) as test:
            self.assertEqual(test.get("/ready").json()["catalog_mode"], "sample")
            self.assertEqual(test.get("/v1/courses").status_code, 200)
            self.assertEqual(test.get("/v1/courses").json()["items"], [])


class ReleaseConfigurationTests(unittest.TestCase):
    def test_default_mode_unconfigured(self):
        self.assertEqual(reviewed_catalog_from_env({}), (None, None))

    def test_partial_configuration_rejected(self):
        for value in (
            {"NEXTRAIL_REVIEWED_CATALOG_PATH": "local.json"},
            {"NEXTRAIL_REVIEWED_CATALOG_SHA256": "0" * 64},
        ):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                reviewed_catalog_from_env(value)

    def test_bad_sha256_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "release.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                reviewed_catalog_from_env({
                    "NEXTRAIL_REVIEWED_CATALOG_PATH": str(path),
                    "NEXTRAIL_REVIEWED_CATALOG_SHA256": "B" * 64,
                })

    def test_valid_configuration_is_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "release.json"
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(reviewed_catalog_from_env({
                "NEXTRAIL_REVIEWED_CATALOG_PATH": str(path),
                "NEXTRAIL_REVIEWED_CATALOG_SHA256": "b" * 64,
            }), (str(path), "b" * 64))


class ReleasePreflightCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.bundle = self.parent / "reviewed.json"
        # Preflight is deliberately real-time; create fresh test evidence so
        # the regression stays deterministic across future CI calendar dates.
        now = datetime.now(timezone.utc)
        base, registry, submissions, reviews, claims = fixtures()
        fresh = now.isoformat()
        for review in reviews:
            review["checked_at"] = fresh
        for claim in claims["claims"]:
            claim["checked_at"] = fresh
        payload = build_reviewed_catalog(
            base, registry, submissions, reviews, claims, now=now
        )
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.bundle.write_bytes(raw)
        self.sha = hashlib.sha256(raw).hexdigest()

    def invoke(self, *extra):
        return subprocess.run([
            sys.executable, str(ROOT / "scripts/verify_release.py"),
            "--bundle", str(self.bundle),
            "--sha256", self.sha, *extra,
        ], cwd=ROOT, capture_output=True, text=True, check=False)

    def test_offline_preflight_with_valid_release(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS: Pinned reviewed catalog", result.stdout)
        self.assertIn("No network requests", result.stdout)

    def test_preflight_refuses_bad_hash(self):
        self.bundle.write_bytes(self.bundle.read_bytes() + b"\n")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PASS", result.stdout)

    def test_preflight_optionally_checks_existing_database(self):
        path = self.parent / "learning.sqlite"
        conn = open_database(path)
        try:
            AccountStore(conn)
            AccountPreferencesStore(conn)
        finally:
            conn.close()
        result = self.invoke("--database", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SQLite integrity", result.stdout)
        self.assertTrue(path.is_file())

    def test_preflight_rejects_missing_database_without_creating_it(self):
        absent = self.parent / "absent.sqlite"
        result = self.invoke("--database", str(absent))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(absent.exists())


if __name__ == "__main__":
    unittest.main()
