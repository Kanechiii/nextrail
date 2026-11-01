"""No-network, fail-closed regression tests for pre-release acceptance records."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api.acceptance import (
    AcceptanceError, GATES, evaluate_acceptance,
)

NOW = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.document = json.loads(
            (ROOT / "data/pre-release-acceptance.sample.json").read_text(encoding="utf-8")
        )
        self.manifest = self.root / "manifest.json"
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()

    def write(self):
        self.manifest.write_text(json.dumps(self.document), encoding="utf-8")

    def check(self, **kwargs):
        self.write()
        return evaluate_acceptance(
            self.manifest, evidence_dir=self.evidence,
            now=kwargs.pop("now", NOW), **kwargs
        )

    def approve(self):
        for gate in GATES:
            name = gate + ".txt"
            value = ("illustrative review evidence: " + gate).encode("utf-8")
            (self.evidence / name).write_bytes(value)
            final = gate == "manual_release_approval"
            self.document["gates"][gate] = {
                "status": "approved",
                "reviewer": "operator-two" if final else "operator-one",
                "reviewed_at": (
                    NOW - timedelta(hours=12) if final else NOW - timedelta(days=1)
                ).isoformat(),
                "evidence_file": name,
                "evidence_sha256": hashlib.sha256(value).hexdigest(),
            }

    def test_sample_remains_blocked_with_zero_approvals(self):
        report = self.check()
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["approved_records"], 0)
        self.assertEqual(report["pending_gates"], list(GATES))
        self.assertFalse(report["production_approval"])
        self.assertFalse(report["manual_signoff_separated"])

    def test_full_evidence_is_not_production_approval(self):
        self.approve()
        report = self.check()
        self.assertEqual(report["status"], "evidence_complete")
        self.assertEqual(report["approved_records"], len(GATES))
        self.assertEqual(report["pending_gates"], [])
        self.assertFalse(report["production_approval"])
        self.assertTrue(report["manual_signoff_separated"])

    def test_final_approval_with_same_reviewer_rejected(self):
        self.approve()
        self.document["gates"]["manual_release_approval"]["reviewer"] = "operator-one"
        with self.assertRaises(AcceptanceError) as error:
            self.check()
        self.assertIn("distinct", str(error.exception))

    def test_final_approval_cannot_precede_other_reviews(self):
        self.approve()
        self.document["gates"]["manual_release_approval"]["reviewed_at"] = (
            NOW - timedelta(days=2)
        ).isoformat()
        with self.assertRaises(AcceptanceError) as error:
            self.check()
        self.assertIn("follow all gate reviews", str(error.exception))

    def test_final_approval_cannot_share_same_review_time(self):
        self.approve()
        self.document["gates"]["manual_release_approval"]["reviewed_at"] = (
            NOW - timedelta(days=1)
        ).isoformat()
        with self.assertRaises(AcceptanceError):
            self.check()

    def test_final_approval_fails_while_critical_gate_pending(self):
        self.approve()
        self.document["gates"]["database_backup_and_restore"] = {
            "status": "pending"
        }
        with self.assertRaises(AcceptanceError) as error:
            self.check()
        self.assertIn("requires all prior approvals", str(error.exception))

    def test_independent_approval_still_not_deployment_authorization(self):
        self.approve()
        result = self.check()
        self.assertEqual(result["status"], "evidence_complete")
        self.assertTrue(result["manual_signoff_separated"])
        self.assertFalse(result["production_approval"])

    def test_partial_approvals_remain_blocked(self):
        self.approve()
        self.document["gates"][GATES[-1]] = {"status": "pending"}
        report = self.check()
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["pending_gates"], [GATES[-1]])

    def test_missing_gate_fails_closed(self):
        self.document["gates"].pop(GATES[0])
        with self.assertRaises(AcceptanceError):
            self.check()

    def test_unknown_gate_fails_closed(self):
        self.document["gates"]["override-production"] = {"status": "approved"}
        with self.assertRaises(AcceptanceError):
            self.check()

    def test_unrecognized_approval_shape_fails_closed(self):
        self.document["gates"][GATES[0]] = {"status": "approved"}
        with self.assertRaises(AcceptanceError):
            self.check()

    def test_unsupported_status_fails_closed(self):
        self.document["gates"][GATES[0]] = {"status": "skipped"}
        with self.assertRaises(AcceptanceError):
            self.check()

    def test_review_expiry_and_future_time_rejected(self):
        self.approve()
        for offset in (-91, 1):
            with self.subTest(offset=offset):
                self.document["gates"][GATES[0]]["reviewed_at"] = (
                    NOW + timedelta(days=offset)
                ).isoformat()
                with self.assertRaises(AcceptanceError):
                    self.check()

    def test_naive_review_clock_rejected(self):
        with self.assertRaises(AcceptanceError):
            self.check(now=datetime(2026, 11, 1))

    def test_changed_evidence_content_rejected(self):
        self.approve()
        (self.evidence / (GATES[0] + ".txt")).write_text("changed")
        with self.assertRaises(AcceptanceError):
            self.check()

    def test_no_evidence_directory_fails_for_approvals(self):
        self.approve()
        self.write()
        with self.assertRaises(AcceptanceError):
            evaluate_acceptance(self.manifest, now=NOW)

    def test_traversal_and_absolute_evidence_names_rejected(self):
        self.approve()
        for value in ("../private.txt", "/tmp/private.txt", ".", "..", ""):
            with self.subTest(value=value):
                self.document["gates"][GATES[0]]["evidence_file"] = value
                with self.assertRaises(AcceptanceError):
                    self.check()

    def test_shared_evidence_file_rejected(self):
        self.approve()
        first = self.document["gates"][GATES[0]]
        second = self.document["gates"][GATES[1]]
        second["evidence_file"] = first["evidence_file"]
        second["evidence_sha256"] = first["evidence_sha256"]
        with self.assertRaises(AcceptanceError):
            self.check()

    def test_oversized_evidence_rejected(self):
        self.approve()
        path = self.evidence / (GATES[0] + ".txt")
        path.write_bytes(b"z" * 2_000_001)
        self.document["gates"][GATES[0]]["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(AcceptanceError):
            self.check()

    def test_symlink_evidence_rejected_when_supported(self):
        self.approve()
        link = self.evidence / (GATES[0] + ".txt")
        link.unlink()
        try:
            link.symlink_to(self.evidence / (GATES[1] + ".txt"))
        except (OSError, NotImplementedError):
            self.skipTest("File symlinks unavailable")
        with self.assertRaises(AcceptanceError):
            self.check()

    def test_duplicate_json_property_rejected(self):
        self.manifest.write_text(
            '{"schema_version":"1.0.0","schema_version":"1.0.0","gates":{}}',
            encoding="utf-8",
        )
        with self.assertRaises(AcceptanceError):
            evaluate_acceptance(self.manifest, now=NOW)

    def test_oversized_manifest_rejected(self):
        self.manifest.write_bytes(b" " * 65537)
        with self.assertRaises(AcceptanceError):
            evaluate_acceptance(self.manifest, now=NOW)

    def test_cli_sample_expected_blocked(self):
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/verify_pre_release_acceptance.py"),
            "--manifest", str(ROOT / "data/pre-release-acceptance.sample.json"),
            "--expect-blocked",
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "blocked"', result.stdout)
        self.assertIn('"production_approval": false', result.stdout)

    def test_cli_default_blocked_exit_code(self):
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts/verify_pre_release_acceptance.py"),
            "--manifest", str(ROOT / "data/pre-release-acceptance.sample.json"),
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("BLOCKED", result.stderr)


if __name__ == "__main__":
    unittest.main()
