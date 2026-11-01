"""Read-only, offline release preflight for reviewed catalog and local SQLite."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api.release import ReleaseError, load_reviewed_bundle
from nextrail_storage.recovery import DatabaseRecoveryError, inspect_database


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate an operator-pinned reviewed course snapshot offline."
    )
    parser.add_argument("--bundle", required=True, help="Existing local reviewed snapshot")
    parser.add_argument("--sha256", required=True, help="Operator-reviewed lowercase SHA-256 digest")
    parser.add_argument("--database", help="Optional existing local database for read-only inspection")
    args = parser.parse_args(argv)
    try:
        release = load_reviewed_bundle(args.bundle, args.sha256)
        release.current_catalog()
        if args.database is not None:
            inspect_database(args.database)
    except (ReleaseError, DatabaseRecoveryError, ValueError, OSError) as exc:
        print("FAIL: Release preflight rejected:", exc, file=sys.stderr)
        return 1
    print("PASS: Pinned reviewed catalog freshness and schema checks")
    print("Reviewed courses:", release.reviewed_course_count)
    if args.database is not None:
        print("PASS: Existing local SQLite integrity and version checks")
    print("No network requests or source file changes performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
