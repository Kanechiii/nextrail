# Multi-agent orchestration

## Architecture

The orchestration engine composes four bounded specialist roles:

1. CatalogAgent validates catalog structure, provenance states, referenced skills, providers, and resources.
2. SkillGapAgent resolves prerequisite closure from requested goals and existing skills.
3. PlanningAgent delegates to the existing deterministic pathway planner and optional local priority provider.
4. QualityAgent validates the published pathway against the approved v1 contract and rejects invented IDs, skipped prerequisites, unsupported resources, and zero-budget claims without appropriate evidence.

Each stage is fixed and synchronous; no recursive agent delegation, shared model swarm, automatic external tool access, or autonomous browsing is enabled. The engine returns a structured pathway and a sequence of completed stage records. No partial result is published when a stage fails.

## Configuration

Default: NEXTRAIL_AGENT_RUNTIME=native and NEXTRAIL_AI_PROVIDER=deterministic.

Optional existing local provider: NEXTRAIL_AGENT_RUNTIME=native with NEXTRAIL_AI_PROVIDER=ollama.

Optional Strands bridge: NEXTRAIL_AGENT_RUNTIME=strands_ollama with NEXTRAIL_AI_PROVIDER=ollama. This bridge is deliberately not installed in CI; optional dependencies, SDK compatibility, and the exact local model behavior require a separate controlled validation before use. It is not required for any pathway feature.

Only the fixed loopback Ollama host may be used; unknown and hosted providers are prohibited. The Strands bridge imports its SDK lazily and cannot configure Bedrock or other paid providers. Neither an Ollama model nor a cloud SDK is downloaded by this phase.

## Grounding and limits

Model output may influence which already-eligible skill is prioritized; the model cannot generate a course, change the catalog, or override prerequisite constraints.

Catalog evidence remains conservative. Zero-budget pathways do not attach courses because there is no claim-level verification of free access. Synthetic fixtures must not be treated as verified offerings.

The workflow uses the established guest-first planning interface. No user profile, authentication, persistence, API endpoint, cloud deployment, or live source ingestion is introduced here.

## Verification

Run the repository, catalog, and discovery validators and all unit tests through the existing CI. The orchestration tests exercise stage order, deterministic fallback, model bounds, fabricated course rejection, skill cycles, and synthetic safety. No live Strands/Ollama integration test is claimed.
