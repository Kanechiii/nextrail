"""Deterministic, account-free discovery over validated catalog records."""

from .contracts import SourceContractError


def discover_courses(catalog, *, query="", provider_id=None, skill_id=None,
                     access_cost=None, certificate_cost=None, limit=20,
                     include_synthetic=False):
    if not isinstance(catalog, dict) or catalog.get("schema_version") != "1.0.0":
        raise SourceContractError("Invalid catalog version")
    if not isinstance(query, str) or len(query) > 120:
        raise SourceContractError("Invalid search term")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise SourceContractError("Invalid result limit")
    if type(include_synthetic) is not bool:
        raise SourceContractError("Invalid preview mode")
    providers = {p["id"]: p for p in catalog["providers"]}
    results = []
    for record in catalog["resources"]:
        if record.get("synthetic") is True and not include_synthetic:
            continue
        provider = providers.get(record.get("provider_id"))
        if provider is None:
            continue
        if not include_synthetic and provider.get("authorization") != "approved":
            continue
        if any([
            provider_id is not None and provider_id != record["provider_id"],
            skill_id is not None and skill_id not in record["skills"],
            access_cost is not None and access_cost != record["access_cost"],
            certificate_cost is not None and certificate_cost != record["certificate_cost"],
        ]):
            continue
        search_text = " ".join([record["title"], provider["name"], *record["skills"]]).casefold()
        if query.strip().casefold() not in search_text:
            continue
        results.append({
            "id": record["id"],
            "title": record["title"],
            "url": record["url"],
            "provider_id": provider["id"],
            "provider_name": provider["name"],
            "skills": list(record["skills"]),
            "access_cost": record["access_cost"],
            "certificate_cost": record["certificate_cost"],
            "evidence_status": record["evidence"]["status"],
            "synthetic": record["synthetic"],
        })
    return sorted(results, key=lambda r: (r["title"].casefold(), r["id"]))[:limit]
