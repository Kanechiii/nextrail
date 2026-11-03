# Deterministic personalized learning intelligence — Phase 48

## Scope

Phase 48 improves the existing guest-first, local-first pathway engine without
altering the public `/v1/pathways/preview` v1 JSON schema, adding a hosted AI
provider, inventing educational resources or changing account storage.

The planner now writes concise, catalog-grounded milestone rationales:

- A foundation skill explains that no prerequisite skills are required.
- A dependent skill identifies up to two **catalog-listed** prerequisite
  skill names and describes why that skill follows them.
- A skills-only milestone explicitly says that no course currently meets
  the reviewed pathway-access policy, rather than suggesting an invented
  enrollment link.
- When vetted resources exist, the explanation says that matching catalog
  resources are listed and that access, pricing and certificates must be
  confirmed separately. A free course does **not** imply a free certificate.

The new `nextrail_orchestration.explain_pathway` is a pure, optional analysis
helper. It takes an **already generated v1 pathway**, the user-provided
`PlanningRequest`, the catalog and an optional immutable
`verified_free_resource_ids` set. Before producing insights, it reruns the
existing CatalogAgent, SkillGapAgent and QualityAgent gates to reject
fabricated skills, course IDs, synthetic/unapproved resources, invalid
prerequisite sequences and unreviewed zero-budget "free" flags.

The separate output reports required skill closure, requested targets,
self-reported known skills inside that closure, missing skills, and
per-milestone reasons, target relevance, prerequisite status and reviewed
catalog resource coverage. It is **not** a saved learner profile, career
assessment, proof of competence, enrollment recommendation or credential
verification. It performs no network calls and persists no learner data.

## Deterministic interpretation

Consider a sample goal that requests CSS and JavaScript with HTML as a shared
prerequisite. A new learner receives three steps: HTML, CSS and JavaScript,
and the analyzer recognizes that HTML supports both requested targets. If
the learner already knows HTML, it is not repeated and two skill gaps remain.
If the learner reports knowing CSS but not HTML, HTML remains in the
prerequisite closure, avoiding a silent assumption that all foundations have
been certified.

All terms are sourced from the versioned skill graph, not invented by the
model. The optional locally configured Ollama/Strands provider may still
reorder **already-ready** skills under the existing bounded policy; it
cannot modify the graph or generate a new course. Invalid local AI output
falls back to deterministic ordering.

The analysis is intentionally a **server-side helper** available for a
future reviewed API/UI integration. The existing guest preview continues to
use improved milestone rationales immediately; the helper's structured
output is not automatically added to the API, nor is a new route exposed.

## Course safety and limitations

A milestone's course IDs must pass the orchestration quality gate. A
zero-budget request needs an immutable free-resource allowlist derived from
a separate SHA-256-pinned, independently reviewed catalog release. The
checked-in sample has zero authorized real providers and offers **no
reviewed course recommendations**. The pathway still helps guests plan
skills without forcing sign-up.

A known skill is a **user assertion**, not an independently assessed ability.
The system does not calculate course durations from weekly hours, automate
course completion, promise a professional credential, cache provider content
or assert an unauthorized provider's rights. Missing resources remain an
honest skills-only step.

## Regression evaluation

From the repository root:

```powershell
python scripts/evaluate_learning_intelligence.py
python -m unittest scripts.test_learning_intelligence -v
```

The evaluation exercises five deterministic guest scenarios, including
shared prerequisites, already-known foundations, an already-known target
with missing prerequisites and an empty route. Tests also exercise
transitive skill graphs, untrusted priority-provider output, evidence-gated
fictional courses, forged course IDs, invalid prerequisite ordering,
no-mutation, response-schema stability and separation of course access
from certificate claims.

The CI workflow adds the pure offline evaluation alongside the existing
pathway evaluation, security/release blockers, zero-provider authorization
gates, frontend tests and browser smoke. No model is downloaded or invoked
by these tests.

## Approval

Before manual squash merge, verify the latest PR-head CI is green and inspect
the v1 pathway contract, rationale wording, skill-gap analyzer and tests.
Confirm the provider authorization sample still contains no real grants and
the production release gates remain blocked. Preserve the local checkout,
stashes and worktrees. Public release, paid services, live course ingestion,
cross-device account sync and automatic merge are outside this phase.
