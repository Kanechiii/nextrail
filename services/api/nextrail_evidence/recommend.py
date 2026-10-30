"""Pure ranking over explicitly reviewed evidence; no model-invented courses."""
from .review import EvidenceError, evaluate_claims


def recommend_courses(catalog, ledger, *, skill_id, completed=(), zero_budget=True,
                      limit=10, now=None):
    if not isinstance(skill_id, str) or not skill_id:
        raise EvidenceError("A skill ID is required")
    if type(zero_budget) is not bool or type(limit) is not int or not 1 <= limit <= 100:
        raise EvidenceError("Invalid recommendation options")
    if not isinstance(completed, (tuple, list, set)) or any(
        not isinstance(x, str) for x in completed
    ):
        raise EvidenceError("Invalid completed skills")
    skills = {s["id"] for s in catalog["skills"]}
    if skill_id not in skills or not set(completed).issubset(skills):
        raise EvidenceError("Unknown skill reference")
    trusted = evaluate_claims(catalog, ledger, now=now)
    providers = {p["id"]: p for p in catalog["providers"]}
    matches = []
    for row in catalog["resources"]:
        rid = row["id"]
        if (row["synthetic"] or providers[row["provider_id"]]["authorization"] != "approved"
                or skill_id not in row["skills"]
                or not set(row["prerequisites"]).issubset(set(completed))
                or trusted.get((rid, "availability")) != "available"):
            continue
        access = trusted.get((rid, "access_cost"))
        certificate = trusted.get((rid, "certificate_cost"))
        if access is None or (zero_budget and access != "free"):
            continue
        if zero_budget and certificate == "paid":
            certificate = "paid"
        score = 100 if access == "free" else 50
        score += 10 if certificate in ("free", "not_offered") else 0
        matches.append({
            "resource_id": rid,
            "provider_id": row["provider_id"],
            "access_cost": access,
            "certificate_cost": certificate or "unknown",
            "availability": "available",
            "score": score,
            "evidence_status": "claim_verified",
        })
    return sorted(matches, key=lambda x: (-x["score"], x["resource_id"]))[:limit]
