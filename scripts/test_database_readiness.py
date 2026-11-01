"""Offline regression tests for non-destructive database readiness checks."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_auth import AccountStore
from nextrail_auth.preferences import AccountPreferencesStore
from nextrail_storage import open_database
from nextrail_storage.recovery import snapshot_database
from nextrail_storage.readiness import DatabaseReadinessError, verify_database_readiness


class DatabaseReadinessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.active = self.root / "active.sqlite"
        self.backup = self.root / "backup.sqlite"
        self.conn = open_database(self.active)
        self.addCleanup(self.conn.close)
        self.auth = AccountStore(self.conn)
        AccountPreferencesStore(self.conn)
        self.owner = self.auth.register("private@example.org", "good-long-password123")
        self.auth.login("private@example.org", "good-long-password123")
        snapshot_database(self.active, self.backup)
        self.pin = hashlib.sha256(self.backup.read_bytes()).hexdigest()
        self.now = datetime.now(timezone.utc)

    def verify(self, **kwargs):
        return verify_database_readiness(
            self.active, self.backup, kwargs.pop("pin", self.pin),
            now=kwargs.pop("now", self.now), **kwargs
        )

    def test_valid_backup_and_active_db(self):
        report = self.verify()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["database_mode"], "wal")
        self.assertEqual(report["schema_versions"]["storage_schema"], 1)

    def test_no_private_data_in_result(self):
        self.assertNotIn("private@example.org", str(self.verify()))
        self.assertNotIn(self.owner, str(self.verify()))

    def test_reject_tampered_backup_hash(self):
        with self.assertRaises(DatabaseReadinessError):
            self.verify(pin="0" * 64)

    def test_reject_invalid_digest(self):
        for pin in ("A" * 64, "bad", "", None):
            with self.subTest(pin=pin), self.assertRaises(DatabaseReadinessError):
                self.verify(pin=pin)

    def test_reject_source_as_backup(self):
        with self.assertRaises(DatabaseReadinessError):
            verify_database_readiness(
                self.active, self.active, self.pin, now=self.now
            )

    def test_reject_missing_backup(self):
        self.backup.unlink()
        with self.assertRaises(DatabaseReadinessError):
            self.verify()

    def test_reject_old_backup(self):
        old = (self.now - timedelta(hours=30)).timestamp()
        os.utime(self.backup, (old, old))
        with self.assertRaises(DatabaseReadinessError):
            self.verify()

    def test_reject_future_backup_timestamp(self):
        future = (self.now + timedelta(hours=1)).timestamp()
        os.utime(self.backup, (future, future))
        with self.assertRaises(DatabaseReadinessError):
            self.verify()

    def test_reject_invalid_age_policy(self):
        for hours in (0, -1, True, 721, 3.5):
            with self.subTest(hours=hours), self.assertRaises(DatabaseReadinessError):
                self.verify(max_backup_age_hours=hours)

    def test_reject_naive_clock(self):
        with self.assertRaises(DatabaseReadinessError):
            self.verify(now=datetime(2026, 11, 1))

    def test_reject_missing_delete_guard(self):
        self.conn.execute("DROP TRIGGER audit_events_no_delete")
        with self.assertRaises(DatabaseReadinessError):
            self.verify()

    def test_reject_incomplete_limiter_schema(self):
        self.conn.execute("CREATE TABLE api_rate_limits (route TEXT)")
        with self.assertRaises(DatabaseReadinessError):
            self.verify()

    def test_reject_backup_with_mismatching_optional_schema(self):
        self.conn.execute("CREATE TABLE api_rate_limits (route TEXT)")
        self.conn.execute(
            "CREATE TABLE api_rate_limits_meta (id INTEGER PRIMARY KEY, key_check TEXT)"
        )
        self.conn.execute(
            "INSERT INTO api_rate_limits_meta VALUES(1,?)", ("a" * 64,)
        )
        with self.assertRaises(DatabaseReadinessError):
            self.verify()

    def test_reject_active_delete_guard_corruption(self):
        self.conn.execute("DROP TRIGGER audit_events_no_delete")
        self.conn.execute("""CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events
            BEGIN SELECT 1; END""")
        with self.assertRaises(DatabaseReadinessError):
            self.verify()

    def test_reject_invalid_backup_sqlite(self):
        self.backup.write_text("invalid SQLite file", encoding="utf-8")
        pin = hashlib.sha256(self.backup.read_bytes()).hexdigest()
        with self.assertRaises(DatabaseReadinessError):
            self.verify(pin=pin)

    def test_reject_non_wal_active_database(self):
        self.conn.close()
        with closing(sqlite3.connect(self.active)) as disk:
            disk.execute("PRAGMA journal_mode=DELETE")
        with self.assertRaises(DatabaseReadinessError):
            self.verify()

    def test_cli_reports_only_non_sensitive_metadata(self):
        proc = subprocess.run([
            sys.executable, str(ROOT / "scripts/verify_database_readiness.py"),
            "--database", str(self.active), "--backup", str(self.backup),
            "--backup-sha256", self.pin
        ], capture_output=True, text=True, cwd=ROOT, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PASS", proc.stdout)
        self.assertNotIn("private@example.org", proc.stdout)
        self.assertNotIn(self.owner, proc.stdout)


if __name__ == "__main__":
    unittest.main()
