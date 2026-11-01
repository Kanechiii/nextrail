"""Offline deployment-readiness evidence for a single-host SQLite installation.

This is a read-only preflight, not a production deployment or provider approval.
It cannot establish operating-system ACLs, encryption, or hosted durability.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import sqlite3
from pathlib import Path

from .recovery import DatabaseRecoveryError, inspect_database

_OPTIONAL_LIMIT_TABLES = frozenset({"api_rate_limits", "api_rate_limits_meta"})
_EXPECTED_AUDIT_ACTIONS = ("UPDATE", "DELETE")


class DatabaseReadinessError(DatabaseRecoveryError):
    """SQLite deployment preflight evidence is missing or unacceptable."""


def _existing_file(path):
    if not isinstance(path, (str, Path)) or not str(path) or str(path) == ":memory:":
        raise DatabaseReadinessError("An existing SQLite file is required")
    location = Path(path)
    if location.is_symlink() or not location.is_file():
        raise DatabaseReadinessError("Database must be an existing regular non-symlink file")
    return location.resolve(strict=True)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _structure(path, *, active):
    """Read SQLite operational configuration and security schema, without writes."""
    try:
        with closing(sqlite3.connect(
            path.as_uri() + "?mode=ro", uri=True, timeout=5.0
        )) as conn:
            conn.execute("PRAGMA query_only=ON")
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
            if active and mode != "wal":
                raise DatabaseReadinessError("Active database must use SQLite WAL mode")
            rows = conn.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
            triggers = {name: sql for name, sql in rows}
            for action in _EXPECTED_AUDIT_ACTIONS:
                name = "audit_events_no_" + action.lower()
                sql = triggers.get(name)
                if not isinstance(sql, str):
                    raise DatabaseReadinessError("Required append-only audit guard missing")
                normalized = " ".join(sql.lower().split())
                if (f"before {action.lower()} on audit_events" not in normalized
                        or "raise(abort, 'audit records are append-only')" not in normalized):
                    raise DatabaseReadinessError("Unexpected append-only audit guard definition")
            names = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            optional = names.intersection(_OPTIONAL_LIMIT_TABLES)
            if optional and optional != _OPTIONAL_LIMIT_TABLES:
                raise DatabaseReadinessError("Incomplete shared request protection schema")
            if optional:
                key_rows = conn.execute(
                    "SELECT id,key_check FROM api_rate_limits_meta"
                ).fetchall()
                if (len(key_rows) != 1 or key_rows[0][0] != 1
                        or not isinstance(key_rows[0][1], str)
                        or not re.fullmatch(r"[0-9a-f]{64}", key_rows[0][1])):
                    raise DatabaseReadinessError("Invalid shared request protection metadata")
            return frozenset(optional)
    except sqlite3.DatabaseError as exc:
        raise DatabaseReadinessError("Unable to inspect SQLite deployment structure") from exc


def _verified_integrity(path, label):
    """Normalize existing recovery errors into the readiness preflight contract."""
    try:
        return inspect_database(path)
    except DatabaseRecoveryError as exc:
        raise DatabaseReadinessError(f"{label} failed SQLite integrity validation") from exc


def verify_database_readiness(
    database, backup, expected_backup_sha256, *,
    max_backup_age_hours=24, now=None,
):
    """Require integrity-checked active storage and a pinned, recent backup.

    A backup checksum is an operator-supplied integrity pin, not proof that a
    backup was independently generated or encryption/retention is configured.
    """
    if (not isinstance(expected_backup_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_backup_sha256)):
        raise DatabaseReadinessError("Expected backup SHA-256 must be lowercase hex")
    if (not isinstance(max_backup_age_hours, int)
            or isinstance(max_backup_age_hours, bool)
            or not 1 <= max_backup_age_hours <= 720):
        raise DatabaseReadinessError("Backup age policy must be 1-720 hours")
    clock = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(clock, datetime) or clock.tzinfo is None
            or clock.utcoffset() is None):
        raise DatabaseReadinessError("Verification clock must be timezone-aware")
    clock = clock.astimezone(timezone.utc)

    source_path = _existing_file(database)
    backup_path = _existing_file(backup)
    if source_path == backup_path:
        raise DatabaseReadinessError("Backup must be a separate SQLite file")
    source_report = _verified_integrity(source_path, "Active database")
    source_optional = _structure(source_path, active=True)

    modified = datetime.fromtimestamp(backup_path.stat().st_mtime, tz=timezone.utc)
    if (modified > clock + timedelta(minutes=5)
            or clock - modified > timedelta(hours=max_backup_age_hours)):
        raise DatabaseReadinessError("Backup file timestamp violates freshness policy")
    if not hmac.compare_digest(_sha256(backup_path), expected_backup_sha256):
        raise DatabaseReadinessError("Backup SHA-256 does not match the approved pin")
    backup_report = _verified_integrity(backup_path, "Backup")
    backup_optional = _structure(backup_path, active=False)
    if backup_report != source_report or source_optional != backup_optional:
        raise DatabaseReadinessError("Backup does not match required application schema")

    return {
        "status": "pass",
        "database_mode": "wal",
        "backup_integrity": "verified",
        "backup_hash": "matched",
        "backup_age_policy_hours": max_backup_age_hours,
        "schema_versions": source_report,
        "shared_rate_limit_schema": "present" if source_optional else "absent",
    }
