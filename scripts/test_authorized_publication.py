"""Offline source authorization enforcement at course publication boundary.

All providers, permission pages and course details in these tests are fictional
local fixtures; no network, provider activation or permissions are created.
"""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from test_course_pipeline import fixtures


class AuthorizedPublicationCLITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        base, registry, submissions, listing, ledger = fixtures()
        now = datetime.now(timezone.utc)
        reviewed = (now - timedelta(days=1)).isoformat()
        for row in listing:
            row["checked_at"] = reviewed
        for row in ledger["claims"]:
            row["checked_at"] = reviewed

        source = registry["sources"][0]
        self.authorizations = {
            "schema_version": "1.0.0",
            "authorizations": [{
                "source_id": source["id"],
                "provider_id": source["provider_id"],
                "source_url": source["source_url"],
                "method": source["method"],
                "status": "approved",
                "allowed_hosts": source["allowed_hosts"][:],
                "permission_basis": "published_terms",
                "permission_url": "https://courses.example.org/terms",
                "reviewer": "operator-one",
                "reviewed_at": reviewed,
                "expires_at": (now + timedelta(days=30)).isoformat(),
            }],
        }
        self.write("catalog.json", base)
        self.write("sources.json", registry)
        self.write("manual.json", submissions[source["id"]])
        self.write("manifest.json", {
            "schema_version": "1.0.0",
            "batches": [{
                "source_id": source["id"],
                "format": "manual", "path": "manual.json"
            }],
        })
        self.write("reviews.json", {"schema_version": "1.0.0", "reviews": listing})
        self.write("claims.json", ledger)
        self.write("authorizations.json", self.authorizations)
        self.output = self.root / "reviewed.json"

    def write(self, name, obj):
        (self.root / name).write_text(json.dumps(obj), encoding="utf-8")

    def publish(self, *, include_authorizations=True):
        args = [
            sys.executable, str(ROOT / "scripts/publish_course_catalog.py"),
            "--base-catalog", str(self.root / "catalog.json"),
            "--sources", str(self.root / "sources.json"),
            "--manifest", str(self.root / "manifest.json"),
            "--listing-reviews", str(self.root / "reviews.json"),
            "--claims", str(self.root / "claims.json"),
            "--output", str(self.output),
        ]
        if include_authorizations:
            args.extend(["--authorizations", str(self.root / "authorizations.json")])
        return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)

    def test_current_exact_authorization_allows_offline_publication(self):
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(output["review_report"]["published"], 1)
        self.assertEqual(len(output["catalog"]["resources"]), 1)
        self.assertIn("Current authorized real-source grants: 1", result.stdout)

    def test_missing_authorization_argument_rejects_publication(self):
        result = self.publish(include_authorizations=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_missing_authorization_record_fails_closed(self):
        self.authorizations["authorizations"] = []
        self.write("authorizations.json", self.authorizations)
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_revoked_source_cannot_publish(self):
        self.authorizations["authorizations"][0]["status"] = "revoked"
        self.write("authorizations.json", self.authorizations)
        self.assertNotEqual(self.publish().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_wrong_source_url_or_method_cannot_publish(self):
        for key, value in [
            ("source_url", "https://courses.example.org/changed"),
            ("method", "rss"),
        ]:
            with self.subTest(key=key):
                doc = copy.deepcopy(self.authorizations)
                doc["authorizations"][0][key] = value
                self.write("authorizations.json", doc)
                self.assertNotEqual(self.publish().returncode, 0)
                self.assertFalse(self.output.exists())

    def test_expired_authorization_rejects_publication(self):
        self.authorizations["authorizations"][0]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat()
        self.write("authorizations.json", self.authorizations)
        self.assertNotEqual(self.publish().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_duplicate_authorization_json_fields_rejected(self):
        (self.root / "authorizations.json").write_text(
            '{"schema_version":"1.0.0","schema_version":"1.0.0","authorizations":[]}',
            encoding="utf-8",
        )
        self.assertNotEqual(self.publish().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_missing_manifest_source_approval_blocks_before_reading_snapshot(self):
        self.authorizations["authorizations"] = []
        self.write("authorizations.json", self.authorizations)
        (self.root / "manual.json").unlink()
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_authorization_symlink_rejected_if_supported(self):
        target = self.root / "authorizations-copy.json"
        target.write_text(json.dumps(self.authorizations), encoding="utf-8")
        link = self.root / "authorizations.json"
        link.unlink()
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this system")
        self.assertNotEqual(self.publish().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_malformed_authorization_does_not_replace_existing_output(self):
        self.output.write_text("preserve", encoding="utf-8")
        (self.root / "authorizations.json").write_text("not json", encoding="utf-8")
        self.assertNotEqual(self.publish().returncode, 0)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
