"""Local password auth with hashed bearer credentials and scoped SQLite sessions."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from uuid import uuid4

from nextrail_storage.database import atomic

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
