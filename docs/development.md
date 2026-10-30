
# Development Environment

## Repository

GitHub: https://github.com/Kanechiii/nextrail

Local workspace: `E:\Projects\nextrail`

## Storage Policy

The E: partition contains source code and repository metadata.

Use D: for large dependency directories, Python virtual
environments, AI model files, and development caches wherever
supported.

Avoid unnecessary writes to C:, which has limited available space.

## Technology Baseline

Frontend: React, TypeScript, Vite, Tailwind CSS.

Backend: Python and FastAPI.

Agent orchestration: Strands Agents.

Local inference: Ollama with lightweight CPU-first models.

Database: SQLite initially.

## Product Rules

Guest access to course discovery, filtering, and personalized
pathway generation is mandatory.

Accounts are optional and provide saved courses, persistent
learning progress, and synchronized learning pathways.

Recommendations must use verified educational resources.

A deterministic pathway engine must work without AI inference.

## Repository Governance

Use Conventional Commits for commits, issues, and pull requests.

Do not place phase numbers in titles or branch names.

Use GitHub labels for phase tracking.

Use development branches and reviewed pull requests.

Preserve existing repository history.

## Financial Safeguards

Do not activate paid subscriptions, billing integrations,
usage-billed inference, or paid cloud infrastructure without
explicit authorization.

## Validation

Run the repository validator:

`python scripts/validate_repository.py`

## Current Scope

Repository foundations only.

Frontend and backend application dependencies are intentionally
deferred to later implementation phases.