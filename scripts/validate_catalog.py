
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog.sample.json"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
COSTS = {"free", "paid", "conditional", "unknown"}
CERTIFICATES = {"free", "paid", "not_offered", "unknown"}
ACCESS = {"manual", "official_api", "rss"}
FIELDS = {
    "catalog": {"schema_version", "providers", "skills", "resources"},
    "provider": {"id", "name", "website", "access_method", "authorization"},
    "skill": {"id", "name", "prerequisites"},
    "resource": {
        "id", "provider_id", "title", "url", "skills",
        "prerequisites", "access_cost", "certificate_cost",
        "evidence", "synthetic"
    },
    "evidence": {"status", "source_url", "checked_at"},
}


def valid_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and not (
        parsed.username or parsed.password
    )


def valid_id(value):
    return isinstance(value, str) and bool(ID_PATTERN.fullmatch(value))


def check_fields(obj, fields, context, errors):
    if not isinstance(obj, dict):
        errors.append(f"{context}: expected object")
        return False
    missing = fields - obj.keys()
    extra = obj.keys() - fields
    if missing:
        errors.append(f"{context}: missing {sorted(missing)}")
    if extra:
        errors.append(f"{context}: unexpected {sorted(extra)}")
    return not missing and not extra


def valid_date(value):
    if not isinstance(value, str):
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.tzinfo is not None and dt.utcoffset() is not None
    except ValueError:
        return False


def validate(data):
    errors = []
    if not check_fields(data, FIELDS["catalog"], "catalog", errors):
        return errors

    if data["schema_version"] != "1.0.0":
        errors.append("Unsupported schema version")

    for field in ("providers", "skills", "resources"):
        if not isinstance(data[field], list):
            errors.append(f"{field}: expected array")
            return errors

    indexes = {}
    for collection in ("providers", "skills", "resources"):
        seen = set()
        for index, obj in enumerate(data[collection]):
            context = f"{collection}[{index}]"
            kind = collection[:-1]
            if not check_fields(obj, FIELDS[kind], context, errors):
                continue
            identifier = obj["id"]
            if not valid_id(identifier):
                errors.append(f"{context}: invalid id")
                continue
            if identifier in seen:
                errors.append(f"{context}: duplicate id {identifier}")
            seen.add(identifier)
        indexes[collection] = seen

    graph = {}

    for provider in data["providers"]:
        if not isinstance(provider, dict) or not FIELDS["provider"] <= provider.keys():
            continue
        if not isinstance(provider["name"], str) or not provider["name"].strip():
            errors.append("Provider must have a name")
        if not valid_url(provider["website"]):
            errors.append(f"Invalid provider URL: {provider['id']}")
        if provider["access_method"] not in ACCESS:
            errors.append(f"Invalid access method: {provider['id']}")
        if provider["authorization"] not in {"pending", "approved"}:
            errors.append(f"Invalid provider authorization: {provider['id']}")

    for skill in data["skills"]:
        if not isinstance(skill, dict) or not FIELDS["skill"] <= skill.keys():
            continue
        sid = skill["id"]
        prereqs = skill["prerequisites"]
        if not isinstance(skill["name"], str) or not skill["name"].strip():
            errors.append(f"Skill name missing: {sid}")
        if not isinstance(prereqs, list):
            errors.append(f"Invalid prerequisites: {sid}")
            continue
        if any(not valid_id(p) for p in prereqs):
            errors.append(f"Invalid prerequisite ID: {sid}")
        if len(prereqs) != len(set(map(str, prereqs))):
            errors.append(f"Duplicate prerequisites: {sid}")
        for prereq in prereqs:
            if prereq not in indexes["skills"]:
                errors.append(f"Unknown skill prerequisite: {sid} -> {prereq}")
        graph[sid] = [p for p in prereqs if isinstance(p, str)]

    visiting = set()
    visited = set()

    def walk(node):
        if node in visiting:
            errors.append(f"Skill prerequisite cycle involving: {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for parent in graph.get(node, []):
            if parent in graph:
                walk(parent)
        visiting.remove(node)
        visited.add(node)

    for skill_id in graph:
        walk(skill_id)

    for resource in data["resources"]:
        if not isinstance(resource, dict) or not FIELDS["resource"] <= resource.keys():
            continue
        rid = resource["id"]
        if not isinstance(resource["title"], str) or not resource["title"].strip():
            errors.append(f"Resource title missing: {rid}")
        if resource["provider_id"] not in indexes["providers"]:
            errors.append(f"Unknown provider: {rid}")
        if not valid_url(resource["url"]):
            errors.append(f"Invalid resource URL: {rid}")

        for field in ("skills", "prerequisites"):
            values = resource[field]
            if not isinstance(values, list):
                errors.append(f"{rid}: {field} must be an array")
                continue
            if field == "skills" and not values:
                errors.append(f"{rid}: no skill outcomes")
            if any(not valid_id(v) for v in values):
                errors.append(f"{rid}: invalid skill ID in {field}")
            if len(values) != len(set(map(str, values))):
                errors.append(f"{rid}: duplicate skills in {field}")
            for skill_id in values:
                if skill_id not in indexes["skills"]:
                    errors.append(f"{rid}: unknown skill {skill_id}")

        if resource["access_cost"] not in COSTS:
            errors.append(f"{rid}: invalid access cost")
        if resource["certificate_cost"] not in CERTIFICATES:
            errors.append(f"{rid}: invalid certificate cost")

        evidence = resource["evidence"]
        if not check_fields(evidence, FIELDS["evidence"], rid, errors):
            continue

        if evidence["status"] not in {"verified", "unverified"}:
            errors.append(f"{rid}: invalid evidence status")

        source = evidence["source_url"]
        checked = evidence["checked_at"]
        if source is not None and not valid_url(source):
            errors.append(f"{rid}: invalid evidence URL")
        if checked is not None and not valid_date(checked):
            errors.append(f"{rid}: invalid verification timestamp")

        if type(resource["synthetic"]) is not bool:
            errors.append(f"{rid}: synthetic must be boolean")
        if resource["synthetic"] is True and evidence["status"] == "verified":
            errors.append(f"{rid}: synthetic resource cannot be verified")
        if evidence["status"] == "verified" and (
            not valid_url(source) or not valid_date(checked)
        ):
            errors.append(f"{rid}: verified claims require source and timestamp")

        if (
            not resource["synthetic"]
            and evidence["status"] == "verified"
        ):
            provider = next(
                (p for p in data["providers"]
                 if isinstance(p, dict) and p.get("id") == resource["provider_id"]),
                None
            )
            if provider and provider.get("authorization") != "approved":
                errors.append(f"{rid}: provider not approved")

    return errors


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else CATALOG
    try:
        with path.open(encoding="utf-8-sig") as file:
            data = json.load(file)
        errors = validate(data)
    except (OSError, ValueError, TypeError) as exc:
        print(f"FAIL: {exc}")
        return 1

    for error in errors:
        print(f"FAIL: {error}")

    if errors:
        return 1

    print("PASS: Catalog contract and integrity validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())