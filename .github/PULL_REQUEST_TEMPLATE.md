## Summary

Describe the completed change and its outcome.

## Motivation

Explain the requirement and why the change is necessary.

## Scope

Describe implemented features, affected modules, integrations, and intentional boundaries.

## Verification

Record checks actually executed, their results, and anything not yet verified. Do not claim success for pending checks.

## Commit Breakdown

List the actual Conventional Commit subjects in the PR in their original order, with a short purpose for each:

- `type(scope): concise change` — explain its reviewable purpose.

## Goals

- [ ] Describe a concrete implementation goal. Check it only when genuinely completed.
- [ ] Add further implementation goals as needed.

## Squash Merge Message

**Title:** `type(scope): concise summary of the complete pull request`

**Description:**

Summarize the aggregate result of the pull request.

Included commits:
- `type(scope): concise change`
- `type(scope): another concise change`

Replace the examples with actual commit subjects before review. During manual squash merge, keep the Conventional Commit title and copy the prepared description into the final commit message. This consolidates the implementation into one main-branch commit while documenting the original steps.
