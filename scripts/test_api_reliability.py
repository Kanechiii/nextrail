"""Phase 28 offline runtime readiness and guest latency regression tests."""
from contextlib import closing
import json
import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_api import create_app
from nextrail_api.reliability import database_connection_ready
from nextrail_auth import AccountStore
from nextrail_storage import open_database
from evaluate_api_reliability import (
    PerformanceGateError, evaluate_guest_api, percentile_95,
)


class DatabaseLivenessTests(unittest.TestCase):
    def test_storage_only_connection_is_not_operationally_ready(self):
        with closing(open_database()) as db:
            self.assertFalse(database_connection_ready(db))
            AccountStore(db)
            self.assertTrue(database_connection_ready(db))

    def test_closed_connection_not_ready(self):
        db = open_database()
        AccountStore(db)
        db.close()
        self.assertFalse(database_connection_ready(db))

    def test_ready_reports_database_failure_but_health_remains_alive(self):
        app = create_app()
        with TestClient(app) as client:
            self.assertEqual(client.get("/ready").status_code, 200)
            app.state.db.close()
            response = client.get("/ready")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"detail": "Database unavailable"})
            self.assertEqual(client.get("/health").json(), {"status": "ok"})
            self.assertEqual(response.headers["cache-control"], "no-store")

    def test_ready_requires_supported_learning_schema(self):
        app = create_app()
        with TestClient(app) as client:
            app.state.db.execute("PRAGMA user_version=5")
            self.assertEqual(client.get("/ready").status_code, 503)
            self.assertEqual(client.get("/health").status_code, 200)

    def test_ready_requires_auth_metadata(self):
        app = create_app()
        with TestClient(app) as client:
            app.state.db.execute("DELETE FROM auth_meta WHERE id=1")
            self.assertEqual(client.get("/ready").status_code, 503)


class GuestPerformanceSmokeTests(unittest.TestCase):
    def test_nearest_rank_percentile_is_deterministic(self):
        self.assertEqual(percentile_95([4, 2, 3, 1]), 4)
        self.assertEqual(percentile_95([1] * 18 + [99] * 2), 99)

    def test_invalid_percentile_samples_fail(self):
        for value in ([], [-1], [float("nan")], [float("inf")]):
            with self.subTest(value=value), self.assertRaises(PerformanceGateError):
                percentile_95(value)

    def test_bounded_profile_contains_no_personal_data(self):
        report = evaluate_guest_api(iterations=1, max_p95_ms=30000)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["total_requests"], 5)
        self.assertEqual(report["profile"], "in_memory_synthetic_guest")
        self.assertEqual(set(report["routes"]),
                         {"health", "ready", "skills", "courses", "pathway_preview"})
        self.assertTrue(all(v["requests"] == 1 for v in report["routes"].values()))
        serialized = json.dumps(report)
        self.assertNotIn("access_token", serialized)
        self.assertNotIn("email", serialized)
        self.assertNotIn("password", serialized)

    def test_invalid_performance_budgets_rejected(self):
        for iterations in (0, -1, 21, True, "12"):
            with self.subTest(iterations=iterations), self.assertRaises(PerformanceGateError):
                evaluate_guest_api(iterations=iterations)
        for budget in (0, 60001, float("nan"), True, "3000"):
            with self.subTest(budget=budget), self.assertRaises(PerformanceGateError):
                evaluate_guest_api(max_p95_ms=budget)

    def test_unexpected_http_failure_fails_closed(self):
        app = FastAPI()

        @app.get("/health")
        def health():
            from fastapi import HTTPException
            raise HTTPException(503, "unavailable")

        with self.assertRaises(PerformanceGateError) as error:
            evaluate_guest_api(iterations=1, app_factory=lambda: app)
        self.assertIn("health", str(error.exception))
        self.assertNotIn("unavailable", str(error.exception))

    def test_missing_privacy_header_fails_closed(self):
        app = FastAPI()

        @app.get("/health")
        def health():
            return {"status": "ok"}

        with self.assertRaises(PerformanceGateError) as error:
            evaluate_guest_api(iterations=1, app_factory=lambda: app)
        self.assertIn("privacy cache header", str(error.exception))


if __name__ == "__main__":
    unittest.main()
