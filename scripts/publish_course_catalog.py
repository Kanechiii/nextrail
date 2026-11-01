"""Offline reviewed course publication; no network fetches or automatic activation."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_discovery import SourceContractError
from nextrail_discovery.pipeline import PublicationError, build_reviewed_catalog
from validate_catalog import validate

MAX_JSON_BYTES = 2_000_000
MAX_FEED_BYTES = 100_000


def read_json(path, *, size_limit=MAX_JSON_BYTES):
    source = Path(path)
    if not source.is_file() or source.stat().st_size > size_limit:
        raise PublicationError("Missing or oversized local JSON input")
    try:
        return json.loads(source.read_text(encoding="utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise PublicationError("Malformed local JSON input") from exc


def input_from_manifest(parent, name, *, suffix):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise PublicationError("Manifest paths must be relative to their directory")
    path = (parent / name).resolve(strict=False)
    if not path.is_relative_to(parent.resolve()) or path.suffix != suffix or not path.is_file():
        raise PublicationError("Unsafe or missing manifest input path")
    return path


def assemble_submissions(manifest, location):
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "batches"}:
        raise PublicationError("Invalid offline source manifest")
    if manifest["schema_version"] != "1.0.0":
        raise PublicationError("Unsupported source manifest version")
    entries = manifest["batches"]
    if not isinstance(entries, list) or len(entries) > 100:
        raise PublicationError("Invalid source manifest size")
    submissions = {}
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("source_id"), str):
            raise PublicationError("Invalid manifest source")
        sid = item["source_id"]
        if sid in submissions:
            raise PublicationError("Duplicate source in manifest")
        kind = item.get("format")
        if kind == "manual" and set(item) == {"source_id", "format", "path"}:
            source = input_from_manifest(location, item["path"], suffix=".json")
            submissions[sid] = read_json(source)
        elif kind == "rss" and set(item) == {
            "source_id", "format", "feed_path", "annotations_path"
        }:
            feed = input_from_manifest(location, item["feed_path"], suffix=".xml")
            if feed.stat().st_size > MAX_FEED_BYTES:
                raise PublicationError("Excessive local feed size")
            annotation = input_from_manifest(
                location, item["annotations_path"], suffix=".json"
            )
            submissions[sid] = {
                "xml": feed.read_bytes(),
                "annotations": read_json(annotation),
            }
        else:
            raise PublicationError("Unsupported offline manifest entry")
    return submissions


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build an offline, reviewed course catalog without network access."
    )
    parser.add_argument("--base-catalog", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--listing-reviews", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.suffix != ".json" or output.exists() or output.is_symlink() or not output.parent.is_dir():
        parser.error("Output must be a new JSON file inside an existing directory")
    try:
        base = read_json(args.base_catalog)
        registry = read_json(args.sources)
        manifest_path = Path(args.manifest)
        manifest = read_json(manifest_path)
        submissions = assemble_submissions(manifest, manifest_path.resolve().parent)
        reviews = read_json(args.listing_reviews)
        if not isinstance(reviews, dict) or set(reviews) != {"schema_version", "reviews"} or reviews["schema_version"] != "1.0.0":
            raise PublicationError("Invalid listing review document")
        claim_ledger = read_json(args.claims)
        result = build_reviewed_catalog(
            base, registry, submissions, reviews["reviews"], claim_ledger
        )
        errors = validate(result["catalog"])
        if errors:
            raise PublicationError("Compiled catalog violates v1 contract")
        serialized = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        with output.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
        print("PASS: Offline reviewed course publication; no remote calls performed")
        print(
            "Candidates:", result["review_report"]["candidates"],
            "Published:", result["review_report"]["published"],
            "Duplicates:", result["review_report"]["exact_duplicates_collapsed"],
        )
        return 0
    except (OSError, SourceContractError, ValueError, TypeError) as exc:
        print("FAIL: Offline course publication rejected:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
