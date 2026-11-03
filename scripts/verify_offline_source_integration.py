"""Fail-closed, read-only validation of locally supplied course source snapshots.

This checks the adapter boundary only. It never fetches providers, grants rights,
publishes reviewed courses or activates a runtime catalog.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_discovery import SourceContractError, load_source_authorizations
from nextrail_discovery.adapters import normalize_feed, normalize_manual
from nextrail_discovery.contracts import load_registry, valid_id
from nextrail_discovery.pipeline import PublicationError
from publish_course_catalog import (
    assemble_submissions, read_authorization_json, read_json,
)
from validate_catalog import validate

METHODS = frozenset({"manual", "official_api", "rss"})
SCHEMA_VERSION = "1.0.0"


def inspect_offline_inputs(base, registry, authorization_document, manifest, manifest_dir):
    """Check approved source contracts, normalize each batch, return safe counts."""
    if validate(base):
        raise PublicationError("Invalid base catalog contract")
    if not isinstance(base, dict) or not isinstance(base.get("skills"), list):
        raise PublicationError("Reviewed skill registry is required")
    known_skills = {item["id"] for item in base["skills"]}
    if not known_skills or any(not valid_id(sid) for sid in known_skills):
        raise PublicationError("Invalid reviewed skill registry")

    sources = load_registry(registry)
    granted = frozenset(load_source_authorizations(registry, authorization_document))
    manifest_entries = manifest.get("batches") if isinstance(manifest, dict) else None
    submissions = assemble_submissions(
        manifest, manifest_dir, approved_sources=granted,
    )
    if not isinstance(manifest_entries, list):
        raise PublicationError("Invalid local manifest")

    rows = []
    total = 0
    for source in sorted(sources, key=lambda item: item.id):
        if source.method not in METHODS:
            raise PublicationError("Unsupported offline source method")
        if source.synthetic:
            status = "synthetic_excluded"
            count = 0
        elif source.authorization != "approved":
            status = "authorization_pending"
            count = 0
        elif source.id not in granted:
            raise PublicationError("Approved source lacks a current matching grant")
        elif source.id not in submissions:
            status = "awaiting_offline_snapshot"
            count = 0
        else:
            payload = submissions[source.id]
            if source.method == "rss":
                normalized, provenance = normalize_feed(
                    source, payload["xml"], payload["annotations"], known_skills,
                )
            else:
                # official_api uses a *previously authorized, local* JSON export
                # with the same explicit curated record fields as manual batches.
                normalized, provenance = normalize_manual(
                    source, payload, known_skills,
                )
            if len(provenance) != len(normalized):
                raise PublicationError("Adapter provenance mismatch")
            count = len(normalized)
            total += count
            status = "snapshot_normalized_pending_course_review"
        rows.append({
            "source_id": source.id,
            "provider_id": source.provider_id,
            "integration_method": source.method,
            "status": status,
            "normalized_course_candidates": count,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_mode": "offline_read_only",
        "status": (
            "manual_course_evidence_review_required" if total else
            "awaiting_offline_snapshot" if granted else
            "blocked_no_authorized_sources"
        ),
        "registered_source_count": len(sources),
        "current_authorization_assertions": len(granted),
        "submitted_snapshot_count": len(submissions),
        "normalized_course_candidates": total,
        "sources": rows,
        "permissions_independently_verified": False,
        "listing_claims_independently_verified": False,
        "course_publication_permitted": False,
        "remote_requests_performed": 0,
        "catalog_files_written": 0,
        "runtime_activation_performed": False,
        "manual_provider_rights_review_required": True,
        "manual_course_evidence_review_required": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect authorized offline source adapters without fetching or publishing"
    )
    parser.add_argument("--base-catalog", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--authorizations", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--expect-empty", action="store_true",
        help="CI guard: no current real-source assertions or local snapshots",
    )
    parser.add_argument(
        "--require-candidates", action="store_true",
        help="Operator gate: exit 2 unless local records are ready for independent review",
    )
    args = parser.parse_args(argv)
    try:
        manifest_path = Path(args.manifest)
        report = inspect_offline_inputs(
            read_json(args.base_catalog), read_json(args.sources),
            read_authorization_json(args.authorizations), read_json(manifest_path),
            manifest_path.resolve().parent,
        )
        if args.expect_empty and (
            report["current_authorization_assertions"] != 0
            or report["submitted_snapshot_count"] != 0
            or report["normalized_course_candidates"] != 0
        ):
            raise PublicationError("Checked-in sample must have no authorized sources or snapshots")
        print(json.dumps(report, sort_keys=True, indent=2))
        if args.require_candidates and not report["normalized_course_candidates"]:
            print("BLOCKED: no locally normalized courses await human review",
                  file=sys.stderr)
            return 2
        return 0
    except (PublicationError, SourceContractError, OSError,
            ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: Offline source integration rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
