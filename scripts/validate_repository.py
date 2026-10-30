
from pathlib import Path
import json
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    ".gitignore",
    ".editorconfig",
    "CONTRIBUTING.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/implementation.md",
    ".github/workflows/ci.yml",
    "apps/web/package.json",
    "services/api/pyproject.toml",
    "docs/development.md",
]

REQUIRED_DIRECTORIES = [
    ".github/ISSUE_TEMPLATE",
    ".github/workflows",
    "apps/web",
    "services/api",
    "packages/schemas",
    "data",
    "infra/supabase",
    "scripts",
    "docs",
]


def main() -> int:
    errors = []

    for name in REQUIRED_FILES:
        if not (ROOT / name).is_file():
            errors.append(f"Missing file: {name}")

    for name in REQUIRED_DIRECTORIES:
        if not (ROOT / name).is_dir():
            errors.append(f"Missing directory: {name}")

    web_manifest = ROOT / "apps/web/package.json"
    if web_manifest.is_file():
        try:
            with web_manifest.open(encoding="utf-8-sig") as file:
                data = json.load(file)
            if data.get("name") != "@nextrail/web":
                errors.append("Invalid frontend package name")
            if data.get("private") is not True:
                errors.append("Frontend package must remain private")
        except (ValueError, OSError) as exc:
            errors.append(f"Invalid frontend manifest: {exc}")

    api_manifest = ROOT / "services/api/pyproject.toml"
    if api_manifest.is_file():
        try:
            with api_manifest.open("rb") as file:
                data = tomllib.load(file)
            if data.get("project", {}).get("name") != "nextrail-api":
                errors.append("Invalid backend project name")
        except (ValueError, OSError) as exc:
            errors.append(f"Invalid backend manifest: {exc}")

    for error in errors:
        print(f"FAIL: {error}")

    if errors:
        print(f"Repository validation failed: {len(errors)} error(s)")
        return 1

    print("PASS: Repository foundation validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())