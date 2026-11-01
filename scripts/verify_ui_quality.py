"""Fail-closed operator-review register for UI QA; never production authorization.

The checker only validates operator evidence format and file integrity. It
cannot run, observe, or certify browser tests. Sample intentionally blocks.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys

SCENARIOS = (
    "desktop_guest_discovery",
    "mobile_guest_pathway",
    "desktop_account_progress",
    "mobile_account_personalization",
    "keyboard_and_screen_reader",
    "theme_and_reduced_motion",
    "provider_evidence_and_synthetic_safety",
    "error_offline_and_retry",
)
REVIEW_FIELDS = frozenset({"status", "reviewer", "checked_at", "evidence_file", "evidence_sha256"})
FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 1_000_000
FRESHNESS = timedelta(days=30)


class UiQualityError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UiQualityError("Duplicate QA manifest property")
        result[key] = value
    return result


def read_manifest(path):
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise UiQualityError("QA manifest must be a regular file")
    try:
        with source.open("rb") as reader:
            raw = reader.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise UiQualityError("QA manifest is too large")
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique)
    except (OSError, UnicodeError, ValueError) as exc:
        raise UiQualityError("Invalid QA manifest") from exc


def _evidence_file(directory, name, digest):
    if not isinstance(name, str) or name in (".", "..") or not FILENAME.fullmatch(name):
        raise UiQualityError("QA evidence filename is invalid")
    if not isinstance(digest, str) or not SHA.fullmatch(digest):
        raise UiQualityError("QA evidence digest must be lowercase SHA-256")
    file = Path(directory) / name
    if file.is_symlink() or not file.is_file():
        raise UiQualityError("QA evidence must be a regular file")
    sha = hashlib.sha256()
    try:
        with file.open("rb") as reader:
            size = 0
            for chunk in iter(lambda: reader.read(65536), b""):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise UiQualityError("QA evidence is too large")
                sha.update(chunk)
    except OSError as exc:
        raise UiQualityError("QA evidence unavailable") from exc
    if not hmac.compare_digest(sha.hexdigest(), digest):
        raise UiQualityError("QA evidence digest mismatch")


def inspect_ui_qa(doc, evidence_dir, *, now=None):
    if not isinstance(doc, dict) or set(doc) != {"schema_version", "scenarios"}:
        raise UiQualityError("Invalid QA manifest structure")
    if doc["schema_version"] != "1.0.0":
        raise UiQualityError("Unsupported QA schema")
    records = doc["scenarios"]
    if not isinstance(records, dict) or set(records) != set(SCENARIOS):
        raise UiQualityError("QA scenarios must match the exact approved checklist")
    moment = datetime.now(timezone.utc) if now is None else now
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise UiQualityError("Timezone-aware verification clock required")
    moment = moment.astimezone(timezone.utc)
    accepted = []
    pending = []
    evidence_names = set()
    for key in SCENARIOS:
        record = records[key]
        if not isinstance(record, dict):
            raise UiQualityError("QA scenario must be a record")
        status = record.get("status")
        if status == "pending":
            if set(record) != {"status"}:
                raise UiQualityError("Pending QA scenarios cannot include approval fields")
            pending.append(key)
            continue
        if status != "approved" or set(record) != REVIEW_FIELDS:
            raise UiQualityError("QA approval requires exact evidence and reviewer fields")
        reviewer = record["reviewer"]
        if not isinstance(reviewer, str) or not 3 <= len(reviewer) <= 80:
            raise UiQualityError("QA reviewer identifier is invalid")
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", reviewer):
            raise UiQualityError("Reviewer must be a pseudonymous ID")
        checked = record["checked_at"]
        if not isinstance(checked, str):
            raise UiQualityError("QA review time must be a string")
        try:
            instant = datetime.fromisoformat(checked.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                raise ValueError("Timezone required")
            instant = instant.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise UiQualityError("QA timestamp is invalid") from None
        if instant > moment or moment - instant > FRESHNESS:
            raise UiQualityError("QA review is stale or future-dated")
        filename = record["evidence_file"]
        if filename in evidence_names:
            raise UiQualityError("QA evidence must be separate for each scenario")
        _evidence_file(evidence_dir, filename, record["evidence_sha256"])
        evidence_names.add(filename)
        accepted.append(key)
    return {
        "status": "blocked" if pending else "evidence_complete",
        "approved_checks": len(accepted),
        "pending_checks": len(pending),
        "pending_scenarios": pending,
        "browser_testing_performed_by_tool": False,
        "production_approval": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate offline UI quality review register")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--evidence-dir", default="docs/ui-qa-evidence")
    parser.add_argument("--expect-blocked", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = inspect_ui_qa(read_manifest(args.manifest), args.evidence_dir)
    except (UiQualityError, OSError, ValueError):
        print("FAIL: Invalid or unsupported UI QA evidence", file=sys.stderr)
        return 1
    print(json.dumps(output, sort_keys=True))
    if args.expect_blocked:
        return 0 if output["status"] == "blocked" else 1
    return 0 if output["status"] == "evidence_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
