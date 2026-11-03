"""Deterministic prerequisite planning with optional bounded local prioritization."""

from dataclasses import dataclass
from typing import Any, Mapping

from .provider import PriorityProvider, SKILL_PATTERN


@dataclass(frozen=True)
class PlanningRequest:
    career_goal: str
    target_skill_ids: tuple[str, ...]
    known_skill_ids: tuple[str, ...] = ()
    weekly_hours: int = 5
    zero_budget: bool = True

    def __post_init__(self):
        if (
            not isinstance(self.career_goal, str)
            or not 1 <= len(self.career_goal.strip()) <= 120
            or any(ord(ch) < 32 for ch in self.career_goal)
        ):
            raise ValueError("Career goal must be 1-120 printable characters")
        for name, items, maximum in (
            ("target_skill_ids", self.target_skill_ids, 32),
            ("known_skill_ids", self.known_skill_ids, 128),
        ):
            if not isinstance(items, tuple) or len(items) > maximum:
                raise ValueError(f"Invalid {name}")
            if name == "target_skill_ids" and not items:
                raise ValueError("At least one target skill is required")
            if len(items) != len(set(items)) or any(
                not isinstance(item, str) or not SKILL_PATTERN.fullmatch(item)
                for item in items
            ):
                raise ValueError(f"Invalid or duplicate IDs in {name}")
        if type(self.weekly_hours) is not int or not 1 <= self.weekly_hours <= 80:
            raise ValueError("Weekly hours must be between 1 and 80")
        if type(self.zero_budget) is not bool:
            raise ValueError("zero_budget must be boolean")


def _skills(catalog: Mapping[str, Any]) -> dict[str, dict]:
    if catalog.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported catalog version")
    rows = catalog.get("skills")
    if not isinstance(rows, list):
        raise ValueError("Missing skill catalog")
    skills: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid skill object")
        skill_id = row.get("id")
        prereqs = row.get("prerequisites")
        if (
            not isinstance(skill_id, str)
            or not SKILL_PATTERN.fullmatch(skill_id)
            or skill_id in skills
            or not isinstance(row.get("name"), str)
            or not row["name"].strip()
            or not isinstance(prereqs, list)
            or len(prereqs) != len(set(map(str, prereqs)))
            or any(not isinstance(p, str) for p in prereqs)
        ):
            raise ValueError("Invalid skill graph")
        skills[skill_id] = row
    for row in skills.values():
        if any(p not in skills for p in row["prerequisites"]):
            raise ValueError("Unresolved prerequisite")
    return skills


def _required_skills(
    skills: Mapping[str, dict], target_ids: tuple[str, ...]
) -> set[str]:
    required: set[str] = set()
    visiting: set[str] = set()

    def visit(skill_id: str):
        if skill_id not in skills:
            raise ValueError(f"Unknown target or prerequisite skill: {skill_id}")
        if skill_id in visiting:
            raise ValueError("Prerequisite cycle detected")
        if skill_id in required:
            return
        visiting.add(skill_id)
        for parent in skills[skill_id]["prerequisites"]:
            visit(parent)
        visiting.remove(skill_id)
        required.add(skill_id)

    for target in target_ids:
        visit(target)
    return required


def _eligible_resources(
    catalog: Mapping[str, Any], skill_id: str, completed: set[str], zero_budget: bool,
    verified_free_resource_ids: frozenset[str],
) -> list[str]:
    """For zero-budget plans, require provenance-approved free access.

    A plain catalog 'free' flag does not establish claim-level verification.
    The allowlist is supplied only from an activated, validated Phase 19
    reviewed release; callers without that release must leave it empty.
    """
    providers = {
        p.get("id") for p in catalog.get("providers", [])
        if isinstance(p, dict) and p.get("authorization") == "approved"
    }
    matches = []
    for resource in catalog.get("resources", []):
        if not isinstance(resource, dict):
            continue
        evidence = resource.get("evidence")
        if (
            resource.get("synthetic") is not False
            or resource.get("provider_id") not in providers
            or not isinstance(evidence, dict)
            or evidence.get("status") != "verified"
            or not evidence.get("source_url")
            or not evidence.get("checked_at")
            or resource.get("access_cost") not in {"free", "paid", "conditional"}
            or (zero_budget and (
                resource.get("access_cost") != "free"
                or resource.get("id") not in verified_free_resource_ids
            ))
            or skill_id not in resource.get("skills", [])
            or not set(resource.get("prerequisites", [])).issubset(completed)
        ):
            continue
        if isinstance(resource.get("id"), str):
            matches.append(resource["id"])
    return sorted(set(matches))


def _milestone_explanation(skills, skill_id, resource_ids):
    """Bounded catalog-grounded wording; never invent courses or completions."""
    name = " ".join(skills[skill_id]["name"].split())[:70]
    parents = skills[skill_id]["prerequisites"]
    if parents:
        labels = [
            " ".join(skills[parent]["name"].split())[:50]
            for parent in parents[:2]
        ]
        suffix = " and other prerequisites" if len(parents) > 2 else ""
        first = f"Build on {', '.join(labels)}{suffix} to learn {name}."
    else:
        first = f"Start with {name}; no prerequisite skills are required."
    if resource_ids:
        second = (
            "Eligible catalog resources are listed; verify current access, "
            "pricing and certificate terms before enrollment."
        )
    else:
        second = (
            "No reviewed course currently meets the pathway access policy; "
            "this milestone remains a skills-only step."
        )
    return f"{first} {second}"


def build_pathway(
    catalog: Mapping[str, Any],
    request: PlanningRequest,
    provider: PriorityProvider | None = None,
    *, verified_free_resource_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Return the v1 pathway contract; never introduce model-created catalog IDs."""
    if not isinstance(request, PlanningRequest):
        raise TypeError("PlanningRequest required")
    if not isinstance(catalog, Mapping):
        raise ValueError("Invalid catalog")
    if (not isinstance(verified_free_resource_ids, frozenset)
            or any(not isinstance(rid, str) for rid in verified_free_resource_ids)):
        raise ValueError("Verified free resource policy must be an immutable ID set")
    skills = _skills(catalog)
    required = _required_skills(skills, request.target_skill_ids)
    unknown = set(request.known_skill_ids) - skills.keys()
    if unknown:
        raise ValueError("Unknown known skill identifiers")

    completed = set(request.known_skill_ids)
    pending = required - completed
    milestones = []
    assisted = False
    attempted_priority = False

    while pending:
        ready = tuple(sorted(
            skill_id for skill_id in pending
            if set(skills[skill_id]["prerequisites"]).issubset(completed)
        ))
        if not ready:
            raise ValueError("No valid prerequisite ordering")
        selected = ready[0]
        if provider is not None and not attempted_priority and len(ready) > 1:
            attempted_priority = True
            try:
                proposed = provider.choose(ready, request.career_goal)
                if isinstance(proposed, str) and proposed in ready:
                    selected = proposed
                    assisted = True
            except Exception:
                selected = ready[0]

        resources = _eligible_resources(
            catalog, selected, completed, request.zero_budget, verified_free_resource_ids
        )
        milestones.append({
            "order": len(milestones) + 1,
            "skill_id": selected,
            "resource_ids": resources,
            "rationale": _milestone_explanation(skills, selected, resources),
        })
        completed.add(selected)
        pending.remove(selected)

    return {
        "schema_version": "1.0.0",
        "career_goal": request.career_goal.strip(),
        "weekly_hours": request.weekly_hours,
        "milestones": milestones,
        "generation_mode": "ai_assisted" if assisted else "deterministic",
    }
