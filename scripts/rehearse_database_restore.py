"""Read-only active database and pinned-backup restore rehearsal.

A disposable SQLite restore is verified and deleted. No real database is
replaced; no user rows or file paths are printed.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_storage.readiness import DatabaseReadinessError
from nextrail_storage.rehearsal import rehearse_database_restore


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rehearse a SQLite backup restore without modifying input files")
    parser.add_argument("--database", required=True, help="Existing active SQLite file")
    parser.add_argument("--backup", required=True, help="Existing independent SQLite backup")
    parser.add_argument("--backup-sha256", required=True, help="Pinned lowercase SHA-256 digest")
    parser.add_argument("--max-backup-age-hours", type=int, default=24)
    args = parser.parse_args(argv)
    try:
        result = rehearse_database_restore(
            args.database, args.backup, args.backup_sha256,
            max_backup_age_hours=args.max_backup_age_hours,
        )
    except (DatabaseReadinessError, OSError, ValueError, OverflowError):
        print("FAIL: Offline SQLite restore rehearsal refused; inputs not modified", file=sys.stderr)
        return 1
    print("PASS: Pinned SQLite backup restored and compared in disposable storage")
    print(json.dumps(result, sort_keys=True))
    print("Not a production restore, encrypted-backup proof, or recovery-time SLA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
