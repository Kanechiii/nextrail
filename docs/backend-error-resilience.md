# Backend error resilience and user recovery contract

This is a bounded, local-first reliability milestone. It does **not**
authorize provider ingestion, hosted identity, paid services, or production
deployment. Existing security, provider-rights, database readiness and
pre-release gates continue to apply.

## HTTP failure behavior

The API preserves its current authorization, validation, and privacy contracts:

| Condition | Response | Client action |
| --- | --- | --- |
| Missing, revoked, or expired session | 401 with existing Bearer challenge | Clear signed-in state and offer sign-in |
| Invalid input | 400 or 422, depending on existing endpoint | Keep form input; correct fields |
| Resource not owned or missing | 404 | Do not expose other account's records |
| Same idempotency key, different plan | 409 | Stop; create a fresh explicit save after correcting inputs |
| Request throttled | 429 with `Retry-After` | Show wait guidance; do not retry automatically |
| SQLite unavailable or locked | 503 with `Retry-After: 3` and generic `DATABASE_UNAVAILABLE` code | Preserve the session; offer explicit retry |
| Network timeout/offline | Client-side typed error | Keep inputs, show unavailable state |
| Response is not parseable JSON | Client-side typed error | Keep local inputs; reload view deliberately |

The DB exception handler intentionally returns **no** SQLite error text,
internal query names, local paths, tokens, emails, or credentials.
`{"error":{"code":"DATABASE_UNAVAILABLE","retryable":true}}` is
machine-readable, but **does not guarantee** that any failed write did
not commit. Recheck the resource state before repeating writes.

## Pathway create idempotency

`POST /v1/me/pathways` accepts an **optional** canonical UUIDv4
`Idempotency-Key` header. Existing clients without this header retain
legacy non-idempotent creation behavior. The enhanced frontend generates
one random UUIDv4 per explicit save intent and retains it if a response
is lost or the request times out. A manual repeat of that **same** save
intent sends the same key; different input or a different signed-in
session produces a fresh key.

The backend uses a SHA-256 digest of the canonical validated PlanInput
body and an owner-bound SHA-256 key digest. Neither the key nor full
inputs are persisted to the sidecar. Under `BEGIN IMMEDIATE`, it
atomically inserts the new pathway, key record and append-only creation
audit event. A same-owner, same-key, same-input retry returns the original
pathway ID and stored snapshot without another write. Reusing a key
with different input fails with HTTP 409; sharing the same key across
different accounts never crosses owner boundaries. Deleting the saved
pathway cascades its replay record. File-backed SQLite keeps this
behavior across application restarts.

This table is an **additive v1 sidecar**, not a new schema version.
It is created during learning-store initialization with the existing
foreign-key protections. For production migration or disaster recovery,
independently verify schema compatibility, backup inclusion and
retention policy. Keys currently persist with their saved pathways;
a future retention/size limit is still an operational requirement.

**Never automatically retry an uncertain write.** The interface
supports manual retry with the original key, providing a safe
reconciliation path when a 201 response was lost after commit. Once
the server confirms the save, the frontend resets the pending key
and de-duplicates the displayed saved-route item by its ID.
The existing `PUT` milestone status endpoint is already naturally
idempotent for a repeated identical state.

## Frontend recovery

A 401 is the only failure class that invalidates the in-memory account
session during initial account loading. A temporary offline condition,
429 or 503 instead leaves the bearer session intact, reports a recoverable
loading problem and offers a retry. The progress panel now separates
loading, unavailable and confirmed states; it never labels a failed
progress read as an indefinitely loading operation.

A progress mutation is **not retried automatically**. On failure it
explains that the state is not confirmed and invites a fresh read. If
the mutation succeeds but the follow-up GET fails, the UI warns that
the update may have saved while retaining the last confirmed display.

The browser API client uses a bounded 12-second default request timeout,
safe messages for 429/503/401/409/422, numeric Retry-After parsing and
a typed API error. It does not leak server response content into the
UI and does not store tokens or pending save keys in persistent browser
storage. No hosted logging or telemetry service is activated.

## Verification

CI executes backend fault-injection tests, account isolation, durable
replay, audit rollback, current pathway/security tests, browser API
classification tests, frontend source-contracts, TypeScript build, and
the existing blocked production/UI acceptance registers.

Manual review remains required for:

- Network interruption while loading a signed-in account, followed by retry.
- Expired token (401) versus service outage (503) session behavior.
- DB busy lock, failed save, recovered save with the **same** UUID.
- Dropped response after DB commit, followed by a manual re-save with no
  duplicate pathway or audit record.
- Failed progress PUT versus successful PUT with failed following GET.
- 429 throttling with a real Retry-After header.
- Mobile and desktop retry controls, status announcements and keyboard focus.

Synthetic regression results are not real production fault-injection or
human accessibility approval. Follow the existing manual PR squash-merge,
local sync, and phase-level acceptance policy. Keep all pre-release gates
blocked until independently reviewed.
