"""Opt-in, SQLite-backed fixed-window throttling shared by API worker processes.

All operations are transactional against one durable SQLite file. Only keyed
HMAC digests of client addresses are stored; forwarded IP headers are ignored.
This protects a single SQLite deployment, not a distributed/cloud topology.
"""
import hashlib
import hmac
import sqlite3
import time

from fastapi import HTTPException

from nextrail_storage.database import atomic

TABLE = """CREATE TABLE IF NOT EXISTS api_rate_limits (
    route TEXT NOT NULL,
    client_digest TEXT NOT NULL,
    window_seconds INTEGER NOT NULL CHECK(window_seconds > 0),
    slot INTEGER NOT NULL,
    used INTEGER NOT NULL CHECK(used >= 1),
    PRIMARY KEY (route, client_digest, window_seconds)
)"""


class SQLiteFixedWindowLimiter:
    """Share fixed-window budgets across connections using BEGIN IMMEDIATE."""

    def __init__(self, connection: sqlite3.Connection, key: bytes, *, clock=None, max_keys=4096):
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("A 32-byte rate-limit HMAC key is required")
        if not isinstance(max_keys, int) or max_keys < 1:
            raise ValueError("Invalid rate-limit capacity")
        self.connection = connection
        self.key = key
        self.clock = time.time if clock is None else clock
        self.max_keys = max_keys
        # Key changes must not silently reset outstanding client budgets.
        key_check = hmac.new(key, b"nextrail-rate-limit-key-v1", hashlib.sha256).hexdigest()
        try:
            with atomic(self.connection):
                self.connection.execute(TABLE)
                self.connection.execute("""CREATE TABLE IF NOT EXISTS api_rate_limits_meta (
                    id INTEGER PRIMARY KEY CHECK(id=1), key_check TEXT NOT NULL
                )""")
                self.connection.execute(
                    "INSERT OR IGNORE INTO api_rate_limits_meta(id,key_check) VALUES(1,?)",
                    (key_check,),
                )
                rows = self.connection.execute(
                    "SELECT id,key_check FROM api_rate_limits_meta"
                ).fetchall()
                if (len(rows) != 1 or rows[0]["id"] != 1
                        or not hmac.compare_digest(rows[0]["key_check"], key_check)):
                    raise ValueError("Shared request protection key changed; refusing startup")
        except sqlite3.Error as exc:
            raise HTTPException(503, "Request protection unavailable") from exc

    def enforce(self, request, route: str, limit: int, seconds: int = 60):
        if (not isinstance(route, str) or not route or not isinstance(limit, int)
                or limit < 1 or not isinstance(seconds, int) or seconds < 1):
            raise ValueError("Invalid request limit policy")
        address = request.client.host if request.client else "unknown"
        digest = hmac.new(self.key, str(address).encode("utf-8"), hashlib.sha256).hexdigest()
        now = int(self.clock())
        slot = now // seconds
        denied = False
        try:
            with atomic(self.connection):
                row = self.connection.execute(
                    """SELECT slot,used FROM api_rate_limits
                    WHERE route=? AND client_digest=? AND window_seconds=?""",
                    (route, digest, seconds),
                ).fetchone()
                if row is None:
                    count = self.connection.execute(
                        "SELECT COUNT(*) FROM api_rate_limits"
                    ).fetchone()[0]
                    if count >= self.max_keys:
                        self.connection.execute(
                            """DELETE FROM api_rate_limits
                            WHERE (slot + 1) * window_seconds <= ?""", (now,),
                        )
                        count = self.connection.execute(
                            "SELECT COUNT(*) FROM api_rate_limits"
                        ).fetchone()[0]
                    if count >= self.max_keys:
                        denied = "capacity"
                    else:
                        self.connection.execute(
                            """INSERT INTO api_rate_limits
                            (route,client_digest,window_seconds,slot,used)
                            VALUES(?,?,?,?,1)""",
                            (route, digest, seconds, slot),
                        )
                elif row["slot"] > slot:
                    # Refuse budget resets caused by a backwards clock jump.
                    denied = "clock"
                elif row["slot"] < slot:
                    self.connection.execute(
                        """UPDATE api_rate_limits SET slot=?,used=1
                        WHERE route=? AND client_digest=? AND window_seconds=?""",
                        (slot, route, digest, seconds),
                    )
                elif row["used"] >= limit:
                    denied = "limit"
                else:
                    self.connection.execute(
                        """UPDATE api_rate_limits SET used=used+1
                        WHERE route=? AND client_digest=? AND window_seconds=?""",
                        (route, digest, seconds),
                    )
        except sqlite3.Error as exc:
            raise HTTPException(503, "Request protection unavailable") from exc
        if denied:
            retry = max(1, (slot + 1) * seconds - now)
            if denied == "clock":
                retry = seconds
            raise HTTPException(
                429,
                "Request capacity exceeded" if denied == "capacity" else "Too many requests",
                headers={"Retry-After": str(retry)},
            )
