# Local-first AI provider boundary

## Scope

The provider abstraction is implemented under services/api/nextrail_ai.
It has no production API endpoints, model dependency, hosted credentials,
cloud integration, installer, or provider auto-discovery.

## Default safety

NEXTRAIL_AI_PROVIDER defaults to deterministic.
Only the exact value ollama enables optional model requests.
Every other value, including bedrock, is rejected rather than silently
falling back to a paid provider.

Ollama communication is restricted to
http://127.0.0.1:11434/api/chat with redirects and proxies disabled.
Model selection accepts constrained local model identifiers only.
The request limits prediction tokens, context and timeout, and unloads
the model after use. The system is intended for CPU-first hardware.

The optional local model can select only one presently eligible skill ID.
It cannot generate or substitute resource IDs, declare prices, bypass
prerequisites, fabricate evidence, or alter the pathway response shape.

## Local configuration (optional)

NEXTRAIL_AI_PROVIDER=ollama
NEXTRAIL_OLLAMA_MODEL=qwen3:0.6b
NEXTRAIL_OLLAMA_TIMEOUT_SECONDS=8

These are configuration examples, not an instruction to install models.
Ollama is not required for testing or for deterministic operation.
No automatic download or network call occurs under default configuration.

## Deterministic pathway engine

PlanningRequest holds career goal, target skill IDs, known skills, time
availability and zero-budget preference. The pathway engine validates the
skill graph, rejects cycles, resolves required prerequisites, and outputs
the existing pathway.schema.json v1 contract.

No model, Strands orchestration, SQLite persistence, or web scraping is
needed to generate the deterministic skill milestones.

The sample catalog is entirely synthetic. Synthetic and unverified resources
are never suggested. Zero-budget plans include a free-access course only if
its resource ID comes from an explicitly activated, SHA-256-pinned reviewed
release with approved and current listing, availability and free-access
claims. Without that trusted release policy, zero-budget resource IDs stay
empty—even if an arbitrary catalog row says `access_cost=free`.
An eligible free course does **not** imply a free certificate; the separate
certificate-cost claim may remain unknown or paid.

The AI-assisted flag is set only when an eligible model suggestion was
accepted. Failure to connect, malformed output, invalid choices or timeout
all cause a deterministic fallback.

## Boundaries and future phases

This phase implements a provider abstraction, not full Strands multi-agent
orchestration. Later phases can add an orchestrator behind this validated
boundary after independent dependency and hardware compatibility checks.
Do not turn on default AWS Bedrock access in any future Strands integration.

Live course discovery, claim-level evidence, accounts, persistent progress,
production auth, endpoints, and cloud deployment remain outside this phase.

## Verification

python scripts/validate_repository.py
python scripts/validate_catalog.py
python -m unittest discover -s scripts -p "test_*.py" -v
python -m py_compile services/api/nextrail_ai/*.py
