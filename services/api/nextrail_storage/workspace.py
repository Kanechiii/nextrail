"""Read-only account workspace projections over saved learning snapshots.

A readiness indicator is advisory: completion is self-reported, prior learning
outside a saved route cannot be verified, and saved course references are not
evidence of current provider availability or certification.
"""
from collections.abc import Mapping


class WorkspaceError(ValueError):
    """Saved pathway or current skill catalog cannot be projected safely."""


def build_workspace(pathway_id, pathway, progress, catalog):
    """Return deterministic, UI-neutral milestone readiness and progress."""
    if not isinstance(pathway_id, str) or not pathway_id:
        raise WorkspaceError("A saved pathway identifier is required")
    if (not isinstance(pathway, dict) or not isinstance(progress, dict)
            or not isinstance(catalog, Mapping)):
        raise WorkspaceError("Invalid saved pathway projection inputs")
    milestones = pathway.get("milestones")
    statuses = progress.get("milestones")
    skill_rows = catalog.get("skills")
    if (not isinstance(milestones, list) or not isinstance(statuses, list)
            or not isinstance(skill_rows, list)
            or progress.get("pathway_id") != pathway_id):
        raise WorkspaceError("Invalid saved milestones or current skill catalog")

    skills = {}
    for skill in skill_rows:
        if (not isinstance(skill, dict) or not isinstance(skill.get("id"), str)
                or skill["id"] in skills
                or not isinstance(skill.get("name"), str)
                or not isinstance(skill.get("prerequisites"), list)
                or any(not isinstance(s, str) for s in skill["prerequisites"])):
            raise WorkspaceError("Invalid current skill catalog")
        skills[skill["id"]] = skill

    status_by_skill = {}
    for row in statuses:
        if (not isinstance(row, dict) or not isinstance(row.get("skill_id"), str)
                or row["skill_id"] in status_by_skill
                or row.get("status") not in ("not_started", "in_progress", "completed")):
            raise WorkspaceError("Invalid saved milestone status")
        status_by_skill[row["skill_id"]] = row["status"]
    route_skills = [m.get("skill_id") for m in milestones if isinstance(m, dict)]
    if (len(route_skills) != len(milestones)
            or any(not isinstance(s, str) for s in route_skills)
            or len(route_skills) != len(set(route_skills))
            or set(status_by_skill) != set(route_skills)):
        raise WorkspaceError("Progress and saved milestones do not agree")

    projections = []
    next_ready = None
    for milestone in milestones:
        skill_id = milestone["skill_id"]
        status = status_by_skill[skill_id]
        skill = skills.get(skill_id)
        if skill is None:
            prerequisites = None
            blocked = []
            untracked = []
            readiness = "catalog_skill_missing"
        else:
            prerequisites = list(skill["prerequisites"])
            blocked = [prerequisite for prerequisite in prerequisites
                       if prerequisite in status_by_skill
                       and status_by_skill[prerequisite] != "completed"]
            untracked = [prerequisite for prerequisite in prerequisites
                         if prerequisite not in status_by_skill]
            if status == "completed":
                readiness = "completed"
            elif blocked:
                readiness = "blocked"
            elif untracked:
                readiness = "prior_knowledge_unconfirmed"
            else:
                readiness = "ready"
        if readiness == "ready" and next_ready is None:
            next_ready = skill_id
        projections.append({
            "order": milestone["order"],
            "skill_id": skill_id,
            "skill_name": skill["name"] if skill is not None else None,
            "status": status,
            "readiness": readiness,
            "prerequisite_skill_ids": prerequisites,
            "blocking_skill_ids": blocked,
            "untracked_prerequisite_skill_ids": untracked,
            "resource_ids": list(milestone["resource_ids"]),
        })

    total = len(projections)
    completed = sum(m["status"] == "completed" for m in projections)
    in_progress = sum(m["status"] == "in_progress" for m in projections)
    return {
        "pathway_id": pathway_id,
        "career_goal": pathway["career_goal"],
        "generation_mode": pathway["generation_mode"],
        "weekly_hours": pathway["weekly_hours"],
        "status_source": "self_reported",
        "readiness_basis": "current_skill_catalog",
        "resource_references_verified": False,
        "completed": completed,
        "in_progress": in_progress,
        "not_started": total - completed - in_progress,
        "total": total,
        "completion_percent": (100 * completed // total) if total else 0,
        "all_completed": bool(total) and completed == total,
        "next_ready_skill_id": next_ready,
        "milestones": projections,
    }
