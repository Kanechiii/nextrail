# Nextrail

AI-assisted personalized career-learning pathways and
cross-provider educational resource discovery.

## Product

Nextrail helps learners discover educational resources,
identify skill gaps, and generate personalized learning
pathways based on career goals.

Core discovery and pathway generation must remain
available without creating an account.

Accounts are optional and enable persistent progress,
saved courses, and synchronized pathways.

## Architecture

- Frontend: React, TypeScript, Vite, Tailwind CSS
- Backend: Python, FastAPI
- Agent orchestration: Strands Agents
- Local inference: Ollama (optional)
- Pathway fallback: Deterministic recommendation engine
- Development database: SQLite

## Repository

- apps/web: Frontend application
- services/api: Backend and AI services
- packages/schemas: Shared contracts
- data: Approved datasets and fixtures
- infra/supabase: Deferred cloud infrastructure
- scripts: Development utilities
- docs: Technical documentation
- .github: Repository governance and CI

## Development

Primary source workspace:

E:\Projects\nextrail

Large dependencies, caches, and AI models should be
stored on D: where supported.

## Current Status

Nextrail is a **local-first development prototype** with guest catalog
discovery, deterministic prerequisite-aware learning pathways, optional
account learning preferences and self-reported progress, and an enhanced
provider-evidence-aware Learning Route Workspace.

Offline provider authorizations, course publication, database restore,
synthetic concurrency and pre-release security checks are enforced in
the regression workflow. The sample source registry grants **zero real
providers** and the production acceptance register remains blocked.
Do not interpret successful CI as a public-launch approval.

No public deployment, paid service, real provider ingestion, production
email delivery, or hosted cross-device account storage is established.

## Controlled Local Demo

See [Controlled Local Demo](docs/controlled-local-demo.md) for a
loopback-only, synthetic-data walkthrough and release blockers.
Run `python scripts/verify_local_demo.py` before showing a disposable
localhost session.

## Governance

Development follows approval-gated steps,
Conventional Commits, and phase-specific GitHub labels.

See CONTRIBUTING.md for repository rules.
