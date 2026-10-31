# Registered account learning workspace

## Integration and dependency

This work is developed concurrently with the shared UI design system but is reviewed as a stacked pull request based on `feat/ui-foundations`. Merge the design-system PR first, then retarget and verify the account-workspace PR against `main` before considering its merge. No force-push or history rewrite is needed.

## Registered mode

After successful authentication, the existing My Learning route renders an account-specific workspace with Overview, My Pathways and Saved Courses sections. Overview statistics are calculated exclusively from authenticated API responses. Milestone completion uses the previously implemented account-scoped progress endpoint; course bookmarks use the existing private saved-course endpoint. No synthetic course enrollments, fabricated progress metrics or new third-party integrations are introduced.

The workspace includes authenticated empty states, route selection, return-to-builder navigation, sign-out, and a compact responsive overview. Navigation and visual treatments reuse Phase 13's theme token contract. Public discovery and pathway preview remain guest accessible.

## Privacy and persistence limitations

The web client retains the existing in-memory bearer session behavior. Reloading the page ends that browser session; credentials and tokens are not placed in browser storage. Account-linked progress is held by the backend only when configured with a persistent database file. The default in-memory database is suitable solely for development demonstrations and does not persist across backend restarts.

Profile edits, password changes, onboarding preference persistence, email verification, account deletion, and production-scale cross-device synchronization remain outside this UI phase and must not be represented as completed.

## Verification

Run `npm test` and `npm run build` from `apps/web`. Verify guest navigation remains unauthenticated, sign-in reveals the private workspace, actual saved-pathway progress updates work, and light/dark appearance remains consistent. Automated contract tests are necessary but do not substitute for browser and accessibility checks.
