"""Account-scoped, durable request replay for pathway creation.

The sidecar deliberately leaves the existing learning schema version unchanged.
Keys are UUIDv4 and stored only as owner-bound digests, never raw headers.
"""
import hashlib
import re
from uuid import UUID

from nextrail_storage.database import StorageError

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = """CREATE TABLE IF NOT EXISTS pathway_idempotency (
    owner_id TEXT NOT NULL,
    key_digest TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    pathway_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(owner_id, key_digest),
    FOREIGN KEY(pathway_id, owner_id)
        REFERENCES learning_pathways(id, owner_id) ON DELETE CASCADE
)"""


class IdempotencyConflict(StorageError):
    """Same account reused a key for different planning inputs."""


def key_digest(owner, key, request_digest):
    if not isinstance(key, str) or not isinstance(request_digest, str):
        raise StorageError("Idempotency key and request digest are required")
    try:
        parsed = UUID(key)
    except (ValueError, AttributeError) as exc:
        raise StorageError("Idempotency key must be UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != key or not SHA256.fullmatch(request_digest):
        raise StorageError("Invalid idempotency key or request digest")
    return hashlib.sha256((owner + ":" + key).encode("utf-8")).hexdigest()


def initialize(conn):
    conn.execute(SCHEMA)


def lookup(conn, owner, key, request_digest):
    digest = key_digest(owner, key, request_digest)
    row = conn.execute(
        "SELECT pathway_id,request_digest FROM pathway_idempotency "
        "WHERE owner_id=? AND key_digest=?", (owner, digest),
    ).fetchone()
    if row is not None and row["request_digest"] != request_digest:
        raise IdempotencyConflict("Idempotency key already used for different planning inputs")
    return row["pathway_id"] if row else None


def record(conn, owner, key, request_digest, pathway_id, timestamp):
    digest = key_digest(owner, key, request_digest)
    conn.execute(
        "INSERT INTO pathway_idempotency(owner_id,key_digest,request_digest,pathway_id,created_at) "
        "VALUES(?,?,?,?,?)", (owner, digest, request_digest, pathway_id, timestamp),
    )
