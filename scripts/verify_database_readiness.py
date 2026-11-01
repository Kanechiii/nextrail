"""Read-only SQLite deployment preflight; no account data, backup or settings writes."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_storage.readiness import DatabaseReadinessError, verify_database_readiness


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect local SQLite readiness and a pinned backup offline.")
    parser.add_argument("--database", required=True, help="Existing local database path")
    parser.add_argument("--backup", required=True, help="Existing independent backup path")
    parser.add_argument("--backup-sha256", required=True, help="Expected exact backup SHA-256")
    parser.add_argument("--max-backup-age-hours", type=int, default=24)
    args = parser.parse_args(argv)
    try:
        report = verify_database_readiness(
            args.database, args.backup, args.backup_sha256,
            max_backup_age_hours=args.max_backup_age_hours,
        )
    except (DatabaseReadinessError, OSError, OverflowError, ValueError) as exc:
        print("FAIL: SQLite deployment-readiness preflight rejected; no files modified", file=sys.stderr)
        return 1
    print("PASS: Offline SQLite database and pinned-backup readiness")
    print(json.dumps(report, sort_keys=True))
    print("Not a production launch, encryption, retention, or multi-host approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
