"""Account-scoped learning progress and append-only audit storage."""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from .database import StorageError, atomic
from . import idempotency

OWNER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
SLUG = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
STATES = ("not_started", "in_progress", "completed")


class ProgressConflict(StorageError):
    """A milestone changed since the client fetched progress."""



def owner_id(value):
    if not isinstance(value, str) or not OWNER.fullmatch(value):
        raise StorageError("Invalid authenticated owner reference")
    return value


def slug(value):
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise StorageError("Invalid resource or skill reference")
    return value


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def serialize_pathway(pathway):
    fields = {"schema_version", "career_goal", "weekly_hours", "generation_mode", "milestones"}
    if not isinstance(pathway, dict) or set(pathway) != fields:
        raise StorageError("Invalid pathway fields")
    goal = pathway["career_goal"]
    if pathway["schema_version"] != "1.0.0" or not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 120:
        raise StorageError("Invalid pathway version or goal")
    if type(pathway["weekly_hours"]) is not int or not 1 <= pathway["weekly_hours"] <= 80:
        raise StorageError("Invalid weekly hours")
    if pathway["generation_mode"] not in ("deterministic", "ai_assisted"):
        raise StorageError("Invalid generation mode")
    steps = pathway["milestones"]
    if not isinstance(steps, list) or len(steps) > 1000:
        raise StorageError("Invalid milestones")
    seen = set()
    for index, row in enumerate(steps, 1):
        if not isinstance(row, dict) or set(row) != {"order", "skill_id", "resource_ids", "rationale"}:
            raise StorageError("Invalid milestone fields")
        skill = slug(row["skill_id"])
        if type(row["order"]) is not int or row["order"] != index or skill in seen:
            raise StorageError("Duplicate or unordered milestone")
        seen.add(skill)
        ids = row["resource_ids"]
        if not isinstance(ids, list) or len(ids) > 100:
            raise StorageError("Invalid course references")
        for rid in ids:
            slug(rid)
        if len(ids) != len(set(ids)):
            raise StorageError("Duplicate course references")
        if not isinstance(row["rationale"], str) or not 1 <= len(row["rationale"].strip()) <= 1000:
            raise StorageError("Invalid rationale")
    encoded = json.dumps(pathway, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 262144:
        raise StorageError("Pathway too large")
    return encoded


class LearningStore:
    """Storage facade. The caller must derive owner_id from verified authentication."""

    def __init__(self, conn: sqlite3.Connection):
        if not isinstance(conn, sqlite3.Connection) or not conn.execute("PRAGMA foreign_keys").fetchone()[0]:
            raise StorageError("Initialized SQLite connection with foreign keys required")
        self.conn = conn
        idempotency.initialize(self.conn)

    def idempotent_pathway(self, owner, key, request_digest):
        owner = owner_id(owner)
        found = idempotency.lookup(self.conn, owner, key, request_digest)
        return {"id": found, "pathway": self.get_pathway(owner, found)} if found else None

    def _audit(self, owner, kind, identifier, action, detail):
        self.conn.execute(
            """INSERT INTO audit_events(owner_id,entity_type,entity_id,operation,detail_json,recorded_at)
            VALUES(?,?,?,?,?,?)""",
            (owner, kind, identifier, action, json.dumps(detail, sort_keys=True), timestamp()),
        )

    def save_pathway(self, owner, pathway, *, idempotency_key=None, request_digest=None):
        owner = owner_id(owner)
        snapshot = serialize_pathway(pathway)
        if (idempotency_key is None) != (request_digest is None):
            raise StorageError("Idempotency key and request digest must be supplied together")
        if idempotency_key is not None:
            idempotency.key_digest(owner, idempotency_key, request_digest)
        identifier = str(uuid4())
        with atomic(self.conn):
            if idempotency_key is not None:
                existing = idempotency.lookup(self.conn, owner, idempotency_key, request_digest)
                if existing:
                    return existing
            self.conn.execute(
                "INSERT INTO learning_pathways(id,owner_id,pathway_json,created_at) VALUES(?,?,?,?)",
                (identifier, owner, snapshot, timestamp()),
            )
            if idempotency_key is not None:
                idempotency.record(self.conn, owner, idempotency_key, request_digest, identifier, timestamp())
            self._audit(owner, "pathway", identifier, "created", {"milestone_count": len(pathway["milestones"])})
        return identifier

    def get_pathway(self, owner, identifier):
        row = self.conn.execute(
            "SELECT pathway_json FROM learning_pathways WHERE owner_id=? AND id=?",
            (owner_id(owner), identifier),
        ).fetchone()
        if row is None:
            raise KeyError("Pathway not found")
        return json.loads(row["pathway_json"])

    def list_pathways(self, owner, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise StorageError("Invalid limit")
        rows = self.conn.execute(
            """SELECT id,pathway_json,created_at FROM learning_pathways
            WHERE owner_id=? ORDER BY created_at DESC,id DESC LIMIT ?""",
            (owner_id(owner), limit),
        )
        return [{"id": row["id"], "pathway": json.loads(row["pathway_json"]),
                 "created_at": row["created_at"]} for row in rows]

    def list_pathway_page(self, owner, *, limit=20, after_id=None):
        """Owner-scoped, stable keyset page with self-reported completion counts."""
        owner = owner_id(owner)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise StorageError("Invalid pathway page limit")
        if after_id is not None and (
            not isinstance(after_id, str) or not 1 <= len(after_id) <= 64
        ):
            raise StorageError("Invalid pathway cursor")
        args = [owner]
        predicate = "owner_id=?"
        if after_id is not None:
            cursor = self.conn.execute(
                "SELECT created_at,id FROM learning_pathways WHERE owner_id=? AND id=?",
                (owner, after_id),
            ).fetchone()
            if cursor is None:
                raise KeyError("Pathway page cursor not found")
            predicate += " AND (created_at<? OR (created_at=? AND id<?))"
            args.extend((cursor["created_at"], cursor["created_at"], cursor["id"]))
        args.append(limit + 1)
        rows = self.conn.execute(
            f"""SELECT id,pathway_json,created_at FROM learning_pathways
            WHERE {predicate} ORDER BY created_at DESC,id DESC LIMIT ?""",
            args,
        ).fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        items = []
        for row in page:
            snapshot = json.loads(row["pathway_json"])
            progress = self.get_progress(owner, row["id"])
            done = progress["completed"]
            total = progress["total"]
            items.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "career_goal": snapshot["career_goal"],
                "generation_mode": snapshot["generation_mode"],
                "completed": done,
                "total": total,
                "completion_percent": (100 * done // total) if total else 0,
            })
        total_pathways = self.conn.execute(
            "SELECT count(*) FROM learning_pathways WHERE owner_id=?", (owner,)
        ).fetchone()[0]
        saved_courses = self.conn.execute(
            "SELECT count(*) FROM saved_courses WHERE owner_id=?", (owner,)
        ).fetchone()[0]
        return {
            "items": items,
            "next_cursor": page[-1]["id"] if has_more and page else None,
            "saved_pathway_count": total_pathways,
            "saved_course_count": saved_courses,
        }

    def delete_pathway(self, owner, identifier):
        """Delete an owned saved route and progress, with an atomic audit entry."""
        owner = owner_id(owner)
        with atomic(self.conn):
            pathway = self.get_pathway(owner, identifier)
            self.conn.execute(
                "DELETE FROM milestone_progress WHERE owner_id=? AND pathway_id=?",
                (owner, identifier),
            )
            deleted = self.conn.execute(
                "DELETE FROM learning_pathways WHERE owner_id=? AND id=?",
                (owner, identifier),
            ).rowcount
            if deleted != 1:
                raise StorageError("Pathway deletion failed")
            self._audit(
                owner, "pathway", identifier, "deleted",
                {"milestone_count": len(pathway["milestones"])},
            )
        return True

    def progress_revision(self, owner, identifier):
        owner = owner_id(owner)
        row = self.conn.execute(
            "SELECT COALESCE(MAX(event_id),0) AS revision FROM audit_events "
            "WHERE owner_id=? AND entity_type='milestone' "
            "AND entity_id=? AND operation='status_changed'",
            (owner, identifier),
        ).fetchone()
        # Do not reveal the global audit sequence to account clients.
        identity = f"{owner}:{identifier}:{row['revision']}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def set_progress(self, owner, identifier, skill, status, *, expected_revision=None):
        owner, skill = owner_id(owner), slug(skill)
        if not isinstance(status, str) or status not in STATES:
            raise StorageError("Invalid progress status")
        with atomic(self.conn):
            pathway = self.get_pathway(owner, identifier)
            # Compare and write under BEGIN IMMEDIATE to prevent stale tab writes.
            if expected_revision is not None and expected_revision != self.progress_revision(owner, identifier):
                raise ProgressConflict("Progress changed since the last read")
            if skill not in {m["skill_id"] for m in pathway["milestones"]}:
                raise StorageError("Skill not in saved pathway")
            previous = self.conn.execute(
                """SELECT status FROM milestone_progress
                WHERE owner_id=? AND pathway_id=? AND skill_id=?""",
                (owner, identifier, skill),
            ).fetchone()
            before = previous["status"] if previous else "not_started"
            if before == status:
                return False
            self.conn.execute(
                """INSERT INTO milestone_progress(owner_id,pathway_id,skill_id,status,updated_at)
                VALUES(?,?,?,?,?) ON CONFLICT(owner_id,pathway_id,skill_id)
                DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at""",
                (owner, identifier, skill, status, timestamp()),
            )
            self._audit(owner, "milestone", identifier, "status_changed",
                        {"skill_id": skill, "from": before, "to": status})
        return True

    def get_progress(self, owner, identifier):
        pathway = self.get_pathway(owner, identifier)
        statuses = {r["skill_id"]: r["status"] for r in self.conn.execute(
            "SELECT skill_id,status FROM milestone_progress WHERE owner_id=? AND pathway_id=?",
            (owner_id(owner), identifier),
        )}
        steps = [{"skill_id": m["skill_id"], "status": statuses.get(m["skill_id"], "not_started")}
                 for m in pathway["milestones"]]
        return {"pathway_id": identifier, "milestones": steps,
                "completed": sum(s["status"] == "completed" for s in steps),
                "total": len(steps), "revision": self.progress_revision(owner, identifier)}

    def save_course(self, owner, resource):
        owner, resource = owner_id(owner), slug(resource)
        with atomic(self.conn):
            changed = self.conn.execute(
                "INSERT OR IGNORE INTO saved_courses(owner_id,resource_id,created_at) VALUES(?,?,?)",
                (owner, resource, timestamp()),
            ).rowcount
            if changed:
                self._audit(owner, "course", resource, "saved", {})
            return bool(changed)

    def unsave_course(self, owner, resource):
        owner, resource = owner_id(owner), slug(resource)
        with atomic(self.conn):
            changed = self.conn.execute(
                "DELETE FROM saved_courses WHERE owner_id=? AND resource_id=?", (owner, resource)
            ).rowcount
            if changed:
                self._audit(owner, "course", resource, "unsaved", {})
            return bool(changed)

    def list_saved_courses(self, owner):
        return [row[0] for row in self.conn.execute(
            "SELECT resource_id FROM saved_courses WHERE owner_id=? ORDER BY resource_id",
            (owner_id(owner),),
        )]

    def audit_history(self, owner, *, after_event_id=0, limit=100):
        if (type(after_event_id) is not int or after_event_id < 0 or
                type(limit) is not int or not 1 <= limit <= 100):
            raise StorageError("Invalid audit cursor")
        return [{
            "event_id": row["event_id"], "entity_type": row["entity_type"],
            "entity_id": row["entity_id"], "operation": row["operation"],
            "detail": json.loads(row["detail_json"]), "recorded_at": row["recorded_at"]
        } for row in self.conn.execute(
            """SELECT event_id,entity_type,entity_id,operation,detail_json,recorded_at
            FROM audit_events WHERE owner_id=? AND event_id>?
            ORDER BY event_id LIMIT ?""", (owner_id(owner), after_event_id, limit)
        )]
