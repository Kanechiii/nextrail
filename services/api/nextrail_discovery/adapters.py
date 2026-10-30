"""Offline reviewed-source adapters; never fetch third-party URLs."""

import copy
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urlunsplit

from .contracts import SourceContractError, valid_id

ATOM = "{http://www.w3.org/2005/Atom}"
MAX_RECORDS = 100
MAX_XML_BYTES = 100_000


def _canonical(url):
    parts = urlsplit(url)
    return urlunsplit(("https", parts.hostname.lower(),
                       parts.path.rstrip("/") or "/", parts.query, ""))


def _normalized(source, rows, known_skills, preview=False):
    source.require_usable(preview=preview)
    if not isinstance(known_skills, set) or not known_skills:
        raise SourceContractError("A reviewed skill registry is required")
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        raise SourceContractError("Source batch exceeds maximum record count")
    results = []
    provenance = {}
    seen_urls = set()
    seen_ids = set()
    required = {"external_id", "title", "url", "skills", "prerequisites"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise SourceContractError("Unexpected record fields")
        external_id = row["external_id"]
        title = row["title"]
        if not valid_id(external_id):
            raise SourceContractError("Invalid external record identifier")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
            raise SourceContractError("Invalid resource title")
        source.check_url(row["url"])
        skill_ids = row["skills"]
        prereqs = row["prerequisites"]
        if not isinstance(skill_ids, list) or not skill_ids or not isinstance(prereqs, list):
            raise SourceContractError("Skills and prerequisites must be explicit arrays")
        if (any(not isinstance(x, str) or x not in known_skills for x in skill_ids + prereqs)
                or len(skill_ids) != len(set(skill_ids))
                or len(prereqs) != len(set(prereqs))):
            raise SourceContractError("Unreviewed, invalid or duplicate skill IDs")
        rid = f"{source.provider_id}-{external_id}"
        canonical = _canonical(row["url"])
        if rid in seen_ids or canonical in seen_urls:
            raise SourceContractError("Duplicate resource ID or canonical URL")
        seen_ids.add(rid)
        seen_urls.add(canonical)
        results.append({
            "id": rid,
            "provider_id": source.provider_id,
            "title": title.strip(),
            "url": canonical,
            "skills": skill_ids[:],
            "prerequisites": prereqs[:],
            "access_cost": "unknown",
            "certificate_cost": "unknown",
            "evidence": {
                "status": "unverified",
                "source_url": None,
                "checked_at": None,
            },
            "synthetic": source.synthetic,
        })
        provenance[rid] = {
            "source_id": source.id,
            "source_url": source.source_url,
            "external_id": external_id,
            "method": source.method,
            "verification": "unverified",
        }
    return results, provenance


def normalize_manual(source, document, known_skills, preview=False):
    if source.method not in ("manual", "official_api"):
        raise SourceContractError("Manual JSON adapter requires manual or official_api source")
    if not isinstance(document, dict) or set(document) != {"source_id", "records"}:
        raise SourceContractError("Invalid source batch")
    if document["source_id"] != source.id:
        raise SourceContractError("Mismatched source ID")
    return _normalized(source, document["records"], known_skills, preview=preview)


def _text(element, name):
    found = element.find(name)
    return (found.text or "").strip() if found is not None else ""


def normalize_feed(source, xml_bytes, annotations, known_skills, preview=False):
    if source.method != "rss":
        raise SourceContractError("RSS/Atom adapter requires rss source")
    source.require_usable(preview=preview)
    if not isinstance(xml_bytes, bytes) or len(xml_bytes) > MAX_XML_BYTES:
        raise SourceContractError("Invalid or excessive XML feed")
    if b"<!doctype" in xml_bytes.lower() or b"<!entity" in xml_bytes.lower():
        raise SourceContractError("XML DTD and entity declarations are prohibited")
    if not isinstance(annotations, dict):
        raise SourceContractError("Feed entries require curated skill mappings")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise SourceContractError("Malformed feed XML") from exc
    if sum(1 for _ in root.iter()) > 800:
        raise SourceContractError("Excessive XML document complexity")
    if root.tag == "rss":
        entries = root.findall("./channel/item")
        def extract(entry):
            return _text(entry, "guid"), _text(entry, "title"), _text(entry, "link")
    elif root.tag == ATOM + "feed":
        entries = root.findall(ATOM + "entry")
        def extract(entry):
            links = [
                link.get("href", "") for link in entry.findall(ATOM + "link")
                if link.get("rel", "alternate") == "alternate"
            ]
            return _text(entry, ATOM + "id"), _text(entry, ATOM + "title"), (
                links[0] if links else ""
            )
    else:
        raise SourceContractError("Only RSS 2.0 and Atom feeds are supported")
    if len(entries) > MAX_RECORDS:
        raise SourceContractError("Excessive feed entries")
    rows = []
    for entry in entries:
        external_id, title, url = extract(entry)
        curated = annotations.get(external_id)
        if not isinstance(curated, dict) or set(curated) != {"skills", "prerequisites"}:
            raise SourceContractError("Feed entry lacks explicit skill mapping")
        rows.append({
            "external_id": external_id,
            "title": title,
            "url": url,
            "skills": curated["skills"],
            "prerequisites": curated["prerequisites"],
        })
    if len(rows) != len(annotations):
        raise SourceContractError("Curated mappings must match feed entry set exactly")
    return _normalized(source, rows, known_skills, preview=preview)


def assemble_catalog(base_catalog, batches):
    """Merge normalized batches into the existing v1 catalog shape."""
    if not isinstance(base_catalog, dict) or base_catalog.get("schema_version") != "1.0.0":
        raise SourceContractError("Expected a v1 skill catalog")
    skills = base_catalog.get("skills")
    if not isinstance(skills, list):
        raise SourceContractError("Expected skill registry")
    known = {row.get("id") for row in skills if isinstance(row, dict)}
    if any(not valid_id(s) for s in known) or len(known) != len(skills):
        raise SourceContractError("Invalid reviewed skill registry")
    providers = {}
    resources = {}
    provenance = {}
    urls = set()
    for source, resource_rows, records_provenance in batches:
        if source.provider_id in providers:
            p = providers[source.provider_id]
            if p["website"] != source.provider_website or p["authorization"] != source.authorization:
                raise SourceContractError("Conflicting provider metadata")
        providers[source.provider_id] = {
            "id": source.provider_id,
            "name": source.provider_name,
            "website": source.provider_website,
            "access_method": source.method,
            "authorization": source.authorization,
        }
        for resource in resource_rows:
            rid = resource["id"]
            url = _canonical(resource["url"])
            if rid in resources or url in urls:
                raise SourceContractError("Duplicate course identity across sources")
            if rid not in records_provenance:
                raise SourceContractError("Missing source provenance")
            if resource["provider_id"] != source.provider_id:
                raise SourceContractError("Resource provider does not match source")
            resources[rid] = copy.deepcopy(resource)
            urls.add(url)
            provenance[rid] = copy.deepcopy(records_provenance[rid])
    catalog = {
        "schema_version": "1.0.0",
        "providers": [providers[k] for k in sorted(providers)],
        "skills": copy.deepcopy(skills),
        "resources": [resources[k] for k in sorted(resources)],
    }
    return catalog, provenance
