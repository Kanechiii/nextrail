"""Authenticated account onboarding and overview API regression coverage."""
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


class AccountModeApiTests(unittest.TestCase):
    def setUp(self):
        self.ctx = TestClient(create_app())
        self.client = self.ctx.__enter__()
        self.password = "valid-long-password123"

    def tearDown(self):
        self.ctx.__exit__(None, None, None)

    def login(self, email):
        created = self.client.post(
            "/v1/auth/register", json={"email": email, "password": self.password}
        )
        self.assertEqual(created.status_code, 201)
        response = self.client.post(
            "/v1/auth/login", json={"email": email, "password": self.password}
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def test_guest_discovery_stays_public(self):
        self.assertEqual(self.client.get("/v1/courses").status_code, 200)

    def test_guest_pathway_stays_public(self):
        result = self.client.post(
            "/v1/pathways/preview",
            json={"career_goal": "Frontend", "target_skill_ids": ["css"]},
        )
        self.assertEqual(result.status_code, 200)

    def test_private_preferences_require_token(self):
        self.assertEqual(self.client.get("/v1/me/preferences").status_code, 401)
        self.assertEqual(
            self.client.patch("/v1/me/preferences", json={"weekly_hours": 8}).status_code,
            401,
        )

    def test_private_overview_requires_token(self):
        self.assertEqual(self.client.get("/v1/me/overview").status_code, 401)

    def test_defaults_without_onboarding(self):
        headers = self.login("first@example.org")
        data = self.client.get("/v1/me/preferences", headers=headers).json()
        self.assertEqual(data["weekly_hours"], 5)
        self.assertFalse(data["onboarding_completed"])
        self.assertEqual(data["target_skill_ids"], [])

    def test_onboarding_uses_catalog_skills(self):
        headers = self.login("first@example.org")
        data = self.client.patch(
            "/v1/me/preferences", headers=headers,
            json={
                "display_name": "Learner",
                "career_goal": "Frontend developer",
                "target_skill_ids": ["html", "css"],
                "known_skill_ids": ["html"],
                "weekly_hours": 8,
            },
        )
        self.assertEqual(data.status_code, 200)
        self.assertTrue(data.json()["onboarding_completed"])
        self.assertEqual(data.json()["weekly_hours"], 8)

    def test_invalid_skill_rejected(self):
        headers = self.login("first@example.org")
        result = self.client.patch(
            "/v1/me/preferences", headers=headers, json={"target_skill_ids": ["fake"]}
        )
        self.assertEqual(result.status_code, 422)

    def test_duplicate_skill_rejected(self):
        headers = self.login("first@example.org")
        result = self.client.patch(
            "/v1/me/preferences", headers=headers, json={"known_skill_ids": ["html", "html"]}
        )
        self.assertEqual(result.status_code, 422)

    def test_unknown_fields_rejected(self):
        headers = self.login("first@example.org")
        result = self.client.patch(
            "/v1/me/preferences", headers=headers,
            json={"owner_id": "other-user", "weekly_hours": 20},
        )
        self.assertEqual(result.status_code, 422)

    def test_empty_patch_rejected(self):
        headers = self.login("first@example.org")
        self.assertEqual(
            self.client.patch("/v1/me/preferences", headers=headers, json={}).status_code,
            422,
        )

    def test_invalid_hours_rejected(self):
        headers = self.login("first@example.org")
        self.assertEqual(
            self.client.patch(
                "/v1/me/preferences", headers=headers, json={"weekly_hours": 90}
            ).status_code, 422
        )

    def test_cross_account_isolation(self):
        first = self.login("first@example.org")
        second = self.login("second@example.org")
        self.client.patch(
            "/v1/me/preferences", headers=first,
            json={"display_name": "First account"},
        )
        self.assertEqual(
            self.client.get("/v1/me/preferences", headers=second).json()["display_name"], ""
        )
        self.assertEqual(
            self.client.get("/v1/me/preferences", headers=first).json()["display_name"],
            "First account",
        )

    def test_private_audit_omits_goal_details(self):
        headers = self.login("first@example.org")
        self.client.patch(
            "/v1/me/preferences", headers=headers,
            json={"career_goal": "A private learning goal"},
        )
        events = self.client.get("/v1/me/audit", headers=headers)
        self.assertEqual(events.status_code, 200)
        serialized = json.dumps(events.json())
        self.assertNotIn("A private learning goal", serialized)
        self.assertIn("changed_fields", serialized)

    def test_overview_uses_actual_saved_pathways(self):
        headers = self.login("first@example.org")
        zero = self.client.get("/v1/me/overview", headers=headers).json()
        self.assertEqual(zero["saved_pathway_count"], 0)
        self.assertEqual(zero["saved_course_count"], 0)
        self.assertIsNone(zero["latest_pathway_id"])
        saved = self.client.post(
            "/v1/me/pathways", headers=headers,
            json={"career_goal": "Frontend", "target_skill_ids": ["css"]},
        )
        self.assertEqual(saved.status_code, 201)
        key = saved.json()["id"]
        self.assertEqual(self.client.put(
            f"/v1/me/pathways/{key}/progress/html", headers=headers,
            json={"status": "completed"},
        ).status_code, 200)
        result = self.client.get("/v1/me/overview", headers=headers).json()
        self.assertEqual(result["saved_pathway_count"], 1)
        self.assertEqual(result["latest_pathway_id"], key)
        self.assertEqual(result["completed_milestones"], 1)
        self.assertEqual(result["total_milestones"], 2)

    def test_overview_does_not_count_other_users_data(self):
        first = self.login("first@example.org")
        second = self.login("second@example.org")
        self.client.post(
            "/v1/me/pathways", headers=first,
            json={"career_goal": "Frontend", "target_skill_ids": ["css"]},
        )
        summary = self.client.get("/v1/me/overview", headers=second).json()
        self.assertEqual(summary["saved_pathway_count"], 0)

    def test_rejects_invalid_bearer(self):
        self.assertEqual(
            self.client.get(
                "/v1/me/preferences", headers={"Authorization": "Bearer invalid"}
            ).status_code, 401
        )


class AccountPreferencesDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = open_database()
        self.auth = AccountStore(self.conn)
        self.owner = self.auth.register("stored@example.org", "valid-long-password123")
        self.prefs = AccountPreferencesStore(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_storage_schema_versions_unchanged(self):
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(
            self.conn.execute("SELECT version FROM auth_meta WHERE id=1").fetchone()[0], 1
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT version FROM account_preferences_meta WHERE id=1"
            ).fetchone()[0], 1,
        )

    def test_idempotent_preferences_schema(self):
        AccountPreferencesStore(self.conn)
        AccountPreferencesStore(self.conn)

    def test_unsupported_schema_version_rejected(self):
        self.conn.execute("UPDATE account_preferences_meta SET version=12")
        with self.assertRaises(AuthError):
            AccountPreferencesStore(self.conn)

    def test_incomplete_schema_rejected(self):
        self.conn.execute("DROP TABLE account_preferences")
        with self.assertRaises(AuthError):
            AccountPreferencesStore(self.conn)

    def test_profile_update_is_idempotent(self):
        self.prefs.update(self.owner, {"display_name": "Student"}, allowed_skill_ids=set())
        before = self.conn.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        self.prefs.update(self.owner, {"display_name": "Student"}, allowed_skill_ids=set())
        after = self.conn.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        self.assertEqual(before, after)

    def test_failed_audit_rolls_back_preferences(self):
        self.conn.execute("""CREATE TRIGGER fail_profile_audit BEFORE INSERT ON audit_events
            BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END""")
        with self.assertRaises(sqlite3.DatabaseError):
            self.prefs.update(
                self.owner, {"display_name": "Private"}, allowed_skill_ids=set()
            )
        self.assertEqual(self.prefs.get(self.owner)["display_name"], "")

    def test_preferences_persist_after_reopening_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "account.sqlite"
            conn = open_database(path)
            auth = AccountStore(conn)
            owner = auth.register("reopen@example.org", "valid-long-password123")
            store = AccountPreferencesStore(conn)
            store.update(
                owner, {"career_goal": "Web developer", "target_skill_ids": ["html"]},
                allowed_skill_ids={"html"},
            )
            conn.close()
            second = open_database(path)
            try:
                AccountStore(second)
                restored = AccountPreferencesStore(second).get(owner)
                self.assertEqual(restored["career_goal"], "Web developer")
                self.assertTrue(restored["onboarding_completed"])
            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
