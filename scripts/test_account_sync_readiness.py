"""Account preference revisions and read-only sync readiness across DB connections."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api import create_app

PASSWORD = "synthetic-development-password-123"
PLAN = {
    "career_goal": "Frontend Developer",
    "target_skill_ids": ["css"],
    "known_skill_ids": [],
    "weekly_hours": 6,
    "zero_budget": True,
}


def register_and_login(client, username):
    email = username + "@example.org"
    result = client.post(
        "/v1/auth/register", json={"email": email, "password": PASSWORD},
    )
    assert result.status_code == 201, result.text
    return login(client, username)


def login(client, username):
    response = client.post(
        "/v1/auth/login",
        json={"email": username + "@example.org", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


class AccountSyncReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "single-authoritative.sqlite")
        first = TestClient(create_app(database_path=self.db))
        second = TestClient(create_app(database_path=self.db))
        self.first = first.__enter__()
        self.addCleanup(first.__exit__, None, None, None)
        self.second = second.__enter__()
        self.addCleanup(second.__exit__, None, None, None)
        self.a = register_and_login(self.first, "sample")
        self.b = login(self.second, "sample")

    def get_preferences(self, client=None, headers=None):
        return (client or self.first).get(
            "/v1/me/preferences", headers=headers or self.a
        )

    def patch(self, changes, *, client=None, headers=None, revision=None):
        h = dict(headers or self.a)
        if revision is not None:
            h["If-Match"] = '"' + revision + '"'
        return (client or self.first).patch(
            "/v1/me/preferences", json=changes, headers=h,
        )

    def sync(self, client=None, headers=None):
        return (client or self.first).get(
            "/v1/me/sync/status", headers=headers or self.a,
        )

    def test_preferences_get_etag_is_opaque_scoped_and_no_store(self):
        first = self.get_preferences()
        second = self.get_preferences(self.second, self.b)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.headers["etag"], second.headers["etag"])
        self.assertRegex(first.headers["etag"], r'^"[0-9a-f]{64}"$')
        self.assertEqual(first.headers["cache-control"], "no-store")
        self.assertNotIn("sample@", first.headers["etag"])

    def test_two_sessions_conflict_with_no_silent_overwrite(self):
        base = self.get_preferences().headers["etag"][1:-1]
        self.assertEqual(
            self.get_preferences(self.second, self.b).headers["etag"][1:-1], base
        )
        first = self.patch(
            {"career_goal": "First confirmed goal"}, revision=base,
        )
        self.assertEqual(first.status_code, 200, first.text)
        revised = first.headers["etag"][1:-1]
        self.assertNotEqual(base, revised)
        before = self.first.get("/v1/me/audit", headers=self.a).json()
        stale = self.patch(
            {"career_goal": "Stale device overwrites goal"}, client=self.second,
            headers=self.b, revision=base,
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertIn("Reload", stale.json()["detail"])
        self.assertEqual(self.first.get(
            "/v1/me/audit", headers=self.a,
        ).json(), before)
        self.assertEqual(self.get_preferences().json()["career_goal"],
                         "First confirmed goal")
        fresh = self.get_preferences(self.second, self.b).headers["etag"][1:-1]
        self.assertEqual(fresh, revised)
        updated = self.patch(
            {"career_goal": "Second confirmed goal"}, client=self.second,
            headers=self.b, revision=fresh,
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(self.get_preferences().json()["career_goal"],
                         "Second confirmed goal")

    def test_same_second_updates_increment_revision_and_noop_does_not(self):
        base = self.get_preferences().headers["etag"][1:-1]
        first = self.patch({"display_name": "Student"}, revision=base)
        self.assertEqual(first.status_code, 200)
        version1 = first.headers["etag"][1:-1]
        noop = self.patch({"display_name": "Student"}, revision=version1)
        self.assertEqual(noop.status_code, 200)
        self.assertEqual(noop.headers["etag"][1:-1], version1)
        second = self.patch({"display_name": "Learner"}, revision=version1)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(second.headers["etag"], first.headers["etag"])

    def test_invalid_revision_is_rejected_without_write(self):
        before = self.get_preferences().headers["etag"]
        for invalid in ("invalid", '"0"', '"z" * 64', "*", 'W/"' + '0' * 64 + '"'):
            with self.subTest(value=invalid):
                result = self.first.patch(
                    "/v1/me/preferences",
                    headers={**self.a, "If-Match": invalid},
                    json={"weekly_hours": 9},
                )
                self.assertIn(result.status_code, (400, 422))
        self.assertEqual(self.get_preferences().headers["etag"], before)
        self.assertEqual(self.get_preferences().json()["weekly_hours"], 5)

    def test_legacy_preferences_patch_remains_compatible(self):
        response = self.patch({"weekly_hours": 8})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["weekly_hours"], 8)
        self.assertRegex(response.headers["etag"], r'^"[0-9a-f]{64}"$')

    def test_sync_readiness_is_account_scoped_and_read_only(self):
        first = self.sync()
        self.assertEqual(first.status_code, 200, first.text)
        report = first.json()
        self.assertEqual(report["schema_version"], "1.0.0")
        self.assertEqual(report["persistence"], "local_sqlite")
        self.assertTrue(report["shared_backend_required"])
        self.assertFalse(report["hosted_cross_device_sync_configured"])
        self.assertFalse(report["automatic_merge_enabled"])
        self.assertEqual(report["saved_pathway_count"], 0)
        self.assertEqual(report["saved_course_count"], 0)
        self.assertEqual(report["completion_source"], "self_reported")
        self.assertEqual(report["remote_requests_performed"], 0)
        self.assertEqual(first.headers["etag"], '"' + report["state_revision"] + '"')
        self.assertEqual(first.headers["cache-control"], "no-store")
        self.assertEqual(self.sync(self.second, self.b).json(), report)
        self.assertNotIn("sample@", first.text)
        self.assertNotIn("access_token", first.text)
        self.assertNotIn(PASSWORD, first.text)
        self.assertEqual(self.sync().json(), report)

    def test_account_revision_tracks_preferences_and_pathway_progress(self):
        original = self.sync().json()["state_revision"]
        self.assertEqual(self.patch({"weekly_hours": 12}).status_code, 200)
        after_preferences = self.sync(self.second, self.b).json()["state_revision"]
        self.assertNotEqual(original, after_preferences)
        created = self.second.post(
            "/v1/me/pathways", headers=self.b, json=PLAN,
        )
        self.assertEqual(created.status_code, 201, created.text)
        path = created.json()["id"]
        after_save = self.sync().json()
        self.assertNotEqual(after_preferences, after_save["state_revision"])
        self.assertEqual(after_save["saved_pathway_count"], 1)
        progress = self.first.put(
            f"/v1/me/pathways/{path}/progress/html",
            headers=self.a, json={"status": "completed"},
        )
        self.assertEqual(progress.status_code, 200, progress.text)
        after_progress = self.sync(self.second, self.b).json()["state_revision"]
        self.assertNotEqual(after_progress, after_save["state_revision"])
        deleted = self.first.delete(
            f"/v1/me/pathways/{path}", headers=self.a,
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        final = self.sync(self.second, self.b).json()
        self.assertNotEqual(final["state_revision"], after_progress)
        self.assertEqual(final["saved_pathway_count"], 0)

    def test_cross_account_revision_and_data_are_isolated(self):
        other = register_and_login(self.second, "different")
        owner = self.sync().json()
        second = self.sync(self.second, other).json()
        self.assertNotEqual(owner["state_revision"], second["state_revision"])
        self.assertNotEqual(
            self.get_preferences().headers["etag"],
            self.get_preferences(self.second, other).headers["etag"],
        )
        self.patch({"career_goal": "Private career goal"})
        self.assertEqual(self.sync(self.second, other).json(), second)
        self.assertEqual(
            self.get_preferences(self.second, other).json()["career_goal"], ""
        )

    def test_revoked_session_and_guests_cannot_read_sync_status(self):
        self.assertEqual(self.first.get("/v1/me/sync/status").status_code, 401)
        invalid = self.first.get(
            "/v1/me/sync/status",
            headers={"Authorization": "Bearer invalid"},
        )
        self.assertEqual(invalid.status_code, 401)
        revoked = self.first.post("/v1/me/sessions/revoke-others", headers=self.a)
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(self.sync(self.second, self.b).status_code, 401)
        self.assertEqual(self.get_preferences(self.second, self.b).status_code, 401)
        self.assertEqual(self.sync().status_code, 200)

    def test_no_schema_migration_or_external_data_transfer(self):
        report = self.sync().json()
        self.assertNotIn("resources", report)
        self.assertNotIn("preferences", report)
        self.assertNotIn("email", report)
        self.assertNotIn("tokens", report)
        self.assertNotIn("hosted_url", report)


if __name__ == "__main__":
    unittest.main()
