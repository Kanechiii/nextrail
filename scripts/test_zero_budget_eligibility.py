"""Regression tests for provenance-aware zero-budget course recommendations.

No third-party network calls, hosted providers, or real-world course publication.
The approved-looking fixture is illustrative and exists only in unit tests.
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_ai import PlanningRequest, build_pathway
from nextrail_api.release import load_reviewed_bundle
from nextrail_discovery.pipeline import build_reviewed_catalog
from nextrail_orchestration import OrchestrationError, orchestrate
from nextrail_orchestration.agents import CatalogAgent, QualityAgent
from test_course_pipeline import COURSE_ID, NOW, fixtures


class ReviewedFreeAccessTests(unittest.TestCase):
    def request(self, zero_budget=True):
        return PlanningRequest(
            career_goal="Frontend developer",
            target_skill_ids=("html",),
            zero_budget=zero_budget,
        )

    def publish(self, access_cost="free"):
        parts = list(fixtures())
        parts[4]["claims"][0]["value"] = access_cost
        return build_reviewed_catalog(*parts, now=NOW)

    def vetted(self, package):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reviewed.json"
            raw = json.dumps(package, sort_keys=True).encode("utf-8")
            path.write_bytes(raw)
            return load_reviewed_bundle(
                path, hashlib.sha256(raw).hexdigest(), now=NOW,
            )

    def test_verified_free_course_available_to_zero_budget_pathway(self):
        bundle = self.vetted(self.publish())
        result = orchestrate(
            bundle.current_catalog(now=NOW), self.request(), env={},
            verified_free_resource_ids=bundle.verified_free_resource_ids,
        )
        self.assertEqual(
            result.pathway["milestones"][0]["resource_ids"], [COURSE_ID]
        )
        self.assertEqual(result.pathway["generation_mode"], "deterministic")

    def test_free_release_preserves_unknown_certificate_price(self):
        bundle = self.vetted(self.publish())
        self.assertEqual(bundle.catalog["resources"][0]["access_cost"], "free")
        self.assertEqual(bundle.catalog["resources"][0]["certificate_cost"], "unknown")
        self.assertEqual(bundle.verified_free_resource_ids, frozenset({COURSE_ID}))

    def test_unreviewed_catalog_free_flag_is_not_enough(self):
        catalog = self.publish()["catalog"]
        result = orchestrate(catalog, self.request(), env={})
        self.assertEqual(result.pathway["milestones"][0]["resource_ids"], [])

    def test_direct_planner_remains_conservative_without_vetted_policy(self):
        catalog = self.publish()["catalog"]
        result = build_pathway(catalog, self.request())
        self.assertEqual(result["milestones"][0]["resource_ids"], [])

    def test_paid_access_excluded_from_zero_budget(self):
        bundle = self.vetted(self.publish("paid"))
        self.assertEqual(bundle.verified_free_resource_ids, frozenset())
        result = orchestrate(
            bundle.catalog, self.request(), env={},
            verified_free_resource_ids=bundle.verified_free_resource_ids,
        )
        self.assertEqual(result.pathway["milestones"][0]["resource_ids"], [])

    def test_conditional_access_excluded_from_zero_budget(self):
        bundle = self.vetted(self.publish("conditional"))
        self.assertEqual(bundle.verified_free_resource_ids, frozenset())
        result = orchestrate(
            bundle.catalog, self.request(), env={},
            verified_free_resource_ids=bundle.verified_free_resource_ids,
        )
        self.assertEqual(result.pathway["milestones"][0]["resource_ids"], [])

    def test_paid_course_can_still_be_suggested_when_budget_allows(self):
        bundle = self.vetted(self.publish("paid"))
        result = orchestrate(
            bundle.catalog, self.request(zero_budget=False), env={}
        )
        self.assertEqual(result.pathway["milestones"][0]["resource_ids"], [COURSE_ID])

    def test_reviewed_free_access_needs_approved_cost_claim(self):
        parts = list(fixtures())
        parts[4]["claims"] = [
            claim for claim in parts[4]["claims"]
            if claim["claim"] != "access_cost"
        ]
        release = self.vetted(build_reviewed_catalog(*parts, now=NOW))
        self.assertEqual(release.verified_free_resource_ids, frozenset())
        self.assertEqual(release.catalog["resources"], [])

    def test_reviewed_free_access_needs_current_availability(self):
        parts = list(fixtures())
        parts[4]["claims"][1]["checked_at"] = "2026-10-01T00:00:00Z"
        release = self.vetted(build_reviewed_catalog(*parts, now=NOW))
        self.assertEqual(release.verified_free_resource_ids, frozenset())
        self.assertEqual(release.catalog["resources"], [])

    def test_reviewed_free_access_requires_listing_approval(self):
        parts = list(fixtures())
        parts[3][0]["status"] = "pending"
        release = self.vetted(build_reviewed_catalog(*parts, now=NOW))
        self.assertEqual(release.verified_free_resource_ids, frozenset())

    def test_reviewed_free_access_does_not_include_sample_synthetic_course(self):
        sample = json.loads((ROOT / "data/catalog.sample.json").read_text())
        result = orchestrate(
            sample, self.request(), env={},
            verified_free_resource_ids=frozenset({COURSE_ID}),
        )
        self.assertEqual(result.pathway["milestones"][0]["resource_ids"], [])

    def test_forged_free_resource_reference_rejected_without_release(self):
        catalog = self.publish()["catalog"]
        request = self.request()
        base = orchestrate(catalog, request, env={}).pathway
        forged = copy.deepcopy(base)
        forged["milestones"][0]["resource_ids"] = [COURSE_ID]
        resources = CatalogAgent().run(catalog)
        with self.assertRaises(OrchestrationError):
            QualityAgent().run(
                catalog, request, {"html"}, forged, resources
            )

    def test_injected_paid_id_rejected_even_with_forged_allowlist(self):
        catalog = self.publish("paid")["catalog"]
        result = orchestrate(
            catalog, self.request(), env={},
            verified_free_resource_ids=frozenset({COURSE_ID}),
        )
        self.assertEqual(result.pathway["milestones"][0]["resource_ids"], [])
        forged = copy.deepcopy(result.pathway)
        forged["milestones"][0]["resource_ids"] = [COURSE_ID]
        with self.assertRaises(OrchestrationError):
            QualityAgent().run(
                catalog, self.request(), {"html"}, forged,
                CatalogAgent().run(catalog),
                verified_free_resource_ids=frozenset({COURSE_ID}),
            )

    def test_review_policy_must_be_immutable_and_well_typed(self):
        catalog = self.publish()["catalog"]
        for policy in ([COURSE_ID], {COURSE_ID}, frozenset({1})):
            with self.subTest(policy=policy), self.assertRaises(OrchestrationError):
                orchestrate(
                    catalog, self.request(), env={},
                    verified_free_resource_ids=policy,
                )

    def test_provenance_is_not_added_to_public_pathway_shape(self):
        bundle = self.vetted(self.publish())
        result = orchestrate(
            bundle.catalog, self.request(), env={},
            verified_free_resource_ids=bundle.verified_free_resource_ids,
        ).pathway
        self.assertEqual(set(result), {
            "schema_version", "career_goal", "weekly_hours",
            "generation_mode", "milestones",
        })
        self.assertEqual(set(result["milestones"][0]), {
            "order", "skill_id", "resource_ids", "rationale",
        })


if __name__ == "__main__":
    unittest.main()
