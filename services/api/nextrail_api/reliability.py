"""Constant-work operational database probe for non-sensitive API readiness.

This is a liveness/readiness probe, not a replacement for SQLite integrity,
backup freshness or security audits. No account data is read or exposed.
"""
import sqlite3


def database_connection_ready(connection: sqlite3.Connection) -> bool:
    """Return false on missing schema, closed connections or SQLite read errors."""
    try:
        version = connection.execute("PRAGMA user_version").fetchone()
        auth = connection.execute(
            "SELECT version FROM auth_meta WHERE id=1"
        ).fetchone()
        return bool(version and version[0] == 1 and auth and auth[0] == 1)
    except sqlite3.Error:
        return False
