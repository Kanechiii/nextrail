"""Pure deterministic learning gap explanations for already validated pathways.

An auxiliary analysis view, not an API schema change or course-eligibility gate.
No model inference, external requests, storage or progress claims.
"""

from nextrail_ai.pathways import PlanningRequest, _required_skills, _skills

from .agents import CatalogAgent, OrchestrationError, QualityAgent, SkillGapAgent


def explain_pathway(
    catalog, request, pathway, *,
    verified_free_resource_ids=frozenset(),
):
    """Derive transparent prerequisite and course-coverage facts.

    Validate the same v1 pathway contract and eligibility rules used by the
    orchestration quality gate before emitting any explanations.
    """
    if not isinstance(request, PlanningRequest):
        raise OrchestrationError("PlanningRequest required")
    if (not isinstance(verified_free_resource_ids, frozenset)
            or any(not isinstance(x, str) for x in verified_free_resource_ids)):
        raise OrchestrationError("Invalid reviewed free-access policy")

    resources = CatalogAgent().run(catalog)
    missing = SkillGapAgent().run(catalog, request)
    QualityAgent().run(
        catalog, request, missing, pathway, resources,
        verified_free_resource_ids=verified_free_resource_ids,
    )
    skills = _skills(catalog)
    targets = set(request.target_skill_ids)
    known = set(request.known_skill_ids)
    required = _required_skills(skills, request.target_skill_ids)
    target_closures = {
        tid: _required_skills(skills, (tid,))
        for tid in sorted(targets)
    }

    milestones = []
    completed = set(known)
    for item in pathway["milestones"]:
        sid = item["skill_id"]
        parents = set(skills[sid]["prerequisites"])
        course_ids = item["resource_ids"]
        milestones.append({
            "order": item["order"],
            "skill_id": sid,
            "reason": "requested_target" if sid in targets else "prerequisite_for_target",
            "supports_target_skill_ids": sorted(
                target for target in targets if sid in target_closures[target]
            ),
            "required_prerequisite_ids": sorted(parents),
            "prerequisites_already_known": sorted(parents & known),
            "prerequisites_learned_earlier_in_route": sorted(parents & (completed - known)),
            "catalog_course_ids": list(course_ids),
            "course_coverage": (
                "eligible_catalog_references" if course_ids
                else "no_eligible_catalog_resources"
            ),
        })
        completed.add(sid)

    return {
        "schema_version": "1.0.0",
        "analysis_mode": "deterministic_offline",
        "career_goal": pathway["career_goal"],
        "requested_target_skill_ids": sorted(targets),
        "required_skill_ids": sorted(required),
        "known_required_skill_ids": sorted(known & required),
        "missing_skill_ids": sorted(missing),
        "requested_targets_already_known": sorted(targets & known),
        "skill_gap_count": len(missing),
        "milestone_count": len(milestones),
        "skills_without_eligible_course_count": sum(
            not entry["catalog_course_ids"] for entry in milestones
        ),
        "milestones": milestones,
        "course_eligibility_inherited_from_quality_gate": True,
        "skills_are_self_reported_not_certified": True,
        "course_access_and_certificate_cost_are_independent": True,
        "remote_requests_performed": 0,
    }
