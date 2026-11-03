"""Offline learning intelligence quality gate. No AI model, network or user storage."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_ai import PlanningRequest
from nextrail_orchestration import explain_pathway, orchestrate


def evaluate():
    catalog = json.loads(
        (ROOT / "data/catalog.sample.json").read_text(encoding="utf-8")
    )
    cases = [
        (("css",), (), ("html", "css")),
        (("javascript",), (), ("html", "javascript")),
        (("css", "javascript"), ("html",), ("css", "javascript")),
        (("html",), ("html",), ()),
        (("css",), ("css",), ("html",)),
    ]
    results = []
    for targets, known, expected in cases:
        request = PlanningRequest(
            career_goal="Frontend Developer",
            target_skill_ids=targets,
            known_skill_ids=known,
            zero_budget=True,
        )
        output = orchestrate(catalog, request, env={}).pathway
        insights = explain_pathway(catalog, request, output)
        actual = tuple(row["skill_id"] for row in output["milestones"])
        if actual != expected:
            raise AssertionError("Unstable or incomplete prerequisite ordering")
        if (insights["skill_gap_count"] != len(expected)
                or insights["milestone_count"] != len(expected)
                or insights["skills_without_eligible_course_count"] != len(expected)
                or insights["remote_requests_performed"] != 0
                or output["generation_mode"] != "deterministic"
                or any(row["resource_ids"] for row in output["milestones"])):
            raise AssertionError("Ungrounded skill-gap or course coverage explanation")
        results.append({
            "target_skill_count": len(targets),
            "known_skill_count": len(known),
            "missing_skill_count": len(expected),
            "passed": True,
        })
    print(json.dumps({
        "evaluation": "offline deterministic learning intelligence",
        "cases_passed": len(results),
        "network_calls": 0,
        "sample_course_recommendations": 0,
        "results": results,
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    evaluate()
