"""Offline acceptance evidence CLI, with an explicit expected-blocked CI mode."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_api.acceptance import AcceptanceError, evaluate_acceptance


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only pre-release evidence inventory")
    parser.add_argument("--manifest", required=True, help="Offline acceptance register JSON")
    parser.add_argument("--evidence-dir", help="Local directory of manually reviewed evidence files")
    parser.add_argument("--expect-blocked", action="store_true",
                        help="CI check: the empty sample must remain blocked")
    args = parser.parse_args(argv)
    try:
        result = evaluate_acceptance(args.manifest, evidence_dir=args.evidence_dir)
    except (AcceptanceError, OSError, ValueError) as exc:
        print("INVALID: Pre-release acceptance evidence rejected", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    if args.expect_blocked:
        if result["status"] != "blocked" or result["approved_records"] != 0:
            print("FAIL: Sample register must contain zero approvals", file=sys.stderr)
            return 1
        print("PASS: Baseline release remains blocked and requires independent review")
        return 0
    if result["status"] == "blocked":
        print("BLOCKED: Missing required operator evidence; production not authorized", file=sys.stderr)
        return 1
    print("EVIDENCE COMPLETE: Local record checks passed; no production authorization granted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
