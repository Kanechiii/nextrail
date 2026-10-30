# Contributing to Nextrail

## Development Governance

All changes must belong to an authorized development phase and step.
Do not modify unrelated functionality.
Preserve the approved monorepo architecture, repository history, and existing integrations.

## Commit Titles

Use Conventional Commits: `type(scope): concise description`.

Examples:
- `chore(repo): configure repository foundations`
- `feat(web): add guest course search`
- `test(api): validate pathway prerequisites`
- `fix(ci): correct validation workflow`
- `docs(architecture): document agent responsibilities`

A pull request may contain several focused commits for discrete functionality, integration,
tests, fixes, and documentation. Keep each commit independently understandable.

## GitHub Issues and Pull Requests

Use Conventional Commit-style titles with no phase numbers. Use phase labels such as
`phase:02`, never phases in branch names, issue titles, pull request titles, or commit subjects.

Pull request descriptions contain only Summary, Motivation, Scope, Verification, and Goals.
Goals are the only PR-description section using task checkboxes. Check off only work that
has actually been completed. Do not include a commit-title list or a squash-merge draft
in the PR description. Never include private local-machine or personal environment details.

The pull request's Commits tab provides the individual commit history for review.

## Squash Merge

After manual review and passing checks, the reviewer may choose Squash and merge.

- Use one Conventional Commit title summarizing the full pull request.
- In GitHub's extended squash-commit description field, summarize the final result and
  list the exact subjects of the original commits, in chronological order.
- The original commit titles belong in this extended merge description, not the PR body.
- Review the prefilled message before confirming the squash merge.
- Do not force-push, rewrite existing main history, or merge without authorization.

## Quality Requirements

Changes must receive the required verification before merging.
Do not bypass failing tests.
Never commit secrets, personal learner data, local databases, or downloaded AI model weights.

## Financial Safeguards

No paid API, cloud billing integration, or usage-billed inference may be activated
without explicit authorization.

## Architecture Safeguards

Guest access to discovery and pathway generation must remain functional.
AI-generated recommendations must be grounded in verified educational resources.
Deterministic pathway generation must remain available when AI services are unavailable.
