"""Offline provider-authorization contract preflight; no network or writes."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_discovery.authorizations import (
    AuthorizationContractError, load_source_authorizations,
)

MAX_INPUT_BYTES = 1_000_000


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthorizationContractError("Duplicate authorization JSON property")
        result[key] = value
    return result


def _read_json(path):
    file = Path(path)
    if file.is_symlink() or not file.is_file():
        raise AuthorizationContractError("Input must be an existing regular JSON file")
    try:
        with file.open("rb") as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise AuthorizationContractError("Authorization input exceeds size limit")
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, ValueError) as exc:
        raise AuthorizationContractError("Invalid authorization JSON input") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate offline source authorization assertions (no network calls)."
    )
    parser.add_argument("--sources", required=True, help="Existing v1 source registry JSON")
    parser.add_argument("--authorizations", required=True, help="Reviewed authorization JSON")
    args = parser.parse_args(argv)
    try:
        approved = load_source_authorizations(
            _read_json(args.sources), _read_json(args.authorizations)
        )
    except (AuthorizationContractError, TypeError, KeyError) as exc:
        print(f"FAIL: Provider authorization preflight rejected: {exc}", file=sys.stderr)
        return 1
    print("PASS: Offline provider authorization preflight; no network calls")
    print(f"Approved real-source grants: {len(approved)}")
    print("No course publication or source activation performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
