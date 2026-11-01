"""Phase 26 offline regression checks for opt-in shared SQLite request budgets."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api import create_app
from nextrail_api.settings import ConfigurationError, shared_rate_limit_key_from_env
from nextrail_api.shared_limits import SQLiteFixedWindowLimiter
from nextrail_storage import open_database

KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))


def request(host="192.0.2.18"):
    return SimpleNamespace(client=SimpleNamespace(host=host),
                           headers={"x-forwarded-for": "203.0.113.55"})


class SharedLimiterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp.name) / "shared.sqlite")
        self.first = open_database(self.db_path)
        self.second = open_database(self.db_path)
        self.clock = [1800]

    def tearDown(self):
        self.second.close()
        self.first.close()
        self.temp.cleanup()

    def limiter(self, conn, *, key=KEY, max_keys=4096):
        return SQLiteFixedWindowLimiter(
            conn, key, clock=lambda: self.clock[0], max_keys=max_keys
        )

    def test_budget_shared_across_separate_database_connections(self):
        first = self.limiter(self.first)
        second = self.limiter(self.second)
        first.enforce(request(), "login", 2)
        second.enforce(request(), "login", 2)
        with self.assertRaises(HTTPException) as caught:
            first.enforce(request(), "login", 2)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertGreaterEqual(int(caught.exception.headers["Retry-After"]), 1)

    def test_budget_survives_new_limiter_and_connection(self):
        self.limiter(self.first).enforce(request(), "register", 1)
        with self.assertRaises(HTTPException):
            self.limiter(self.second).enforce(request(), "register", 1)

    def test_window_reset_and_backward_clock_fail_closed(self):
        limiter = self.limiter(self.first)
        limiter.enforce(request(), "reset", 1, seconds=60)
        self.clock[0] += 60
        limiter.enforce(request(), "reset", 1, seconds=60)
        self.clock[0] -= 61
        with self.assertRaises(HTTPException):
            limiter.enforce(request(), "reset", 1, seconds=60)

    def test_routes_and_clients_are_independent(self):
        limiter = self.limiter(self.first)
        limiter.enforce(request(), "login", 1)
        limiter.enforce(request(), "register", 1)
        limiter.enforce(request("192.0.2.19"), "login", 1)

    def test_raw_client_ip_and_secret_not_stored(self):
        self.limiter(self.first).enforce(request(), "login", 1)
        row = self.first.execute("SELECT route,client_digest FROM api_rate_limits").fetchone()
        self.assertEqual(row["route"], "login")
        self.assertEqual(len(row["client_digest"]), 64)
        self.assertNotIn("192.0.2.18", row["client_digest"])
        self.assertNotIn("203.0.113.55", row["client_digest"])
        self.assertNotIn(KEY.hex(), row["client_digest"])

    def test_rotation_does_not_reset_rate_budget(self):
        self.limiter(self.first).enforce(request(), "login", 1)
        with self.assertRaises(ValueError):
            self.limiter(self.second, key=OTHER_KEY)

    def test_capacity_fails_closed_and_prunes_expired_keys(self):
        limiter = self.limiter(self.first, max_keys=1)
        limiter.enforce(request(), "login", 1)
        with self.assertRaises(HTTPException) as caught:
            limiter.enforce(request("192.0.2.19"), "login", 1)
        self.assertEqual(caught.exception.status_code, 429)
        self.clock[0] += 61
        limiter.enforce(request("192.0.2.19"), "login", 1)

    def test_missing_table_does_not_allow_request(self):
        limiter = self.limiter(self.first)
        self.first.execute("DROP TABLE api_rate_limits")
        with self.assertRaises(HTTPException) as caught:
            limiter.enforce(request(), "login", 1)
        self.assertEqual(caught.exception.status_code, 503)

    def test_existing_storage_version_unchanged(self):
        self.limiter(self.first)
        self.assertEqual(self.first.execute("PRAGMA user_version").fetchone()[0], 1)


class SharedLimiterConfigurationTests(unittest.TestCase):
    def test_default_is_local_only(self):
        self.assertIsNone(shared_rate_limit_key_from_env({}))

    def test_invalid_or_missing_secret_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "db.sqlite")
            for value in ("a", "a" * 64, "A" * 64, "00" * 32 + " "):
                if value == "a" * 64:
                    continue
                with self.subTest(secret=value), self.assertRaises(ConfigurationError):
                    shared_rate_limit_key_from_env({
                        "NEXTRAIL_DB_PATH": path, "NEXTRAIL_RATE_LIMIT_HMAC_KEY": value,
                    })

    def test_requires_file_backed_database(self):
        with self.assertRaises(ConfigurationError):
            shared_rate_limit_key_from_env({
                "NEXTRAIL_RATE_LIMIT_HMAC_KEY": KEY.hex(),
            })

    def test_valid_durable_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "db.sqlite")
            self.assertEqual(shared_rate_limit_key_from_env({
                "NEXTRAIL_DB_PATH": path,
                "NEXTRAIL_RATE_LIMIT_HMAC_KEY": KEY.hex(),
            }), KEY)

    def test_app_rejects_in_memory_shared_limiting(self):
        with self.assertRaises(ValueError):
            create_app(shared_rate_limit_key=KEY)


class SharedLimiterIntegrationTests(unittest.TestCase):
    def test_registration_budget_persists_across_app_restarts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "api.sqlite")
            with TestClient(create_app(database_path=path, shared_rate_limit_key=KEY)) as first:
                for n in range(4):
                    result = first.post("/v1/auth/register", json={
                        "email": f"person{n}@example.org",
                        "password": "long-testing-password123"
                    })
                    self.assertEqual(result.status_code, 201, result.text)
                self.assertEqual(first.get("/v1/courses").status_code, 200)
            with TestClient(create_app(database_path=path, shared_rate_limit_key=KEY)) as second:
                for n in range(4, 6):
                    result = second.post("/v1/auth/register", json={
                        "email": f"person{n}@example.org",
                        "password": "long-testing-password123"
                    })
                    self.assertEqual(result.status_code, 201, result.text)
                self.assertEqual(second.post("/v1/auth/register", json={
                    "email": "person6@example.org", "password": "long-testing-password123"
                }).status_code, 429)
                self.assertEqual(second.get("/v1/courses").status_code, 200)


if __name__ == "__main__":
    unittest.main()
