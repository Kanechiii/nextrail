"""Local password auth with hashed bearer credentials and scoped SQLite sessions."""
import hashlib
import json
import hmac
import re
import secrets
import sqlite3
import time
from uuid import uuid4

from nextrail_storage.database import atomic
from nextrail_storage.store import LearningStore

EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,63}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
ITERATIONS = 210_000
SESSION_TTL = 24 * 3600
RESET_TTL = 15 * 60
FAILED_LIMIT = 5
BLOCK_SECONDS = 15 * 60

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS auth_meta (
        id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
        secret_hash TEXT NOT NULL, created_at INTEGER NOT NULL,
        last_reset_at INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS auth_sessions (
        token_hash TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
        expires_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (owner_id) REFERENCES accounts(id) ON DELETE CASCADE
    )""",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_owner ON auth_sessions(owner_id)",
    """CREATE TABLE IF NOT EXISTS password_reset_tokens (
        token_hash TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        FOREIGN KEY (owner_id) REFERENCES accounts(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS login_attempts (
        email TEXT PRIMARY KEY, failures INTEGER NOT NULL,
        blocked_until INTEGER NOT NULL
    )""",
)


class AuthError(ValueError):
    """Authentication or credential validation was rejected."""


def normalize_email(value):
    if not isinstance(value, str) or len(value) > 254:
        raise AuthError("Invalid email address")
    email = value.strip().lower()
    if email != value.lower() or not EMAIL_RE.fullmatch(email):
        raise AuthError("Invalid email address")
    return email


def password_ok(value):
    return (
        isinstance(value, str)
        and 12 <= len(value) <= 128
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)
    )


def _password_hash(password, salt=None):
    salt = secrets.token_bytes(16) if salt is None else salt
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${key.hex()}"


def _verify_password(password, stored):
    try:
        method, iterations, salt, encoded = stored.split("$")
        if method != "pbkdf2_sha256" or int(iterations) != ITERATIONS:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
        )
        return hmac.compare_digest(actual, bytes.fromhex(encoded))
    except (ValueError, UnicodeError):
        return False


_DUMMY_HASH = _password_hash("not-the-correct-password")


def _digest(token):
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def initialize_auth_schema(conn: sqlite3.Connection):
    """Add isolated auth tables without modifying Phase 08 schema version or records."""
    if not conn.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise AuthError("Foreign keys must be enabled")
    with atomic(conn):
        for statement in SCHEMA:
            conn.execute(statement)
        conn.execute("INSERT OR IGNORE INTO auth_meta(id,version) VALUES(1,1)")
        rows = conn.execute("SELECT id,version FROM auth_meta").fetchall()
        if len(rows) != 1 or tuple(rows[0]) != (1, 1):
            raise AuthError("Unsupported authentication schema version")


class AccountStore:
    def __init__(self, conn: sqlite3.Connection, *, clock=None):
        self.conn = conn
        self.clock = time.time if clock is None else clock
        initialize_auth_schema(conn)

    def _now(self):
        return int(self.clock())

    def register(self, email, password):
        email = normalize_email(email)
        if not password_ok(password):
            raise AuthError("Password must be 12-128 printable characters")
        owner = "acct_" + uuid4().hex
        try:
            with atomic(self.conn):
                self.conn.execute(
                    "INSERT INTO accounts(id,email,secret_hash,created_at) VALUES(?,?,?,?)",
                    (owner, email, _password_hash(password), self._now()),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthError("Account could not be created") from exc
        return owner

    def login(self, email, password):
        email = normalize_email(email)
        if not isinstance(password, str) or len(password) > 128:
            raise AuthError("Invalid credentials")
        now = self._now()
        status = self.conn.execute(
            "SELECT failures,blocked_until FROM login_attempts WHERE email=?", (email,)
        ).fetchone()
        if status and status["blocked_until"] > now:
            raise AuthError("Invalid credentials")
        row = self.conn.execute(
            "SELECT id,secret_hash FROM accounts WHERE email=?", (email,)
        ).fetchone()
        stored = row["secret_hash"] if row else _DUMMY_HASH
        matched = _verify_password(password, stored)
        if not row or not matched:
            failures = (status["failures"] if status else 0) + 1
            blocked = now + BLOCK_SECONDS if failures >= FAILED_LIMIT else 0
            with atomic(self.conn):
                self.conn.execute(
                    """INSERT INTO login_attempts(email,failures,blocked_until)
                    VALUES(?,?,?) ON CONFLICT(email)
                    DO UPDATE SET failures=excluded.failures, blocked_until=excluded.blocked_until""",
                    (email, failures, blocked),
                )
            raise AuthError("Invalid credentials")
        token = secrets.token_urlsafe(32)
        with atomic(self.conn):
            self.conn.execute("DELETE FROM login_attempts WHERE email=?", (email,))
            self.conn.execute(
                "INSERT INTO auth_sessions(token_hash,owner_id,expires_at) VALUES(?,?,?)",
                (_digest(token), row["id"], now + SESSION_TTL),
            )
        return {"access_token": token, "token_type": "bearer", "expires_in": SESSION_TTL}

    def session_owner(self, token):
        hashed = _digest(token)
        if not hashed:
            raise AuthError("Invalid session")
        row = self.conn.execute(
            """SELECT owner_id FROM auth_sessions
            WHERE token_hash=? AND revoked=0 AND expires_at>?""",
            (hashed, self._now()),
        ).fetchone()
        if not row:
            raise AuthError("Invalid session")
        return row["owner_id"]

    def revoke_session(self, token):
        hashed = _digest(token)
        if not hashed:
            raise AuthError("Invalid session")
        with atomic(self.conn):
            changed = self.conn.execute(
                "UPDATE auth_sessions SET revoked=1 WHERE token_hash=? AND revoked=0",
                (hashed,),
            ).rowcount
        if not changed:
            raise AuthError("Invalid session")

    def account(self, owner):
        row = self.conn.execute(
            "SELECT id,email,created_at FROM accounts WHERE id=?", (owner,)
        ).fetchone()
        if not row:
            raise AuthError("Account not found")
        return dict(row)

    def request_password_reset(self, email, delivery=None):
        """Generic acknowledgement. Never return reset tokens to HTTP callers."""
        try:
            email = normalize_email(email)
        except AuthError:
            return
        if delivery is None:
            return
        row = self.conn.execute(
            "SELECT id,last_reset_at FROM accounts WHERE email=?", (email,)
        ).fetchone()
        if not row:
            return
        now = self._now()
        if now - row["last_reset_at"] < 60:
            return
        token = secrets.token_urlsafe(32)
        with atomic(self.conn):
            self.conn.execute(
                "UPDATE accounts SET last_reset_at=? WHERE id=?", (now, row["id"])
            )
            self.conn.execute(
                "DELETE FROM password_reset_tokens WHERE owner_id=?", (row["id"],)
            )
            self.conn.execute(
                """INSERT INTO password_reset_tokens(token_hash,owner_id,expires_at)
                VALUES(?,?,?)""", (_digest(token), row["id"], now + RESET_TTL)
            )
        try:
            delivery(email, token)
        except Exception:
            with atomic(self.conn):
                self.conn.execute(
                    "DELETE FROM password_reset_tokens WHERE token_hash=?", (_digest(token),)
                )

    def confirm_password_reset(self, token, new_password):
        hashed = _digest(token)
        if not hashed or not password_ok(new_password):
            raise AuthError("Invalid or expired reset credentials")
        with atomic(self.conn):
            row = self.conn.execute(
                """SELECT owner_id FROM password_reset_tokens
                WHERE token_hash=? AND expires_at>?""", (hashed, self._now())
            ).fetchone()
            if not row:
                raise AuthError("Invalid or expired reset credentials")
            owner = row["owner_id"]
            self.conn.execute(
                "UPDATE accounts SET secret_hash=? WHERE id=?",
                (_password_hash(new_password), owner)
            )
            self.conn.execute(
                "DELETE FROM password_reset_tokens WHERE owner_id=?", (owner,)
            )
            self.conn.execute(
                "UPDATE auth_sessions SET revoked=1 WHERE owner_id=?", (owner,)
            )
        return True

    def active_sessions(self, token):
        """Count a verified account's active sessions without revealing token data."""
        owner = self.session_owner(token)
        return self.conn.execute(
            """SELECT count(*) FROM auth_sessions
            WHERE owner_id=? AND revoked=0 AND expires_at>?""",
            (owner, self._now()),
        ).fetchone()[0]

    def revoke_other_sessions(self, token):
        """Keep the current bearer valid; revoke every other active session."""
        owner = self.session_owner(token)
        current_hash = _digest(token)
        with atomic(self.conn):
            if self.session_owner(token) != owner:
                raise AuthError("Invalid session")
            affected = self.conn.execute(
                """UPDATE auth_sessions SET revoked=1
                WHERE owner_id=? AND token_hash<>? AND revoked=0
                AND expires_at>?""",
                (owner, current_hash, self._now()),
            ).rowcount
        return affected

    def change_password(self, token, current_password, new_password):
        """Reauthenticate and revoke every session and reset link on success."""
        owner = self.session_owner(token)
        if (not isinstance(current_password, str) or len(current_password) > 128
                or not password_ok(new_password)):
            raise AuthError("Invalid password change credentials")
        with atomic(self.conn):
            if self.session_owner(token) != owner:
                raise AuthError("Invalid session")
            row = self.conn.execute(
                "SELECT email,secret_hash FROM accounts WHERE id=?", (owner,)
            ).fetchone()
            if (row is None or not _verify_password(current_password, row["secret_hash"])
                    or current_password == new_password):
                raise AuthError("Invalid password change credentials")
            self.conn.execute(
                "UPDATE accounts SET secret_hash=? WHERE id=?",
                (_password_hash(new_password), owner),
            )
            self.conn.execute(
                "UPDATE auth_sessions SET revoked=1 WHERE owner_id=?", (owner,)
            )
            self.conn.execute(
                "DELETE FROM password_reset_tokens WHERE owner_id=?", (owner,)
            )
            self.conn.execute(
                "DELETE FROM login_attempts WHERE email=?", (row["email"],)
            )
        return True

    def export_account(self, token):
        """A bounded, owner-only account export without authentication secrets.

        The database transaction makes the exported snapshot consistent.
        Refuse oversized exports instead of silently omitting records.
        """
        owner = self.session_owner(token)
        from .preferences import AccountPreferencesStore

        preferences_store = AccountPreferencesStore(self.conn)
        with atomic(self.conn):
            account = self.account(owner)
            preferences = preferences_store.get(owner)
            pathways = self.conn.execute(
                """SELECT id,pathway_json,created_at FROM learning_pathways
                WHERE owner_id=? ORDER BY created_at DESC,id DESC LIMIT 501""",
                (owner,),
            ).fetchall()
            saved_courses = self.conn.execute(
                """SELECT resource_id FROM saved_courses
                WHERE owner_id=? ORDER BY resource_id LIMIT 2001""",
                (owner,),
            ).fetchall()
            audit_events = self.conn.execute(
                """SELECT event_id,entity_type,entity_id,operation,detail_json,recorded_at
                FROM audit_events WHERE owner_id=?
                ORDER BY event_id LIMIT 5001""",
                (owner,),
            ).fetchall()
            if (len(pathways) > 500 or len(saved_courses) > 2000
                    or len(audit_events) > 5000):
                raise AuthError("Account export exceeds the safe synchronous limit")
            learning = LearningStore(self.conn)
            payload = {
                "schema_version": "1.0.0",
                "account": account,
                "preferences": preferences,
                "pathways": [
                    {
                        "id": row["id"],
                        "created_at": row["created_at"],
                        "pathway": json.loads(row["pathway_json"]),
                        "progress": learning.get_progress(owner, row["id"]),
                    }
                    for row in pathways
                ],
                "saved_course_ids": [row["resource_id"] for row in saved_courses],
                "audit_events": [
                    {
                        "event_id": row["event_id"],
                        "entity_type": row["entity_type"],
                        "entity_id": row["entity_id"],
                        "operation": row["operation"],
                        "detail": json.loads(row["detail_json"]),
                        "recorded_at": row["recorded_at"],
                    }
                    for row in audit_events
                ],
            }
            if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 2_000_000:
                raise AuthError("Account export exceeds the safe synchronous limit")
        return payload

    def delete_account(self, token, current_password):
        """Permanently remove a reauthenticated account's local records.

        The normal audit table is append-only. Privacy erasure is an explicit
        exception: drop its deletion guard *within the same SQLite write
        transaction*, erase only this owner's rows, then restore the exact
        original guard before commit. Any error restores data and DDL.
        """
        owner = self.session_owner(token)
        if not isinstance(current_password, str) or len(current_password) > 128:
            raise AuthError("Invalid account deletion credentials")
        with atomic(self.conn):
            row = self.conn.execute(
                "SELECT email,secret_hash FROM accounts WHERE id=?", (owner,)
            ).fetchone()
            if row is None or not _verify_password(current_password, row["secret_hash"]):
                raise AuthError("Invalid account deletion credentials")
            guard = self.conn.execute(
                """SELECT sql FROM sqlite_master
                WHERE type='trigger' AND name='audit_events_no_delete'"""
            ).fetchone()
            statement = guard[0] if guard is not None else None
            normalized = " ".join(statement.lower().split()) if isinstance(statement, str) else ""
            if not (
                normalized.startswith(
                    "create trigger audit_events_no_delete before delete on audit_events"
                )
                and "raise(abort, 'audit records are append-only')" in normalized
            ):
                raise AuthError("Unexpected audit deletion guard; refusing account erasure")

            # Verify the *behavior* rather than comparing SQLite's stored DDL
            # byte-for-byte. SQLite may normalize trigger definitions across
            # versions. Probe and roll back a disposable row within this
            # transaction; never touch another account's audit history.
            self.conn.execute("SAVEPOINT account_guard_probe")
            try:
                probe = self.conn.execute(
                    """INSERT INTO audit_events(owner_id,entity_type,entity_id,
                    operation,detail_json,recorded_at) VALUES(?,?,?,?,?,?)""",
                    (owner, "account", owner, "guard_probe", "{}", "1970-01-01T00:00:00Z"),
                ).lastrowid
                try:
                    self.conn.execute(
                        "DELETE FROM audit_events WHERE event_id=?", (probe,)
                    )
                except sqlite3.DatabaseError as exc:
                    if "audit records are append-only" not in str(exc):
                        raise AuthError("Audit deletion guard is not operating") from exc
                else:
                    raise AuthError("Audit deletion guard is not operating")
            finally:
                self.conn.execute("ROLLBACK TO SAVEPOINT account_guard_probe")
                self.conn.execute("RELEASE SAVEPOINT account_guard_probe")

            self.conn.execute("DROP TRIGGER audit_events_no_delete")
            self.conn.execute(
                "DELETE FROM milestone_progress WHERE owner_id=?", (owner,)
            )
            self.conn.execute(
                "DELETE FROM learning_pathways WHERE owner_id=?", (owner,)
            )
            self.conn.execute(
                "DELETE FROM saved_courses WHERE owner_id=?", (owner,)
            )
            self.conn.execute("DELETE FROM audit_events WHERE owner_id=?", (owner,))
            self.conn.execute(
                "DELETE FROM login_attempts WHERE email=?", (row["email"],)
            )
            deleted = self.conn.execute(
                "DELETE FROM accounts WHERE id=?", (owner,)
            ).rowcount
            if deleted != 1:
                raise AuthError("Account erasure failed")
            self.conn.execute(statement)
        return True
