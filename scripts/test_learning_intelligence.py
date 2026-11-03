"""Deterministic personalized pathway explanations and safety regressions."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_ai import PlanningRequest
from nextrail_orchestration import OrchestrationError, explain_pathway, orchestrate
from nextrail_discovery.pipeline import build_reviewed_catalog
from test_course_pipeline import COURSE_ID, NOW, fixtures


class LearningIntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(
            (ROOT / "data/catalog.sample.json").read_text(encoding="utf-8")
        )

    def request(self, **changes):
        fields = {
            "career_goal": "Frontend Developer",
            "target_skill_ids": ("css", "javascript"),
            "zero_budget": True,
        }
        fields.update(changes)
        return PlanningRequest(**fields)

    def explain(self, request=None, catalog=None, *, provider=None, free_ids=frozenset()):
        catalog = self.catalog if catalog is None else catalog
        request = self.request() if request is None else request
        outcome = orchestrate(
            catalog, request, priority_provider=provider, env={},
            verified_free_resource_ids=free_ids,
        )
        return outcome.pathway, explain_pathway(
            catalog, request, outcome.pathway,
            verified_free_resource_ids=free_ids,
        )

    def test_guest_skill_gap_closure_identifies_shared_prerequisite(self):
        plan, details = self.explain()
        self.assertEqual(
            [item["skill_id"] for item in plan["milestones"]],
            ["html", "css", "javascript"],
        )
        self.assertEqual(details["requested_target_skill_ids"], ["css", "javascript"])
        self.assertEqual(details["required_skill_ids"], ["css", "html", "javascript"])
        self.assertEqual(details["known_required_skill_ids"], [])
        self.assertEqual(details["missing_skill_ids"], ["css", "html", "javascript"])
        self.assertEqual(details["skill_gap_count"], 3)
        self.assertEqual(details["skills_without_eligible_course_count"], 3)
        html = details["milestones"][0]
        self.assertEqual(html["reason"], "prerequisite_for_target")
        self.assertEqual(html["supports_target_skill_ids"], ["css", "javascript"])
        self.assertEqual(html["required_prerequisite_ids"], [])
        self.assertEqual(html["course_coverage"], "no_eligible_catalog_resources")
        self.assertIn("no prerequisite", plan["milestones"][0]["rationale"])
        self.assertIn("skills-only", plan["milestones"][0]["rationale"])
        self.assertTrue(details["skills_are_self_reported_not_certified"])
        self.assertEqual(details["remote_requests_performed"], 0)

    def test_known_prerequisite_is_not_repeated_and_is_explained(self):
        req = self.request(known_skill_ids=("html",))
        plan, details = self.explain(req)
        self.assertEqual(details["known_required_skill_ids"], ["html"])
        self.assertEqual(details["missing_skill_ids"], ["css", "javascript"])
        self.assertEqual(details["milestone_count"], 2)
        css = details["milestones"][0]
        self.assertEqual(css["reason"], "requested_target")
        self.assertEqual(css["prerequisites_already_known"], ["html"])
        self.assertEqual(css["prerequisites_learned_earlier_in_route"], [])
        self.assertIn("HTML Fundamentals", plan["milestones"][0]["rationale"])
        self.assertEqual(plan["generation_mode"], "deterministic")

    def test_known_target_with_missing_foundation_is_not_silently_skipped(self):
        req = self.request(target_skill_ids=("css",), known_skill_ids=("css",))
        plan, details = self.explain(req)
        self.assertEqual([m["skill_id"] for m in plan["milestones"]], ["html"])
        self.assertEqual(details["requested_targets_already_known"], ["css"])
        self.assertEqual(details["missing_skill_ids"], ["html"])
        self.assertEqual(details["skill_gap_count"], 1)

    def test_unrelated_known_skill_does_not_change_required_gap(self):
        req = self.request(target_skill_ids=("css",), known_skill_ids=("javascript",))
        _, details = self.explain(req)
        self.assertEqual(details["required_skill_ids"], ["css", "html"])
        self.assertEqual(details["known_required_skill_ids"], [])
        self.assertEqual(details["missing_skill_ids"], ["css", "html"])

    def test_multi_step_transitive_dependency_explanations(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["skills"].append({
            "id": "react", "name": "React", "prerequisites": ["javascript"],
        })
        req = self.request(target_skill_ids=("react",))
        plan, details = self.explain(req, catalog)
        self.assertEqual(
            [m["skill_id"] for m in plan["milestones"]],
            ["html", "javascript", "react"],
        )
        self.assertEqual(details["milestones"][1]["supports_target_skill_ids"], ["react"])
        self.assertEqual(
            details["milestones"][2]["prerequisites_learned_earlier_in_route"],
            ["javascript"],
        )

    def test_already_known_target_can_produce_empty_route(self):
        req = self.request(target_skill_ids=("html",), known_skill_ids=("html",))
        plan, details = self.explain(req)
        self.assertEqual(plan["milestones"], [])
        self.assertEqual(details["milestones"], [])
        self.assertEqual(details["skill_gap_count"], 0)
        self.assertEqual(details["requested_targets_already_known"], ["html"])

    def test_invalid_priority_falls_back_without_inventing_courses(self):
        class Untrusted:
            def choose(self, candidates, goal):
                return "invented-ai-skill"
        plan, details = self.explain(
            self.request(known_skill_ids=("html",)), provider=Untrusted()
        )
        self.assertEqual(plan["generation_mode"], "deterministic")
        self.assertEqual(details["skills_without_eligible_course_count"], 2)
        self.assertTrue(all(not row["catalog_course_ids"] for row in details["milestones"]))

    def test_fictional_reviewed_course_is_explained_without_certificate_claim(self):
        package = build_reviewed_catalog(*fixtures(), now=NOW)
        catalog = package["catalog"]
        request = self.request(target_skill_ids=("html",))
        policy = frozenset({COURSE_ID})
        plan, details = self.explain(request, catalog, free_ids=policy)
        self.assertEqual(details["milestones"][0]["catalog_course_ids"], [COURSE_ID])
        self.assertEqual(details["milestones"][0]["course_coverage"],
                         "eligible_catalog_references")
        self.assertEqual(details["skills_without_eligible_course_count"], 0)
        self.assertIn("certificate terms", plan["milestones"][0]["rationale"])
        self.assertTrue(details["course_access_and_certificate_cost_are_independent"])
        untrusted_plan, untrusted_details = self.explain(
            request, catalog, free_ids=frozenset()
        )
        self.assertEqual(untrusted_plan["milestones"][0]["resource_ids"], [])
        self.assertEqual(untrusted_details["skills_without_eligible_course_count"], 1)

    def test_fabricated_course_or_broken_prerequisite_rejected(self):
        req = self.request()
        plan, _ = self.explain(req)
        fake = copy.deepcopy(plan)
        fake["milestones"][0]["resource_ids"] = ["fabricated-course"]
        with self.assertRaises(OrchestrationError):
            explain_pathway(self.catalog, req, fake)
        fake = copy.deepcopy(plan)
        fake["milestones"][0]["skill_id"] = "css"
        with self.assertRaises(OrchestrationError):
            explain_pathway(self.catalog, req, fake)
        with self.assertRaises(OrchestrationError):
            explain_pathway(
                self.catalog, req, plan, verified_free_resource_ids=["fake"],
            )

    def test_invalid_catalog_unknown_skill_and_cycle_fail_closed(self):
        with self.assertRaises(OrchestrationError):
            self.explain(self.request(target_skill_ids=("unlisted",)))
        catalog = copy.deepcopy(self.catalog)
        catalog["skills"][0]["prerequisites"] = ["css"]
        with self.assertRaises(OrchestrationError):
            self.explain(catalog=catalog)

    def test_determinism_no_mutation_and_v1_api_schema_unchanged(self):
        catalog = copy.deepcopy(self.catalog)
        req = self.request(known_skill_ids=("html",))
        first_plan, first_insights = self.explain(req, catalog)
        second_plan, second_insights = self.explain(req, catalog)
        self.assertEqual(first_plan, second_plan)
        self.assertEqual(first_insights, second_insights)
        self.assertEqual(catalog, self.catalog)
        self.assertEqual(set(first_plan), {
            "schema_version", "career_goal", "weekly_hours",
            "generation_mode", "milestones",
        })
        self.assertEqual(set(first_plan["milestones"][0]), {
            "order", "skill_id", "resource_ids", "rationale",
        })


if __name__ == "__main__":
    unittest.main()
