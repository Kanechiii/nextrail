# Registered account mode — backend foundation

## Objective

Registered learners can set persistent onboarding and learning preferences without depending on the UI redesign. All account routes derive their owner solely from an authenticated server-side bearer session. Guests retain unrestricted access to course discovery and transient pathway generation.

## Account preferences

The authenticated `GET /v1/me/preferences` and `PATCH /v1/me/preferences` routes expose display name, career goal, weekly learning hours, target skill IDs and known skill IDs. These are stored in an isolated versioned SQLite sidecar with an account foreign key. The API validates selected skills against the current catalog, rejects unknown preference properties, and records changed field names (not goal text) in the existing append-only audit table.

The `GET /v1/me/overview` route provides account-scoped saved-pathway and saved-course counts plus progress from the latest saved pathway. It reports actual persisted records rather than synthetic analytics. It is not an AI inference endpoint.

## Migration safety

The sidecar creates its own `account_preferences_meta` version without changing `PRAGMA user_version`, existing authentication schema version, accounts, sessions, saved pathways or progress. Initialization rejects incomplete or unsupported sidecar schemas. The storage connection must have SQLite foreign keys enabled.

## Explicit scope boundary

No React components, CSS, color palette, navigation layouts, or other UI redesign files are changed in this phase. The distinct Phase 13 UI branch is independent and can be reviewed or merged later. Existing guest endpoints do not require a login or preference record. Persistent saved data requires a configured durable database path; the current default in-memory database is not production persistent.

Email verification, password reset delivery, deletion and export, security hardening for publicly exposed accounts, production cloud storage, and true cross-device hosting remain separately gated work.

## Verification

Run the existing backend tests plus `scripts/test_account_mode.py` through unittest discovery. GitHub Actions also runs frontend build and tests unchanged. Manual review should verify tenant isolation, existing schema preservation, valid skill selections, append-only audit behavior, and unchanged guest endpoints.
