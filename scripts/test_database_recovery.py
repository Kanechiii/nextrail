"""Fail-closed local SQLite backup, integrity and durability tests."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api.settings import ConfigurationError, database_path_from_env
from nextrail_auth import AccountStore
from nextrail_auth.preferences import AccountPreferencesStore
from nextrail_storage import LearningStore, open_database
from nextrail_storage.recovery import (
    DatabaseRecoveryError, inspect_database, snapshot_database,
)


class DatabaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.parent = Path(self.directory.name)
        self.source = self.parent / "account-data.sqlite"
        self.connection = open_database(self.source)
        self.addCleanup(self.connection.close)
        self.accounts = AccountStore(self.connection)
        self.preferences = AccountPreferencesStore(self.connection)
        self.learning = LearningStore(self.connection)
        self.owner = self.accounts.register("recovery@example.org", "local-recovery-password123")

    def backup_path(self):
        return self.parent / "backup.sqlite"

    def test_read_only_inspect_finds_all_schema_versions(self):
        self.assertEqual(inspect_database(self.source), {
            "storage_schema": 1, "auth_schema": 1, "preferences_schema": 1
        })

    def test_snapshot_copies_live_wal_transactions_and_account_state(self):
        self.preferences.update(
            self.owner,
            {"career_goal": "Developer", "target_skill_ids": ["html"]},
            allowed_skill_ids={"html"},
        )
        pathway = {
            "schema_version": "1.0.0", "career_goal": "Developer",
            "weekly_hours": 5, "generation_mode": "deterministic",
            "milestones": [{
                "order": 1, "skill_id": "html", "resource_ids": [],
                "rationale": "Begin with HTML",
            }],
        }
        key = self.learning.save_pathway(self.owner, pathway)
        self.learning.set_progress(self.owner, key, "html", "completed")
        self.learning.save_course(self.owner, "approved-resource")
        self.accounts.login("recovery@example.org", "local-recovery-password123")
        result = snapshot_database(self.source, self.backup_path())
        self.assertEqual(result["storage_schema"], 1)
        self.assertTrue(self.backup_path().is_file())

        with closing(open_database(self.backup_path())) as restored:
            user = AccountStore(restored)
            self.assertEqual(user.account(self.owner)["email"], "recovery@example.org")
            self.assertEqual(
                AccountPreferencesStore(restored).get(self.owner)["career_goal"],
                "Developer",
            )
            self.assertEqual(LearningStore(restored).get_progress(self.owner, key)["completed"], 1)
            self.assertEqual(LearningStore(restored).list_saved_courses(self.owner), ["approved-resource"])

    def test_source_stays_writable_after_snapshot(self):
        snapshot_database(self.source, self.backup_path())
        owner = self.accounts.register("later@example.org", "local-recovery-password123")
        self.assertNotEqual(owner, self.owner)
        self.assertTrue(self.backup_path().exists())

    def test_restore_uses_fresh_path_and_preserves_previous_snapshot(self):
        backup = self.backup_path()
        snapshot_database(self.source, backup)
        restored = self.parent / "restored.sqlite"
        snapshot_database(backup, restored)
        self.assertEqual(inspect_database(restored), inspect_database(self.source))
        with closing(sqlite3.connect(restored)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 1)

    def test_existing_destination_must_never_be_overwritten(self):
        destination = self.backup_path()
        destination.write_bytes(b"original content")
        with self.assertRaises(DatabaseRecoveryError):
            snapshot_database(self.source, destination)
        self.assertEqual(destination.read_bytes(), b"original content")

    def test_backup_rejects_source_as_destination(self):
        with self.assertRaises(DatabaseRecoveryError):
            snapshot_database(self.source, self.source)

    def test_backup_rejects_missing_source(self):
        with self.assertRaises(DatabaseRecoveryError):
            snapshot_database(self.parent / "missing.sqlite", self.backup_path())

    def test_backup_rejects_missing_destination_parent(self):
        with self.assertRaises(DatabaseRecoveryError):
            snapshot_database(self.source, self.parent / "new" / "backup.sqlite")

    def test_inspect_rejects_memory_path(self):
        with self.assertRaises(DatabaseRecoveryError):
            inspect_database(":memory:")

    def test_inspect_rejects_invalid_file_format(self):
        invalid = self.parent / "invalid.sqlite"
        invalid.write_text("not a SQLite database", encoding="utf-8")
        with self.assertRaises(DatabaseRecoveryError):
            inspect_database(invalid)

    def test_inspect_rejects_unsupported_schema_version(self):
        self.connection.execute("PRAGMA user_version=8")
        with self.assertRaises(DatabaseRecoveryError):
            inspect_database(self.source)

    def test_inspect_rejects_incomplete_account_schema(self):
        self.connection.execute("DROP TABLE account_preferences_meta")
        with self.assertRaises(DatabaseRecoveryError):
            inspect_database(self.source)

    def test_inspect_rejects_broken_foreign_keys(self):
        with closing(sqlite3.connect(self.source)) as unguarded:
            unguarded.execute("PRAGMA foreign_keys=OFF")
            unguarded.execute(
                "INSERT INTO auth_sessions(token_hash,owner_id,expires_at) VALUES(?,?,?)",
                ("invalid-hash", "acct_missing_owner", 3000),
            )
            unguarded.commit()
        with self.assertRaises(DatabaseRecoveryError):
            inspect_database(self.source)

    def test_snapshot_of_corrupt_schema_does_not_create_destination(self):
        self.connection.execute("PRAGMA user_version=11")
        with self.assertRaises(DatabaseRecoveryError):
            snapshot_database(self.source, self.backup_path())
        self.assertFalse(self.backup_path().exists())

    def test_symlink_sources_are_rejected(self):
        link = self.parent / "linked.sqlite"
        try:
            link.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not allowed on this filesystem")
        with self.assertRaises(DatabaseRecoveryError):
            inspect_database(link)

    def test_cli_inspection_does_not_print_private_records(self):
        proc = subprocess.run([
            sys.executable, str(ROOT / "scripts/database_recovery.py"),
            "inspect", "--source", str(self.source)
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PASS", proc.stdout)
        self.assertNotIn("recovery@example.org", proc.stdout)
        self.assertNotIn("acct_", proc.stdout)

    def test_snapshot_rejects_existing_output_without_partial_temp_files(self):
        output = self.backup_path()
        output.write_text("retain", encoding="utf-8")
        with self.assertRaises(DatabaseRecoveryError):
            snapshot_database(self.source, output)
        self.assertEqual(list(self.parent.glob(".nextrail-snapshot-*.tmp")), [])


class DatabaseConfigTests(unittest.TestCase):
    def test_default_remains_ephemeral_for_tests(self):
        self.assertEqual(database_path_from_env({}), ":memory:")

    def test_explicit_file_path_is_supported(self):
        with tempfile.TemporaryDirectory() as path:
            location = str(Path(path) / "nextrail.sqlite")
            self.assertEqual(database_path_from_env({
                "NEXTRAIL_DB_PATH": location,
                "NEXTRAIL_REQUIRE_DURABLE_STORAGE": "true",
            }), location)

    def test_required_durability_rejects_missing_path(self):
        with self.assertRaises(ConfigurationError):
            database_path_from_env({"NEXTRAIL_REQUIRE_DURABLE_STORAGE": "true"})

    def test_invalid_durability_flag_rejected(self):
        with self.assertRaises(ConfigurationError):
            database_path_from_env({"NEXTRAIL_REQUIRE_DURABLE_STORAGE": "yes"})

    def test_uri_file_paths_rejected(self):
        with self.assertRaises(ConfigurationError):
            database_path_from_env({"NEXTRAIL_DB_PATH": "file:test.sqlite?mode=memory"})

    def test_missing_parent_rejected(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(ConfigurationError):
                database_path_from_env({"NEXTRAIL_DB_PATH": str(Path(path) / "missing" / "db.sqlite")})

    def test_directory_cannot_be_a_database(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(ConfigurationError):
                database_path_from_env({"NEXTRAIL_DB_PATH": path})

    def test_whitespace_and_control_characters_rejected(self):
        for path in ("", " :memory:", "local\n.sqlite", "local\x00.sqlite"):
            with self.subTest(path=repr(path)), self.assertRaises(ConfigurationError):
                database_path_from_env({"NEXTRAIL_DB_PATH": path})


if __name__ == "__main__":
    unittest.main()
