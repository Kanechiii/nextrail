"""Offline reviewed course publication; no network fetches or automatic activation."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from nextrail_discovery import SourceContractError, load_source_authorizations
from nextrail_discovery.pipeline import PublicationError, build_reviewed_catalog
from validate_catalog import validate

MAX_JSON_BYTES = 2_000_000
MAX_FEED_BYTES = 100_000


def _unique_properties(pairs):
    """Reject ambiguous nested JSON objects rather than trusting last-key wins."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise PublicationError("Duplicate local JSON property")
        result[key] = value
    return result


def _reject_constant(value):
    raise PublicationError("Non-finite local JSON number is prohibited")


def read_json(path, *, size_limit=MAX_JSON_BYTES):
    """Read at most the configured bytes; prohibit symlinks and duplicate keys."""
    source = Path(path)
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != ".json":
        raise PublicationError("Local JSON must be an existing regular .json file")
    try:
        with source.open("rb") as handle:
            raw = handle.read(size_limit + 1)
        if len(raw) > size_limit:
            raise PublicationError("Local JSON input exceeds size limit")
        return json.loads(
            raw.decode("utf-8-sig"),
            object_pairs_hook=_unique_properties,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, PublicationError):
            raise
        raise PublicationError("Invalid local JSON input") from exc


def read_authorization_json(path):
    """Use the same strict decoder, with a tighter permission-ledger limit."""
    return read_json(path, size_limit=1_000_000)


def input_from_manifest(parent, name, *, suffix):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise PublicationError("Manifest paths must be relative to their directory")
    path = (parent / name).resolve(strict=False)
    if (not path.is_relative_to(parent.resolve()) or path.suffix != suffix
            or not path.is_file() or path.is_symlink()):
        raise PublicationError("Unsafe or missing manifest input path")
    return path


def assemble_submissions(manifest, location, *, approved_sources=None):
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
        if approved_sources is not None and sid not in approved_sources:
            raise PublicationError("Manifest source lacks current authorization approval")
        kind = item.get("format")
        if kind == "manual" and set(item) == {"source_id", "format", "path"}:
            source = input_from_manifest(location, item["path"], suffix=".json")
            submissions[sid] = read_json(source)
        elif kind == "rss" and set(item) == {
            "source_id", "format", "feed_path", "annotations_path"
        }:
            feed = input_from_manifest(location, item["feed_path"], suffix=".xml")
            try:
                with feed.open("rb") as handle:
                    xml_bytes = handle.read(MAX_FEED_BYTES + 1)
            except OSError as exc:
                raise PublicationError("Unable to read local feed snapshot") from exc
            if len(xml_bytes) > MAX_FEED_BYTES:
                raise PublicationError("Excessive local feed size")
            annotation = input_from_manifest(
                location, item["annotations_path"], suffix=".json"
            )
            submissions[sid] = {
                "xml": xml_bytes,
                "annotations": read_json(annotation),
            }
        else:
            raise PublicationError("Unsupported offline manifest entry")
    return submissions


def compile_local_bundle(
    base_catalog, sources, authorizations, manifest, listing_reviews, claims, *, now=None,
):
    """Strict offline permission, snapshot, review and claim preflight.

    Returns a catalog candidate, not permission to activate the public API.
    """
    base = read_json(base_catalog)
    registry = read_json(sources)
    approved = frozenset(load_source_authorizations(
        registry, read_authorization_json(authorizations), now=now,
    ))
    manifest_path = Path(manifest)
    entry_list = read_json(manifest_path)
    submissions = assemble_submissions(
        entry_list, manifest_path.resolve().parent, approved_sources=approved,
    )
    reviews = read_json(listing_reviews)
    if (not isinstance(reviews, dict)
            or set(reviews) != {"schema_version", "reviews"}
            or reviews["schema_version"] != "1.0.0"):
        raise PublicationError("Invalid listing review document")
    ledger = read_json(claims)
    result = build_reviewed_catalog(
        base, registry, submissions, reviews["reviews"], ledger, now=now,
    )
    if validate(result["catalog"]):
        raise PublicationError("Compiled catalog violates v1 contract")
    return result, approved


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build an offline, reviewed course catalog without network access."
    )
    parser.add_argument("--base-catalog", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--authorizations", required=True,
                        help="Existing reviewed provider authorization JSON")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--listing-reviews", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.suffix != ".json" or output.exists() or output.is_symlink() or not output.parent.is_dir():
        parser.error("Output must be a new JSON file inside an existing directory")
    try:
        result, approved_sources = compile_local_bundle(
            args.base_catalog, args.sources, args.authorizations, args.manifest,
            args.listing_reviews, args.claims,
        )
        serialized = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        with output.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
        print("PASS: Offline reviewed course publication; no remote calls performed")
        print("Current authorized real-source grants:", len(approved_sources))
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
