"""Fail-closed offline publication of reviewed course-source snapshots.

Source approval and signed-off evidence are *human review claims*, not proof that
a course is live. This module performs no fetching, scraping, or AI inference.
"""
import copy
import json
from datetime import datetime, timedelta, timezone

from nextrail_evidence import EvidenceError, evaluate_claims

from .adapters import assemble_catalog, normalize_feed, normalize_manual
from .contracts import SourceContractError, hostname, load_registry, valid_id

LISTING_REVIEW_DAYS = 90
MAX_SUBMISSIONS = 100
MAX_REVIEWS = 10000
REVIEW_FIELDS = frozenset({
    "resource_id", "source_id", "status", "reviewer", "checked_at", "evidence_url"
})
STATUSES = frozenset({"approved", "pending", "rejected"})
COST_CLAIMS = frozenset({"access_cost", "certificate_cost"})


class PublicationError(SourceContractError):
    """Course publication is unsafe or lacks reviewed source evidence."""


def _clock(value):
    moment = datetime.now(timezone.utc) if value is None else value
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise PublicationError("A timezone-aware review clock is required")
    return moment.astimezone(timezone.utc)


def _checked_at(value):
    if not isinstance(value, str):
        raise PublicationError("A timezone-aware listing review timestamp is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationError("Invalid listing review timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise PublicationError("Listing review timestamp must be timezone-aware")
    return result.astimezone(timezone.utc)


def _deduplicate(batches):
    """Collapse exact duplicate records; reject conflicting IDs or URLs.

    Source-level attribution is preserved for each corroborating entry. No
    conflicting claim is silently chosen as the winner.
    """
    seen_by_id = {}
    seen_by_url = {}
    corroboration = {}
    kept = []
    duplicates = 0
    for source, records, provenance in sorted(batches, key=lambda b: b[0].id):
        valid_ids = {r["id"] for r in records}
        if set(provenance) != valid_ids:
            raise PublicationError("Source records and provenance do not match")
        accepted = []
        accepted_provenance = {}
        for resource in records:
            rid, url = resource["id"], resource["url"]
            if rid in seen_by_id or url in seen_by_url:
                prior = seen_by_id.get(rid)
                url_owner = seen_by_url.get(url)
                if (prior is None or url_owner != rid or
                        prior != resource or prior["provider_id"] != source.provider_id):
                    raise PublicationError("Conflicting course identity or canonical URL")
                if source.id in corroboration[rid]:
                    raise PublicationError("Repeated source contribution")
                corroboration[rid].append(source.id)
                duplicates += 1
                continue
            seen_by_id[rid] = copy.deepcopy(resource)
            seen_by_url[url] = rid
            corroboration[rid] = [source.id]
            accepted.append(resource)
            accepted_provenance[rid] = provenance[rid]
        if accepted:
            kept.append((source, accepted, accepted_provenance))
    return kept, corroboration, duplicates


def _validate_reviews(reviews, resource_ids, source_by_id, contributions):
    if not isinstance(reviews, list) or len(reviews) > MAX_REVIEWS:
        raise PublicationError("Invalid listing review batch")
    result = {}
    for review in reviews:
        if not isinstance(review, dict) or set(review) != REVIEW_FIELDS:
            raise PublicationError("Unexpected listing review fields")
        rid = review["resource_id"]
        sid = review["source_id"]
        if not isinstance(rid, str) or rid not in resource_ids:
            raise PublicationError("Review references an unknown course")
        if not isinstance(sid, str) or sid not in contributions[rid]:
            raise PublicationError("Listing review source does not match provenance")
        if rid in result:
            raise PublicationError("Ambiguous duplicate listing review")
        if review["status"] not in STATUSES:
            raise PublicationError("Unsupported listing review status")
        reviewer = review["reviewer"]
        if (not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 80
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in reviewer)):
            raise PublicationError("Invalid listing reviewer identifier")
        checked = _checked_at(review["checked_at"])
        source = source_by_id[sid]
        source.check_url(review["evidence_url"])
        official = hostname(source.provider_website)
        reviewed = hostname(review["evidence_url"])
        if reviewed != official and not reviewed.endswith("." + official):
            raise PublicationError("Listing evidence must be on the official provider domain")
        result[rid] = (review, checked)
    return result


def build_reviewed_catalog(
    base_catalog, registry, submissions, listing_reviews, ledger, *, now=None
):
    """Compile publication candidates using approved offline sources only.

    submissions: dict[source_id] -> manual JSON batch, or for RSS
    {"xml": bytes, "annotations": curated skill mapping}.

    Release requires a current approved listing review plus independently reviewed
    official claims for availability=available and course-access cost. Certificate
    claims remain unknown unless separately approved and current.
    """
    moment = _clock(now)
    sources = load_registry(registry)
    source_by_id = {s.id: s for s in sources}
    if not isinstance(submissions, dict) or len(submissions) > MAX_SUBMISSIONS:
        raise PublicationError("Invalid offline submission registry")
    if not isinstance(base_catalog, dict) or base_catalog.get("schema_version") != "1.0.0":
        raise PublicationError("Invalid base skill catalog")
    skills = base_catalog.get("skills")
    if not isinstance(skills, list) or not skills:
        raise PublicationError("A reviewed skill catalog is required")
    known_skills = {skill.get("id") for skill in skills if isinstance(skill, dict)}
    if len(known_skills) != len(skills) or any(not valid_id(s) for s in known_skills):
        raise PublicationError("Invalid skill registry")
    batches = []
    for sid in sorted(submissions):
        if not isinstance(sid, str) or sid not in source_by_id:
            raise PublicationError("Submission references an unregistered source")
        source = source_by_id[sid]
        source.require_usable()
        payload = submissions[sid]
        if source.method == "rss":
            if not isinstance(payload, dict) or set(payload) != {"xml", "annotations"}:
                raise PublicationError("RSS submission requires XML and curated annotations")
            rows, provenance = normalize_feed(
                source, payload["xml"], payload["annotations"], known_skills
            )
        else:
            rows, provenance = normalize_manual(source, payload, known_skills)
        batches.append((source, rows, provenance))
    unique_batches, contributions, duplicates = _deduplicate(batches)
    staging, attribution = assemble_catalog(base_catalog, unique_batches)
    resources = {record["id"]: record for record in staging["resources"]}
    reviews = _validate_reviews(
        listing_reviews, set(resources), source_by_id, contributions
    )
    # Stage only the explicit reviewer-submitted values. evaluate_claims then
    # independently checks approval, recency, official domain and expected values.
    if not isinstance(ledger, dict) or set(ledger) != {"schema_version", "claims"}:
        raise PublicationError("Unsupported claim ledger")
    if not isinstance(ledger["claims"], list) or len(ledger["claims"]) > MAX_REVIEWS:
        raise PublicationError("Invalid claim ledger batch")
    by_claim = {}
    for claim in ledger["claims"]:
        required = {"resource_id", "claim", "value", "source_url", "checked_at",
                    "reviewer", "status"}
        if (not isinstance(claim, dict) or set(claim) != required
                or not isinstance(claim["resource_id"], str)
                or not isinstance(claim["claim"], str)):
            raise PublicationError("Invalid claim review record")
        if claim["claim"] in COST_CLAIMS:
            rid = claim["resource_id"]
            if rid in resources and claim["status"] == "approved":
                resources[rid][claim["claim"]] = claim["value"]
        by_claim[(claim["resource_id"], claim["claim"])] = claim
    try:
        trusted = evaluate_claims(staging, ledger, now=moment)
    except (EvidenceError, KeyError, TypeError) as exc:
        raise PublicationError("Invalid or unsupported claim review ledger") from exc
    published = []
    excluded = []
    reasons = {}
    for rid in sorted(resources):
        review_data = reviews.get(rid)
        if review_data is None:
            reason = "missing_listing_review"
        else:
            review, reviewed_at = review_data
            if review["status"] != "approved":
                reason = "listing_not_approved"
            elif reviewed_at > moment or moment - reviewed_at > timedelta(days=LISTING_REVIEW_DAYS):
                reason = "listing_review_stale"
            elif trusted.get((rid, "availability")) != "available":
                reason = "availability_not_verified"
            elif (rid, "access_cost") not in trusted:
                reason = "access_cost_not_verified"
            else:
                reason = None
        if reason:
            excluded.append({"resource_id": rid, "reason": reason})
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        cost = trusted[(rid, "access_cost")]
        certificate = trusted.get((rid, "certificate_cost"), "unknown")
        availability = by_claim[(rid, "availability")]
        published_resource = copy.deepcopy(resources[rid])
        published_resource["access_cost"] = cost
        published_resource["certificate_cost"] = certificate
        published_resource["evidence"] = {
            "status": "verified",
            "source_url": availability["source_url"],
            "checked_at": availability["checked_at"],
        }
        published.append(published_resource)
        attribution[rid]["source_ids"] = list(contributions[rid])
        attribution[rid]["listing_reviewed_at"] = review["checked_at"]
        attribution[rid]["listing_evidence_url"] = review["evidence_url"]
        attribution[rid]["listing_reviewer"] = review["reviewer"]
        attribution[rid]["verified_claims"] = sorted([
            claim for claim in ("availability", "access_cost", "certificate_cost")
            if (rid, claim) in trusted
        ])
        attribution[rid]["claim_evidence"] = {
            name: {
                "source_url": by_claim[(rid, name)]["source_url"],
                "checked_at": by_claim[(rid, name)]["checked_at"],
                "reviewer": by_claim[(rid, name)]["reviewer"],
            }
            for name in attribution[rid]["verified_claims"]
        }
    used_providers = {resource["provider_id"] for resource in published}
    output_catalog = {
        "schema_version": "1.0.0",
        "providers": [p for p in staging["providers"] if p["id"] in used_providers],
        "skills": copy.deepcopy(staging["skills"]),
        "resources": published,
    }
    return {
        "schema_version": "1.0.0",
        "catalog": output_catalog,
        "provenance": {rid: attribution[rid] for rid in sorted(attribution) if rid in {
            r["id"] for r in published
        }},
        "review_report": {
            "candidates": len(resources),
            "published": len(published),
            "exact_duplicates_collapsed": duplicates,
            "excluded": excluded,
            "excluded_reasons": {reason: reasons[reason] for reason in sorted(reasons)},
        },
    }
