"""Non-destructive integrity checks and consistent SQLite backups.

No automatic restore, destructive overwrite, network transfer, or secret logging.
"""
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from .database import SCHEMA_VERSION, StorageError

_REQUIRED_TABLES = frozenset({
    "learning_pathways", "milestone_progress", "saved_courses", "audit_events",
    "auth_meta", "accounts", "auth_sessions", "password_reset_tokens",
    "login_attempts", "account_preferences_meta", "account_preferences",
})


class DatabaseRecoveryError(StorageError):
    """Database was not safe to inspect, snapshot, or restore."""


def _source_file(path: str | Path) -> Path:
    if not isinstance(path, (str, Path)) or not str(path) or str(path) == ":memory:":
        raise DatabaseRecoveryError("An existing SQLite file is required")
    location = Path(path)
    if location.is_symlink() or not location.is_file():
        raise DatabaseRecoveryError("Source database must be an existing regular file")
    return location.resolve(strict=True)


def _read_only(location: Path) -> sqlite3.Connection:
    # mode=ro prevents accidentally creating a missing source database.
    connection = sqlite3.connect(location.as_uri() + "?mode=ro", uri=True, timeout=5.0)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _inspect_connection(connection: sqlite3.Connection) -> dict[str, int]:
    try:
        results = connection.execute("PRAGMA integrity_check").fetchall()
        if results != [("ok",)]:
            raise DatabaseRecoveryError("Database integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise DatabaseRecoveryError("Database foreign-key check failed")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise DatabaseRecoveryError("Unsupported learning database schema version")
        names = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not _REQUIRED_TABLES.issubset(names):
            raise DatabaseRecoveryError("Database is missing required application tables")
        versions = {}
        for name in ("auth_meta", "account_preferences_meta"):
            entries = connection.execute(f"SELECT id,version FROM {name}").fetchall()
            if len(entries) != 1 or tuple(entries[0]) != (1, 1):
                raise DatabaseRecoveryError("Unsupported account schema version")
            versions[name] = 1
        return {
            "storage_schema": version,
            "auth_schema": versions["auth_meta"],
            "preferences_schema": versions["account_preferences_meta"],
        }
    except sqlite3.DatabaseError as exc:
        raise DatabaseRecoveryError("Unable to validate SQLite database") from exc


def inspect_database(path: str | Path) -> dict[str, int]:
    """Validate a read-only local database without exposing learner records."""
    location = _source_file(path)
    try:
        with closing(_read_only(location)) as connection:
            return _inspect_connection(connection)
    except sqlite3.DatabaseError as exc:
        raise DatabaseRecoveryError("Unable to open SQLite database read-only") from exc


def _windows_platform() -> bool:
    """Use an atomic rename on Windows instead of hard-link publication."""
    return sys.platform == "win32"


def _publish_exclusively(staged: Path, destination: Path) -> None:
    """Publish in the same directory without ever replacing an existing file.

    Windows os.rename refuses to replace an existing destination. POSIX rename
    would overwrite, so POSIX uses atomic exclusive hard-link creation instead.
    """
    if _windows_platform():
        os.rename(staged, destination)
    else:
        os.link(staged, destination)


def _snapshot_error(stage: str, cause: BaseException) -> DatabaseRecoveryError:
    """Expose a safe operation and error code, not private filesystem paths."""
    code = getattr(cause, "winerror", None)
    if code is None:
        code = getattr(cause, "errno", None)
    if code is None:
        code = getattr(cause, "sqlite_errorcode", None)
    hint = f" (error code {code})" if isinstance(code, int) else ""
    return DatabaseRecoveryError(
        f"Database snapshot failed while {stage}{hint}; "
        "original database was not changed and no existing backup was replaced"
    )


def snapshot_database(source: str | Path, destination: str | Path) -> dict[str, int]:
    """Capture a consistent SQLite snapshot into a new file, never overwriting.

    Safe to use while SQLite is in WAL mode. A restore is an identical copy into
    a *different, nonexistent* destination; replacing a running DB is prohibited.
    """
    source_path = _source_file(source)
    if not isinstance(destination, (str, Path)) or not str(destination):
        raise DatabaseRecoveryError("Destination database path is required")
    dest = Path(destination)
    if dest.is_symlink() or dest.exists() or not dest.parent.is_dir():
        raise DatabaseRecoveryError("Destination must not exist and its parent must exist")
    if dest.resolve() == source_path:
        raise DatabaseRecoveryError("Source and destination must differ")
    # Inspect first to reject unknown or broken databases without touching them.
    inspect_database(source_path)
    temporary_path = None
    stage = "creating a temporary snapshot"
    try:
        handle, name = tempfile.mkstemp(
            prefix=".nextrail-snapshot-", suffix=".tmp", dir=str(dest.parent)
        )
        os.close(handle)
        temporary_path = Path(name)

        stage = "copying committed SQLite data"
        with closing(_read_only(source_path)) as current:
            with closing(sqlite3.connect(str(temporary_path), timeout=5.0)) as snapshot:
                current.backup(snapshot)

        stage = "validating the temporary snapshot"
        report = inspect_database(temporary_path)

        # Windows CRT fsync may reject a read-only descriptor. Flush using a
        # writable descriptor after the SQLite connection has been closed.
        stage = "flushing snapshot data"
        with open(temporary_path, "r+b") as temporary_file:
            os.fsync(temporary_file.fileno())

        # Exclusive, same-directory publication; never overwrite a prior file.
        stage = "publishing the completed snapshot"
        _publish_exclusively(temporary_path, dest)
        return report
    except (sqlite3.DatabaseError, OSError) as exc:
        raise _snapshot_error(stage, exc) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
