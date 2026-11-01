"""Manual, offline SQLite inspection / snapshot / restore-to-new-file commands."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_storage.recovery import DatabaseRecoveryError, inspect_database, snapshot_database


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect, back up, or restore a local Nextrail database without overwrite."
    )
    sub = parser.add_subparsers(dest="operation", required=True)
    inspect = sub.add_parser("inspect", help="Read-only schema and integrity validation")
    inspect.add_argument("--source", required=True)
    for action in ("backup", "restore"):
        command = sub.add_parser(action, help="Create an exclusive SQLite snapshot")
        command.add_argument("--source", required=True)
        command.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "inspect":
            result = inspect_database(args.source)
            print("SQLite integrity and schema checks: PASS")
        else:
            result = snapshot_database(args.source, args.destination)
            print("Consistent SQLite snapshot created without overwriting existing files.")
        print(
            "Schema versions:",
            "learning=" + str(result["storage_schema"]),
            "auth=" + str(result["auth_schema"]),
            "preferences=" + str(result["preferences_schema"]),
        )
        return 0
    except DatabaseRecoveryError as exc:
        print(f"Database operation refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
