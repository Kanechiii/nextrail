
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

## Required local synchronization gate for every development phase

GitHub repository updates do **not** automatically update the local VS Code
checkout. After the author creates or fixes a phase PR, fetch its branch
before testing; after the user manually merges the PR, synchronize `main`
and rerun phase verification. Never claim local synchronization completed
without terminal output from the user's own machine.

Before checking out a PR branch, preserve any uncommitted files:

```powershell
git status --short --branch
git fetch origin
git branch -r
```

For a new phase branch, run
`git switch --track origin/<branch-name>` when it does not exist locally;
otherwise `git switch <branch-name>` followed by
`git pull --ff-only origin <branch-name>`. Replace the placeholder with
the actual phase branch. Run the appropriate phase's Python tests and
frontend build (if applicable), then review the PR and merge it manually.

After GitHub confirms the merge and post-merge CI succeeds, run:

```powershell
git fetch --prune origin
git switch main
git pull --ff-only origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

The last two SHAs must match. A non-clean working tree or divergent history
requires inspection; never use `git reset --hard`, force-push or delete
branches to work around it. Confirm the phase's backend and frontend tests
locally, and only then close the phase and start the next one. Keep PRs for
subsequent phases unmerged until this gate passes.
