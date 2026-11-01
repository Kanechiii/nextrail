"""Phase 18: account lifecycle, erasure and bearer-security regression coverage."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api import create_app
from nextrail_auth import AccountStore, AuthError
from nextrail_auth.preferences import AccountPreferencesStore
from nextrail_storage import LearningStore, open_database
from nextrail_storage.recovery import inspect_database

PASSWORD = "strong-original-password123"
NEW_PASSWORD = "strong-updated-password321"


class AccountLifecycleApiTests(unittest.TestCase):
    def setUp(self):
        self.context = TestClient(create_app())
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)

    def login(self, email="owner@example.org", password=PASSWORD):
        response = self.client.post(
            "/v1/auth/login", json={"email": email, "password": password}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def register(self, email="owner@example.org", password=PASSWORD):
        response = self.client.post(
            "/v1/auth/register", json={"email": email, "password": password}
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_guest_apis_stay_available(self):
        self.assertEqual(self.client.get("/v1/courses").status_code, 200)
        self.assertEqual(self.client.get("/v1/skills").status_code, 200)
        self.assertEqual(self.client.post(
            "/v1/pathways/preview", json={
                "career_goal": "Frontend",
                "target_skill_ids": ["css"],
            },
        ).status_code, 200)

    def test_all_new_endpoints_require_bearer_authentication(self):
        self.assertEqual(self.client.get("/v1/me/sessions").status_code, 401)
        self.assertEqual(self.client.post("/v1/me/sessions/revoke-others").status_code, 401)
        self.assertEqual(self.client.get("/v1/me/export").status_code, 401)
        self.assertEqual(self.client.post(
            "/v1/me/password", json={
                "current_password": PASSWORD, "new_password": NEW_PASSWORD,
            },
        ).status_code, 401)
        self.assertEqual(self.client.request(
            "DELETE", "/v1/me/account",
            json={"current_password": PASSWORD, "confirmation": "DELETE MY ACCOUNT"},
        ).status_code, 401)

    def test_forged_bearer_rejected_for_all_new_routes(self):
        h = {"Authorization": "Bearer invalid"}
        self.assertEqual(self.client.get("/v1/me/sessions", headers=h).status_code, 401)
        self.assertEqual(self.client.get("/v1/me/export", headers=h).status_code, 401)
        self.assertEqual(self.client.post(
            "/v1/me/sessions/revoke-others", headers=h,
        ).status_code, 401)

    def test_active_sessions_and_revoke_other_sessions(self):
        self.register()
        first = self.login()
        second = self.login()
        self.assertEqual(self.client.get(
            "/v1/me/sessions", headers=first,
        ).json(), {"active_count": 2})
        result = self.client.post(
            "/v1/me/sessions/revoke-others", headers=first
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {"revoked_count": 1})
        self.assertEqual(self.client.get("/v1/me/sessions", headers=first).json(), {
            "active_count": 1,
        })
        self.assertEqual(self.client.get("/v1/me", headers=second).status_code, 401)
        self.assertEqual(self.client.get("/v1/me", headers=first).status_code, 200)

    def test_revocation_of_other_sessions_is_idempotent(self):
        self.register()
        h = self.login()
        self.assertEqual(self.client.post(
            "/v1/me/sessions/revoke-others", headers=h,
        ).json()["revoked_count"], 0)

    def test_session_count_does_not_expose_bearer_or_token_hash(self):
        self.register()
        h = self.login()
        r = self.client.get("/v1/me/sessions", headers=h)
        self.assertEqual(set(r.json()), {"active_count"})
        self.assertNotIn(h["Authorization"][7:], r.text)
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_account_password_change_revokes_all_sessions(self):
        self.register()
        first = self.login()
        second = self.login()
        r = self.client.post("/v1/me/password", headers=first, json={
            "current_password": PASSWORD, "new_password": NEW_PASSWORD,
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"updated": True, "sessions_revoked": True})
        self.assertEqual(self.client.get("/v1/me", headers=first).status_code, 401)
        self.assertEqual(self.client.get("/v1/me", headers=second).status_code, 401)
        self.assertEqual(self.client.post("/v1/auth/login", json={
            "email": "owner@example.org", "password": PASSWORD,
        }).status_code, 401)
        self.login(password=NEW_PASSWORD)

    def test_wrong_current_password_does_not_revoke_sessions(self):
        self.register()
        h = self.login()
        r = self.client.post("/v1/me/password", headers=h, json={
            "current_password": "incorrect-password",
            "new_password": NEW_PASSWORD,
        })
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/v1/me", headers=h).status_code, 200)
        self.login()

    def test_password_reuse_rejected(self):
        self.register()
        h = self.login()
        self.assertEqual(self.client.post(
            "/v1/me/password", headers=h,
            json={"current_password": PASSWORD, "new_password": PASSWORD},
        ).status_code, 400)
        self.assertEqual(self.client.get("/v1/me", headers=h).status_code, 200)

    def test_short_new_password_and_extra_fields_rejected(self):
        self.register()
        h = self.login()
        self.assertEqual(self.client.post(
            "/v1/me/password", headers=h,
            json={"current_password": PASSWORD, "new_password": "weak"},
        ).status_code, 422)
        self.assertEqual(self.client.post(
            "/v1/me/password", headers=h,
            json={
                "current_password": PASSWORD,
                "new_password": NEW_PASSWORD,
                "owner_id": "someone-else",
            },
        ).status_code, 422)

    def test_learner_export_contains_scoped_progress_and_not_secrets(self):
        self.register()
        h = self.login()
        prefs = self.client.patch("/v1/me/preferences", headers=h, json={
            "display_name": "Learner",
            "career_goal": "Frontend Engineer",
            "target_skill_ids": ["css"],
            "weekly_hours": 9,
        })
        self.assertEqual(prefs.status_code, 200)
        saved = self.client.post("/v1/me/pathways", headers=h, json={
            "career_goal": "Frontend Engineer", "target_skill_ids": ["css"],
        })
        self.assertEqual(saved.status_code, 201)
        pathway_id = saved.json()["id"]
        self.assertEqual(self.client.put(
            f"/v1/me/pathways/{pathway_id}/progress/html",
            headers=h, json={"status": "completed"},
        ).status_code, 200)
        response = self.client.get("/v1/me/export", headers=h)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        export = response.json()
        self.assertEqual(export["schema_version"], "1.0.0")
        self.assertEqual(export["account"]["email"], "owner@example.org")
        self.assertEqual(export["preferences"]["display_name"], "Learner")
        self.assertEqual(export["pathways"][0]["id"], pathway_id)
        self.assertEqual(export["pathways"][0]["progress"]["completed"], 1)
        self.assertTrue(export["audit_events"])
        self.assertEqual(export["saved_course_ids"], [])
        self.assertNotIn("secret_hash", response.text)
        self.assertNotIn("token_hash", response.text)
        self.assertNotIn("reset_token", response.text)
        self.assertNotIn(PASSWORD, response.text)
        self.assertNotIn(h["Authorization"][7:], response.text)

    def test_export_isolation_between_accounts(self):
        self.register("one@example.org")
        self.register("two@example.org")
        first = self.login("one@example.org")
        second = self.login("two@example.org")
        self.client.patch("/v1/me/preferences", headers=first,
                          json={"career_goal": "Private first goal"})
        self.client.post("/v1/me/pathways", headers=first, json={
            "career_goal": "First personal learning plan",
            "target_skill_ids": ["css"],
        })
        exported = self.client.get("/v1/me/export", headers=second)
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.json()["account"]["email"], "two@example.org")
        self.assertEqual(exported.json()["pathways"], [])
        self.assertNotIn("Private first goal", exported.text)
        self.assertNotIn("First personal learning plan", exported.text)

    def test_delete_requires_exact_confirmation(self):
        self.register()
        h = self.login()
        response = self.client.request("DELETE", "/v1/me/account",
            headers=h, json={
                "current_password": PASSWORD, "confirmation": "delete my account",
            })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/v1/me", headers=h).status_code, 200)

    def test_delete_rejects_wrong_password_without_changes(self):
        self.register()
        h = self.login()
        response = self.client.request("DELETE", "/v1/me/account",
            headers=h, json={
                "current_password": "incorrect",
                "confirmation": "DELETE MY ACCOUNT",
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/v1/me", headers=h).status_code, 200)

    def test_delete_erases_account_and_revokes_sessions(self):
        self.register()
        first = self.login()
        second = self.login()
        saved = self.client.post("/v1/me/pathways", headers=first, json={
            "career_goal": "Delete the learning history",
            "target_skill_ids": ["css"],
        })
        pid = saved.json()["id"]
        self.client.put(
            f"/v1/me/pathways/{pid}/progress/html",
            headers=first, json={"status": "completed"},
        )
        self.client.patch(
            "/v1/me/preferences", headers=first,
            json={"career_goal": "Erase this private goal"},
        )
        response = self.client.request(
            "DELETE", "/v1/me/account", headers=first, json={
                "current_password": PASSWORD,
                "confirmation": "DELETE MY ACCOUNT",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"deleted": True})
        self.assertEqual(self.client.get("/v1/me", headers=first).status_code, 401)
        self.assertEqual(self.client.get("/v1/me", headers=second).status_code, 401)
        self.assertEqual(self.client.post("/v1/auth/login", json={
            "email": "owner@example.org", "password": PASSWORD,
        }).status_code, 401)
        # Other stores never require a guest account, and email becomes reusable.
        self.assertEqual(self.client.post(
            "/v1/auth/register", json={
                "email": "owner@example.org", "password": NEW_PASSWORD,
            },
        ).status_code, 201)

    def test_delete_does_not_purge_other_account(self):
        self.register("first@example.org")
        self.register("second@example.org")
        first = self.login("first@example.org")
        second = self.login("second@example.org")
        self.client.post("/v1/me/pathways", headers=second, json={
            "career_goal": "Keep this goal", "target_skill_ids": ["html"],
        })
        self.assertEqual(self.client.request(
            "DELETE", "/v1/me/account", headers=first, json={
                "current_password": PASSWORD,
                "confirmation": "DELETE MY ACCOUNT",
            },
        ).status_code, 200)
        self.assertEqual(self.client.get("/v1/me", headers=second).status_code, 200)
        self.assertEqual(self.client.get(
            "/v1/me/learning/summary", headers=second,
        ).json()["saved_pathway_count"], 1)

    def test_export_and_delete_refuse_unverified_owner_fields(self):
        self.register()
        h = self.login()
        self.assertEqual(self.client.request(
            "DELETE", "/v1/me/account", headers=h, json={
                "current_password": PASSWORD,
                "confirmation": "DELETE MY ACCOUNT",
                "owner_id": "other",
            },
        ).status_code, 422)
        self.assertEqual(self.client.get("/v1/me", headers=h).status_code, 200)


class AccountLifecycleStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = open_database()
        self.store = AccountStore(self.db, clock=lambda: 4000)
        self.preferences = AccountPreferencesStore(self.db)
        self.learning = LearningStore(self.db)
        self.owner = self.store.register("owner@example.org", PASSWORD)
        self.token = self.store.login("owner@example.org", PASSWORD)["access_token"]

    def tearDown(self):
        self.db.close()

    def test_password_change_invalidates_reset_tokens(self):
        received = []
        self.store.request_password_reset(
            "owner@example.org", lambda email, token: received.append(token)
        )
        self.assertEqual(len(received), 1)
        self.assertTrue(self.store.change_password(self.token, PASSWORD, NEW_PASSWORD))
        with self.assertRaises(AuthError):
            self.store.confirm_password_reset(received[0], PASSWORD)

    def test_password_change_is_atomic_if_session_update_fails(self):
        self.db.execute("""CREATE TRIGGER fail_session_revoke BEFORE UPDATE ON auth_sessions
            BEGIN SELECT RAISE(ABORT, 'cannot revoke'); END""")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.change_password(self.token, PASSWORD, NEW_PASSWORD)
        self.assertEqual(self.store.session_owner(self.token), self.owner)
        self.store.login("owner@example.org", PASSWORD)

    def test_change_password_unicode_current_password_does_not_break(self):
        with self.assertRaises(AuthError):
            self.store.change_password(self.token, "é" * 12, NEW_PASSWORD)
        self.assertEqual(self.store.session_owner(self.token), self.owner)

    def test_session_revoke_other_owner_sessions_remain_intact(self):
        bob = self.store.register("bob@example.org", PASSWORD)
        bob_token = self.store.login("bob@example.org", PASSWORD)["access_token"]
        self.store.login("owner@example.org", PASSWORD)
        self.assertEqual(self.store.revoke_other_sessions(self.token), 1)
        self.assertEqual(self.store.session_owner(bob_token), bob)

    def test_deletion_erases_all_scoped_records_and_restores_guard(self):
        bob = self.store.register("bob@example.org", PASSWORD)
        self.preferences.update(
            self.owner, {"career_goal": "Private goal"},
            allowed_skill_ids=set(),
        )
        self.learning.save_course(self.owner, "sample-course")
        self.learning.save_course(bob, "other-course")
        pid = self.learning.save_pathway(self.owner, {
            "schema_version": "1.0.0",
            "career_goal": "Secret learning goal",
            "weekly_hours": 5,
            "generation_mode": "deterministic",
            "milestones": [{
                "order": 1, "skill_id": "html",
                "resource_ids": [], "rationale": "Begin",
            }],
        })
        self.learning.set_progress(self.owner, pid, "html", "completed")
        reset = []
        self.store.request_password_reset(
            "owner@example.org", lambda email, token: reset.append(token)
        )
        self.assertTrue(self.store.delete_account(self.token, PASSWORD))
        for table, col in (
            ("accounts", "id"), ("auth_sessions", "owner_id"),
            ("password_reset_tokens", "owner_id"),
            ("account_preferences", "owner_id"),
            ("learning_pathways", "owner_id"),
            ("milestone_progress", "owner_id"),
            ("saved_courses", "owner_id"), ("audit_events", "owner_id"),
        ):
            with self.subTest(table=table):
                self.assertEqual(self.db.execute(
                    f"SELECT count(*) FROM {table} WHERE {col}=?", (self.owner,)
                ).fetchone()[0], 0)
        self.assertEqual(self.learning.list_saved_courses(bob), ["other-course"])
        self.assertEqual(self.db.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertIsNotNone(self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='audit_events_no_delete'"
        ).fetchone())
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("DELETE FROM audit_events WHERE owner_id=?", (bob,))

    def test_deletion_rolls_back_if_account_delete_is_blocked(self):
        self.learning.save_course(self.owner, "sample-course")
        self.db.execute("""CREATE TRIGGER fail_erasure BEFORE DELETE ON accounts
            BEGIN SELECT RAISE(ABORT, 'account delete blocked'); END""")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.delete_account(self.token, PASSWORD)
        self.assertEqual(self.store.account(self.owner)["email"], "owner@example.org")
        self.assertEqual(self.learning.list_saved_courses(self.owner), ["sample-course"])
        self.assertIsNotNone(self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='audit_events_no_delete'"
        ).fetchone())
        self.assertEqual(self.store.session_owner(self.token), self.owner)

    def test_deletion_requires_current_password(self):
        self.assertRaises(AuthError, self.store.delete_account, self.token, "invalid")
        self.assertEqual(self.store.account(self.owner)["email"], "owner@example.org")

    def test_deletion_requires_current_session(self):
        self.store.revoke_session(self.token)
        with self.assertRaises(AuthError):
            self.store.delete_account(self.token, PASSWORD)

    def test_export_can_be_empty(self):
        export = self.store.export_account(self.token)
        self.assertEqual(export["pathways"], [])
        self.assertEqual(export["saved_course_ids"], [])
        self.assertEqual(export["schema_version"], "1.0.0")

    def test_export_refuses_partial_output_if_over_limit(self):
        records = [
            (self.owner, "course-" + str(i), "2026-11-01T00:00:00Z")
            for i in range(2001)
        ]
        self.db.executemany(
            "INSERT INTO saved_courses(owner_id,resource_id,created_at) VALUES(?,?,?)",
            records,
        )
        with self.assertRaises(AuthError):
            self.store.export_account(self.token)

    def test_account_deletion_does_not_reset_schema_versions(self):
        self.store.delete_account(self.token, PASSWORD)
        self.assertEqual(self.db.execute(
            "SELECT version FROM auth_meta WHERE id=1"
        ).fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT version FROM account_preferences_meta WHERE id=1"
        ).fetchone()[0], 1)

    def test_existing_file_storage_reopens_after_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lifecycle.sqlite"
            conn = open_database(path)
            try:
                accounts = AccountStore(conn)
                AccountPreferencesStore(conn)
                LearningStore(conn)
                account = accounts.register("delete@example.org", PASSWORD)
                token = accounts.login("delete@example.org", PASSWORD)["access_token"]
                self.assertTrue(accounts.delete_account(token, PASSWORD))
            finally:
                conn.close()
            self.assertEqual(inspect_database(path)["storage_schema"], 1)
            reopened = open_database(path)
            try:
                AccountStore(reopened)
                AccountPreferencesStore(reopened)
                self.assertEqual(reopened.execute(
                    "SELECT count(*) FROM accounts"
                ).fetchone()[0], 0)
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
