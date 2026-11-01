"""Disposable, offline SQLite restore rehearsal for an operator-pinned backup.

Never replaces the active database or original backup, never logs learner rows
or their fingerprints, and never asserts encryption or production durability.
"""
from contextlib import closing
import hashlib
import hmac
from pathlib import Path
import sqlite3
import tempfile

from .readiness import DatabaseReadinessError, verify_database_readiness
from .recovery import DatabaseRecoveryError, inspect_database, snapshot_database


def _fingerprint_database(path: Path):
    """Compare complete restored logical contents without returning private data.

    This is an ephemeral consistency digest, not a credential or audit artifact.
    Tables in the supported Nextrail schema are ordinary rowid SQLite tables.
    """
    digest = hashlib.sha256()
    table_count = 0
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5.0)) as connection:
            connection.execute("PRAGMA query_only=ON")
            definitions = connection.execute(
                "SELECT type,name,sql FROM sqlite_master "
                "WHERE sql IS NOT NULL ORDER BY type,name"
            ).fetchall()
            for item in definitions:
                value = repr(tuple(item)).encode("utf-8")
                digest.update(len(value).to_bytes(8, "big"))
                digest.update(value)
            names = [
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ) if row[0] == "sqlite_sequence" or not row[0].startswith("sqlite_")
            ]
            for table in names:
                table_count += 1
                identifier = '"' + table.replace('"', '""') + '"'
                digest.update(repr(table).encode("utf-8"))
                for row in connection.execute(f"SELECT * FROM {identifier} ORDER BY rowid"):
                    value = repr(tuple(row)).encode("utf-8")
                    digest.update(len(value).to_bytes(8, "big"))
                    digest.update(value)
    except (sqlite3.Error, OSError, OverflowError) as exc:
        raise DatabaseReadinessError("Unable to compare restored SQLite contents") from exc
    return digest.digest(), table_count


def rehearse_database_restore(
    database, backup, expected_backup_sha256, *, max_backup_age_hours=24, now=None,
):
    """Verify active/backup readiness, then restore independently and compare.

    The backup is pinned and checked for freshness before use. Its contents
    are rehearsed in an automatically removed temporary directory, not beside
    the active database. No private row contents are returned or logged.
    """
    report = verify_database_readiness(
        database, backup, expected_backup_sha256,
        max_backup_age_hours=max_backup_age_hours, now=now,
    )
    source = Path(backup).resolve(strict=True)
    try:
        original_fingerprint, original_tables = _fingerprint_database(source)
        with tempfile.TemporaryDirectory(prefix="nextrail-rehearsal-") as folder:
            restored = Path(folder) / "restored.sqlite"
            snapshot_database(source, restored)
            restored_report = inspect_database(restored)
            restored_fingerprint, restored_tables = _fingerprint_database(restored)
            if (restored_report != report["schema_versions"]
                    or restored_tables != original_tables
                    or not hmac.compare_digest(original_fingerprint, restored_fingerprint)):
                raise DatabaseReadinessError("Restored database does not match pinned backup")
    except (DatabaseRecoveryError, OSError, sqlite3.Error) as exc:
        if isinstance(exc, DatabaseReadinessError):
            raise
        raise DatabaseReadinessError("Disposable SQLite restore rehearsal failed") from exc
    # Detect changes to the backup file during the rehearsal. A checksum pin
    # is integrity evidence, not proof of independent backup authenticity.
    digest = hashlib.sha256()
    try:
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DatabaseReadinessError("Unable to recheck pinned backup") from exc
    if not hmac.compare_digest(digest.hexdigest(), expected_backup_sha256):
        raise DatabaseReadinessError("Pinned backup changed during restore rehearsal")
    return {
        "status": "pass",
        "restore_rehearsal": "verified",
        "temporary_copy_removed": True,
        "database_mode": report["database_mode"],
        "backup_hash": report["backup_hash"],
        "schema_versions": report["schema_versions"],
        "logical_tables_compared": original_tables,
        "production_approval": False,
    }
