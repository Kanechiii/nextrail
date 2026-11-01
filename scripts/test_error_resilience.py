"""Offline error-resilience contract and durable save-replay regression tests."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
from nextrail_api import create_app

PLAN = {"career_goal": "Frontend developer", "target_skill_ids": ["css"],
        "known_skill_ids": [], "weekly_hours": 6, "zero_budget": True}
PASSWORD = "synthetic-demo-password-1234"


class ApiErrorResilienceTests(unittest.TestCase):
    def setUp(self):
        self.ctx = TestClient(create_app())
        self.client = self.ctx.__enter__()
        self.addCleanup(self.ctx.__exit__, None, None, None)

    def owner(self, label="owner"):
        address = label + "@example.org"
        self.assertEqual(self.client.post("/v1/auth/register", json={
            "email": address, "password": PASSWORD,
        }).status_code, 201)
        logged = self.client.post("/v1/auth/login", json={
            "email": address, "password": PASSWORD,
        })
        self.assertEqual(logged.status_code, 200)
        return {"Authorization": "Bearer " + logged.json()["access_token"]}

    def assert_database_outage(self, response):
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"],
                         {"code": "DATABASE_UNAVAILABLE", "retryable": True})
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["retry-after"], "3")
        self.assertNotIn("private.sqlite", response.text)
        self.assertNotIn("private@example.org", response.text)

    def test_database_failure_does_not_masquerade_as_invalid_session(self):
        token = self.owner()
        self.client.app.state.db.close()
        self.assert_database_outage(self.client.get("/v1/me", headers=token))
        self.assert_database_outage(self.client.post("/v1/auth/login", json={
            "email": "private@example.org", "password": PASSWORD,
        }))

    def test_preferences_read_and_write_database_failure_are_503(self):
        token = self.owner()
        class BrokenPreferences:
            def get(self, owner):
                raise sqlite3.OperationalError("secret private.sqlite is locked")
            def update(self, *args, **kwargs):
                raise sqlite3.OperationalError("private@example.org")
        self.client.app.state.preferences = BrokenPreferences()
        self.assert_database_outage(self.client.get("/v1/me/preferences", headers=token))
        self.assert_database_outage(self.client.patch("/v1/me/preferences",
            headers=token, json={"display_name": "New name"}))

    def test_progress_and_pathway_store_failures_are_retryable_503(self):
        token = self.owner()
        class BrokenLearning:
            def get_progress(self, owner, identifier):
                raise sqlite3.OperationalError("private.sqlite failure")
            def save_pathway(self, *args, **kwargs):
                raise sqlite3.OperationalError("private.sqlite failure")
            def idempotent_pathway(self, *args, **kwargs):
                raise sqlite3.OperationalError("private.sqlite failure")
        self.client.app.state.learning = BrokenLearning()
        self.assert_database_outage(self.client.get("/v1/me/pathways/any/progress", headers=token))
        self.assert_database_outage(self.client.post("/v1/me/pathways", json=PLAN, headers=token))

    def test_401_422_404_and_429_remain_distinct(self):
        self.assertEqual(self.client.get("/v1/me").status_code, 401)
        self.assertEqual(self.client.post("/v1/pathways/preview", json={
            **PLAN, "weekly_hours": 200,
        }).status_code, 422)
        token = self.owner()
        self.assertEqual(self.client.get("/v1/me/pathways/nonexistent", headers=token).status_code, 404)
        for _ in range(30):
            self.assertEqual(self.client.post("/v1/pathways/preview", json=PLAN).status_code, 200)
        rejected = self.client.post("/v1/pathways/preview", json=PLAN)
        self.assertEqual(rejected.status_code, 429)
        self.assertIn("retry-after", rejected.headers)

    def test_same_key_replays_one_pathway_and_one_creation_audit(self):
        token = self.owner()
        headers = {**token, "Idempotency-Key": str(uuid4())}
        first = self.client.post("/v1/me/pathways", json=PLAN, headers=headers)
        again = self.client.post("/v1/me/pathways", json=PLAN, headers=headers)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(again.status_code, 201, again.text)
        self.assertEqual(first.json(), again.json())
        self.assertEqual(len(self.client.get("/v1/me/pathways", headers=token).json()["items"]), 1)
        events = self.client.get("/v1/me/audit", headers=token).json()["events"]
        self.assertEqual(sum(e["entity_type"] == "pathway" and
                             e["operation"] == "created" for e in events), 1)

    def test_conflicting_key_returns_409_without_any_new_route(self):
        token = self.owner()
        headers = {**token, "Idempotency-Key": str(uuid4())}
        self.assertEqual(self.client.post("/v1/me/pathways", json=PLAN, headers=headers).status_code, 201)
        conflict = self.client.post("/v1/me/pathways", json={
            **PLAN, "weekly_hours": 12,
        }, headers=headers)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(len(self.client.get("/v1/me/pathways", headers=token).json()["items"]), 1)

    def test_invalid_key_422_and_legacy_requests_still_save(self):
        token = self.owner()
        for key in ("", "bad", "1234567890"):
            self.assertEqual(self.client.post("/v1/me/pathways",
                json=PLAN, headers={**token, "Idempotency-Key": key}).status_code, 422)
        a = self.client.post("/v1/me/pathways", json=PLAN, headers=token)
        b = self.client.post("/v1/me/pathways", json=PLAN, headers=token)
        self.assertEqual(a.status_code, 201)
        self.assertEqual(b.status_code, 201)
        self.assertNotEqual(a.json()["id"], b.json()["id"])

    def test_reused_key_is_isolated_per_account(self):
        first = self.owner("alpha")
        second = self.owner("beta")
        key = str(uuid4())
        a = self.client.post("/v1/me/pathways", json=PLAN,
            headers={**first, "Idempotency-Key": key})
        b = self.client.post("/v1/me/pathways", json=PLAN,
            headers={**second, "Idempotency-Key": key})
        self.assertEqual(a.status_code, 201)
        self.assertEqual(b.status_code, 201)
        self.assertNotEqual(a.json()["id"], b.json()["id"])

    def test_audit_failure_rolls_back_pathway_and_idempotency_ledger(self):
        token = self.owner()
        key = str(uuid4())
        self.client.app.state.db.execute(
            "CREATE TRIGGER block_creation BEFORE INSERT ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'private.sqlite blocked'); END"
        )
        response = self.client.post("/v1/me/pathways", json=PLAN,
            headers={**token, "Idempotency-Key": key})
        self.assert_database_outage(response)
        self.assertEqual(self.client.app.state.db.execute(
            "SELECT COUNT(*) FROM pathway_idempotency").fetchone()[0], 0)
        self.assertEqual(self.client.app.state.db.execute(
            "SELECT COUNT(*) FROM learning_pathways").fetchone()[0], 0)
        self.client.app.state.db.execute("DROP TRIGGER block_creation")
        retry = self.client.post("/v1/me/pathways", json=PLAN,
            headers={**token, "Idempotency-Key": key})
        self.assertEqual(retry.status_code, 201, retry.text)
        self.assertEqual(len(self.client.get("/v1/me/pathways", headers=token).json()["items"]), 1)

    def test_delete_cascades_key_record_without_leaving_stale_replays(self):
        token = self.owner()
        headers = {**token, "Idempotency-Key": str(uuid4())}
        first = self.client.post("/v1/me/pathways", json=PLAN, headers=headers)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.client.delete(
            "/v1/me/pathways/" + first.json()["id"], headers=token).status_code, 200)
        next_save = self.client.post("/v1/me/pathways", json=PLAN, headers=headers)
        self.assertEqual(next_save.status_code, 201, next_save.text)
        self.assertNotEqual(next_save.json()["id"], first.json()["id"])


class DurableReplayTests(unittest.TestCase):
    def test_same_key_survives_database_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "temporary.sqlite")
            key = str(uuid4())
            with TestClient(create_app(database_path=path)) as client:
                client.post("/v1/auth/register", json={
                    "email": "safe@example.org", "password": PASSWORD,
                })
                login = client.post("/v1/auth/login", json={
                    "email": "safe@example.org", "password": PASSWORD,
                })
                token = login.json()["access_token"]
                first = client.post("/v1/me/pathways", json=PLAN,
                    headers={"Authorization": "Bearer " + token, "Idempotency-Key": key})
                self.assertEqual(first.status_code, 201)
            with TestClient(create_app(database_path=path)) as client:
                second = client.post("/v1/me/pathways", json=PLAN,
                    headers={"Authorization": "Bearer " + token, "Idempotency-Key": key})
                self.assertEqual(second.status_code, 201, second.text)
                self.assertEqual(first.json(), second.json())


if __name__ == "__main__":
    unittest.main()
