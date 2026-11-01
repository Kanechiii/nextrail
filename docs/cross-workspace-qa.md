# Cross-workspace QA and browser acceptance — Phase 35

This phase establishes a **repeatable, fail-closed quality gate**, not a
claim that browser visual QA has already been completed.

## Automated evidence

GitHub Actions validates the existing source and security contracts and now
also executes the following regression coverage:

- Guest discovery and prerequisite pathway preview without authentication.
- No synthetic or unapproved sample courses published to the guest catalog.
- Account creation, sign-in, explicit pathway persistence, preferences,
  milestone updates, overview consistency and session revocation.
- Cross-account privacy: other users cannot access or change another account's
  saved routes, progress or preferences.
- Rejected unauthorized skill and synthetic-course mutations.
- UI source contracts: accessible mobile navigation and API status, native
  course details, disclosure controls, progress semantics, comparison
  headings, optional onboarding and reduced-motion styling.
- The sample UI QA acceptance register remains **blocked** until independent
  human evidence is recorded. The production acceptance register also stays
  blocked.

The frontend dependency step uses `npm ci --no-audit --no-fund` rather than
unlocked `npm install`, so a stale lockfile causes an explicit failure.
This also addresses the earlier local missing-Anime.js module issue once
local dependencies are refreshed after syncing the approved PR.

## Required manual browser matrix

Complete all eight scenarios in
`data/ui-quality-acceptance.sample.json` using a supported browser, an
approved disposable development account where necessary, and a local API.
The public catalog is not populated with real providers until separate
authorization and publication review.

| Scenario key | Required acceptance |
| --- | --- |
| `desktop_guest_discovery` | Verify search/filters, native course dialog, source badges, illustrative-only warnings, 3-course comparison and keyboard scroll |
| `mobile_guest_pathway` | Verify narrow-screen sidebar, search, guest preview and prerequisite-ordered route without account requirement or overflow |
| `desktop_account_progress` | Disposable account save, mark/unmark, progress percentage and saved resources with no cross-account leakage |
| `mobile_account_personalization` | Optional sign-in, learning preferences, applying goals, explicit guest-plan save or dismissal, and logout state clearing |
| `keyboard_and_screen_reader` | Tab order, focus, button names, dialog Escape, input labels, expanded state and live/error announcements using an actual screen reader |
| `theme_and_reduced_motion` | Light/dark contrast, OS reduced-motion before and during navigation, static availability and responsive layouts |
| `provider_evidence_and_synthetic_safety` | After Phase 34 merge, reviewed versus illustrative status, no unsafe provider links, certificate/access distinctions and conditional eligibility notice |
| `error_offline_and_retry` | Local API disconnected, rejected sign-in, expired sessions, failed save and preferences retry without false-success claims |

Capture approved evidence in independent local files, for example
short QA notes with OS/browser version, device viewport, steps,
screenshots stored privately if needed, observed defects and reviewer
signature. **Do not include real student emails, session tokens,
passwords or sensitive personal data in evidence or GitHub comments.**

## Fail-closed review register

`python scripts/verify_ui_quality.py --manifest data/ui-quality-acceptance.sample.json --expect-blocked`
must report `status=blocked` while sample reviews remain pending.
CI deliberately requires this blocked state.

For a *separately maintained, uncommitted* human QA register, each approved
scenario must contain these exact keys:

```json
{
  "status": "approved",
  "reviewer": "qa-reviewer-id",
  "checked_at": "2026-11-02T08:00:00+08:00",
  "evidence_file": "desktop-guest.txt",
  "evidence_sha256": "<lowercase SHA-256 of the evidence file>"
}
```

The example date is illustrative and must be replaced with the actual
review date. Files must be direct children of an approved private
evidence directory, no symlinks or traversal, and each file must have a
unique digest matched to its scenario. Reviews older than 30 days are
rejected. The eight recorded reviewer IDs are operator assertions,
**not independently verified human identities**.

Run on an approved, uncommitted local register with reviewed evidence:

```powershell
python scripts/verify_ui_quality.py --manifest path/to/private-ui-qa.json --evidence-dir path/to/private-evidence
```

This tool only verifies the manifest's structure, timestamps, pseudonymous
reviewer IDs and file checksums. It cannot validate rendered appearance,
real browser behavior, visual accessibility, or the truthfulness of a
review. A complete register still reports `production_approval=false`.

## Remaining gates

The local source, TypeScript and Python regression suites cannot replace
Playwright/manual rendered-browser QA, device profiling, independent
accessibility testing, security pen testing or representative production
performance/load observations.

If Phase 34 PR has not yet merged, do **not** mark
`provider_evidence_and_synthetic_safety` complete: the new UI requires
a separate reviewed test and later `main` regression. Merge approval,
local sync and Phase 35 acceptance remain manual.

Do not deploy publicly or activate paid services on the basis of this
register. The ten formal production acceptance gates remain independently
blocked by Phase 29 until all evidence and explicit release authorization
are obtained.
