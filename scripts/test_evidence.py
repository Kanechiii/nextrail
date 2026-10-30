import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
from nextrail_evidence import EvidenceError, evaluate_claims, recommend_courses


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 30, tzinfo=timezone.utc)
        self.catalog = json.loads((ROOT / "data/catalog.sample.json").read_text())
        self.catalog["providers"][0]["authorization"] = "approved"
        self.catalog["resources"][0]["synthetic"] = False
        self.catalog["resources"][0]["access_cost"] = "free"
        self.catalog["resources"][0]["certificate_cost"] = "paid"
        self.ledger = {"schema_version": "1.0.0", "claims": []}
        for claim, value in (("access_cost", "free"), ("certificate_cost", "paid"),
                             ("availability", "available")):
            self.ledger["claims"].append({
                "resource_id": "example-html-course", "claim": claim, "value": value,
                "source_url": "https://example.org/official",
                "checked_at": "2026-10-29T00:00:00Z",
                "reviewer": "reviewer-sample", "status": "approved"
            })

    def test_current_claims(self):
        self.assertEqual(len(evaluate_claims(self.catalog, self.ledger, now=self.now)), 3)

    def test_free_course_with_paid_certificate(self):
        results = recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now)
        self.assertEqual(results[0]["access_cost"], "free")
        self.assertEqual(results[0]["certificate_cost"], "paid")

    def test_missing_availability(self):
        self.ledger["claims"].pop()
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])

    def test_pending_review(self):
        self.ledger["claims"][0]["status"] = "pending"
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])

    def test_external_source_rejected(self):
        self.ledger["claims"][0]["source_url"] = "https://untrusted.example.net"
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])

    def test_stale_price(self):
        self.ledger["claims"][0]["checked_at"] = "2026-09-01T00:00:00Z"
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])

    def test_future_evidence(self):
        self.ledger["claims"][0]["checked_at"] = "2026-11-01T00:00:00Z"
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])

    def test_synthetic_excluded(self):
        self.catalog["resources"][0]["synthetic"] = True
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])

    def test_unauthorized_provider_excluded(self):
        self.catalog["providers"][0]["authorization"] = "pending"
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])

    def test_duplicate_claim_rejected(self):
        self.ledger["claims"].append(copy.deepcopy(self.ledger["claims"][0]))
        with self.assertRaises(EvidenceError):
            evaluate_claims(self.catalog, self.ledger, now=self.now)

    def test_invalid_timestamp_rejected(self):
        self.ledger["claims"][0]["checked_at"] = "yesterday"
        with self.assertRaises(EvidenceError):
            evaluate_claims(self.catalog, self.ledger, now=self.now)

    def test_unknown_resource_rejected(self):
        self.ledger["claims"][0]["resource_id"] = "fake-course"
        with self.assertRaises(EvidenceError):
            evaluate_claims(self.catalog, self.ledger, now=self.now)

    def test_unknown_skill_rejected(self):
        with self.assertRaises(EvidenceError):
            recommend_courses(self.catalog, self.ledger, skill_id="invented", now=self.now)

    def test_paid_access_not_zero_budget(self):
        self.catalog["resources"][0]["access_cost"] = "paid"
        self.ledger["claims"][0]["value"] = "paid"
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])
        self.assertEqual(len(recommend_courses(
            self.catalog, self.ledger, skill_id="html", zero_budget=False, now=self.now)), 1)

    def test_catalog_mismatch_rejected(self):
        self.catalog["resources"][0]["access_cost"] = "unknown"
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])

    def test_missing_cost_is_not_free(self):
        self.ledger["claims"].pop(0)
        self.assertEqual(recommend_courses(self.catalog, self.ledger, skill_id="html", now=self.now), [])


if __name__ == "__main__":
    unittest.main()
