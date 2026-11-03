# Account synchronization readiness — Phase 49

## Scope and deployment boundary

This milestone strengthens **existing account persistence on one authoritative
SQLite database**. It is not a production multi-device service, replication
protocol, remote database migration, user-data export to a cloud provider, or
automatic sync client. Two sessions see the same account state **only if they
connect to the same manually configured, trusted backend instance/database**.
Separate offline databases on separate devices are NOT synchronized.

Guest course discovery, guest pathway generation and optional conversion of
guest choices to an account remain unchanged. No credentials or personal
learner data are stored in local browser storage or sent between tabs by this
change; existing authenticated endpoints continue to derive ownership from
the validated bearer token.

## Preference optimistic concurrency

Previously saved pathway progress already offered an opaque, account-scoped
revision and optional conditional `If-Match` writes. Account **preferences**
now use the same explicit *read → edit → conditional save* pattern.

1. `GET /v1/me/preferences` returns the original preferences JSON and a
   quoted 64-character hexadecimal `ETag` with `Cache-Control: no-store`.
2. The current Nextrail web editor retains the revision only in component
   memory. On `PATCH /v1/me/preferences`, it sends the quoted `If-Match`
   for the last confirmed server snapshot.
3. The server validates the revision and compares it **within the same
   `BEGIN IMMEDIATE` SQLite transaction** as the update and audit event.
   A stale revision yields HTTP **409**, without any preference or audit
   mutation. Malformed conditional headers yield **422**.
4. The web editor preserves unsaved local edits on a 409 and offers an
   **explicit** "Load latest saved preferences" action. The user confirms
   discarding their local draft before the newer server state is loaded.
   No last-write-wins silent overwrite, auto-merge or false save confirmation
   is performed by the current web client.
5. A successful preference edit returns a fresh `ETag`; an unchanged update
   does not bump the revision. Revision hashes use the owner ID and latest
   account-specific preference audit event ID, **not** second-resolution
   timestamps, private profile contents or global audit sequence numbers.
   Hence two rapid edits in the same second are still distinguishable.

Older API consumers that omit `If-Match` continue to use the existing PATCH
contract for compatibility, but **they do not receive conflict protection**.
Future cross-device clients should require conditional writes by default.
The public preferences JSON schema, existing SQLite schema versions and
account creation flows are unchanged.

## Read-only account change indicator

`GET /v1/me/sync/status` is a new authenticated, account-scoped snapshot
containing only a per-owner opaque `state_revision`, counts of saved pathways
and bookmarked courses, and explicit local-only/readiness indicators. It
returns a matching `ETag` with `Cache-Control: no-store`.

The state revision changes with recorded account operations such as saving or
deleting pathways, progress updates, bookmark mutations and preference saves.
It is based on the per-owner append-only audit stream. It does **not** expose
event IDs, progress details, goals, emails, credential hashes, bearer tokens,
source-provider data or full pathway snapshots. It does not poll, initiate
downloads, subscribe to changes or write to the database.

`hosted_cross_device_sync_configured=false` and
`shared_backend_required=true` deliberately tell future clients that
there is **no configured remote sync transport**. A client may compare two
status responses from the *same trusted backend* and explicitly fetch its
own account records when the opaque revision differs.

This endpoint is a **readiness signal**, not a durable event log for a future
network protocol, replacement for conditional progress writes, a promise that
two independently hosted databases agree, or a guarantee of notification in
real time. Future infrastructure must separately design an authenticated
transport, TLS, allowed origins, encryption and retention controls,
multi-instance consistency, backup/restore validation, session revocation,
credential safety, quotas and approved spending.

## Safety and acceptance

The current web client never silently promotes locally edited preferences to
confirmed account state following a rejected or unknown save. Stale-save
recovery is operator-controlled; genuine network failures remain retryable
without forcing an incorrect sign-out. A same-origin tab invalidation remains
best-effort; backend conditional writes are the correctness boundary.

A full independent review must verify:
- Two authenticated sessions sharing one SQLite database see identical
  confirmed revisions, and a stale second-session PATCH returns 409.
- A conflict does not write preferences or append an audit event. Explicit
  reload then conditional retry succeeds.
- An unchanged save leaves the ETag stable; same-second changed updates
  advance the revision.
- Invalid `If-Match` returns 422; legacy clients remain compatible but
  unprotected.
- Guest requests and revoked sessions cannot read account status; two
  different account owners have separate opaque revisions and counts.
- The new status endpoint never returns PII, tokens, pathway contents or
  provider permissions; it is read-only with no-store headers.
- No schema migration or cloud deployment occurs; the existing
  source-rights, zero-provider, frontend and production-release CI gates
  remain blocked exactly as before.

The tests use **disposable fictional accounts** and two concurrent API
connections to the same temporary SQLite file, not a hosted service.
They must pass alongside the existing authorization, account lifecycle,
backup, restore, optimistic progress, frontend and browser-smoke checks.

## Commands

From the current repository root:

```powershell
python -m unittest scripts.test_account_sync_readiness -v
python -m unittest discover -s scripts -p "test_*.py" -v
cd apps/web
npm test
npm run build
npm run test:dev
```

The phase is **engineering-ready for independent review** when CI is green.
Actual cross-device connectivity, hosted storage or production deployment
requires separate permission and infrastructure approval. User-controlled
manual squash merge and local synchronization are mandatory; no automatic
merge, paid infrastructure or worktree changes are included.
