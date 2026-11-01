"""Learning pathway lifecycle, guest-boundary and progress projection regression tests."""
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
from nextrail_storage import LearningStore, StorageError, open_database
from nextrail_storage.workspace import WorkspaceError, build_workspace

PASSWORD = "long-learning-password123"


class LearningWorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.ctx = TestClient(create_app())
        self.client = self.ctx.__enter__()

    def tearDown(self):
        self.ctx.__exit__(None, None, None)

    def auth(self, email="learner@example.org"):
        register = self.client.post(
            "/v1/auth/register", json={"email": email, "password": PASSWORD}
        )
        self.assertEqual(register.status_code, 201)
        login = self.client.post(
            "/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        self.assertEqual(login.status_code, 200)
        return {"Authorization": "Bearer " + login.json()["access_token"]}

    def save(self, headers, *, target="css"):
        result = self.client.post(
            "/v1/me/pathways", headers=headers, json={
                "career_goal": "Frontend developer",
                "target_skill_ids": [target],
                "weekly_hours": 5,
            },
        )
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()["id"]

    def workspace(self, headers, identifier):
        return self.client.get(f"/v1/me/pathways/{identifier}/workspace", headers=headers)

    def summary(self, headers, **params):
        return self.client.get("/v1/me/learning/summary", headers=headers, params=params)

    def test_guest_pathway_preview_remains_public(self):
        self.assertEqual(self.client.get("/v1/skills").status_code, 200)
        self.assertEqual(self.client.get("/v1/courses").status_code, 200)
        response = self.client.post(
            "/v1/pathways/preview",
            json={"career_goal": "Frontend", "target_skill_ids": ["css"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["generation_mode"], "deterministic")

    def test_all_new_routes_require_authentication(self):
        self.assertEqual(self.client.get("/v1/me/learning/summary").status_code, 401)
        self.assertEqual(self.workspace({}, "unknown").status_code, 401)
        self.assertEqual(self.client.delete("/v1/me/pathways/unknown").status_code, 401)

    def test_forged_bearer_rejected(self):
        forged = {"Authorization": "Bearer forged"}
        self.assertEqual(self.summary(forged).status_code, 401)
        self.assertEqual(self.workspace(forged, "unknown").status_code, 401)
        self.assertEqual(
            self.client.delete("/v1/me/pathways/unknown", headers=forged).status_code,
            401,
        )

    def test_empty_summary(self):
        h = self.auth()
        self.assertEqual(self.summary(h).json(), {
            "items": [], "next_cursor": None,
            "saved_pathway_count": 0, "saved_course_count": 0,
        })

    def test_workspace_prerequisite_readiness(self):
        h = self.auth()
        pid = self.save(h)
        response = self.workspace(h, pid)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status_source"], "self_reported")
        self.assertFalse(data["resource_references_verified"])
        self.assertEqual(data["readiness_basis"], "current_skill_catalog")
        self.assertEqual([m["skill_id"] for m in data["milestones"]], ["html", "css"])
        self.assertEqual(data["milestones"][0]["readiness"], "ready")
        self.assertEqual(data["milestones"][1]["readiness"], "blocked")
        self.assertEqual(data["milestones"][1]["blocking_skill_ids"], ["html"])
        self.assertEqual(data["next_ready_skill_id"], "html")
        self.assertEqual(data["completion_percent"], 0)
        self.assertEqual(data["total"], 2)
        self.assertFalse(data["all_completed"])

    def test_completed_prerequisite_unblocks_next_step(self):
        h = self.auth()
        pid = self.save(h)
        change = self.client.put(
            f"/v1/me/pathways/{pid}/progress/html",
            headers=h, json={"status": "completed"},
        )
        self.assertEqual(change.status_code, 200)
        state = self.workspace(h, pid).json()
        self.assertEqual(state["completed"], 1)
        self.assertEqual(state["completion_percent"], 50)
        self.assertEqual(state["milestones"][0]["readiness"], "completed")
        self.assertEqual(state["milestones"][1]["readiness"], "ready")
        self.assertEqual(state["next_ready_skill_id"], "css")

    def test_in_progress_is_distinct_from_completed(self):
        h = self.auth()
        pid = self.save(h)
        self.assertEqual(self.client.put(
            f"/v1/me/pathways/{pid}/progress/html",
            headers=h, json={"status": "in_progress"},
        ).status_code, 200)
        state = self.workspace(h, pid).json()
        self.assertEqual(state["in_progress"], 1)
        self.assertEqual(state["completed"], 0)
        self.assertEqual(state["not_started"], 1)
        self.assertEqual(state["completion_percent"], 0)
        self.assertEqual(state["milestones"][1]["readiness"], "blocked")

    def test_every_milestone_completed(self):
        h = self.auth()
        pid = self.save(h)
        for skill in ("html", "css"):
            self.client.put(
                f"/v1/me/pathways/{pid}/progress/{skill}",
                headers=h, json={"status": "completed"},
            )
        state = self.workspace(h, pid).json()
        self.assertEqual(state["completion_percent"], 100)
        self.assertTrue(state["all_completed"])
        self.assertIsNone(state["next_ready_skill_id"])

    def test_progress_reset_reblocks_dependent_step(self):
        h = self.auth()
        pid = self.save(h)
        self.client.put(
            f"/v1/me/pathways/{pid}/progress/html",
            headers=h, json={"status": "completed"},
        )
        self.client.put(
            f"/v1/me/pathways/{pid}/progress/html",
            headers=h, json={"status": "not_started"},
        )
        self.assertEqual(
            self.workspace(h, pid).json()["milestones"][1]["readiness"], "blocked"
        )

    def test_existing_pathway_and_progress_responses_unchanged(self):
        h = self.auth()
        pid = self.save(h)
        saved = self.client.get(f"/v1/me/pathways/{pid}", headers=h)
        progress = self.client.get(f"/v1/me/pathways/{pid}/progress", headers=h)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(saved.json()["schema_version"], "1.0.0")
        self.assertEqual(progress.json()["total"], 2)
        self.assertEqual(progress.json()["pathway_id"], pid)

    def test_summary_has_stable_completion_counts(self):
        h = self.auth()
        pid = self.save(h)
        self.client.put(
            f"/v1/me/pathways/{pid}/progress/html",
            headers=h, json={"status": "completed"},
        )
        response = self.summary(h)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["saved_pathway_count"], 1)
        self.assertEqual(data["saved_course_count"], 0)
        self.assertEqual(data["items"][0]["id"], pid)
        self.assertEqual(data["items"][0]["completed"], 1)
        self.assertEqual(data["items"][0]["total"], 2)
        self.assertEqual(data["items"][0]["completion_percent"], 50)
        self.assertIsNone(data["next_cursor"])

    def test_summary_counts_bookmarks_without_disclosing_them(self):
        h = self.auth()
        self.client.put("/v1/me/courses/example-html-course", headers=h)
        # The sample resource is synthetic and cannot be publicly bookmarked.
        self.assertEqual(self.summary(h).json()["saved_course_count"], 0)

    def test_page_cursor_does_not_duplicate_items(self):
        h = self.auth()
        keys = [self.save(h) for _ in range(5)]
        seen = []
        cursor = None
        while True:
            params = {"limit": 2}
            if cursor:
                params["after_id"] = cursor
            r = self.summary(h, **params)
            self.assertEqual(r.status_code, 200, r.text)
            obj = r.json()
            seen.extend(item["id"] for item in obj["items"])
            self.assertEqual(obj["saved_pathway_count"], 5)
            cursor = obj["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(seen), 5)
        self.assertEqual(set(seen), set(keys))

    def test_page_boundary_invalid_limit(self):
        h = self.auth()
        for number in (0, 51, -1):
            self.assertEqual(self.summary(h, limit=number).status_code, 422)

    def test_unknown_cursor_returns_404(self):
        h = self.auth()
        self.assertEqual(self.summary(h, after_id="not-a-saved-pathway").status_code, 404)

    def test_cross_account_cursor_hidden(self):
        alice = self.auth("alice@example.org")
        bob = self.auth("bob@example.org")
        pid = self.save(alice)
        self.assertEqual(self.summary(bob, after_id=pid).status_code, 404)
        self.assertEqual(self.summary(bob).json()["items"], [])

    def test_cross_account_workspace_hidden(self):
        alice = self.auth("alice@example.org")
        bob = self.auth("bob@example.org")
        pid = self.save(alice)
        self.assertEqual(self.workspace(bob, pid).status_code, 404)

    def test_cross_account_deletion_denied(self):
        alice = self.auth("alice@example.org")
        bob = self.auth("bob@example.org")
        pid = self.save(alice)
        self.assertEqual(
            self.client.delete(f"/v1/me/pathways/{pid}", headers=bob).status_code,
            404,
        )
        self.assertEqual(self.workspace(alice, pid).status_code, 200)

    def test_delete_pathway_cascades_progress_and_updates_summary(self):
        h = self.auth()
        pid = self.save(h)
        self.client.put(
            f"/v1/me/pathways/{pid}/progress/html",
            headers=h, json={"status": "completed"},
        )
        removed = self.client.delete(f"/v1/me/pathways/{pid}", headers=h)
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json(), {"deleted": True})
        self.assertEqual(self.workspace(h, pid).status_code, 404)
        self.assertEqual(self.client.get(
            f"/v1/me/pathways/{pid}/progress", headers=h
        ).status_code, 404)
        self.assertEqual(self.summary(h).json()["saved_pathway_count"], 0)
        events = self.client.get("/v1/me/audit", headers=h).json()["events"]
        self.assertEqual(events[-1]["operation"], "deleted")
        self.assertEqual(events[-1]["entity_id"], pid)
        self.assertEqual(events[-1]["detail"], {"milestone_count": 2})
        self.assertNotIn("Frontend developer", json.dumps(events))

    def test_deleting_twice_returns_404(self):
        h = self.auth()
        pid = self.save(h)
        self.assertEqual(self.client.delete(f"/v1/me/pathways/{pid}", headers=h).status_code, 200)
        self.assertEqual(self.client.delete(f"/v1/me/pathways/{pid}", headers=h).status_code, 404)

    def test_delete_does_not_touch_other_saved_pathways(self):
        h = self.auth()
        first = self.save(h, target="css")
        second = self.save(h, target="javascript")
        self.client.delete(f"/v1/me/pathways/{first}", headers=h)
        summary = self.summary(h).json()
        self.assertEqual(summary["saved_pathway_count"], 1)
        self.assertEqual(summary["items"][0]["id"], second)

    def test_logout_revokes_new_route_access(self):
        h = self.auth()
        pid = self.save(h)
        self.assertEqual(self.client.post("/v1/auth/logout", headers=h).status_code, 200)
        self.assertEqual(self.workspace(h, pid).status_code, 401)
        self.assertEqual(self.summary(h).status_code, 401)


class LearningWorkspaceStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = open_database()
        self.store = LearningStore(self.conn)
        self.pathway = {
            "schema_version": "1.0.0",
            "career_goal": "Private skill goal",
            "weekly_hours": 6,
            "generation_mode": "deterministic",
            "milestones": [
                {"order": 1, "skill_id": "html", "resource_ids": [],
                 "rationale": "Learn HTML"},
                {"order": 2, "skill_id": "css", "resource_ids": [],
                 "rationale": "Learn CSS"},
            ],
        }
        self.catalog = json.loads((ROOT / "data/catalog.sample.json").read_text())
        self.owner = "account_one"

    def tearDown(self):
        self.conn.close()

    def save(self, pathway=None):
        return self.store.save_pathway(self.owner, self.pathway if pathway is None else pathway)

    def test_page_limit_rejects_boolean_and_excessive_number(self):
        for limit in (True, 0, 51, -3):
            with self.subTest(limit=limit), self.assertRaises(StorageError):
                self.store.list_pathway_page(self.owner, limit=limit)

    def test_page_cursor_rejects_invalid_values(self):
        for value in ("", 12, "x" * 65):
            with self.subTest(cursor=value), self.assertRaises(StorageError):
                self.store.list_pathway_page(self.owner, after_id=value)

    def test_missing_cursor_does_not_disclose_other_owner(self):
        pid = self.save()
        with self.assertRaises(KeyError):
            self.store.list_pathway_page("account_two", after_id=pid)

    def test_storage_delete_progress_and_pathway_atomic(self):
        pid = self.save()
        self.store.set_progress(self.owner, pid, "html", "completed")
        self.assertTrue(self.store.delete_pathway(self.owner, pid))
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM milestone_progress WHERE pathway_id=?", (pid,)
        ).fetchone()[0], 0)
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM learning_pathways WHERE id=?", (pid,)
        ).fetchone()[0], 0)

    def test_storage_delete_rolls_back_if_audit_fails(self):
        pid = self.save()
        self.store.set_progress(self.owner, pid, "html", "completed")
        self.conn.execute("""CREATE TRIGGER reject_route_deletion_audit
            BEFORE INSERT ON audit_events
            WHEN NEW.operation='deleted'
            BEGIN SELECT RAISE(ABORT, 'audit blocked'); END""")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.delete_pathway(self.owner, pid)
        self.assertEqual(self.store.get_pathway(self.owner, pid), self.pathway)
        self.assertEqual(self.store.get_progress(self.owner, pid)["completed"], 1)

    def test_delete_never_affects_other_owner(self):
        pid = self.save()
        with self.assertRaises(KeyError):
            self.store.delete_pathway("account_two", pid)
        self.assertEqual(self.store.get_pathway(self.owner, pid), self.pathway)

    def test_workspace_does_not_modify_saved_snapshot(self):
        pid = self.save()
        before = self.store.get_pathway(self.owner, pid)
        workspace = build_workspace(
            pid, before, self.store.get_progress(self.owner, pid), self.catalog
        )
        self.assertEqual(self.store.get_pathway(self.owner, pid), before)
        self.assertEqual(workspace["milestones"][1]["blocking_skill_ids"], ["html"])

    def test_untracked_prior_knowledge_is_not_claimed_completed(self):
        partial = dict(self.pathway)
        partial["milestones"] = [{
            "order": 1, "skill_id": "css", "resource_ids": [],
            "rationale": "HTML was studied previously",
        }]
        pid = self.save(partial)
        projected = build_workspace(
            pid, self.store.get_pathway(self.owner, pid),
            self.store.get_progress(self.owner, pid), self.catalog,
        )
        self.assertEqual(projected["milestones"][0]["readiness"], "prior_knowledge_unconfirmed")
        self.assertEqual(projected["milestones"][0]["untracked_prerequisite_skill_ids"], ["html"])
        self.assertIsNone(projected["next_ready_skill_id"])

    def test_missing_current_catalog_skill_is_not_invented(self):
        pid = self.save()
        catalog = dict(self.catalog)
        catalog["skills"] = [
            x for x in self.catalog["skills"] if x["id"] != "css"
        ]
        projected = build_workspace(
            pid, self.store.get_pathway(self.owner, pid),
            self.store.get_progress(self.owner, pid), catalog,
        )
        self.assertEqual(projected["milestones"][1]["readiness"], "catalog_skill_missing")
        self.assertIsNone(projected["milestones"][1]["skill_name"])

    def test_zero_milestone_pathway_is_safe(self):
        blank = dict(self.pathway)
        blank["milestones"] = []
        pid = self.save(blank)
        projected = build_workspace(
            pid, self.store.get_pathway(self.owner, pid),
            self.store.get_progress(self.owner, pid), self.catalog,
        )
        self.assertEqual(projected["total"], 0)
        self.assertEqual(projected["completion_percent"], 0)
        self.assertFalse(projected["all_completed"])

    def test_mismatched_progress_rejected(self):
        pid = self.save()
        progress = self.store.get_progress(self.owner, pid)
        progress["milestones"].pop()
        with self.assertRaises(WorkspaceError):
            build_workspace(pid, self.pathway, progress, self.catalog)

    def test_unknown_progress_status_rejected(self):
        pid = self.save()
        progress = self.store.get_progress(self.owner, pid)
        progress["milestones"][0]["status"] = "certified"
        with self.assertRaises(WorkspaceError):
            build_workspace(pid, self.pathway, progress, self.catalog)

    def test_duplicate_catalog_skill_rejected(self):
        pid = self.save()
        catalog = dict(self.catalog)
        catalog["skills"] = self.catalog["skills"] + [self.catalog["skills"][0]]
        with self.assertRaises(WorkspaceError):
            build_workspace(
                pid, self.pathway, self.store.get_progress(self.owner, pid), catalog
            )

    def test_saved_progress_survives_database_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "learning.sqlite"
            first = open_database(path)
            try:
                owner = "account_durable"
                store = LearningStore(first)
                pid = store.save_pathway(owner, self.pathway)
                store.set_progress(owner, pid, "html", "completed")
            finally:
                first.close()
            restored = open_database(path)
            try:
                store = LearningStore(restored)
                page = store.list_pathway_page(owner)
                self.assertEqual(page["items"][0]["completion_percent"], 50)
                self.assertEqual(store.get_progress(owner, pid)["completed"], 1)
            finally:
                restored.close()


if __name__ == "__main__":
    unittest.main()
