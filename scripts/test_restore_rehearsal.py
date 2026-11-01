"""Disposable SQLite recovery rehearsal: offline regression and corruption gates."""
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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api.shared_limits import SQLiteFixedWindowLimiter
from nextrail_auth import AccountStore
from nextrail_auth.preferences import AccountPreferencesStore
from nextrail_storage import LearningStore, open_database
from nextrail_storage.readiness import DatabaseReadinessError
from nextrail_storage.recovery import DatabaseRecoveryError, snapshot_database
from nextrail_storage.rehearsal import rehearse_database_restore
from nextrail_storage import rehearsal as rehearsal_module


class RestoreRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "active.sqlite"
        self.backup = self.root / "backup.sqlite"
        self.connection = open_database(self.source)
        self.addCleanup(self.connection.close)
        auth = AccountStore(self.connection)
        AccountPreferencesStore(self.connection)
        LearningStore(self.connection)
        self.owner = auth.register("private-recovery@example.org", "disposable-password123")
        auth.login("private-recovery@example.org", "disposable-password123")
        self.connection.execute(
            "INSERT INTO saved_courses(owner_id,resource_id,created_at) VALUES(?,?,?)",
            (self.owner, "synthetic-course", "2026-11-01T00:00:00Z"),
        )
        snapshot_database(self.source, self.backup)
        self.pin = hashlib.sha256(self.backup.read_bytes()).hexdigest()
        self.now = datetime.now(timezone.utc)

    def rehearse(self, **kwargs):
        pin = kwargs.pop("pin", self.pin)
        return rehearse_database_restore(
            kwargs.pop("database", self.source),
            kwargs.pop("backup", self.backup),
            pin, now=kwargs.pop("now", self.now), **kwargs,
        )

    def test_disposable_restore_verifies_complete_contents(self):
        result = self.rehearse()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["restore_rehearsal"], "verified")
        self.assertTrue(result["temporary_copy_removed"])
        self.assertEqual(result["schema_versions"], {
            "storage_schema": 1, "auth_schema": 1, "preferences_schema": 1,
        })
        self.assertGreater(result["logical_tables_compared"], 7)
        self.assertFalse(result["production_approval"])

    def test_source_and_backup_are_not_modified(self):
        original = self.backup.read_bytes()
        self.rehearse()
        self.assertEqual(self.backup.read_bytes(), original)
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM accounts"
        ).fetchone()[0], 1)
        self.assertEqual(sorted(p.name for p in self.root.glob("*.sqlite")),
                         ["active.sqlite", "backup.sqlite"])

    def test_private_identifiers_and_fingerprints_are_not_reported(self):
        result = str(self.rehearse())
        for private in ("private-recovery@example.org", self.owner,
                        "synthetic-course", self.pin):
            self.assertNotIn(private, result)

    def test_wrong_backup_digest_rejected(self):
        with self.assertRaises(DatabaseReadinessError):
            self.rehearse(pin="0" * 64)

    def test_missing_backup_rejected(self):
        self.backup.unlink()
        with self.assertRaises(DatabaseReadinessError):
            self.rehearse()

    def test_same_active_and_backup_refused(self):
        with self.assertRaises(DatabaseReadinessError):
            self.rehearse(backup=self.source)

    def test_tampered_backup_rejected(self):
        self.backup.write_bytes(self.backup.read_bytes() + b"tampered")
        with self.assertRaises(DatabaseReadinessError):
            self.rehearse()

    def test_stale_backup_rejected(self):
        old = (self.now - timedelta(hours=30)).timestamp()
        os.utime(self.backup, (old, old))
        with self.assertRaises(DatabaseReadinessError):
            self.rehearse()

    def test_unsafe_backup_symlink_refused(self):
        link = self.root / "linked.sqlite"
        try:
            link.symlink_to(self.backup)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this filesystem")
        with self.assertRaises(DatabaseReadinessError):
            self.rehearse(backup=link)

    def test_unapproved_schema_change_rejected(self):
        self.connection.execute("PRAGMA user_version=7")
        with self.assertRaises(DatabaseReadinessError):
            self.rehearse()

    def test_restored_row_mutation_detected(self):
        original = snapshot_database

        def corrupt_restored_copy(source, destination):
            report = original(source, destination)
            with closing(sqlite3.connect(destination)) as editor:
                editor.execute(
                    "INSERT INTO saved_courses(owner_id,resource_id,created_at) VALUES(?,?,?)",
                    ("acct-example", "extra", "2026-11-01T00:00:00Z"),
                )
                editor.commit()
            return report

        with patch.object(rehearsal_module, "snapshot_database",
                          side_effect=corrupt_restored_copy):
            with self.assertRaises(DatabaseReadinessError) as error:
                self.rehearse()
        self.assertIn("does not match pinned backup", str(error.exception))

    def test_restore_failure_leaves_no_persistent_destination(self):
        captured = []

        def unavailable(source, destination):
            captured.append(Path(destination))
            raise DatabaseRecoveryError("Synthetic snapshot failure")

        with patch.object(rehearsal_module, "snapshot_database",
                          side_effect=unavailable):
            with self.assertRaises(DatabaseReadinessError) as error:
                self.rehearse()
        self.assertIn("rehearsal failed", str(error.exception))
        self.assertTrue(captured)
        self.assertFalse(captured[0].parent.exists())
        self.assertTrue(self.backup.exists())

    def test_shared_throttling_metadata_survives_recovery(self):
        # The backup must be generated after optional security tables appear.
        self.backup.unlink()
        SQLiteFixedWindowLimiter(self.connection, bytes(range(32)))
        snapshot_database(self.source, self.backup)
        self.pin = hashlib.sha256(self.backup.read_bytes()).hexdigest()
        result = self.rehearse()
        self.assertEqual(result["status"], "pass")
        self.assertGreater(result["logical_tables_compared"], 10)

    def test_cli_prints_only_safe_aggregate_evidence(self):
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/rehearse_database_restore.py"),
            "--database", str(self.source), "--backup", str(self.backup),
            "--backup-sha256", self.pin,
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS: Pinned SQLite backup restored", result.stdout)
        self.assertIn('"production_approval": false', result.stdout)
        self.assertNotIn("private-recovery@example.org", result.stdout)
        self.assertNotIn(self.owner, result.stdout)
        self.assertNotIn(str(self.root), result.stdout)

    def test_cli_fails_closed_on_invalid_pin(self):
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/rehearse_database_restore.py"),
            "--database", str(self.source), "--backup", str(self.backup),
            "--backup-sha256", "0" * 64,
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL:", result.stderr)
        self.assertNotIn(str(self.root), result.stderr)


if __name__ == "__main__":
    unittest.main()
