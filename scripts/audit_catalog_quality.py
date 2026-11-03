"""Offline catalog freshness and quality audit; no remote requests or publication.

Reuse the exact reviewed-course publisher to avoid inventing another
eligibility policy. Only already-eligible courses enter the refresh queue.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_discovery import SourceContractError
from nextrail_discovery.pipeline import LISTING_REVIEW_DAYS, PublicationError
from nextrail_evidence.review import MAX_AGE_DAYS
from publish_course_catalog import compile_local_bundle


def _clock(now):
    moment = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(moment, datetime) or moment.tzinfo is None
            or moment.utcoffset() is None):
        raise PublicationError("Quality audit requires a timezone-aware clock")
    return moment.astimezone(timezone.utc)


def _reviewed_at(value):
    if not isinstance(value, str):
        raise PublicationError("Invalid reviewed catalog timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationError("Invalid reviewed catalog timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PublicationError("Catalog review timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def quality_report(bundle, grant_count, *, now=None, refresh_window_hours=48):
    """Report safe quality/freshness counts from the existing compiled bundle."""
    moment = _clock(now)
    if (type(refresh_window_hours) is not int
            or not 0 <= refresh_window_hours <= 168):
        raise PublicationError("Refresh window must be between 0 and 168 hours")
    if type(grant_count) is not int or grant_count < 0:
        raise PublicationError("Invalid authorization assertion count")
    window_end = moment + timedelta(hours=refresh_window_hours)
    catalog = bundle["catalog"]
    review = bundle["review_report"]
    provenance = bundle["provenance"]
    courses = catalog["resources"]
    course_ids = {course["id"] for course in courses}
    if (len(course_ids) != len(courses)
            or set(provenance) != course_ids
            or review["published"] != len(courses)
            or review["candidates"] != len(courses) + len(review["excluded"])
            or review["candidates"] < 0):
        raise PublicationError("Reviewed catalog quality counts are inconsistent")

    age_policies = {
        "listing": LISTING_REVIEW_DAYS,
        "availability": MAX_AGE_DAYS["availability"],
        "access_cost": MAX_AGE_DAYS["access_cost"],
        "certificate_cost": MAX_AGE_DAYS["certificate_cost"],
    }
    due_counts = {claim: 0 for claim in age_policies}
    refresh_queue = []
    unknown_certificates = 0

    for course in sorted(courses, key=lambda item: item["id"]):
        rid = course["id"]
        details = provenance[rid]
        claims = details["claim_evidence"]
        expected = {"availability", "access_cost"}
        if course["certificate_cost"] == "unknown":
            unknown_certificates += 1
        else:
            expected.add("certificate_cost")
        if (set(claims) != expected
                or course["access_cost"] not in ("free", "paid", "conditional")
                or course["evidence"]["checked_at"] != claims["availability"]["checked_at"]):
            raise PublicationError("Inconsistent reviewed claim provenance")

        timestamps = {"listing": details["listing_reviewed_at"]}
        timestamps.update({
            claim: claims[claim]["checked_at"]
            for claim in expected
        })
        due = []
        for claim, value in sorted(timestamps.items()):
            checked = _reviewed_at(value)
            expires = checked + timedelta(days=age_policies[claim])
            if checked > moment or expires < moment:
                raise PublicationError("Published course has stale or future evidence")
            if expires <= window_end:
                due_counts[claim] += 1
                due.append(claim)
        if due:
            refresh_queue.append({
                "resource_id": rid,
                "checks_due": due,
            })

    exclusions = review["excluded_reasons"]
    if (sum(exclusions.values()) != len(review["excluded"])
            or any(exclusions.get(row["reason"], 0) < 1
                   for row in review["excluded"])):
        raise PublicationError("Invalid catalog exclusion summary")

    return {
        "schema_version": "1.0.0",
        "audit_mode": "offline_read_only",
        "status": ("manual_release_approval_required" if courses
                   else "blocked_no_reviewed_courses"),
        "current_authorization_assertions": grant_count,
        "candidate_count": review["candidates"],
        "reviewed_course_candidates": len(courses),
        "excluded_course_count": len(review["excluded"]),
        "excluded_reasons": {key: exclusions[key] for key in sorted(exclusions)},
        "exact_duplicates_collapsed": review["exact_duplicates_collapsed"],
        "certificate_cost_unknown_count": unknown_certificates,
        "refresh_window_hours": refresh_window_hours,
        "refresh_due_counts": due_counts,
        "refresh_queue": refresh_queue,
        "manual_provider_permission_verification_required": True,
        "manual_course_evidence_verification_required": True,
        "manual_release_approval_required": True,
        "remote_requests_performed": 0,
        "catalog_files_written": 0,
        "runtime_activation_performed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit offline reviewed catalog quality without publishing or fetching"
    )
    parser.add_argument("--base-catalog", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--authorizations", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--listing-reviews", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument("--refresh-window-hours", type=int, default=48)
    parser.add_argument(
        "--expect-empty", action="store_true",
        help="CI: require zero real-source assertions and zero course candidates",
    )
    parser.add_argument(
        "--require-reviewed-candidates", action="store_true",
        help="Operator: exit 2 if no locally eligible courses await release review",
    )
    args = parser.parse_args(argv)
    try:
        bundle, grants = compile_local_bundle(
            args.base_catalog, args.sources, args.authorizations,
            args.manifest, args.listing_reviews, args.claims,
        )
        report = quality_report(
            bundle, len(grants), refresh_window_hours=args.refresh_window_hours,
        )
        if args.expect_empty and (
            report["current_authorization_assertions"] != 0
            or report["candidate_count"] != 0
            or report["reviewed_course_candidates"] != 0
        ):
            raise PublicationError("Sample must contain zero authorized real sources and courses")
        print(json.dumps(report, sort_keys=True, indent=2))
        if args.require_reviewed_candidates and not report["reviewed_course_candidates"]:
            print("BLOCKED: no reviewed courses await independent release approval",
                  file=sys.stderr)
            return 2
        return 0
    except (PublicationError, SourceContractError, OSError, KeyError,
            TypeError, ValueError, OverflowError) as exc:
        print(f"FAIL: Catalog quality audit rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
