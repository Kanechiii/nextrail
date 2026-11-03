"""Read-only provider rights dossier audit; never an authorization or activation.

The dossier documents reviewer assertions for independent manual sign-off.
It is intentionally disconnected from the runtime authorization ledger.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_discovery.contracts import SourceContractError, hostname, valid_id
from nextrail_discovery.pipeline import PublicationError
from publish_course_catalog import read_json

SCHEMA_VERSION = "1.0.0"
MAX_PROVIDERS = 100
MAX_REVIEW_AGE = timedelta(days=90)
ENTRY_FIELDS = frozenset({
    "provider_id", "provider_name", "official_website", "review_state",
    "proposed_method", "rights", "evidence", "course_claims",
})
RIGHTS_FIELDS = frozenset({
    "metadata_collection", "metadata_display", "metadata_caching",
    "commercial_use", "attribution_requirements",
})
CLAIM_FIELDS = frozenset({
    "availability", "access_cost", "certificate_cost", "student_eligibility",
})
EVIDENCE_FIELDS = frozenset({
    "permission_basis", "permission_url", "reviewer_id", "reviewed_at", "expires_at",
})
RIGHT_CHOICES = frozenset({"unknown", "permitted", "prohibited"})
REVIEW_STATES = frozenset({"pending", "blocked", "evidence_submitted"})
METHODS = frozenset({"undetermined", "manual", "official_api", "rss"})


class RightsReviewError(ValueError):
    """Provider evidence is invalid or incompatible with a safe review."""


def _timestamp(value, field):
    if not isinstance(value, str) or not 15 <= len(value) <= 40:
        raise RightsReviewError(f"Invalid {field} timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RightsReviewError(f"Invalid {field} timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise RightsReviewError(f"{field} must specify a timezone")
    return result.astimezone(timezone.utc)


def _evidence_status(evidence, moment):
    basis = evidence["permission_basis"]
    url = evidence["permission_url"]
    reviewer = evidence["reviewer_id"]
    checked = evidence["reviewed_at"]
    expires = evidence["expires_at"]
    if basis == "unverified":
        if any(field is not None for field in (url, reviewer, checked, expires)):
            raise RightsReviewError("Unverified evidence must have empty metadata")
        return "permission_evidence_missing"
    if basis not in ("published_terms", "direct_permission"):
        raise RightsReviewError("Unsupported permission evidence basis")
    if not isinstance(url, str):
        return "permission_evidence_missing"
    hostname(url)
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment:
        raise RightsReviewError("Permission evidence URL must not contain query or fragment")
    if not valid_id(reviewer):
        return "permission_evidence_missing"
    if checked is None or expires is None:
        return "permission_evidence_missing"
    reviewed_at = _timestamp(checked, "reviewed_at")
    expires_at = _timestamp(expires, "expires_at")
    if expires_at <= reviewed_at or expires_at - reviewed_at > MAX_REVIEW_AGE:
        return "permission_evidence_stale"
    if reviewed_at > moment or expires_at <= moment or moment - reviewed_at > MAX_REVIEW_AGE:
        return "permission_evidence_stale"
    return "evidence_submitted_for_review"


def audit_dossier(document, *, now=None):
    """Assess supplied local evidence, without issuing provider permission."""
    moment = datetime.now(timezone.utc) if now is None else now
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise RightsReviewError("A timezone-aware audit clock is required")
    moment = moment.astimezone(timezone.utc)
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "review_purpose", "providers"}
            or document["schema_version"] != SCHEMA_VERSION
            or document["review_purpose"] != "planning_only"):
        raise RightsReviewError("Invalid provider-rights dossier header")
    providers = document["providers"]
    if not isinstance(providers, list) or len(providers) > MAX_PROVIDERS:
        raise RightsReviewError("Invalid provider review collection")
    seen = set()
    rows = []
    for entry in providers:
        if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS:
            raise RightsReviewError("Unexpected provider review fields")
        pid = entry["provider_id"]
        if not valid_id(pid) or pid in seen:
            raise RightsReviewError("Invalid or duplicate provider review ID")
        seen.add(pid)
        name = entry["provider_name"]
        if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 120
                or any(ord(c) < 32 or ord(c) == 127 for c in name)):
            raise RightsReviewError("Invalid provider label")
        hostname(entry["official_website"])
        state = entry["review_state"]
        method = entry["proposed_method"]
        if state not in REVIEW_STATES or method not in METHODS:
            raise RightsReviewError("Invalid provider review state or method")
        rights = entry["rights"]
        claims = entry["course_claims"]
        evidence = entry["evidence"]
        if (not isinstance(rights, dict) or set(rights) != RIGHTS_FIELDS
                or not isinstance(claims, dict) or set(claims) != CLAIM_FIELDS
                or not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS):
            raise RightsReviewError("Missing or unexpected review evidence fields")
        if (any(rights[k] not in RIGHT_CHOICES
                for k in RIGHTS_FIELDS - {"attribution_requirements"})
                or rights["attribution_requirements"] not in ("unknown", "documented")
                or any(claims[k] not in ("unknown", "reviewed") for k in CLAIM_FIELDS)):
            raise RightsReviewError("Unrecognized rights or claim review status")
        evidence_status = _evidence_status(evidence, moment)
        if state == "pending":
            if (method != "undetermined" or evidence_status != "permission_evidence_missing"
                    or any(value != "unknown" for value in rights.values())
                    or any(value != "unknown" for value in claims.values())):
                raise RightsReviewError("Pending reviews cannot assert provider rights")
            status = "pending"
        elif state == "blocked":
            status = "blocked_by_reviewer"
        elif method == "undetermined":
            status = "collection_method_unverified"
        elif evidence_status != "evidence_submitted_for_review":
            status = evidence_status
        elif any(rights[key] == "prohibited" for key in
                 ("metadata_collection", "metadata_display", "metadata_caching")):
            status = "rights_prohibit_planned_use"
        elif any(value == "unknown" for value in rights.values()):
            status = "rights_review_incomplete"
        elif any(value != "reviewed" for value in claims.values()):
            status = "course_claim_review_incomplete"
        else:
            # Evidence completeness is a human-review queue, not authorization.
            status = "requires_independent_signoff"
        rows.append({"provider_id": pid, "review_state": state, "status": status})

    rows.sort(key=lambda item: item["provider_id"])
    ready = sum(row["status"] == "requires_independent_signoff" for row in rows)
    pending = sum(row["status"] == "pending" for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_mode": "offline_read_only",
        "status": "manual_independent_review_required" if ready else "blocked_no_provider_rights",
        "provider_count": len(rows),
        "pending_provider_reviews": pending,
        "evidence_dossiers_for_signoff": ready,
        "providers": rows,
        "rights_independently_verified": False,
        "authorization_records_written": 0,
        "remote_requests_performed": 0,
        "runtime_activation_performed": False,
        "manual_source_approval_required": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit local provider-rights evidence without granting permission"
    )
    parser.add_argument("--dossier", required=True)
    parser.add_argument(
        "--expect-pending", action="store_true",
        help="CI gate: all planned providers remain pending with zero signoff dossiers",
    )
    parser.add_argument(
        "--require-review-ready", action="store_true",
        help="Operator check: exit 2 if no evidence dossier needs independent signoff",
    )
    args = parser.parse_args(argv)
    try:
        report = audit_dossier(read_json(args.dossier, size_limit=1_000_000))
        if args.expect_pending and (
            not report["provider_count"]
            or report["pending_provider_reviews"] != report["provider_count"]
            or report["evidence_dossiers_for_signoff"] != 0
        ):
            raise RightsReviewError("Sample requires pending rights with no provider approvals")
        print(json.dumps(report, sort_keys=True, indent=2))
        if args.require_review_ready and not report["evidence_dossiers_for_signoff"]:
            print("BLOCKED: no evidence dossiers are ready for independent review",
                  file=sys.stderr)
            return 2
        return 0
    except (RightsReviewError, PublicationError, SourceContractError,
            OSError, KeyError, TypeError, ValueError) as exc:
        print(f"FAIL: Provider rights audit rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
