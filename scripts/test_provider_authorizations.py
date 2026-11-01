"""Offline permission review regression checks: no network or real provider rights."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_discovery.authorizations import (
    AuthorizationContractError, load_source_authorizations,
)

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
REVIEWED = (NOW - timedelta(days=1)).isoformat()
EXPIRES = (NOW + timedelta(days=30)).isoformat()


def fixtures():
    registry = json.loads((ROOT / "data/sources.sample.json").read_text(encoding="utf-8"))
    source = registry["sources"][0]
    source["authorization"] = "approved"
    source["synthetic"] = False
    document = {"schema_version": "1.0.0", "authorizations": [{
        "source_id": source["id"],
        "provider_id": source["provider_id"],
        "source_url": source["source_url"],
        "method": source["method"],
        "status": "approved",
        "allowed_hosts": source["allowed_hosts"][:],
        "permission_basis": "published_terms",
        "permission_url": "https://example.org/terms",
        "reviewer": "operator-one",
        "reviewed_at": REVIEWED,
        "expires_at": EXPIRES,
    }]}
    return registry, document


class ProviderAuthorizationTests(unittest.TestCase):
    def approve(self, registry=None, document=None, *, now=NOW):
        defaults = fixtures()
        return load_source_authorizations(
            defaults[0] if registry is None else registry,
            defaults[1] if document is None else document,
            now=now,
        )

    def test_valid_reviewed_authorization(self):
        self.assertEqual(self.approve(), ("example-manual-source",))

    def test_empty_fixture_creates_no_real_approvals(self):
        sample = json.loads(
            (ROOT / "data/provider-authorizations.sample.json").read_text()
        )
        sources = json.loads((ROOT / "data/sources.sample.json").read_text())
        self.assertEqual(
            load_source_authorizations(sources, sample, now=NOW), ()
        )

    def test_does_not_mutate_review_inputs(self):
        registry, document = fixtures()
        old = copy.deepcopy((registry, document))
        self.approve(registry, document)
        self.assertEqual((registry, document), old)

    def test_multiple_approved_sources_return_sorted_ids(self):
        registry, document = fixtures()
        second = registry["sources"][1]
        second.update({"authorization": "approved", "synthetic": False})
        doc = copy.deepcopy(document["authorizations"][0])
        doc.update({
            "source_id": second["id"],
            "provider_id": second["provider_id"],
            "source_url": second["source_url"],
            "method": second["method"],
            "allowed_hosts": second["allowed_hosts"][:],
            "permission_url": "https://example.net/terms",
        })
        document["authorizations"].insert(0, doc)
        self.assertEqual(
            self.approve(registry, document),
            ("example-feed-source", "example-manual-source"),
        )

    def test_missing_permission_record_fails_closed(self):
        registry, document = fixtures()
        document["authorizations"] = []
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_revoked_permission_fails_closed(self):
        registry, document = fixtures()
        document["authorizations"][0]["status"] = "revoked"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_duplicate_record_rejected(self):
        registry, document = fixtures()
        document["authorizations"].append(copy.deepcopy(document["authorizations"][0]))
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_unknown_source_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["source_id"] = "not-registered"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_nonapproved_registry_source_cannot_be_authorized(self):
        registry, document = fixtures()
        registry["sources"][0]["authorization"] = "pending"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_synthetic_source_cannot_be_authorized(self):
        registry, document = fixtures()
        registry["sources"][0]["synthetic"] = True
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_provider_identity_mismatch_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["provider_id"] = "other-provider"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_source_url_mismatch_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["source_url"] = "https://example.org/other"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_method_change_requires_reapproval(self):
        registry, document = fixtures()
        document["authorizations"][0]["method"] = "rss"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_allowed_host_scope_cannot_expand(self):
        registry, document = fixtures()
        document["authorizations"][0]["allowed_hosts"] = [
            "example.org", "other.example.org"
        ]
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_permission_url_must_be_on_registered_official_host(self):
        registry, document = fixtures()
        for url in (
            "https://evil.example.net/terms",
            "https://example.org.evil.net/terms",
            "https://user:pass@example.org/terms",
            "http://example.org/terms",
        ):
            with self.subTest(url=url), self.assertRaises(AuthorizationContractError):
                document["authorizations"][0]["permission_url"] = url
                self.approve(registry, document)

    def test_permission_url_must_be_in_explicit_allowlist(self):
        registry, document = fixtures()
        document["authorizations"][0]["permission_url"] = "https://help.example.org/terms"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_permission_basis_is_constrained(self):
        registry, document = fixtures()
        document["authorizations"][0]["permission_basis"] = "assumed_public"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_reviewer_must_be_a_pseudonymous_id(self):
        registry, document = fixtures()
        for bad in ("", "mailto:test@example.org", "a" * 81):
            with self.subTest(value=bad), self.assertRaises(AuthorizationContractError):
                document["authorizations"][0]["reviewer"] = bad
                self.approve(registry, document)

    def test_future_review_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["reviewed_at"] = (
            NOW + timedelta(days=1)
        ).isoformat()
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_stale_review_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["reviewed_at"] = (
            NOW - timedelta(days=91)
        ).isoformat()
        document["authorizations"][0]["expires_at"] = (
            NOW - timedelta(days=1)
        ).isoformat()
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_expired_approval_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["expires_at"] = (
            NOW - timedelta(minutes=1)
        ).isoformat()
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_excessively_long_approval_window_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["expires_at"] = (
            NOW + timedelta(days=91)
        ).isoformat()
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_invalid_time_zone_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["reviewed_at"] = "2026-10-31T12:00:00"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_naive_verification_clock_rejected(self):
        with self.assertRaises(AuthorizationContractError):
            self.approve(now=datetime(2026, 11, 1))

    def test_extra_fields_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["unreviewed_scope"] = "scrape"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_unknown_document_version_rejected(self):
        registry, document = fixtures()
        document["schema_version"] = "2.0.0"
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_nonstring_permission_basis_rejected(self):
        registry, document = fixtures()
        document["authorizations"][0]["permission_basis"] = ["published_terms"]
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)

    def test_unbounded_record_collection_rejected(self):
        registry, document = fixtures()
        document["authorizations"] = [document["authorizations"][0]] * 101
        with self.assertRaises(AuthorizationContractError):
            self.approve(registry, document)


class AuthorizationPreflightCliTests(unittest.TestCase):
    def run_cli(self, registry, document):
        return subprocess.run([
            sys.executable, str(ROOT / "scripts/verify_source_authorizations.py"),
            "--sources", str(registry), "--authorizations", str(document),
        ], capture_output=True, text=True, cwd=ROOT, check=False)

    def test_pending_synthetic_samples_produce_no_approval(self):
        result = self.run_cli(
            ROOT / "data/sources.sample.json",
            ROOT / "data/provider-authorizations.sample.json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Approved real-source grants: 0", result.stdout)
        self.assertIn("No course publication", result.stdout)

    def test_missing_approval_refuses_approved_source(self):
        with tempfile.TemporaryDirectory() as folder:
            registry, document = fixtures()
            source_file = Path(folder) / "sources.json"
            grant_file = Path(folder) / "authorizations.json"
            document["authorizations"] = []
            source_file.write_text(json.dumps(registry), encoding="utf-8")
            grant_file.write_text(json.dumps(document), encoding="utf-8")
            result = self.run_cli(source_file, grant_file)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL:", result.stderr)

    def test_duplicate_json_property_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            grant_file = Path(folder) / "authorizations.json"
            grant_file.write_text(
                '{"schema_version":"1.0.0","schema_version":"1.0.0","authorizations":[]}',
                encoding="utf-8",
            )
            result = self.run_cli(
                ROOT / "data/sources.sample.json", grant_file,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_oversized_json_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            grant_file = Path(folder) / "authorizations.json"
            grant_file.write_bytes(b" " * 1_000_001)
            result = self.run_cli(
                ROOT / "data/sources.sample.json", grant_file,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
