import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
from nextrail_discovery import load_registry, normalize_manual, normalize_feed, assemble_catalog, discover_courses
from validate_catalog import validate


def main():
    sources = load_registry(json.loads((ROOT / "data/sources.sample.json").read_text()))
    catalog = json.loads((ROOT / "data/catalog.sample.json").read_text())
    skill_ids = {row["id"] for row in catalog["skills"]}
    manual = json.loads((ROOT / "data/discovery.manual.sample.json").read_text())
    annotations = json.loads((ROOT / "data/discovery.feed.annotations.sample.json").read_text())
    feed = (ROOT / "data/discovery.feed.sample.xml").read_bytes()
    first = normalize_manual(sources[0], manual, skill_ids, preview=True)
    second = normalize_feed(sources[1], feed, annotations, skill_ids, preview=True)
    merged, provenance = assemble_catalog(catalog, [(sources[0], *first), (sources[1], *second)])
    errors = validate(merged)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    preview = discover_courses(merged, include_synthetic=True)
    public = discover_courses(merged)
    if len(preview) != 3 or public or len(provenance) != 3:
        print("FAIL: Guest discovery preview or production isolation mismatch")
        return 1
    print("PASS: Source contracts, offline adapters, catalog integrity, and guest discovery")
    print("PASS: Synthetic records excluded from public discovery")
    return 0


if __name__ == "__main__":
    sys.exit(main())
