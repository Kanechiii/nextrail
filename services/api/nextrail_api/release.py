"""Pinned, offline reviewed catalog release gate.

The hash pins operator-reviewed bytes, not provider authenticity. No third-party
network calls, automatic downloads, file replacement, or provider activation.
"""
import copy
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nextrail_discovery.contracts import hostname, valid_id
from nextrail_discovery.pipeline import LISTING_REVIEW_DAYS
from nextrail_evidence.review import MAX_AGE_DAYS
from nextrail_orchestration.agents import CatalogAgent, OrchestrationError

MAX_RELEASE_BYTES = 2_000_000
DIGEST = re.compile(r"^[0-9a-f]{64}$")
SOURCE_METHODS = frozenset({"manual", "official_api", "rss"})
PROVIDER_FIELDS = {"id", "name", "website", "access_method", "authorization"}
RESOURCE_FIELDS = {
    "id", "provider_id", "title", "url", "skills", "prerequisites",
    "access_cost", "certificate_cost", "evidence", "synthetic",
}
PROVENANCE_FIELDS = {
    "source_id", "source_url", "external_id", "method", "verification",
    "source_ids", "listing_reviewed_at", "listing_evidence_url",
    "listing_reviewer", "verified_claims", "claim_evidence",
}
REPORT_FIELDS = {
    "candidates", "published", "exact_duplicates_collapsed",
    "excluded", "excluded_reasons",
}


class ReleaseError(ValueError):
    """An untrusted, inconsistent or expired reviewed catalog release."""


def _now(value):
    clock = datetime.now(timezone.utc) if value is None else value
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        raise ReleaseError("A timezone-aware release clock is required")
    return clock.astimezone(timezone.utc)


def _checked(value, label):
    if not isinstance(value, str) or len(value) > 64:
        raise ReleaseError(f"Missing {label} review timestamp")
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseError(f"Invalid {label} review timestamp") from exc
    if date.tzinfo is None or date.utcoffset() is None:
        raise ReleaseError(f"Timezone required for {label} review")
    return date.astimezone(timezone.utc)


def _expiry(value, days, label, moment):
    date = _checked(value, label)
    if date > moment:
        raise ReleaseError(f"Future-dated {label} evidence")
    expiry = date + timedelta(days=days)
    if expiry < moment:
        raise ReleaseError(f"Stale {label} evidence")
    return expiry


def _official(url, provider_host, label):
    try:
        host = hostname(url)
    except (TypeError, ValueError) as exc:
        raise ReleaseError(f"Invalid {label} source URL") from exc
    if host != provider_host and not host.endswith("." + provider_host):
        raise ReleaseError(f"{label} URL must be on the provider's official domain")


def _reviewer(value):
    return (
        isinstance(value, str) and 1 <= len(value.strip()) <= 80
        and all(ord(ch) >= 32 and ord(ch) != 127 for ch in value)
    )


def _positive_int(value):
    return type(value) is int and value >= 0


@dataclass(frozen=True)
class ReviewedBundle:
    """Runtime holds a fixed validated catalog until an explicit restart."""
    catalog: dict
    expires_at: datetime
    reviewed_course_count: int
    sha256: str
    verified_free_resource_ids: frozenset[str]

    def current_catalog(self, *, now=None):
        if _now(now) > self.expires_at:
            raise ReleaseError("Reviewed course evidence has expired")
        return self.catalog


def validate_reviewed_bundle(document, *, now=None):
    """Check every published record and provenance link; fail closed as a unit."""
    moment = _now(now)
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "catalog", "provenance", "review_report"}
            or document["schema_version"] != "1.0.0"):
        raise ReleaseError("Unsupported reviewed catalog release")
    catalog = document["catalog"]
    try:
        CatalogAgent().run(catalog)
    except (OrchestrationError, ValueError, TypeError, KeyError, RecursionError) as exc:
        raise ReleaseError("Reviewed catalog violates the existing quality contract") from exc

    provider_by_id = {}
    for provider in catalog["providers"]:
        if (not isinstance(provider, dict) or set(provider) != PROVIDER_FIELDS
                or not valid_id(provider["id"])
                or provider["authorization"] != "approved"
                or provider["access_method"] not in SOURCE_METHODS):
            raise ReleaseError("Unapproved or malformed reviewed provider")
        host = hostname(provider["website"])
        provider_by_id[provider["id"]] = host

    resources = catalog["resources"]
    provenance = document["provenance"]
    report = document["review_report"]
    resource_ids = {resource["id"] for resource in resources}
    if (not isinstance(provenance, dict) or set(provenance) != resource_ids
            or not isinstance(report, dict) or set(report) != REPORT_FIELDS
            or not _positive_int(report["candidates"])
            or not _positive_int(report["published"])
            or report["published"] != len(resources)
            or report["candidates"] < report["published"]
            or not _positive_int(report["exact_duplicates_collapsed"])
            or not isinstance(report["excluded"], list)
            or not isinstance(report["excluded_reasons"], dict)):
        raise ReleaseError("Invalid reviewed publication manifest")

    expiry_values = []
    for resource in resources:
        rid = resource["id"]
        provider_host = provider_by_id[resource["provider_id"]]
        if (set(resource) != RESOURCE_FIELDS
                or resource["synthetic"] is not False
                or resource["access_cost"] not in {"free", "paid", "conditional"}
                or resource["evidence"]["status"] != "verified"
                or set(resource["evidence"]) != {"status", "source_url", "checked_at"}):
            raise ReleaseError("Unverified or malformed published course")
        _official(resource["url"], provider_host, "course")
        item = provenance[rid]
        if not isinstance(item, dict) or set(item) != PROVENANCE_FIELDS:
            raise ReleaseError("Missing or malformed source attribution")
        sid = item["source_id"]
        source_ids = item["source_ids"]
        if (not valid_id(sid) or not valid_id(item["external_id"])
                or item["method"] not in SOURCE_METHODS
                or item["verification"] != "unverified"
                or not isinstance(source_ids, list) or not source_ids
                or any(not valid_id(s) for s in source_ids)
                or len(source_ids) != len(set(source_ids)) or sid not in source_ids
                or not _reviewer(item["listing_reviewer"])):
            raise ReleaseError("Invalid source lineage or listing reviewer")
        _official(item["source_url"], provider_host, "snapshot")
        _official(item["listing_evidence_url"], provider_host, "listing")
        expiry_values.append(_expiry(
            item["listing_reviewed_at"], LISTING_REVIEW_DAYS, "listing", moment
        ))

        claims = item["verified_claims"]
        evidence = item["claim_evidence"]
        if (not isinstance(claims, list) or len(claims) != len(set(claims))
                or not isinstance(evidence, dict) or set(claims) != set(evidence)
                or not {"availability", "access_cost"}.issubset(claims)
                or not set(claims).issubset(MAX_AGE_DAYS)):
            raise ReleaseError("Missing required claim evidence")
        if ("certificate_cost" in claims) != (resource["certificate_cost"] != "unknown"):
            raise ReleaseError("Certificate price requires independently reviewed evidence")
        for claim in claims:
            detail = evidence[claim]
            if (not isinstance(detail, dict)
                    or set(detail) != {"source_url", "checked_at", "reviewer"}
                    or not _reviewer(detail["reviewer"])):
                raise ReleaseError("Malformed claim review record")
            _official(detail["source_url"], provider_host, claim)
            expiry_values.append(_expiry(
                detail["checked_at"], MAX_AGE_DAYS[claim], claim, moment
            ))
        availability = evidence["availability"]
        if (resource["evidence"]["source_url"] != availability["source_url"]
                or resource["evidence"]["checked_at"] != availability["checked_at"]):
            raise ReleaseError("Published availability disagrees with review provenance")

    if report["candidates"] != report["published"] + len(report["excluded"]):
        raise ReleaseError("Reviewed release report counts do not match")
    excluded_counts = {}
    for row in report["excluded"]:
        if (not isinstance(row, dict) or set(row) != {"resource_id", "reason"}
                or not valid_id(row["resource_id"])
                or not isinstance(row["reason"], str) or not row["reason"]):
            raise ReleaseError("Malformed exclusion report")
        excluded_counts[row["reason"]] = excluded_counts.get(row["reason"], 0) + 1
    if (report["excluded_reasons"] != excluded_counts
            or any(not _positive_int(v) for v in report["excluded_reasons"].values())):
        raise ReleaseError("Inconsistent excluded-course counts")

    # Empty, reviewed-source-only dry runs are allowed; they still have no courses.
    expiry = min(expiry_values) if expiry_values else moment + timedelta(days=1)
    return copy.deepcopy(catalog), expiry


def _no_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ReleaseError("Ambiguous duplicate JSON key")
        obj[key] = value
    return obj


def load_reviewed_bundle(path, expected_sha256, *, now=None):
    if (not isinstance(expected_sha256, str) or not DIGEST.fullmatch(expected_sha256)):
        raise ReleaseError("Explicit lowercase SHA-256 release pin is required")
    if not isinstance(path, (str, Path)) or not str(path):
        raise ReleaseError("Reviewed bundle path is required")
    location = Path(path)
    if location.is_symlink() or not location.is_file() or location.suffix != ".json":
        raise ReleaseError("Reviewed bundle must be an existing regular JSON file")
    if location.stat().st_size > MAX_RELEASE_BYTES:
        raise ReleaseError("Reviewed bundle exceeds the safe file limit")
    try:
        with location.open("rb") as handle:
            raw = handle.read(MAX_RELEASE_BYTES + 1)
        if len(raw) > MAX_RELEASE_BYTES:
            raise ReleaseError("Reviewed bundle exceeds the safe file limit")
        digest = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(digest, expected_sha256):
            raise ReleaseError("Reviewed bundle does not match its pinned SHA-256")
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        raise ReleaseError("Unable to read the pinned reviewed bundle") from exc
    try:
        catalog, expires_at = validate_reviewed_bundle(document, now=now)
    except (TypeError, KeyError, IndexError, AttributeError) as exc:
        raise ReleaseError("Malformed reviewed release fields") from exc
    return ReviewedBundle(
        catalog=catalog,
        expires_at=expires_at,
        reviewed_course_count=len(catalog["resources"]),
        sha256=digest,
        # The full reviewed bundle has already passed provenance, provider,
        # official-domain and claim-freshness gates. Bare v1 catalogs cannot
        # grant zero-budget access by setting an arbitrary "free" flag.
        verified_free_resource_ids=frozenset(
            resource["id"] for resource in catalog["resources"]
            if resource["access_cost"] == "free"
        ),
    )
