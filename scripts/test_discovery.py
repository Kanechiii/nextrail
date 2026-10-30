import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
from nextrail_discovery import (
    SourceContractError, assemble_catalog, discover_courses,
    load_registry, normalize_manual, normalize_feed,
)


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = load_registry(json.loads((ROOT / "data/sources.sample.json").read_text()))
        cls.catalog = json.loads((ROOT / "data/catalog.sample.json").read_text())
        cls.manual = json.loads((ROOT / "data/discovery.manual.sample.json").read_text())
        cls.feed = (ROOT / "data/discovery.feed.sample.xml").read_bytes()
        cls.annotations = json.loads((ROOT / "data/discovery.feed.annotations.sample.json").read_text())
        cls.skills = {s["id"] for s in cls.catalog["skills"]}

    def build(self):
        first = normalize_manual(self.sources[0], self.manual, self.skills, preview=True)
        second = normalize_feed(self.sources[1], self.feed, self.annotations, self.skills, preview=True)
        return assemble_catalog(self.catalog, [(self.sources[0], *first), (self.sources[1], *second)])

    def test_manual_normalization(self):
        rows, evidence = normalize_manual(self.sources[0], self.manual, self.skills, preview=True)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["access_cost"] == "unknown" for r in rows))
        self.assertEqual(len(evidence), 2)

    def test_rss_normalization(self):
        rows, _ = normalize_feed(self.sources[1], self.feed, self.annotations, self.skills, preview=True)
        self.assertEqual(rows[0]["id"], "example-feed-intro-js")

    def test_catalog_shape(self):
        catalog, evidence = self.build()
        self.assertEqual(len(catalog["resources"]), 3)
        self.assertEqual(len(evidence), 3)

    def test_guest_search_preview(self):
        catalog, _ = self.build()
        rows = discover_courses(catalog, query="html", include_synthetic=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["certificate_cost"], "unknown")

    def test_guest_search_hidden_synthetic(self):
        catalog, _ = self.build()
        self.assertEqual(discover_courses(catalog), [])

    def test_skill_and_provider_filters(self):
        catalog, _ = self.build()
        self.assertEqual(len(discover_courses(catalog, skill_id="css", include_synthetic=True)), 1)
        self.assertEqual(len(discover_courses(catalog, provider_id="example-feed", include_synthetic=True)), 1)

    def test_no_account_required(self):
        catalog, _ = self.build()
        self.assertIsInstance(discover_courses(catalog, include_synthetic=True), list)

    def test_pending_source_rejected(self):
        with self.assertRaises(SourceContractError):
            normalize_manual(self.sources[0], self.manual, self.skills)

    def test_wrong_host_rejected(self):
        doc = copy.deepcopy(self.manual)
        doc["records"][0]["url"] = "https://unapproved.example.com/course"
        with self.assertRaises(SourceContractError):
            normalize_manual(self.sources[0], doc, self.skills, preview=True)

    def test_unknown_skill_rejected(self):
        doc = copy.deepcopy(self.manual)
        doc["records"][0]["skills"] = ["made-up"]
        with self.assertRaises(SourceContractError):
            normalize_manual(self.sources[0], doc, self.skills, preview=True)

    def test_duplicate_record_rejected(self):
        doc = copy.deepcopy(self.manual)
        doc["records"].append(copy.deepcopy(doc["records"][0]))
        with self.assertRaises(SourceContractError):
            normalize_manual(self.sources[0], doc, self.skills, preview=True)

    def test_feed_entity_rejected(self):
        with self.assertRaises(SourceContractError):
            normalize_feed(self.sources[1], b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss/>',
                           self.annotations, self.skills, preview=True)

    def test_feed_missing_annotations_rejected(self):
        with self.assertRaises(SourceContractError):
            normalize_feed(self.sources[1], self.feed, {}, self.skills, preview=True)

    def test_source_host_credentials_rejected(self):
        registry = json.loads((ROOT / "data/sources.sample.json").read_text())
        registry["sources"][0]["source_url"] = "https://user:pass@example.org/catalog"
        with self.assertRaises(SourceContractError):
            load_registry(registry)

    def test_source_duplicate_rejected(self):
        registry = json.loads((ROOT / "data/sources.sample.json").read_text())
        registry["sources"].append(copy.deepcopy(registry["sources"][0]))
        with self.assertRaises(SourceContractError):
            load_registry(registry)

    def test_cost_filter_never_claims_free(self):
        catalog, _ = self.build()
        self.assertEqual(discover_courses(catalog, access_cost="free", include_synthetic=True), [])

    def test_catalog_validator_compatible(self):
        from validate_catalog import validate
        catalog, _ = self.build()
        self.assertEqual(validate(catalog), [])


if __name__ == "__main__":
    unittest.main()
