"""Deterministic agents with explicit responsibilities and no external side effects."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from nextrail_ai.pathways import (
    PlanningRequest, _required_skills, _skills, build_pathway,
)
from nextrail_ai.provider import PriorityProvider
from nextrail_discovery.contracts import hostname, valid_id


class OrchestrationError(ValueError):
    """A specialist gate rejected incomplete or untrusted workflow data."""


@dataclass(frozen=True)
class StageRecord:
    stage: str
    status: str


@dataclass(frozen=True)
class OrchestrationResult:
    pathway: dict[str, Any]
    stages: tuple[StageRecord, ...]


def _utc_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except ValueError:
        return False


class CatalogAgent:
    """Verify structure, linked entities and conservative evidence state."""

    def run(self, catalog: Mapping[str, Any]) -> dict[str, dict]:
        if not isinstance(catalog, Mapping):
            raise OrchestrationError("Catalog must be a mapping")
        if set(catalog) != {"schema_version", "providers", "skills", "resources"}:
            raise OrchestrationError("Unexpected catalog fields")
        for section, maximum in (("providers", 100), ("skills", 1000), ("resources", 2000)):
            if not isinstance(catalog[section], list) or len(catalog[section]) > maximum:
                raise OrchestrationError("Invalid catalog collection")

        try:
            skill_map = _skills(catalog)
            if len(skill_map) != len(catalog["skills"]):
                raise ValueError("Duplicate skills")
            for skill in skill_map:
                _required_skills(skill_map, (skill,))
        except (ValueError, TypeError, KeyError) as exc:
            raise OrchestrationError("Invalid catalog skill graph") from exc

        providers = {}
        for p in catalog["providers"]:
            if not isinstance(p, dict) or not valid_id(p.get("id")):
                raise OrchestrationError("Invalid provider ID")
            pid = p["id"]
            if pid in providers or p.get("authorization") not in ("pending", "approved"):
                raise OrchestrationError("Invalid provider registry")
            if not isinstance(p.get("name"), str) or not p["name"].strip():
                raise OrchestrationError("Provider name is required")
            try:
                hostname(p.get("website"))
            except ValueError as exc:
                raise OrchestrationError("Invalid provider website") from exc
            providers[pid] = p

        resources = {}
        urls = set()
        for row in catalog["resources"]:
            if not isinstance(row, dict) or not valid_id(row.get("id")):
                raise OrchestrationError("Invalid resource ID")
            rid = row["id"]
            if rid in resources or row.get("provider_id") not in providers:
                raise OrchestrationError("Duplicate resource or unknown provider")
            if not isinstance(row.get("title"), str) or not row["title"].strip():
                raise OrchestrationError("Invalid resource title")
            try:
                hostname(row.get("url"))
            except ValueError as exc:
                raise OrchestrationError("Invalid resource URL") from exc
            if row["url"] in urls:
                raise OrchestrationError("Duplicate resource URL")
            urls.add(row["url"])
            for key in ("skills", "prerequisites"):
                items = row.get(key)
                if not isinstance(items, list) or (key == "skills" and not items):
                    raise OrchestrationError("Missing resource skills")
                if any(not isinstance(item, str) or item not in skill_map for item in items):
                    raise OrchestrationError("Resource references unknown skills")
                if len(items) != len(set(items)):
                    raise OrchestrationError("Duplicate resource skills")
            if row.get("access_cost") not in ("free", "paid", "conditional", "unknown"):
                raise OrchestrationError("Invalid access-cost category")
            if row.get("certificate_cost") not in ("free", "paid", "not_offered", "unknown"):
                raise OrchestrationError("Invalid certificate-cost category")
            if type(row.get("synthetic")) is not bool:
                raise OrchestrationError("Invalid synthetic status")
            evidence = row.get("evidence")
            if not isinstance(evidence, dict) or evidence.get("status") not in (
                "verified", "unverified"
            ):
                raise OrchestrationError("Invalid resource evidence")
            if evidence["status"] == "verified":
                if row["synthetic"] or providers[row["provider_id"]]["authorization"] != "approved":
                    raise OrchestrationError("Synthetic or unapproved source cannot be verified")
                try:
                    hostname(evidence.get("source_url"))
                except ValueError as exc:
                    raise OrchestrationError("Missing valid verification URL") from exc
                if not _utc_timestamp(evidence.get("checked_at")):
                    raise OrchestrationError("Missing verification time")
            elif evidence.get("checked_at") is not None and not _utc_timestamp(
                evidence["checked_at"]
            ):
                raise OrchestrationError("Invalid verification time")
            resources[rid] = row
        return resources


class SkillGapAgent:
    """Compute required skills without inventing IDs or skipping prerequisites."""

    def run(self, catalog: Mapping[str, Any], request: PlanningRequest) -> set[str]:
        try:
            skills = _skills(catalog)
            required = _required_skills(skills, request.target_skill_ids)
        except (KeyError, TypeError, ValueError) as exc:
            raise OrchestrationError("Cannot resolve required skills") from exc
        if not set(request.known_skill_ids).issubset(skills):
            raise OrchestrationError("Unknown declared existing skills")
        return required - set(request.known_skill_ids)


class PlanningAgent:
    """Delegate bounded optional prioritization to the existing local provider."""

    def run(
        self, catalog, request, priority_provider: PriorityProvider | None,
        *, verified_free_resource_ids: frozenset[str] = frozenset(),
    ):
        return build_pathway(
            catalog, request, priority_provider,
            verified_free_resource_ids=verified_free_resource_ids,
        )


class QualityAgent:
    """Validate the final v1 pathway against the approved catalog and skill graph."""

    def run(
        self, catalog, request, expected_skills, pathway, resources,
        *, verified_free_resource_ids: frozenset[str] = frozenset(),
    ):
        if not isinstance(pathway, dict) or set(pathway) != {
            "schema_version", "career_goal", "weekly_hours", "generation_mode", "milestones"
        }:
            raise OrchestrationError("Invalid pathway output fields")
        if pathway["schema_version"] != "1.0.0" or pathway["career_goal"] != request.career_goal.strip():
            raise OrchestrationError("Pathway goal or version mismatch")
        if pathway["weekly_hours"] != request.weekly_hours or pathway["generation_mode"] not in (
            "deterministic", "ai_assisted"
        ):
            raise OrchestrationError("Invalid pathway planning metadata")
        milestones = pathway["milestones"]
        if not isinstance(milestones, list) or len(milestones) != len(expected_skills):
            raise OrchestrationError("Incorrect milestone count")
        skills = _skills(catalog)
        completed = set(request.known_skill_ids)
        visited = set()
        for ordinal, item in enumerate(milestones, 1):
            if not isinstance(item, dict) or set(item) != {
                "order", "skill_id", "resource_ids", "rationale"
            } or type(item["order"]) is not int or item["order"] != ordinal:
                raise OrchestrationError("Invalid milestone shape or ordering")
            skill = item["skill_id"]
            if skill not in expected_skills or skill in visited:
                raise OrchestrationError("Invented or duplicate milestone skill")
            if not set(skills[skill]["prerequisites"]).issubset(completed):
                raise OrchestrationError("Pathway violates skill prerequisites")
            ids = item["resource_ids"]
            if not isinstance(ids, list) or len(ids) != len(set(map(str, ids))):
                raise OrchestrationError("Invalid resource references")
            if not isinstance(item["rationale"], str) or not item["rationale"].strip():
                raise OrchestrationError("Missing milestone rationale")
            for rid in ids:
                if not isinstance(rid, str) or rid not in resources:
                    raise OrchestrationError("Invented resource reference")
                resource = resources[rid]
                if (resource["synthetic"] or resource["evidence"]["status"] != "verified"
                        or skill not in resource["skills"]
                        or not set(resource["prerequisites"]).issubset(completed)):
                    raise OrchestrationError("Unverified, synthetic or ineligible course")
                if request.zero_budget and (
                    rid not in verified_free_resource_ids
                    or resource["access_cost"] != "free"
                ):
                    raise OrchestrationError(
                        "Zero-budget course lacks reviewed free-access evidence"
                    )
            completed.add(skill)
            visited.add(skill)
        if visited != expected_skills:
            raise OrchestrationError("Pathway did not cover the required skills")
        return pathway
