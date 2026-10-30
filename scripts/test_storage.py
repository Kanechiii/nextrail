import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
from nextrail_storage import LearningStore, StorageError, open_database, migrate


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.conn = open_database()
        self.store = LearningStore(self.conn)
        self.pathway = {
            "schema_version": "1.0.0", "career_goal": "Frontend", "weekly_hours": 5,
            "generation_mode": "deterministic",
            "milestones": [
                {"order": 1, "skill_id": "html", "resource_ids": [], "rationale": "Start"},
                {"order": 2, "skill_id": "css", "resource_ids": [], "rationale": "Continue"},
            ],
        }

    def tearDown(self):
        self.conn.close()

    def test_schema_version(self):
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_migration_idempotent(self):
        migrate(self.conn)

    def test_pathway_roundtrip(self):
        key = self.store.save_pathway("account_a", self.pathway)
        self.assertEqual(self.store.get_pathway("account_a", key), self.pathway)

    def test_pathway_list_scoped(self):
        self.store.save_pathway("account_a", self.pathway)
        self.assertEqual(len(self.store.list_pathways("account_b")), 0)

    def test_cross_account_read_rejected(self):
        key = self.store.save_pathway("account_a", self.pathway)
        with self.assertRaises(KeyError):
            self.store.get_pathway("account_b", key)

    def test_cross_account_progress_rejected(self):
        key = self.store.save_pathway("account_a", self.pathway)
        with self.assertRaises(KeyError):
            self.store.set_progress("account_b", key, "html", "completed")

    def test_default_progress(self):
        key = self.store.save_pathway("account_a", self.pathway)
        self.assertEqual(self.store.get_progress("account_a", key)["completed"], 0)

    def test_progress_completion(self):
        key = self.store.save_pathway("account_a", self.pathway)
        self.assertTrue(self.store.set_progress("account_a", key, "html", "completed"))
        self.assertEqual(self.store.get_progress("account_a", key)["completed"], 1)

    def test_progress_idempotency(self):
        key = self.store.save_pathway("account_a", self.pathway)
        self.store.set_progress("account_a", key, "html", "completed")
        before = len(self.store.audit_history("account_a"))
        self.assertFalse(self.store.set_progress("account_a", key, "html", "completed"))
        self.assertEqual(len(self.store.audit_history("account_a")), before)

    def test_progress_reset(self):
        key = self.store.save_pathway("account_a", self.pathway)
        self.store.set_progress("account_a", key, "html", "completed")
        self.store.set_progress("account_a", key, "html", "not_started")
        self.assertEqual(self.store.get_progress("account_a", key)["completed"], 0)

    def test_unknown_skill_rejected(self):
        key = self.store.save_pathway("account_a", self.pathway)
        with self.assertRaises(StorageError):
            self.store.set_progress("account_a", key, "unknown", "completed")

    def test_invalid_status_rejected(self):
        key = self.store.save_pathway("account_a", self.pathway)
        with self.assertRaises(StorageError):
            self.store.set_progress("account_a", key, "html", "graded")

    def test_save_course_idempotent(self):
        self.assertTrue(self.store.save_course("account_a", "example-html-course"))
        self.assertFalse(self.store.save_course("account_a", "example-html-course"))

    def test_course_scope(self):
        self.store.save_course("account_a", "example-html-course")
        self.assertEqual(self.store.list_saved_courses("account_b"), [])

    def test_unsave_course(self):
        self.store.save_course("account_a", "example-html-course")
        self.assertTrue(self.store.unsave_course("account_a", "example-html-course"))
        self.assertFalse(self.store.unsave_course("account_a", "example-html-course"))

    def test_audit_scope(self):
        self.store.save_course("account_a", "example-html-course")
        self.assertEqual(self.store.audit_history("account_b"), [])

    def test_audit_pagination(self):
        self.store.save_course("account_a", "example-html-course")
        self.store.save_course("account_a", "example-css-course")
        first = self.store.audit_history("account_a", limit=1)
        second = self.store.audit_history("account_a", after_event_id=first[0]["event_id"])
        self.assertEqual(len(second), 1)

    def test_audit_excludes_goal_text(self):
        self.store.save_pathway("account_a", self.pathway)
        self.assertNotIn("Frontend", json.dumps(self.store.audit_history("account_a")))

    def test_audit_update_protected(self):
        self.store.save_course("account_a", "example-html-course")
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("UPDATE audit_events SET operation='tampered'")

    def test_audit_delete_protected(self):
        self.store.save_course("account_a", "example-html-course")
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("DELETE FROM audit_events")

    def test_atomic_rollback(self):
        self.conn.execute("""CREATE TRIGGER block_audit BEFORE INSERT ON audit_events
            BEGIN SELECT RAISE(ABORT, 'blocked'); END""")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.save_course("account_a", "example-html-course")
        self.assertEqual(self.store.list_saved_courses("account_a"), [])

    def test_invalid_owner_rejected(self):
        for bad in ("", "owner@example.com", None):
            with self.subTest(value=bad), self.assertRaises(StorageError):
                self.store.save_course(bad, "example-html-course")

    def test_invalid_course_ref_rejected(self):
        with self.assertRaises(StorageError):
            self.store.save_course("account_a", "https://example.org")

    def test_duplicate_milestone_rejected(self):
        path = json.loads(json.dumps(self.pathway))
        path["milestones"][1]["skill_id"] = "html"
        with self.assertRaises(StorageError):
            self.store.save_pathway("account_a", path)

    def test_milestone_order_rejected(self):
        path = json.loads(json.dumps(self.pathway))
        path["milestones"][0]["order"] = 2
        with self.assertRaises(StorageError):
            self.store.save_pathway("account_a", path)

    def test_extra_pathway_fields_rejected(self):
        with self.assertRaises(StorageError):
            self.store.save_pathway("account_a", dict(self.pathway, secret="test"))

    def test_invalid_list_limit(self):
        with self.assertRaises(StorageError):
            self.store.list_pathways("account_a", 0)

    def test_unknown_schema_rejected(self):
        self.conn.execute("PRAGMA user_version=9")
        with self.assertRaises(StorageError):
            migrate(self.conn)

    def test_incomplete_schema_rejected(self):
        self.conn.execute("DROP TABLE saved_courses")
        with self.assertRaises(StorageError):
            migrate(self.conn)

    def test_unversioned_existing_db_protected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "existing.sqlite"
            raw = sqlite3.connect(path)
            raw.execute("CREATE TABLE legacy(id TEXT)")
            raw.commit()
            raw.close()
            with self.assertRaises(StorageError):
                open_database(path)

    def test_persistence_across_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "learning.sqlite"
            a = open_database(path)
            LearningStore(a).save_course("account_a", "example-html-course")
            a.close()
            b = open_database(path)
            try:
                self.assertEqual(LearningStore(b).list_saved_courses("account_a"),
                                 ["example-html-course"])
            finally:
                b.close()


if __name__ == "__main__":
    unittest.main()
