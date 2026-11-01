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

Phases 01–19 have completed and been merged into `main`; backend contracts,
reviewed offline course publication, optional accounts and progress APIs,
local recovery, and pinned release gates have been validated in CI.
The current stabilization effort closes zero-budget free-course eligibility
gaps before additional frontend integration.

No production deployment, paid services, live provider ingestion, or hosted
cross-device account storage is currently established.

## Governance

Development follows approval-gated steps,
Conventional Commits, and phase-specific GitHub labels.

See CONTRIBUTING.md for repository rules.
