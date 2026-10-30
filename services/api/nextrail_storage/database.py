"""Minimal SQLite migrations and transaction boundary for learning persistence."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3

SCHEMA_VERSION = 1

SCHEMA = (
    """CREATE TABLE learning_pathways (
        id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        pathway_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(id, owner_id)
    )""",
    "CREATE INDEX idx_pathways_owner ON learning_pathways(owner_id, created_at, id)",
    """CREATE TABLE milestone_progress (
        owner_id TEXT NOT NULL,
        pathway_id TEXT NOT NULL,
        skill_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('not_started', 'in_progress', 'completed')),
        updated_at TEXT NOT NULL,
        PRIMARY KEY(owner_id, pathway_id, skill_id),
        FOREIGN KEY(pathway_id, owner_id)
            REFERENCES learning_pathways(id, owner_id) ON DELETE RESTRICT
    )""",
    """CREATE TABLE saved_courses (
        owner_id TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(owner_id, resource_id)
    )""",
    """CREATE TABLE audit_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        detail_json TEXT NOT NULL,
        recorded_at TEXT NOT NULL
    )""",
    "CREATE INDEX idx_events_owner ON audit_events(owner_id, event_id)",
    """CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events
        BEGIN SELECT RAISE(ABORT, 'audit records are append-only'); END""",
    """CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events
        BEGIN SELECT RAISE(ABORT, 'audit records are append-only'); END""",
)


class StorageError(ValueError):
    """Invalid persistent data or an unsupported database schema."""


def open_database(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a standalone SQLite connection; no databases are auto-created in the repo."""
    if not isinstance(path, (str, Path)) or not str(path):
        raise StorageError("A database location is required")
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=5.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        if str(path) != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        migrate(conn)
        return conn
    except BaseException:
        conn.close()
        raise


def migrate(conn: sqlite3.Connection) -> None:
    """Create version 1 atomically; never overwrite an unknown preexisting DB."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        required = {"learning_pathways", "milestone_progress", "saved_courses", "audit_events"}
        present = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not required.issubset(present):
            raise StorageError("Existing storage schema is incomplete")
        return
    if version != 0:
        raise StorageError("Unsupported database schema version")
    present = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if present:
        raise StorageError("Refusing to modify an unversioned existing database")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


@contextmanager
def atomic(conn: sqlite3.Connection):
    """Make the state transition and append-only audit insert all-or-nothing."""
    if conn.in_transaction:
        raise StorageError("Nested transactions are not supported")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
