# Contributing to Nextrail

## Development Governance

All changes must belong to an authorized development
phase and step.

Do not modify unrelated project functionality.

Preserve the established monorepo architecture,
repository history, and existing integrations.

## Commit Titles

Use Conventional Commits:

type(scope): concise description

Examples:

chore(repo): configure repository foundations
feat(web): add guest course search
test(api): validate pathway prerequisites
docs(architecture): document agent responsibilities

## GitHub Issues and Pull Requests

Use descriptive Conventional Commits-style titles.

Track phases through labels such as:

phase:01
phase:02

Do not include the phase number in an issue,
pull request, or commit title.

Descriptions use consistent sections and must
not use checklist formatting.

## Quality Requirements

Changes must receive the required verification
before merging.

Do not bypass failing tests.

Never commit secrets, personal learner data,
local databases, or downloaded AI model weights.

## Financial Safeguards

No paid API, cloud billing integration, or
usage-billed inference may be activated without
explicit authorization.

## Architecture Safeguards

Guest access to discovery and pathway generation
must remain functional.

AI-generated recommendations must be grounded
in verified educational resources.

Deterministic pathway generation must remain
available when AI services are unavailable.
