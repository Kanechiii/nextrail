"""Optional account onboarding and learning preferences, never guest-required."""
import json
import sqlite3
from datetime import datetime, timezone

from nextrail_storage.database import atomic
from nextrail_storage.store import owner_id

from .accounts import AuthError

SCHEMA_VERSION = 1
DEFAULTS = {
    "display_name": "",
    "career_goal": "",
    "weekly_hours": 5,
    "target_skill_ids": [],
    "known_skill_ids": [],
}
FIELDS = frozenset(DEFAULTS)
CREATE_META = """CREATE TABLE account_preferences_meta (
    id INTEGER PRIMARY KEY CHECK(id=1),
    version INTEGER NOT NULL
)"""
CREATE_PREFERENCES = """CREATE TABLE account_preferences (
    owner_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    career_goal TEXT NOT NULL,
    weekly_hours INTEGER NOT NULL CHECK(weekly_hours BETWEEN 1 AND 80),
    target_skill_ids TEXT NOT NULL,
    known_skill_ids TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE
)"""


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialize_preferences_schema(conn: sqlite3.Connection):
    """Add versioned sidecar tables without changing existing auth/storage versions."""
    if not conn.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise AuthError("SQLite foreign keys are required")
    existing = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "accounts" not in existing or "auth_meta" not in existing:
        raise AuthError("Initialize account authentication before preferences")
    present = {"account_preferences_meta", "account_preferences"} & existing
    if present and len(present) != 2:
        raise AuthError("Incomplete account-preferences schema")
    if not present:
        with atomic(conn):
            conn.execute(CREATE_META)
            conn.execute(CREATE_PREFERENCES)
            conn.execute(
                "INSERT INTO account_preferences_meta(id, version) VALUES(1, ?)",
                (SCHEMA_VERSION,),
            )
    version = conn.execute(
        "SELECT version FROM account_preferences_meta WHERE id=1"
    ).fetchone()
    rows = conn.execute("SELECT count(*) FROM account_preferences_meta").fetchone()[0]
    if not version or version[0] != SCHEMA_VERSION or rows != 1:
        raise AuthError("Unsupported account-preferences schema version")


def _check_text(value, name, limit):
    if not isinstance(value, str) or len(value) > limit:
        raise AuthError("Invalid " + name)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise AuthError("Invalid " + name)
    return value.strip()


def _check_skills(values, allowed, limit):
    if not isinstance(values, list) or len(values) > limit:
        raise AuthError("Invalid skill selections")
    if any(not isinstance(item, str) or item not in allowed for item in values):
        raise AuthError("Unknown skill selection")
    if len(set(values)) != len(values):
        raise AuthError("Duplicate skill selection")
    return list(values)


class AccountPreferencesStore:
    """Persistent learning preferences keyed solely by verified account owner."""

    def __init__(self, conn: sqlite3.Connection):
        if not isinstance(conn, sqlite3.Connection):
            raise AuthError("SQLite connection required")
        self.conn = conn
        initialize_preferences_schema(conn)

    def get(self, owner):
        owner = owner_id(owner)
        account = self.conn.execute(
            "SELECT id FROM accounts WHERE id=?", (owner,)
        ).fetchone()
        if not account:
            raise AuthError("Account not found")
        row = self.conn.execute(
            """SELECT display_name, career_goal, weekly_hours,
               target_skill_ids, known_skill_ids, updated_at
               FROM account_preferences WHERE owner_id=?""",
            (owner,),
        ).fetchone()
        if row is None:
            return {
                **DEFAULTS,
                "onboarding_completed": False,
                "updated_at": None,
            }
        result = {
            "display_name": row["display_name"],
            "career_goal": row["career_goal"],
            "weekly_hours": row["weekly_hours"],
            "target_skill_ids": json.loads(row["target_skill_ids"]),
            "known_skill_ids": json.loads(row["known_skill_ids"]),
            "updated_at": row["updated_at"],
        }
        result["onboarding_completed"] = bool(
            result["career_goal"] and result["target_skill_ids"]
        )
        return result

    def update(self, owner, changes, *, allowed_skill_ids):
        owner = owner_id(owner)
        if not isinstance(changes, dict) or not changes or not set(changes).issubset(FIELDS):
            raise AuthError("Unsupported preference fields")
        allowed = set(allowed_skill_ids)
        validated = {}
        for key, value in changes.items():
            if key == "display_name":
                validated[key] = _check_text(value, key, 80)
            elif key == "career_goal":
                validated[key] = _check_text(value, key, 120)
            elif key == "weekly_hours":
                if type(value) is not int or not 1 <= value <= 80:
                    raise AuthError("Invalid weekly learning hours")
                validated[key] = value
            elif key == "target_skill_ids":
                validated[key] = _check_skills(value, allowed, 32)
            elif key == "known_skill_ids":
                validated[key] = _check_skills(value, allowed, 128)
        current = self.get(owner)
        proposed = {key: current[key] for key in FIELDS}
        proposed.update(validated)
        changed = sorted(key for key in validated if current[key] != proposed[key])
        if not changed:
            return current
        timestamp = _timestamp()
        with atomic(self.conn):
            self.conn.execute(
                """INSERT INTO account_preferences(
                    owner_id,display_name,career_goal,weekly_hours,target_skill_ids,
                    known_skill_ids,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(owner_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    career_goal=excluded.career_goal,
                    weekly_hours=excluded.weekly_hours,
                    target_skill_ids=excluded.target_skill_ids,
                    known_skill_ids=excluded.known_skill_ids,
                    updated_at=excluded.updated_at""",
                (
                    owner, proposed["display_name"], proposed["career_goal"],
                    proposed["weekly_hours"], json.dumps(proposed["target_skill_ids"]),
                    json.dumps(proposed["known_skill_ids"]), timestamp,
                ),
            )
            self.conn.execute(
                """INSERT INTO audit_events(
                    owner_id,entity_type,entity_id,operation,detail_json,recorded_at
                ) VALUES(?,?,?,?,?,?)""",
                (
                    owner, "account_preferences", owner, "updated",
                    json.dumps({"changed_fields": changed}, sort_keys=True),
                    timestamp,
                ),
            )
        return self.get(owner)
