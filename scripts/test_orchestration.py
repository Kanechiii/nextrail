import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from nextrail_ai import PlanningRequest
from nextrail_orchestration import OrchestrationError, orchestrate
from nextrail_orchestration.agents import QualityAgent


class OrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "data/catalog.sample.json").read_text())

    def request(self, **values):
        fields = {
            "career_goal": "Frontend developer",
            "target_skill_ids": ("css", "javascript"),
        }
        fields.update(values)
        return PlanningRequest(**fields)

    def test_guest_deterministic_pipeline(self):
        result = orchestrate(self.catalog, self.request())
        self.assertEqual([x.stage for x in result.stages], [
            "catalog_validation", "skill_gap", "pathway_planning", "quality_gate"
        ])
        self.assertTrue(all(x.status == "passed" for x in result.stages))
        self.assertEqual(result.pathway["generation_mode"], "deterministic")

    def test_prerequisites_ordered(self):
        result = orchestrate(self.catalog, self.request())
        self.assertEqual(result.pathway["milestones"][0]["skill_id"], "html")

    def test_completed_prerequisite_excluded(self):
        result = orchestrate(self.catalog, self.request(known_skill_ids=("html",)))
        self.assertEqual(len(result.pathway["milestones"]), 2)

    def test_zero_budget_excludes_unverified_courses(self):
        result = orchestrate(self.catalog, self.request())
        self.assertTrue(all(not x["resource_ids"] for x in result.pathway["milestones"]))

    def test_no_cloud_default(self):
        with patch("nextrail_orchestration.engine.select_provider", return_value=None) as selector:
            orchestrate(self.catalog, self.request(), env={})
            selector.assert_called_once_with({})

    def test_cloud_selection_is_rejected(self):
        with self.assertRaises(OrchestrationError):
            orchestrate(self.catalog, self.request(), env={"NEXTRAIL_AI_PROVIDER": "bedrock"})

    def test_unknown_runtime_rejected(self):
        with self.assertRaises(OrchestrationError):
            orchestrate(self.catalog, self.request(), env={"NEXTRAIL_AGENT_RUNTIME": "remote"})

    def test_strands_requires_opt_in(self):
        with self.assertRaises(OrchestrationError):
            orchestrate(self.catalog, self.request(), env={"NEXTRAIL_AGENT_RUNTIME": "strands_ollama"})

    def test_malformed_provider_falls_back(self):
        class Invalid:
            def choose(self, candidates, goal):
                return "invented-skill"
        result = orchestrate(self.catalog, self.request(known_skill_ids=("html",)),
                             priority_provider=Invalid())
        self.assertEqual(result.pathway["generation_mode"], "deterministic")

    def test_valid_prioritizer_is_bounded(self):
        class Valid:
            def choose(self, candidates, goal):
                return "javascript"
        result = orchestrate(self.catalog, self.request(known_skill_ids=("html",)),
                             priority_provider=Valid())
        self.assertEqual(result.pathway["milestones"][0]["skill_id"], "javascript")

    def test_synthetic_verified_is_rejected(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["resources"][0]["evidence"]["status"] = "verified"
        with self.assertRaises(OrchestrationError):
            orchestrate(catalog, self.request())

    def test_duplicate_provider_rejected(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["providers"].append(copy.deepcopy(catalog["providers"][0]))
        with self.assertRaises(OrchestrationError):
            orchestrate(catalog, self.request())

    def test_prerequisite_cycle_rejected(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["skills"][0]["prerequisites"] = ["css"]
        with self.assertRaises(OrchestrationError):
            orchestrate(catalog, self.request())

    def test_unknown_skill_rejected(self):
        with self.assertRaises(OrchestrationError):
            orchestrate(self.catalog, self.request(target_skill_ids=("unknown",)))

    def test_original_catalog_not_modified(self):
        catalog = copy.deepcopy(self.catalog)
        orchestrate(catalog, self.request())
        self.assertEqual(catalog, self.catalog)

    def test_quality_rejects_fabricated_course(self):
        result = orchestrate(self.catalog, self.request())
        bad = copy.deepcopy(result.pathway)
        bad["milestones"][0]["resource_ids"] = ["fake-course"]
        resources = {row["id"]: row for row in self.catalog["resources"]}
        with self.assertRaises(OrchestrationError):
            QualityAgent().run(self.catalog, self.request(),
                               {"html", "css", "javascript"}, bad, resources)

    def test_quality_rejects_out_of_order_skills(self):
        result = orchestrate(self.catalog, self.request())
        bad = copy.deepcopy(result.pathway)
        bad["milestones"][0], bad["milestones"][1] = (
            bad["milestones"][1], bad["milestones"][0]
        )
        resources = {row["id"]: row for row in self.catalog["resources"]}
        with self.assertRaises(OrchestrationError):
            QualityAgent().run(self.catalog, self.request(),
                               {"html", "css", "javascript"}, bad, resources)

    def test_strands_import_not_required_by_default(self):
        result = orchestrate(self.catalog, self.request(), env={})
        self.assertEqual(result.pathway["schema_version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
