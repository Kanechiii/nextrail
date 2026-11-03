"""Bounded read-only account sync readiness over one authoritative SQLite store.

This is NOT an external sync transport or a hosted deployment. Any clients
seeing the same revision must already use the same explicitly configured
backend and database.
"""
import hashlib
import sqlite3

from .store import owner_id


def account_sync_status(conn: sqlite3.Connection, owner):
    """Return only owner-scoped counts and an opaque change revision."""
    owner = owner_id(owner)
    if not isinstance(conn, sqlite3.Connection):
        raise ValueError("Initialized SQLite connection required")
    latest = conn.execute(
        "SELECT COALESCE(MAX(event_id),0) FROM audit_events WHERE owner_id=?",
        (owner,),
    ).fetchone()[0]
    pathways = conn.execute(
        "SELECT COUNT(*) FROM learning_pathways WHERE owner_id=?", (owner,),
    ).fetchone()[0]
    bookmarks = conn.execute(
        "SELECT COUNT(*) FROM saved_courses WHERE owner_id=?", (owner,),
    ).fetchone()[0]
    revision = hashlib.sha256(
        f"{owner}:account-state:{latest}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "1.0.0",
        "persistence": "local_sqlite",
        "shared_backend_required": True,
        "hosted_cross_device_sync_configured": False,
        "state_revision": revision,
        "saved_pathway_count": pathways,
        "saved_course_count": bookmarks,
        "completion_source": "self_reported",
        "automatic_merge_enabled": False,
        "remote_requests_performed": 0,
    }
