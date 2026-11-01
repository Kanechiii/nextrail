"""Offline single-host SQLite concurrency, contention, and rollback tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_storage import LearningStore, open_database
from nextrail_auth import AccountStore
from nextrail_auth.preferences import AccountPreferencesStore
from evaluate_storage_concurrency import ConcurrencyGateError, evaluate_storage_concurrency


class OfflineStorageContentionTests(unittest.TestCase):
    def test_parallel_workers_preserve_atomic_writes_audit_and_rate_budget(self):
        result = evaluate_storage_concurrency(workers=3, steps=2)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["committed_synthetic_writes"], 6)
        self.assertEqual(result["matching_audit_events"], 6)
        self.assertTrue(result["shared_quota_enforced"])
        self.assertTrue(result["locked_write_failed_closed"])
        self.assertTrue(result["wal_reader_consistent"])
        self.assertTrue(result["rollback_verified"])
        self.assertTrue(result["post_lock_recovery_verified"])
        self.assertFalse(result["production_approval"])

    def test_single_worker_uses_same_recovery_contract(self):
        result = evaluate_storage_concurrency(workers=1, steps=1)
        self.assertEqual(result["committed_synthetic_writes"], 1)
        self.assertTrue(result["shared_quota_enforced"])

    def test_worker_limits_are_explicit_and_bounded(self):
        for workers in (0, -1, 5, True, 2.0, "4"):
            with self.subTest(workers=workers), self.assertRaises(ConcurrencyGateError):
                evaluate_storage_concurrency(workers=workers)
        for steps in (0, -1, 9, True, 2.0, "3"):
            with self.subTest(steps=steps), self.assertRaises(ConcurrencyGateError):
                evaluate_storage_concurrency(steps=steps)

    def test_competing_identical_saves_are_idempotent_and_audited_once(self):
        with tempfile.TemporaryDirectory(prefix="nextrail-idempotency-") as directory:
            location = str(Path(directory) / "idempotency.sqlite")
            with closing(open_database(location)) as conn:
                AccountStore(conn)
                AccountPreferencesStore(conn)
                LearningStore(conn)
            workers = 4
            barrier = threading.Barrier(workers)

            def save_one():
                with closing(open_database(location)) as conn:
                    store = LearningStore(conn)
                    barrier.wait(timeout=10)
                    return store.save_course("shared-owner", "same-course")

            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(lambda _: save_one(), range(workers)))
            self.assertEqual(results.count(True), 1)
            self.assertEqual(results.count(False), workers - 1)
            with closing(open_database(location)) as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM saved_courses").fetchone()[0], 1
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 1
                )
                self.assertEqual(
                    LearningStore(conn).list_saved_courses("shared-owner"), ["same-course"]
                )

    def test_cli_only_returns_non_sensitive_aggregate_statistics(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/evaluate_storage_concurrency.py"),
             "--workers", "2", "--steps", "2"],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=40
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout.splitlines()[0])
        self.assertEqual(report["committed_synthetic_writes"], 4)
        self.assertEqual(report["matching_audit_events"], 4)
        self.assertNotIn("192.0.2.30", result.stdout)
        self.assertNotIn("shared-owner", result.stdout)
        self.assertNotIn("password", result.stdout)
        self.assertNotIn("sqlite_path", report)
        self.assertNotIn("token", result.stdout)
        self.assertFalse(report["production_approval"])

    def test_cli_refuses_excessive_parallel_requests(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/evaluate_storage_concurrency.py"),
             "--workers", "20"],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=15
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL:", result.stderr)


if __name__ == "__main__":
    unittest.main()
