"""Offline claim review: explicit evidence, review status and bounded freshness."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

CLAIMS = {"access_cost", "certificate_cost", "availability"}
VALUES = {
    "access_cost": {"free", "paid", "conditional"},
    "certificate_cost": {"free", "paid", "not_offered"},
    "availability": {"available", "unavailable"},
}
MAX_AGE_DAYS = {"access_cost": 30, "certificate_cost": 30, "availability": 7}


class EvidenceError(ValueError):
    pass


def _timestamp(value):
    if not isinstance(value, str):
        raise EvidenceError("Missing evidence timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("Invalid evidence timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise EvidenceError("Evidence timestamp must be timezone-aware")
    return result.astimezone(timezone.utc)


def _url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(x) < 33 for x in value):
        raise EvidenceError("Invalid evidence URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise EvidenceError("Invalid evidence URL") from exc
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or port not in (None, 443)
            or parsed.fragment):
        raise EvidenceError("Evidence requires a credential-free HTTPS URL")
    return parsed.hostname.lower()


def evaluate_claims(catalog, ledger, *, now=None):
    """Return trusted claims keyed by (resource_id, claim); never trust ledger alone."""
    if not isinstance(catalog, dict) or catalog.get("schema_version") != "1.0.0":
        raise EvidenceError("Invalid catalog")
    if not isinstance(ledger, dict) or set(ledger) != {"schema_version", "claims"}:
        raise EvidenceError("Invalid evidence ledger")
    if ledger["schema_version"] != "1.0.0" or not isinstance(ledger["claims"], list):
        raise EvidenceError("Unsupported evidence ledger")
    moment = datetime.now(timezone.utc) if now is None else now
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise EvidenceError("Review clock must be timezone-aware")
    moment = moment.astimezone(timezone.utc)
    if len(ledger["claims"]) > 10000:
        raise EvidenceError("Excessive evidence records")
    resources = {r["id"]: r for r in catalog["resources"]}
    providers = {p["id"]: p for p in catalog["providers"]}
    trusted = {}
    seen = set()
    for item in ledger["claims"]:
        fields = {"resource_id", "claim", "value", "source_url", "checked_at", "reviewer", "status"}
        if not isinstance(item, dict) or set(item) != fields:
            raise EvidenceError("Invalid evidence record fields")
        rid, claim = item["resource_id"], item["claim"]
        if not isinstance(rid, str) or rid not in resources or claim not in CLAIMS:
            raise EvidenceError("Unknown resource or claim")
        key = (rid, claim)
        if key in seen:
            raise EvidenceError("Ambiguous duplicate claim")
        seen.add(key)
        value = item["value"]
        if not isinstance(value, str) or value not in VALUES[claim]:
            raise EvidenceError("Unsupported claim value")
        if item["status"] not in ("approved", "pending", "rejected"):
            raise EvidenceError("Invalid review state")
        if not isinstance(item["reviewer"], str) or not 1 <= len(item["reviewer"]) <= 80:
            raise EvidenceError("Missing reviewer identifier")
        host = _url(item["source_url"])
        date = _timestamp(item["checked_at"])
        resource = resources[rid]
        provider = providers.get(resource["provider_id"])
        if not provider:
            raise EvidenceError("Unknown provider")
        if resource["synthetic"] or provider["authorization"] != "approved":
            continue
        expected = resource.get(claim)
        if claim != "availability" and expected != value:
            continue
        official_host = _url(provider["website"])
        if host != official_host and not host.endswith("." + official_host):
            continue
        if date > moment or moment - date > timedelta(days=MAX_AGE_DAYS[claim]):
            continue
        if item["status"] == "approved":
            trusted[key] = value
    return trusted
