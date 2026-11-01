# Account Experience & Personalization — Phase 33

This frontend milestone exposes Nextrail's existing authenticated learning
preferences without changing the backend's account model or its production
security status. A guest can still discover real approved-source courses
and generate prerequisite-aware routes without registering.

## Features

### Optional account learning profile

After a user signs in, My learning retrieves
`GET /v1/me/preferences` using the existing in-memory bearer token.
It presents editable learning preferences backed by
`PATCH /v1/me/preferences`:

- Display name (up to 80 characters; optional).
- Career goal (up to 120 characters; optional).
- Weekly learning hours (1–80).
- Target skills (up to 32 catalog skill IDs).
- Known skills (up to 128 catalog skill IDs).

Only the current user's API-authenticated preferences are read or changed.
The backend validates all skill IDs and enforces account isolation. Saving is
an explicit action; editing does not immediately mutate the server. Discarding
restores the most recently fetched or saved profile. If the preferences
endpoint fails, the panel offers a retry; guest access and existing saved
learning routes are not blocked.

`onboarding_completed` comes directly from the backend. The editor never
pretends that a display name alone is equivalent to completing onboarding.

**Use in pathway builder** is a separate, explicit action. It copies the
saved career goal, study hours, target skills and known skills into the
existing planning form. The user's current free-only preference remains
unchanged and no route is generated until they click Generate pathway.

### Guest-to-account continuity

The pathway preview stores an immutable copy of the user's chosen planning
inputs **only after a successful guest preview**. It is held in React state;
the plan, credentials and token are not stored in browser local/session
storage or a connector. Signing in or creating an account does not
automatically save the guest plan.

When a user signs in with a pending guest plan, the My learning page presents
an explicit choice:

- **Save guest plan**: submit the captured planning inputs using the existing
  authenticated `POST /v1/me/pathways` endpoint, then select the newly
  returned account pathway. This creates a new pathway using the current
  backend catalog; it does not pretend to transfer a previously verified
  immutable result or auto-complete lessons.
- **Not now**: discard the pending guest-plan copy without an account write.

The guest plan is cleared on successful save or sign-out. It is not uploaded
without the user taking an explicit saving action. The account's existing
cross-device state depends on the independently authorized hosting/backing
store and should not be assumed from local-only API execution.

### Existing restrictions preserved

Guest course discovery, source-authorized listings and route previews remain
public. Private preference endpoints retain bearer-token authorization.
Saved learning progress is self-reported and remains under account ownership.
Synthetic course cards cannot be bookmarked or linked to invented providers.
Password reset delivery, email verification, hosted security, backup
durability, paid services and production deployment are **not enabled**.

No full account export, deletion, session management or recovery UI is
implemented in this phase. Those require separate security/privacy review
and are not implied by the presence of a profile editor.

## Verification

GitHub Actions must pass backend regressions, source authorization, synthetic
SQLite concurrency and API reliability, the deliberately blocked pre-release
acceptance gate, frontend source-contract tests and production build.

Manual desktop/mobile checks are still necessary:

1. As a guest, preview a route; verify no account is required.
2. Sign in or register using an approved disposable local test account.
   Confirm the pending guest-plan prompt appears only after a successful
   guest preview, does not auto-save, and Not now dismisses it.
3. Select Save guest plan and verify the new pathway appears under the
   signed-in account. Check that signing out removes the pending plan.
4. Load the profile editor; save and re-fetch a goal, weekly hours, target
   skill IDs, known skill IDs and display name. Verify invalid selections
   are rejected by the API and the editor shows an error.
5. Apply saved preferences to the builder. Verify target/known skills and
   hours populate the form and that no pathway is generated automatically.
6. Test account switching, API offline errors, the retry action, reduced
   motion, focus visibility and both light/dark themes on narrow and desktop
   screens.
7. Verify the prior Anime.js local installation issue is resolved by
   reinstalling from the checked-in lockfile, not by deleting the lockfile.

Run these commands only after the PR is manually reviewed and squash-merged:

```powershell
Set-Location E:\Projects\nextrail
git status --short
git fetch origin
git switch main
git pull --ff-only origin main

python scripts/validate_repository.py
python scripts/validate_catalog.py
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/evaluate_pathways.py
python scripts/evaluate_api_reliability.py --iterations 12 --max-p95-ms 3000
python scripts/evaluate_storage_concurrency.py --workers 4 --steps 3
python scripts/validate_discovery.py
python scripts/verify_source_authorizations.py --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json
python scripts/verify_pre_release_acceptance.py --manifest data/pre-release-acceptance.sample.json --expect-blocked

Set-Location apps/web
npm ci --no-audit --no-fund
npm test
npm run build

Set-Location ../..
git status --short
git rev-parse HEAD
git rev-parse origin/main
git stash list
```

Stop on unexpected local Git changes, conflicts or failing tests. Do not
create worktrees, clean/reset the checkout, pop preserved stashes, merge
automatically, enable real providers, or activate paid infrastructure.

This PR provides the Phase 33 UI foundation. Browser QA and phase-level
approval remain outstanding, as do production acceptance Phases 25–29.
