"""Read-only provider onboarding audit for human reviewer sign-off.

This tool reuses the existing strict offline publication compiler. A successful
audit never authorizes providers, grants network permission, activates a
catalog, or creates deployment artifacts.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts"))

from nextrail_discovery.contracts import load_registry, SourceContractError
from nextrail_discovery.pipeline import PublicationError
from publish_course_catalog import compile_local_bundle, read_json

SCHEMA_VERSION = "1.0.0"


def onboarding_report(registry, manifest, bundle, grants):
    """Expose only statuses and counts, not evidence URLs or reviewer identities."""
    sources = load_registry(registry)
    if (not isinstance(manifest, dict)
            or set(manifest) != {"schema_version", "batches"}
            or manifest["schema_version"] != SCHEMA_VERSION
            or not isinstance(manifest["batches"], list)):
        raise PublicationError("Invalid offline source manifest")

    source_batches = {item["source_id"] for item in manifest["batches"]}
    rows = []
    for source in sorted(sources, key=lambda item: item.id):
        if source.synthetic:
            status = "synthetic_excluded"
        elif source.authorization != "approved":
            status = "source_approval_pending"
        elif source.id not in grants:
            # This is defense-in-depth: compile_local_bundle already rejects
            # missing, revoked, mismatched and expired source grants.
            raise PublicationError("Approved source is missing a current permission")
        elif source.id not in source_batches:
            status = "authorized_snapshot_missing"
        else:
            status = "offline_snapshot_submitted"
        rows.append({
            "source_id": source.id,
            "provider_id": source.provider_id,
            "integration_method": source.method,
            "status": status,
        })
    summary = bundle["review_report"]
    published = summary["published"]
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_mode": "offline_read_only",
        "source_count": len(sources),
        "authorized_source_assertions": len(grants),
        "sources": rows,
        "course_candidates": summary["candidates"],
        "reviewed_course_candidates": published,
        "excluded_reasons": summary["excluded_reasons"],
        "status": ("manual_independent_review_required" if published else
                   "blocked_no_reviewed_courses"),
        "independent_permission_verification_required": True,
        "manual_release_approval_required": True,
        "remote_requests_performed": 0,
        "catalog_files_written": 0,
        "runtime_activation_performed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit provider onboarding locally without publication or network calls"
    )
    parser.add_argument("--base-catalog", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--authorizations", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--listing-reviews", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument(
        "--expect-empty", action="store_true",
        help="CI sample gate: fail if any real grant or reviewed candidate is present",
    )
    parser.add_argument(
        "--require-candidates", action="store_true",
        help="Operator gate: fail if no reviewed candidates are available for human sign-off",
    )
    args = parser.parse_args(argv)
    try:
        result, grants = compile_local_bundle(
            args.base_catalog, args.sources, args.authorizations, args.manifest,
            args.listing_reviews, args.claims,
        )
        report = onboarding_report(
            read_json(args.sources), read_json(args.manifest), result, grants,
        )
        if args.expect_empty and (report["authorized_source_assertions"] != 0
                                  or report["reviewed_course_candidates"] != 0):
            raise PublicationError("Sample gate requires zero approved real sources or courses")
        if args.require_candidates and not report["reviewed_course_candidates"]:
            print(json.dumps(report, sort_keys=True, indent=2))
            print("BLOCKED: no reviewed courses are eligible for human sign-off",
                  file=sys.stderr)
            return 2
        print(json.dumps(report, sort_keys=True, indent=2))
        return 0
    except (PublicationError, SourceContractError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"FAIL: Provider onboarding preflight rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
