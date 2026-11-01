"""Read-only, local-only Nextrail demo safety gate (no server or network calls).

Checks the repository's synthetic fixtures and loopback Vite configuration.
A PASS allows preparation of a disposable localhost walkthrough ONLY; never
production hosting, real provider ingestion, or account-data processing.
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 1_000_000

PRODUCTION_GATES = frozenset({
    "authorized_provider_integration",
    "reviewed_catalog_publication",
    "production_account_recovery",
    "transport_origin_and_abuse_controls",
    "privacy_retention_and_erasure",
    "database_backup_and_restore",
    "reliability_load_and_observability",
    "security_and_regression_validation",
    "rollback_and_incident_response",
    "manual_release_approval",
})

UI_SCENARIOS = frozenset({
    "desktop_guest_discovery", "mobile_guest_pathway", "desktop_account_progress",
    "mobile_account_personalization", "keyboard_and_screen_reader",
    "theme_and_reduced_motion", "provider_evidence_and_synthetic_safety",
    "error_offline_and_retry",
})


class DemoSafetyError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DemoSafetyError("Duplicate demo fixture property")
        result[key] = value
    return result


def _json(path):
    file = Path(path)
    if file.is_symlink() or not file.is_file():
        raise DemoSafetyError("Demo fixture must be a regular file")
    try:
        with file.open("rb") as reader:
            raw = reader.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise DemoSafetyError("Demo fixture too large")
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, OSError) as exc:
        raise DemoSafetyError("Invalid demo fixture") from exc


def evaluate_local_demo(root=ROOT, *, env=None):
    import os

    root = Path(root)
    values = os.environ if env is None else env
    if not hasattr(values, "items"):
        raise DemoSafetyError("Invalid environment contract")
    prohibited = sorted(
        key for key in values
        if isinstance(key, str) and
        (key.startswith("NEXTRAIL_") or key == "VITE_API_BASE_URL")
    )
    if prohibited:
        raise DemoSafetyError("External or durable configuration is not allowed for local-only demo")

    catalog = _json(root / "data/catalog.sample.json")
    registry = _json(root / "data/sources.sample.json")
    ledger = _json(root / "data/provider-authorizations.sample.json")
    approval = _json(root / "data/pre-release-acceptance.sample.json")

    if catalog.get("schema_version") != "1.0.0" or not isinstance(catalog.get("resources"), list):
        raise DemoSafetyError("Invalid synthetic catalog")
    if not catalog["resources"] or any(
        not isinstance(row, dict) or row.get("synthetic") is not True
        for row in catalog["resources"]
    ):
        raise DemoSafetyError("Sample catalog includes real or invalid courses")
    if not isinstance(catalog.get("providers"), list) or any(
        not isinstance(row, dict) or row.get("authorization") == "approved"
        for row in catalog["providers"]
    ):
        raise DemoSafetyError("Sample catalog has an approved provider")
    if registry.get("schema_version") != "1.0.0" or not isinstance(registry.get("sources"), list):
        raise DemoSafetyError("Invalid source registry")
    if any(
        not isinstance(row, dict) or row.get("synthetic") is not True
        or row.get("authorization") == "approved"
        for row in registry["sources"]
    ):
        raise DemoSafetyError("Demo source registry includes enabled provider ingestion")
    if (ledger.get("schema_version") != "1.0.0"
            or ledger.get("authorizations") != []):
        raise DemoSafetyError("Demo authorization ledger must be empty")

    if (approval.get("schema_version") != "1.0.0"
            or not isinstance(approval.get("gates"), dict)
            or set(approval["gates"]) != PRODUCTION_GATES
            or any(value != {"status": "pending"} for value in approval["gates"].values())):
        raise DemoSafetyError("Sample production acceptance must stay fully blocked")

    config = root / "apps/web/vite.config.ts"
    if config.is_symlink() or not config.is_file():
        raise DemoSafetyError("Missing loopback web configuration")
    try:
        code = config.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DemoSafetyError("Unreadable Vite configuration") from exc
    if (not re.search(r"\bhost:\s*['\"]127\.0\.0\.1['\"]", code)
            or not re.search(r"\bport:\s*5173\b", code)
            or not re.search(r"\btarget:\s*['\"]http://127\.0\.0\.1:8000['\"]", code)):
        raise DemoSafetyError("Local demo must bind and proxy over loopback only")

    ui_path = root / "data/ui-quality-acceptance.sample.json"
    if ui_path.exists() or ui_path.is_symlink():
        ui = _json(ui_path)
        if (ui.get("schema_version") != "1.0.0"
                or not isinstance(ui.get("scenarios"), dict)
                or set(ui["scenarios"]) != UI_SCENARIOS
                or any(value != {"status": "pending"} for value in ui["scenarios"].values())):
            raise DemoSafetyError("Sample UI QA acceptance must stay blocked")
        ui_review="blocked"
    else:
        ui_review="not_in_current_branch"

    return {
        "status": "local_demo_only",
        "localhost_frontend": "http://127.0.0.1:5173",
        "localhost_api": "http://127.0.0.1:8000",
        "synthetic_courses": len(catalog["resources"]),
        "real_courses_enabled": 0,
        "provider_grants_enabled": 0,
        "production_acceptance": "blocked",
        "ui_qa_acceptance": ui_review,
        "network_requests_performed": 0,
        "deployment_performed": False,
        "production_approval": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline local-only demo preflight")
    parser.add_argument("--root", default=str(ROOT), help="Existing Nextrail checkout")
    args = parser.parse_args(argv)
    try:
        report = evaluate_local_demo(args.root)
    except (DemoSafetyError, OSError, TypeError, KeyError):
        print("FAIL: Local-only demo safety constraints not satisfied", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    print("PASS: Synthetic localhost walkthrough may be prepared; no production authorization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
