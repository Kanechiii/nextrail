# Learning persistence and audit contracts

## Scope

Nextrail course discovery and guest pathway generation remain fully independent of database accounts. This storage facade only persists optional account-linked saved courses, pathways, milestone progress, and audit events. No authentication endpoints, public APIs, external providers, paid services, or cloud databases are introduced.

## Database

Use Python standard-library SQLite. `open_database()` provides an ephemeral in-memory database; `open_database(path)` creates or reopens a private file. Existing repository ignore rules exclude SQLite database files and WAL/journal sidecars.

Version 1 is created inside a transaction through `PRAGMA user_version`. The migrator rejects unsupported versions, incomplete schemas, and unversioned databases that already have application tables. It never destroys or overwrites unknown previous application data.

Tables: `learning_pathways`, `milestone_progress`, `saved_courses`, and `audit_events`. Milestone progress is constrained by owner and saved-pathway foreign keys. All state modifications and audit records are committed atomically. Repeated saves and identical progress updates are idempotent.

## Ownership boundary

Every data operation uses an opaque account owner identifier. The storage layer validates syntax and uses owner-scoped SQL for reads and writes, which prevents accidental cross-account query mixing. **This is not authentication**. Callers must obtain owner identity from a verified server-side session. Exposing arbitrary owner IDs in an unauthenticated API would be unsafe. Authentication and account lifecycle belong to the backend authorization phase.

Guests must never require storage to explore catalog resources or generate transient pathways.

## Audit trail

Audit records contain only entity identifiers and minimal status changes, not goals or full pathway text. SQL triggers reject normal updates or deletions. These controls are append-only at the application level, **not tamper proof** against database administrators. Event IDs support cursor pagination.

Privacy, retention, account deletion, and backup policies remain to be designed and approved before production account storage. No production data is created by this phase.

## Other boundaries

Saved pathway snapshots are structurally checked against the v1 output shape, but this package does not itself re-validate learning content against the current catalog; future authenticated API code must integrate the orchestration and evidence checks before saving. Saved course references do not assert eligibility, availability, or verified prices. Cross-device synchronization is not yet implemented.

## Validation

`python -m unittest discover -s scripts -p "test_*.py" -v`

`python -m compileall -q services/api/nextrail_storage`
