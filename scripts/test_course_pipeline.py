"""Offline reviewed-course publication regression tests, including negative gates."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_discovery import SourceContractError, discover_courses
from nextrail_discovery.pipeline import PublicationError, build_reviewed_catalog
from validate_catalog import validate

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
REVIEWED = "2026-10-31T12:00:00Z"
COURSE_ID = "example-training-intro-html"
COURSE_URL = "https://courses.example.org/learn-html"


def fixtures():
    registry = {
        "schema_version": "1.0.0",
        "sources": [{
            "id": "example-manual-one",
            "provider_id": "example-training",
            "provider_name": "Illustrative provider used only in tests",
            "provider_website": "https://courses.example.org",
            "source_url": "https://courses.example.org/approved-catalog",
            "method": "manual",
            "authorization": "approved",
            "allowed_hosts": ["courses.example.org"],
            "synthetic": False,
        }],
    }
    manual = {"source_id": "example-manual-one", "records": [{
        "external_id": "intro-html",
        "title": "Illustrative HTML course — test only",
        "url": COURSE_URL,
        "skills": ["html"],
        "prerequisites": [],
    }]}
    review = [{
        "resource_id": COURSE_ID,
        "source_id": "example-manual-one",
        "status": "approved",
        "reviewer": "human-reviewer-example",
        "checked_at": REVIEWED,
        "evidence_url": COURSE_URL,
    }]
    claims = {"schema_version": "1.0.0", "claims": [
        {
            "resource_id": COURSE_ID, "claim": claim, "value": value,
            "source_url": COURSE_URL,
            "checked_at": REVIEWED,
            "reviewer": "human-reviewer-example", "status": "approved",
        } for claim, value in [
            ("access_cost", "free"), ("availability", "available")
        ]
    ]}
    catalog = json.loads((ROOT / "data/catalog.sample.json").read_text(encoding="utf-8"))
    return catalog, registry, {"example-manual-one": manual}, review, claims


class ReviewedCoursePipelineTests(unittest.TestCase):
    def compile(self, inputs=None, now=NOW):
        return build_reviewed_catalog(*(fixtures() if inputs is None else inputs), now=now)

    def test_empty_registry_submissions_never_publish_sample_courses(self):
        base = json.loads((ROOT / "data/catalog.sample.json").read_text())
        reg = json.loads((ROOT / "data/sources.sample.json").read_text())
        result = build_reviewed_catalog(
            base, reg, {}, [], {"schema_version": "1.0.0", "claims": []}, now=NOW
        )
        self.assertEqual(result["catalog"]["resources"], [])
        self.assertEqual(result["catalog"]["providers"], [])
        self.assertEqual(result["review_report"]["published"], 0)

    def test_current_approved_listing_and_claims_publish(self):
        result = self.compile()
        rows = result["catalog"]["resources"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], COURSE_ID)
        self.assertEqual(rows[0]["access_cost"], "free")
        self.assertEqual(rows[0]["certificate_cost"], "unknown")
        self.assertEqual(rows[0]["evidence"]["status"], "verified")
        self.assertFalse(rows[0]["synthetic"])
        self.assertEqual(result["provenance"][COURSE_ID]["source_ids"], ["example-manual-one"])
        self.assertEqual(validate(result["catalog"]), [])

    def test_guest_search_returns_only_reviewed_published_course(self):
        catalog = self.compile()["catalog"]
        rows = discover_courses(catalog, query="HTML", access_cost="free")
        self.assertEqual([row["id"] for row in rows], [COURSE_ID])
        self.assertEqual(rows[0]["certificate_cost"], "unknown")

    def test_missing_listing_review_excludes_course(self):
        base, registry, data, reviews, ledger = fixtures()
        result = self.compile((base, registry, data, [], ledger))
        self.assertEqual(result["review_report"]["excluded_reasons"], {
            "missing_listing_review": 1
        })
        self.assertEqual(result["catalog"]["resources"], [])

    def test_listing_pending_cannot_publish(self):
        values = list(fixtures())
        values[3][0]["status"] = "pending"
        self.assertEqual(self.compile(values)["review_report"]["excluded_reasons"], {
            "listing_not_approved": 1
        })

    def test_listing_rejected_cannot_publish(self):
        values = list(fixtures())
        values[3][0]["status"] = "rejected"
        self.assertFalse(self.compile(values)["catalog"]["resources"])

    def test_listing_older_than_ninety_days_excluded(self):
        values = list(fixtures())
        values[3][0]["checked_at"] = "2026-01-01T00:00:00Z"
        self.assertEqual(self.compile(values)["review_report"]["excluded_reasons"], {
            "listing_review_stale": 1
        })

    def test_future_listing_review_excluded(self):
        values = list(fixtures())
        values[3][0]["checked_at"] = "2026-11-02T00:00:00Z"
        self.assertEqual(self.compile(values)["review_report"]["excluded_reasons"], {
            "listing_review_stale": 1
        })

    def test_missing_availability_excludes_course(self):
        values = list(fixtures())
        values[4]["claims"] = [x for x in values[4]["claims"] if x["claim"] != "availability"]
        self.assertEqual(self.compile(values)["review_report"]["excluded_reasons"], {
            "availability_not_verified": 1
        })

    def test_unavailable_course_is_not_published(self):
        values = list(fixtures())
        values[4]["claims"][1]["value"] = "unavailable"
        self.assertEqual(self.compile(values)["catalog"]["resources"], [])

    def test_stale_availability_is_not_published(self):
        values = list(fixtures())
        values[4]["claims"][1]["checked_at"] = "2026-10-20T00:00:00Z"
        self.assertEqual(self.compile(values)["catalog"]["resources"], [])

    def test_future_availability_is_not_published(self):
        values = list(fixtures())
        values[4]["claims"][1]["checked_at"] = "2026-11-02T00:00:00Z"
        self.assertEqual(self.compile(values)["catalog"]["resources"], [])

    def test_missing_access_cost_is_not_assumed_free(self):
        values = list(fixtures())
        values[4]["claims"] = [x for x in values[4]["claims"] if x["claim"] != "access_cost"]
        self.assertEqual(self.compile(values)["review_report"]["excluded_reasons"], {
            "access_cost_not_verified": 1
        })

    def test_pending_access_cost_cannot_publish(self):
        values = list(fixtures())
        values[4]["claims"][0]["status"] = "pending"
        self.assertEqual(self.compile(values)["catalog"]["resources"], [])

    def test_stale_access_cost_cannot_publish(self):
        values = list(fixtures())
        values[4]["claims"][0]["checked_at"] = "2026-09-01T00:00:00Z"
        self.assertEqual(self.compile(values)["catalog"]["resources"], [])

    def test_certificate_cost_is_independently_reviewed(self):
        values = list(fixtures())
        certificate = copy.deepcopy(values[4]["claims"][0])
        certificate.update({"claim": "certificate_cost", "value": "paid"})
        values[4]["claims"].append(certificate)
        result = self.compile(values)
        self.assertEqual(result["catalog"]["resources"][0]["certificate_cost"], "paid")
        self.assertIn("certificate_cost", result["provenance"][COURSE_ID]["verified_claims"])

    def test_stale_certificate_cost_returns_unknown(self):
        values = list(fixtures())
        certificate = copy.deepcopy(values[4]["claims"][0])
        certificate.update({
            "claim": "certificate_cost", "value": "free",
            "checked_at": "2026-09-01T00:00:00Z",
        })
        values[4]["claims"].append(certificate)
        self.assertEqual(self.compile(values)["catalog"]["resources"][0]["certificate_cost"], "unknown")

    def test_unofficial_availability_evidence_cannot_publish(self):
        values = list(fixtures())
        values[4]["claims"][1]["source_url"] = "https://impostor.example.net/offer"
        self.assertEqual(self.compile(values)["catalog"]["resources"], [])

    def test_unofficial_listing_evidence_fails_closed(self):
        values = list(fixtures())
        values[3][0]["evidence_url"] = "https://impostor.example.net/offer"
        with self.assertRaises(SourceContractError):
            self.compile(values)

    def test_unknown_source_submission_rejected(self):
        values = list(fixtures())
        values[2]["unregistered-source"] = values[2].pop("example-manual-one")
        with self.assertRaises(PublicationError):
            self.compile(values)

    def test_pending_source_cannot_enter_public_pipeline(self):
        values = list(fixtures())
        values[1]["sources"][0]["authorization"] = "pending"
        with self.assertRaises(SourceContractError):
            self.compile(values)

    def test_synthetic_source_cannot_enter_public_pipeline(self):
        values = list(fixtures())
        values[1]["sources"][0]["synthetic"] = True
        with self.assertRaises(SourceContractError):
            self.compile(values)

    def test_wrong_record_host_rejected(self):
        values = list(fixtures())
        values[2]["example-manual-one"]["records"][0]["url"] = "https://other.example.net/learn"
        with self.assertRaises(SourceContractError):
            self.compile(values)

    def test_unknown_skill_rejected(self):
        values = list(fixtures())
        values[2]["example-manual-one"]["records"][0]["skills"] = ["invented"]
        with self.assertRaises(SourceContractError):
            self.compile(values)

    def test_duplicate_review_rejected(self):
        values = list(fixtures())
        values[3].append(copy.deepcopy(values[3][0]))
        with self.assertRaises(PublicationError):
            self.compile(values)

    def test_unknown_review_reference_rejected(self):
        values = list(fixtures())
        values[3][0]["resource_id"] = "invented-course"
        with self.assertRaises(PublicationError):
            self.compile(values)

    def test_duplicate_evidence_claim_rejected(self):
        values = list(fixtures())
        values[4]["claims"].append(copy.deepcopy(values[4]["claims"][0]))
        with self.assertRaises(PublicationError):
            self.compile(values)

    def test_timezone_naive_clock_rejected(self):
        with self.assertRaises(PublicationError):
            self.compile(now=datetime(2026, 11, 1))

    def test_does_not_mutate_inputs(self):
        values = fixtures()
        before = copy.deepcopy(values)
        self.compile(values)
        self.assertEqual(values, before)

    def test_stable_output_for_same_snapshot_and_clock(self):
        self.assertEqual(self.compile(), self.compile())

    def test_exact_duplicates_collapse_with_both_sources_preserved(self):
        values = list(fixtures())
        second = copy.deepcopy(values[1]["sources"][0])
        second["id"] = "example-manual-two"
        second["source_url"] = "https://courses.example.org/second-source"
        values[1]["sources"].append(second)
        second_batch = copy.deepcopy(values[2]["example-manual-one"])
        second_batch["source_id"] = "example-manual-two"
        values[2]["example-manual-two"] = second_batch
        result = self.compile(values)
        self.assertEqual(len(result["catalog"]["resources"]), 1)
        self.assertEqual(result["review_report"]["exact_duplicates_collapsed"], 1)
        self.assertEqual(
            result["provenance"][COURSE_ID]["source_ids"],
            ["example-manual-one", "example-manual-two"],
        )

    def test_conflicting_duplicate_id_rejected(self):
        values = list(fixtures())
        second = copy.deepcopy(values[1]["sources"][0])
        second["id"] = "example-manual-two"
        values[1]["sources"].append(second)
        second_batch = copy.deepcopy(values[2]["example-manual-one"])
        second_batch["source_id"] = "example-manual-two"
        second_batch["records"][0]["title"] = "Conflicting title"
        values[2]["example-manual-two"] = second_batch
        with self.assertRaises(PublicationError):
            self.compile(values)

    def test_same_url_different_id_rejected(self):
        values = list(fixtures())
        second = copy.deepcopy(values[1]["sources"][0])
        second["id"] = "example-manual-two"
        values[1]["sources"].append(second)
        second_batch = copy.deepcopy(values[2]["example-manual-one"])
        second_batch["source_id"] = "example-manual-two"
        second_batch["records"][0]["external_id"] = "different-id"
        values[2]["example-manual-two"] = second_batch
        with self.assertRaises(PublicationError):
            self.compile(values)


class OfflinePublisherCLITests(unittest.TestCase):
    def run_publisher(self, output, manifest=None):
        arguments = [
            sys.executable, str(ROOT / "scripts/publish_course_catalog.py"),
            "--base-catalog", str(ROOT / "data/catalog.sample.json"),
            "--sources", str(ROOT / "data/sources.sample.json"),
            "--manifest", str(manifest or ROOT / "data/course-publication.manifest.sample.json"),
            "--listing-reviews", str(ROOT / "data/course-publication.reviews.sample.json"),
            "--claims", str(ROOT / "data/evidence.sample.json"),
            "--output", str(output),
        ]
        return subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, check=False)

    def test_sample_manifest_outputs_no_public_courses(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "reviewed.json"
            proc = self.run_publisher(output)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["review_report"]["published"], 0)
            self.assertEqual(result["catalog"]["resources"], [])
            self.assertNotIn("https://example.org/html", str(result))

    def test_existing_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "reviewed.json"
            output.write_text("preserve", encoding="utf-8")
            self.assertNotEqual(self.run_publisher(output).returncode, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "preserve")

    def test_manifest_cannot_read_parent_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inner = root / "manifests"
            inner.mkdir()
            parent_file = root / "secret.json"
            parent_file.write_text("{}", encoding="utf-8")
            manifest = inner / "batches.json"
            manifest.write_text(json.dumps({
                "schema_version": "1.0.0",
                "batches": [{"source_id": "example-manual-source",
                             "format": "manual", "path": "../secret.json"}]
            }), encoding="utf-8")
            result = self.run_publisher(inner / "out.json", manifest)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((inner / "out.json").exists())


if __name__ == "__main__":
    unittest.main()
