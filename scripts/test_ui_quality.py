"""Offline UI QA evidence register regression tests with entirely fake records."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from verify_ui_quality import SCENARIOS, UiQualityError, inspect_ui_qa, read_manifest

NOW=datetime(2026,11,2,0,0,tzinfo=timezone.utc)


class UIQualityRegisterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.document={
            "schema_version":"1.0.0",
            "scenarios":{key:{"status":"pending"} for key in SCENARIOS},
        }

    def approve(self):
        for key in SCENARIOS:
            filename=key+".txt"
            raw=("Disposable illustrative test record for "+key).encode("utf-8")
            (self.root/filename).write_bytes(raw)
            self.document["scenarios"][key]={
                "status":"approved",
                "reviewer":"qa-example",
                "checked_at":(NOW-timedelta(days=1)).isoformat(),
                "evidence_file":filename,
                "evidence_sha256":hashlib.sha256(raw).hexdigest(),
            }

    def inspect(self):
        return inspect_ui_qa(self.document,self.root,now=NOW)

    def test_all_pending_is_blocked_not_production_approval(self):
        report=self.inspect()
        self.assertEqual(report["status"],"blocked")
        self.assertEqual(report["approved_checks"],0)
        self.assertEqual(report["pending_checks"],len(SCENARIOS))
        self.assertFalse(report["browser_testing_performed_by_tool"])
        self.assertFalse(report["production_approval"])

    def test_incomplete_review_stays_blocked(self):
        self.approve()
        self.document["scenarios"][SCENARIOS[1]]={"status":"pending"}
        report=self.inspect()
        self.assertEqual(report["status"],"blocked")
        self.assertEqual(report["pending_scenarios"],[SCENARIOS[1]])

    def test_fully_pinned_fixture_is_still_not_production_approval(self):
        self.approve()
        report=self.inspect()
        self.assertEqual(report["status"],"evidence_complete")
        self.assertEqual(report["approved_checks"],len(SCENARIOS))
        self.assertFalse(report["production_approval"])
        self.assertFalse(report["browser_testing_performed_by_tool"])

    def test_tampered_evidence_fails_closed(self):
        self.approve()
        (self.root/(SCENARIOS[0]+".txt")).write_text("tampered",encoding="utf-8")
        with self.assertRaises(UiQualityError):
            self.inspect()

    def test_duplicate_evidence_rejected(self):
        self.approve()
        self.document["scenarios"][SCENARIOS[1]]["evidence_file"]=SCENARIOS[0]+".txt"
        with self.assertRaises(UiQualityError):
            self.inspect()

    def test_stale_and_future_review_rejected(self):
        self.approve()
        for value in [NOW-timedelta(days=31),NOW+timedelta(seconds=1)]:
            with self.subTest(value=value):
                self.document["scenarios"][SCENARIOS[0]]["checked_at"]=value.isoformat()
                with self.assertRaises(UiQualityError):
                    self.inspect()

    def test_missing_scenarios_and_fake_approval_rejected(self):
        del self.document["scenarios"][SCENARIOS[0]]
        with self.assertRaises(UiQualityError):
            self.inspect()
        self.document["scenarios"][SCENARIOS[0]]={"status":"approved"}
        with self.assertRaises(UiQualityError):
            self.inspect()

    def test_bad_pseudonymous_reviewer_and_unsafe_filename_rejected(self):
        self.approve()
        for reviewer in ["real person", "", "../../bad"]:
            with self.subTest(reviewer=reviewer):
                doc=copy.deepcopy(self.document)
                doc["scenarios"][SCENARIOS[0]]["reviewer"]=reviewer
                with self.assertRaises(UiQualityError):
                    inspect_ui_qa(doc,self.root,now=NOW)
        self.document["scenarios"][SCENARIOS[0]]["evidence_file"]="../../outside.txt"
        with self.assertRaises(UiQualityError):
            self.inspect()

    def test_manifest_duplicates_rejected_and_sample_blocked(self):
        filename=self.root/"bad.json"
        filename.write_text('{"schema_version":"1.0.0","schema_version":"1.0.0","scenarios":{}}',encoding="utf-8")
        with self.assertRaises(UiQualityError):
            read_manifest(filename)
        sample=ROOT/"data/ui-quality-acceptance.sample.json"
        blocked=inspect_ui_qa(read_manifest(sample),self.root)
        self.assertEqual(blocked["status"],"blocked")

    def test_cli_expect_blocked_for_sample(self):
        response=subprocess.run([
            sys.executable,str(ROOT/"scripts/verify_ui_quality.py"),
            "--manifest",str(ROOT/"data/ui-quality-acceptance.sample.json"),
            "--expect-blocked",
        ],cwd=ROOT,capture_output=True,text=True,check=False)
        self.assertEqual(response.returncode,0,response.stderr)
        self.assertIn('"status": "blocked"',response.stdout)
        self.assertIn('"production_approval": false',response.stdout)

    def test_cli_requires_actual_review_for_nonblocking_mode(self):
        response=subprocess.run([
            sys.executable,str(ROOT/"scripts/verify_ui_quality.py"),
            "--manifest",str(ROOT/"data/ui-quality-acceptance.sample.json"),
        ],cwd=ROOT,capture_output=True,text=True,check=False)
        self.assertEqual(response.returncode,1)


if __name__=="__main__":
    unittest.main()
