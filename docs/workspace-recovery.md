# Global error boundaries and data protection — Phase 40

This milestone improves guest/account safety on responsive web browsers and
introduces conditional concurrency controls for saved learning progress.
**No** provider activation, paid service, deployment or account schema
migration is authorized by this work.

## Recovery contracts

| Scenario | Implementation |
| --- | --- |
| Unexpected React render error | A root and view-level error boundary expose retry and return-to-Discover controls without logging private component stacks or account data. Saved server state is not deleted. |
| Mobile background during pathway generation | The current in-memory plan and request snapshot remain intact while the tab is alive. A completed response is shown only after the backend confirms it; failed requests retain inputs. |
| Mobile network switches | The offline/online and page-visibility listeners offer a manual reconnect path and revalidate saved progress via read-only GET on return. Neither a network event nor resumed tab signs out the user or repeats a write. |
| Mobile browser Back in course detail | A transient browser-history entry closes the native dialog, restoring focus to its originating course control; no course, plan, or account state is erased. |
| Mobile keyboard with preferences | Field-level feedback, focus on the first invalid input, visible focus outlines and scroll margins accommodate the virtual keyboard and 320 px mobile layouts. |
| Two desktop tabs update progress | GET returns a monotonic `revision` and an HTTP ETag; new frontend sends `If-Match: "<revision>"` with PUT. If another update committed first, the storage layer rejects the stale write inside `BEGIN IMMEDIATE`, returning HTTP 409 without altering progress or its audit trail. |
| Invalid account/pathway forms | Specific inline error text and focus on the first invalid field; a bad form never sends a POST/PATCH. |
| Pathway save response lost | The existing account-scoped UUIDv4 idempotency key is reused only on explicit user action. A visible 'Check save status' control retries the same intent safely; it never creates another pathway or assumes the original response was successful. |
| Repeated API errors | The same error notification is suppressed for six seconds; different errors and persistent reconnection warnings remain visible. No remote logging or browser storage is introduced. |
| Reduced motion / enlarged text | Error and recovery controls remain operable with no required animation; CSS provides responsive wrapping, 16 px minimum form input text on mobile, safe-area placement and virtual-keyboard scroll margins. |

## Progress concurrency details

The revision is generated from the latest owner-scoped, append-only
`milestone/status_changed` audit event ID. This prevents an
update-then-revert ("ABA") sequence from silently appearing unchanged.
The revision is **not** a sensitive token and is invalidated on every
actual milestone change. Invalid conditional headers return 422, and
valid but stale headers return 409; 401 and 404 ownership behavior is
unchanged. GET progress replies use `Cache-Control: no-store`.

The conditional header is **optional** for backward compatibility with
existing API clients. Nextrail's new web client sends it for every saved
progress edit. Legacy clients that omit `If-Match` retain the old
unconditional behavior and are not protected against cross-tab races.
Before any future production launch, require up-to-date clients and
consider a versioned endpoint enforcing preconditions.

The saved-route snapshot, append-only audit and in-memory session model
are otherwise unchanged. There is no new table and no migration.

## Data privacy and limits

Guest and account form drafts remain **in browser memory**, as before.
Backgrounding/resuming a live tab preserves them; operating-system
termination or a full browser reload may discard them. The
`beforeunload` guard warns only when unsaved edits or an uncertain save
are present, subject to browser platform support; it is **not**
persistent backup or a guarantee against mobile OS tab eviction.
No password, bearer token or private guest plan is written to
`localStorage`, `sessionStorage` or an external service.

Component error boundaries cannot catch asynchronous or event-handler
exceptions; those continue through existing request handlers. A fatal
app-level render failure may lose a transient unsaved draft when the
application reloads. Users are warned without claiming otherwise.

The "Check save status" action is a **manual replay** of the same
idempotent POST, not a provider or account synchronization process.
A successful response is the only condition for the UI to say Saved.

## Verification

CI must pass all backend security and learning regressions, the new
cross-connection progress-conflict tests, frontend typecheck and unit
tests, the real Vite `npm run dev` smoke and Chromium interactions.
The existing UI and production acceptance registers must remain
explicitly blocked.

Human QA remains separately required:

1. Background a mobile browser mid-preview, return after success or
   interruption, and verify choices/route status accurately reflect
   confirmed results.
2. Switch Wi-Fi to mobile data; test session preservation, a persistent
   reconnect banner, and manual retry (no automatically repeated writes).
3. Open course details on mobile, press system/browser Back, and confirm
   dialog closes, opener receives focus and the plan remains.
4. Open preferences on a phone with the software keyboard visible,
   enter invalid hours, submit, inspect visible inline correction and focus.
5. Use two browser tabs for the same signed-in route: change milestone
   in tab A, then attempt stale edit in tab B. Confirm 409, preserved
   latest state, and read-only Refresh before another edit.
6. Trigger an isolated render error in a disposable development-only
   fixture and verify the section recovery panel (no private details).
7. Simulate loss of POST response after commit; use Check save status
   and confirm exactly one pathway/audit creation.
8. Generate repeated API faults and validate one persistent error toast
   rather than a new announcement for every response.
9. Verify 320 px and 400% zoom, both themes, reduced-motion and
   NVDA/VoiceOver; ensure visible form controls and notifications.
10. Repeat with disposable accounts and no approved real provider
    catalog records. Keep all release acceptance gates blocked.

These manual scenarios are **not certified** merely by automated
source checks or headless Chromium. The PR remains unmerged until user
review and approval.
