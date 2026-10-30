import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from fastapi.testclient import TestClient
from nextrail_api import create_app
from nextrail_auth import AccountStore, AuthError
from nextrail_storage import open_database, LearningStore


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.context = TestClient(create_app())
        self.client = self.context.__enter__()
        self.password = "long-testing-password123"

    def tearDown(self):
        self.context.__exit__(None, None, None)

    def register(self, email):
        return self.client.post("/v1/auth/register", json={"email": email, "password": self.password})

    def login(self, email):
        res = self.client.post("/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(res.status_code, 200)
        return {"Authorization": "Bearer " + res.json()["access_token"]}

    def plan(self):
        return {"career_goal": "Frontend", "target_skill_ids": ["css"], "weekly_hours": 5}

    def test_health(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_guest_courses_without_login(self):
        self.assertEqual(self.client.get("/v1/courses").status_code, 200)

    def test_guest_skills_without_login(self):
        result = self.client.get("/v1/skills")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(any(skill["id"] == "html" for skill in result.json()["items"]))

    def test_guest_preview_without_login(self):
        r = self.client.post("/v1/pathways/preview", json=self.plan())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["generation_mode"], "deterministic")

    def test_guest_preview_rejects_unknown_skill(self):
        r = self.client.post("/v1/pathways/preview", json={"career_goal": "Frontend", "target_skill_ids": ["fake"]})
        self.assertEqual(r.status_code, 422)

    def test_private_endpoint_requires_session(self):
        self.assertEqual(self.client.get("/v1/me").status_code, 401)

    def test_register_and_login(self):
        self.assertEqual(self.register("first@example.org").status_code, 201)
        headers = self.login("first@example.org")
        self.assertEqual(self.client.get("/v1/me", headers=headers).json()["email"], "first@example.org")

    def test_wrong_password(self):
        self.register("first@example.org")
        r = self.client.post("/v1/auth/login", json={"email": "first@example.org", "password": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_duplicate_registration(self):
        self.register("first@example.org")
        self.assertEqual(self.register("first@example.org").status_code, 400)

    def test_short_password_rejected(self):
        self.assertEqual(self.client.post("/v1/auth/register",
            json={"email": "x@example.org", "password": "short"}).status_code, 400)

    def test_logout_revokes_access(self):
        self.register("first@example.org")
        headers = self.login("first@example.org")
        self.assertEqual(self.client.post("/v1/auth/logout", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/v1/me", headers=headers).status_code, 401)

    def test_save_pathway_scoped(self):
        self.register("a@example.org")
        self.register("b@example.org")
        a, b = self.login("a@example.org"), self.login("b@example.org")
        saved = self.client.post("/v1/me/pathways", headers=a, json=self.plan())
        self.assertEqual(saved.status_code, 201)
        key = saved.json()["id"]
        self.assertEqual(self.client.get("/v1/me/pathways/" + key, headers=b).status_code, 404)
        self.assertEqual(self.client.get("/v1/me/pathways/" + key, headers=a).status_code, 200)

    def test_update_progress_scoped(self):
        self.register("a@example.org")
        self.register("b@example.org")
        a, b = self.login("a@example.org"), self.login("b@example.org")
        key = self.client.post("/v1/me/pathways", headers=a, json=self.plan()).json()["id"]
        path = f"/v1/me/pathways/{key}/progress/html"
        self.assertEqual(self.client.put(path, headers=b, json={"status": "completed"}).status_code, 404)
        self.assertEqual(self.client.put(path, headers=a, json={"status": "completed"}).status_code, 200)
        self.assertEqual(self.client.get(f"/v1/me/pathways/{key}/progress", headers=a).json()["completed"], 1)

    def test_reset_unknown_email_generic(self):
        self.assertEqual(self.client.post("/v1/auth/password-reset/request",
            json={"email": "unknown@example.org"}).json(), {"accepted": True})

    def test_reset_without_delivery_does_not_issue_token(self):
        self.register("a@example.org")
        self.assertEqual(self.client.post("/v1/auth/password-reset/request",
            json={"email": "a@example.org"}).status_code, 200)
        self.assertEqual(self.client.post("/v1/auth/password-reset/confirm",
            json={"token": "invalid", "new_password": "new-long-password123"}).status_code, 400)

    def test_invalid_bearer_token_rejected(self):
        self.assertEqual(self.client.get("/v1/me", headers={"Authorization": "Bearer forged"}).status_code, 401)

    def test_save_unknown_synthetic_course_rejected(self):
        self.register("a@example.org")
        self.assertEqual(self.client.put("/v1/me/courses/example-html-course",
            headers=self.login("a@example.org")).status_code, 404)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.conn = open_database()
        self.now = [5000]
        self.auth = AccountStore(self.conn, clock=lambda: self.now[0])

    def tearDown(self):
        self.conn.close()

    def test_secure_password_storage(self):
        self.auth.register("a@example.org", "long-testing-password123")
        stored = self.conn.execute("SELECT secret_hash FROM accounts").fetchone()[0]
        self.assertNotIn("long-testing-password123", stored)
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))

    def test_token_not_stored_plaintext(self):
        self.auth.register("a@example.org", "long-testing-password123")
        token = self.auth.login("a@example.org", "long-testing-password123")["access_token"]
        row = self.conn.execute("SELECT token_hash FROM auth_sessions").fetchone()[0]
        self.assertNotEqual(token, row)

    def test_expired_session_rejected(self):
        self.auth.register("a@example.org", "long-testing-password123")
        token = self.auth.login("a@example.org", "long-testing-password123")["access_token"]
        self.now[0] += 86401
        with self.assertRaises(AuthError):
            self.auth.session_owner(token)

    def test_five_failures_throttle(self):
        self.auth.register("a@example.org", "long-testing-password123")
        for _ in range(5):
            with self.assertRaises(AuthError):
                self.auth.login("a@example.org", "wrong")
        with self.assertRaises(AuthError):
            self.auth.login("a@example.org", "long-testing-password123")

    def test_reset_revokes_existing_sessions(self):
        self.auth.register("a@example.org", "long-testing-password123")
        token = self.auth.login("a@example.org", "long-testing-password123")["access_token"]
        out = []
        self.auth.request_password_reset("a@example.org", lambda email, secret: out.append(secret))
        self.assertEqual(len(out), 1)
        self.auth.confirm_password_reset(out[0], "new-testing-password123")
        with self.assertRaises(AuthError):
            self.auth.session_owner(token)
        self.auth.login("a@example.org", "new-testing-password123")

    def test_reset_token_single_use(self):
        self.auth.register("a@example.org", "long-testing-password123")
        out = []
        self.auth.request_password_reset("a@example.org", lambda email, token: out.append(token))
        self.auth.confirm_password_reset(out[0], "new-testing-password123")
        with self.assertRaises(AuthError):
            self.auth.confirm_password_reset(out[0], "another-testing-password123")

    def test_reset_expiry(self):
        self.auth.register("a@example.org", "long-testing-password123")
        out = []
        self.auth.request_password_reset("a@example.org", lambda email, token: out.append(token))
        self.now[0] += 901
        with self.assertRaises(AuthError):
            self.auth.confirm_password_reset(out[0], "new-testing-password123")

    def test_existing_learning_schema_preserved(self):
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(LearningStore(self.conn).list_saved_courses("acct_x"), [])

    def test_unversioned_database_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.sqlite"
            import sqlite3
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE legacy (value TEXT)")
            connection.close()
            from nextrail_storage import StorageError
            with self.assertRaises(StorageError):
                open_database(path)


if __name__ == "__main__":
    unittest.main()
