"""Bounded, offline SQLite contention and recovery gate for Nextrail.

Only synthetic records in an automatically removed temporary database. This
evaluates single-host SQLite transaction safety, not production concurrency,
distributed scaling, or a service-level objective.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Barrier
from types import SimpleNamespace

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api.shared_limits import SQLiteFixedWindowLimiter
from nextrail_auth import AccountStore
from nextrail_auth.preferences import AccountPreferencesStore
from nextrail_storage import LearningStore, open_database
from nextrail_storage.recovery import inspect_database

TEST_KEY = bytes(range(32))


class ConcurrencyGateError(ValueError):
    """The synthetic single-host SQLite reliability gate failed."""


def synthetic_request():
    return SimpleNamespace(client=SimpleNamespace(host="192.0.2.30"))


def _worker(path, worker, steps, limit, barrier):
    # SQLite connections are opened, used and closed inside their own thread.
    with closing(open_database(path)) as conn:
        store = LearningStore(conn)
        limiter = SQLiteFixedWindowLimiter(conn, TEST_KEY)
        barrier.wait(timeout=12)
        for step in range(steps):
            limiter.enforce(synthetic_request(), "synthetic-login", limit)
            if not store.save_course(f"worker-{worker}", f"course-{worker}-{step}"):
                raise ConcurrencyGateError("Unexpected duplicate synthetic write")
    return steps


def _busy_writer_check(path):
    """A short database lock must deny safely, then recover without a ghost hit."""
    with closing(open_database(path)) as first, closing(open_database(path)) as second:
        limiter = SQLiteFixedWindowLimiter(second, TEST_KEY)
        second.execute("PRAGMA busy_timeout=100")
        first.execute("BEGIN IMMEDIATE")
        try:
            first.execute(
                "INSERT INTO saved_courses(owner_id,resource_id,created_at) VALUES(?,?,?)",
                ("rollback-owner", "rolled-back-course", "2026-11-01T00:00:00Z"),
            )
            # WAL readers must continue seeing committed rows during a writer lock.
            committed = second.execute("SELECT COUNT(*) FROM saved_courses").fetchone()[0]
            try:
                limiter.enforce(synthetic_request(), "locked-transaction", 1)
            except HTTPException as exc:
                if exc.status_code != 503:
                    raise ConcurrencyGateError("Lock contention did not fail closed") from exc
            else:
                raise ConcurrencyGateError("Locked request was unexpectedly allowed")
        finally:
            first.execute("ROLLBACK")
        if second.execute(
            "SELECT COUNT(*) FROM saved_courses WHERE owner_id='rollback-owner'"
        ).fetchone()[0]:
            raise ConcurrencyGateError("Rolled-back synthetic transaction persisted")
        limiter.enforce(synthetic_request(), "locked-transaction", 1)
        with closing(open_database(path)) as verifier:
            after = verifier.execute("SELECT COUNT(*) FROM saved_courses").fetchone()[0]
        if committed != after:
            raise ConcurrencyGateError("WAL reader observed an uncommitted write")
        with closing(open_database(path)) as verifier:
            row = verifier.execute(
                "SELECT used FROM api_rate_limits WHERE route='locked-transaction'"
            ).fetchone()
            if row is None or row["used"] != 1:
                raise ConcurrencyGateError("Failed transaction consumed an unexpected quota")
    return True


def evaluate_storage_concurrency(*, workers=4, steps=3):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ConcurrencyGateError("Worker count must be 1-4")
    if type(steps) is not int or not 1 <= steps <= 8:
        raise ConcurrencyGateError("Steps per worker must be 1-8")
    expected = workers * steps
    try:
        with tempfile.TemporaryDirectory(prefix="nextrail-concurrency-") as directory:
            path = str(Path(directory) / "synthetic.sqlite")
            with closing(open_database(path)) as conn:
                AccountStore(conn)
                AccountPreferencesStore(conn)
                LearningStore(conn)
                SQLiteFixedWindowLimiter(conn, TEST_KEY)

            barrier = Barrier(workers)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_worker, path, index, steps, expected, barrier)
                    for index in range(workers)
                ]
                completions = [future.result(timeout=30) for future in as_completed(futures)]
            if sum(completions) != expected:
                raise ConcurrencyGateError("Not all concurrent writes completed")

            with closing(open_database(path)) as conn:
                courses = conn.execute("SELECT COUNT(*) FROM saved_courses").fetchone()[0]
                audits = conn.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE operation='saved' AND entity_type='course'"
                ).fetchone()[0]
                rate_row = conn.execute(
                    "SELECT used FROM api_rate_limits WHERE route='synthetic-login'"
                ).fetchone()
                if courses != expected or audits != expected or not rate_row or rate_row["used"] != expected:
                    raise ConcurrencyGateError("Concurrent commits or audit/request budgets were lost")
                limiter = SQLiteFixedWindowLimiter(conn, TEST_KEY)
                try:
                    limiter.enforce(synthetic_request(), "synthetic-login", expected)
                except HTTPException as exc:
                    if exc.status_code != 429:
                        raise ConcurrencyGateError("Shared quota did not fail closed") from exc
                else:
                    raise ConcurrencyGateError("Over-budget request was allowed")

            _busy_writer_check(path)
            report = inspect_database(path)
            if report != {
                "storage_schema": 1, "auth_schema": 1, "preferences_schema": 1,
            }:
                raise ConcurrencyGateError("Unexpected storage schema after concurrent operations")
            return {
                "status": "pass",
                "profile": "temporary_sqlite_single_host",
                "workers": workers,
                "steps_per_worker": steps,
                "committed_synthetic_writes": courses,
                "matching_audit_events": audits,
                "shared_quota_enforced": True,
                "locked_write_failed_closed": True,
                "wal_reader_consistent": True,
                "rollback_verified": True,
                "post_lock_recovery_verified": True,
                "production_approval": False,
            }
    except ConcurrencyGateError:
        raise
    except (sqlite3.Error, OSError, HTTPException, TimeoutError, RuntimeError) as exc:
        raise ConcurrencyGateError("Offline SQLite concurrency gate failed") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description="Synthetic single-host SQLite contention and recovery gate")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--steps", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        result = evaluate_storage_concurrency(workers=args.workers, steps=args.steps)
    except ConcurrencyGateError:
        print("FAIL: Offline SQLite concurrency gate rejected", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    print("No real account data, provider requests, network calls, or deployment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
