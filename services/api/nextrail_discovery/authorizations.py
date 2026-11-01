"""Offline, explicit authorization preflight for future real source onboarding.

Records are operator assertions, not cryptographic signatures, proof of
provider consent, or permission to start network ingestion. The Phase 16
publication path is deliberately unchanged until a separate reviewed gate.
"""
from datetime import datetime, timedelta, timezone

from .contracts import SourceContractError, hostname, load_registry, valid_id

MAX_AUTHORIZATIONS = 100
MAX_REVIEW_AGE = timedelta(days=90)
PERMISSION_BASES = frozenset({"published_terms", "direct_permission"})
ENTRY_FIELDS = frozenset({
    "source_id", "provider_id", "source_url", "method", "status",
    "allowed_hosts", "permission_basis", "permission_url",
    "reviewer", "reviewed_at", "expires_at",
})


class AuthorizationContractError(SourceContractError):
    """A source authorization record is missing, inconsistent or not current."""


def _moment(now):
    value = datetime.now(timezone.utc) if now is None else now
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AuthorizationContractError("Authorization clock must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value, field):
    if not isinstance(value, str) or not 15 <= len(value) <= 40:
        raise AuthorizationContractError(f"Invalid {field} timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorizationContractError(f"Invalid {field} timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthorizationContractError(f"{field} must specify a time zone")
    return parsed.astimezone(timezone.utc)


def load_source_authorizations(source_registry, document, *, now=None):
    """Verify matching approved source permissions without changing the registry.

    The return value contains only approved, non-synthetic source IDs, sorted
    deterministically. An approved registry source without current matching
    review evidence aborts the entire preflight, rather than being skipped.
    """
    moment = _moment(now)
    try:
        sources = load_registry(source_registry)
    except SourceContractError as exc:
        raise AuthorizationContractError("Invalid source registry for authorization preflight") from exc
    by_id = {source.id: source for source in sources}
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "authorizations"}
            or document["schema_version"] != "1.0.0"):
        raise AuthorizationContractError("Invalid provider authorization document")
    rows = document["authorizations"]
    if not isinstance(rows, list) or len(rows) > MAX_AUTHORIZATIONS:
        raise AuthorizationContractError("Invalid authorization record collection")

    seen = set()
    approved = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != ENTRY_FIELDS:
            raise AuthorizationContractError("Unknown or missing authorization properties")
        sid = row["source_id"]
        if not valid_id(sid) or sid not in by_id or sid in seen:
            raise AuthorizationContractError("Unknown or duplicate authorization source")
        seen.add(sid)
        source = by_id[sid]
        if (row["provider_id"] != source.provider_id
                or row["source_url"] != source.source_url
                or row["method"] != source.method
                or not isinstance(row["allowed_hosts"], list)
                or row["allowed_hosts"] != list(source.allowed_hosts)):
            raise AuthorizationContractError("Authorization scope conflicts with source registry")

        if row["status"] not in ("approved", "revoked"):
            raise AuthorizationContractError("Unsupported authorization status")
        if not isinstance(row["permission_basis"], str) or row["permission_basis"] not in PERMISSION_BASES:
            raise AuthorizationContractError("Unknown permission basis")
        if not isinstance(row["reviewer"], str) or len(row["reviewer"]) > 80 or not valid_id(row["reviewer"]):
            raise AuthorizationContractError("Invalid reviewer identifier")

        # Permission evidence is tied to the registered official provider
        # website and explicitly approved hosts, never an arbitrary URL.
        try:
            official_host = hostname(source.provider_website)
            permission_host = hostname(row["permission_url"])
        except SourceContractError as exc:
            raise AuthorizationContractError("Invalid official permission evidence URL") from exc
        if (permission_host not in source.allowed_hosts
                or (permission_host != official_host
                    and not permission_host.endswith("." + official_host))):
            raise AuthorizationContractError("Permission evidence must use an allowed official host")

        reviewed = _timestamp(row["reviewed_at"], "reviewed_at")
        expires = _timestamp(row["expires_at"], "expires_at")
        if (reviewed > moment or expires <= reviewed
                or expires - reviewed > MAX_REVIEW_AGE):
            raise AuthorizationContractError("Invalid authorization review time window")

        if row["status"] == "approved":
            if source.synthetic or source.authorization != "approved":
                raise AuthorizationContractError("Pending or synthetic source cannot be authorized")
            if reviewed < moment - MAX_REVIEW_AGE or expires <= moment:
                raise AuthorizationContractError("Approved source authorization is stale or expired")
            approved.add(sid)

    required = {
        source.id for source in sources
        if source.authorization == "approved" and not source.synthetic
    }
    if approved != required:
        raise AuthorizationContractError("Missing current approval or source authorization revoked")
    return tuple(sorted(approved))
