"""Offline pre-release evidence completeness check; never a deployment approval.

Approval records are operator assertions. Integrity pins protect copied review
artifacts against accidental changes, not against malicious/fabricated reviews.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re

GATES = (
    "authorized_provider_integration",
    "reviewed_catalog_publication",
    "production_account_recovery",
    "transport_origin_and_abuse_controls",
    "privacy_retention_and_erasure",
    "database_backup_and_restore",
    "reliability_load_and_observability",
    "security_and_regression_validation",
    "rollback_and_incident_response",
    "manual_release_approval",
)
MAX_MANIFEST_BYTES = 65536
MAX_EVIDENCE_BYTES = 2000000
MAX_REVIEW_AGE = timedelta(days=90)
_REVIEWER_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_FILE_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class AcceptanceError(ValueError):
    """Pre-release acceptance evidence is missing, invalid or inconsistent."""


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AcceptanceError("Duplicate acceptance JSON property")
        result[key] = value
    return result


def _document(path):
    if not isinstance(path, (str, Path)):
        raise AcceptanceError("Expected an existing acceptance JSON file")
    file = Path(path)
    if file.is_symlink() or not file.is_file():
        raise AcceptanceError("Expected an existing non-symlink acceptance JSON file")
    try:
        with file.open("rb") as handle:
            raw = handle.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise AcceptanceError("Acceptance manifest exceeds size limit")
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, ValueError) as exc:
        raise AcceptanceError("Invalid acceptance JSON input") from exc


def _review_timestamp(value, now):
    if not isinstance(value, str) or not 15 <= len(value) <= 40:
        raise AcceptanceError("Invalid approval review timestamp")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcceptanceError("Invalid approval review timestamp") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise AcceptanceError("Review timestamp requires a time zone")
    moment = moment.astimezone(timezone.utc)
    if moment > now or now - moment > MAX_REVIEW_AGE:
        raise AcceptanceError("Approval review is in the future or stale")


def _check_evidence(directory, name, expected_sha):
    if (not isinstance(name, str) or not _FILE_NAME.fullmatch(name)
            or name in (".", "..")):
        raise AcceptanceError("Invalid acceptance evidence filename")
    if not isinstance(expected_sha, str) or not _SHA.fullmatch(expected_sha):
        raise AcceptanceError("Invalid acceptance evidence checksum")
    if directory is None:
        raise AcceptanceError("Approved gates require an evidence directory")
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise AcceptanceError("Evidence directory must be an existing non-symlink directory")
    file = root / name
    if file.is_symlink() or not file.is_file():
        raise AcceptanceError("Evidence must be an existing non-symlink file")
    digest = hashlib.sha256()
    try:
        with file.open("rb") as handle:
            remaining = MAX_EVIDENCE_BYTES
            while True:
                chunk = handle.read(min(remaining + 1, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
                if remaining < 0:
                    raise AcceptanceError("Acceptance evidence exceeds size limit")
                digest.update(chunk)
    except OSError as exc:
        raise AcceptanceError("Unable to read acceptance evidence") from exc
    if not hmac.compare_digest(digest.hexdigest(), expected_sha):
        raise AcceptanceError("Acceptance evidence SHA-256 mismatch")


def evaluate_acceptance(manifest_path, *, evidence_dir=None, now=None):
    """Validate a complete review register without accessing external services.

    'evidence_complete' means required attestations and artifact hashes check
    out locally, NOT that their claims are true or production may begin.
    """
    moment = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(moment, datetime) or moment.tzinfo is None
            or moment.utcoffset() is None):
        raise AcceptanceError("Acceptance verification clock requires a time zone")
    moment = moment.astimezone(timezone.utc)
    manifest = _document(manifest_path)
    if (not isinstance(manifest, dict)
            or set(manifest) != {"schema_version", "gates"}
            or manifest["schema_version"] != "1.0.0"
            or not isinstance(manifest["gates"], dict)
            or set(manifest["gates"]) != set(GATES)):
        raise AcceptanceError("Acceptance register has missing, unknown or invalid gates")

    pending = []
    seen_files = set()
    for gate in GATES:
        record = manifest["gates"][gate]
        if record == {"status": "pending"}:
            pending.append(gate)
            continue
        if (not isinstance(record, dict)
                or set(record) != {
                    "status", "reviewer", "reviewed_at",
                    "evidence_file", "evidence_sha256",
                }
                or record["status"] != "approved"):
            raise AcceptanceError("Unsupported or incomplete acceptance gate record")
        reviewer = record["reviewer"]
        if (not isinstance(reviewer, str) or len(reviewer) > 80
                or not _REVIEWER_ID.fullmatch(reviewer)):
            raise AcceptanceError("Invalid pseudonymous reviewer identifier")
        _review_timestamp(record["reviewed_at"], moment)
        name = record["evidence_file"]
        if isinstance(name, str) and name in seen_files:
            raise AcceptanceError("Each gate requires a distinct evidence file")
        _check_evidence(evidence_dir, name, record["evidence_sha256"])
        seen_files.add(name)

    return {
        "status": "blocked" if pending else "evidence_complete",
        "total_gates": len(GATES),
        "approved_records": len(GATES) - len(pending),
        "pending_gates": pending,
        "production_approval": False,
    }
