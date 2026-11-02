# Mobile Lifecycle & Touch Recovery — Phase 41

Nextrail remains a guest-first, responsive web application. This phase covers
Android/iOS **browser** recovery; it does not add a native app, service worker,
background synchronization, push notifications, provider ingestion or any paid
service. The existing Phase 40 account/session boundaries and production
release gates remain unchanged.

## Recovery behavior

| Mobile event | Expected behavior |
| --- | --- |
| Browser moved to background | In-memory guest choices remain in the active tab. On return, a throttled, read-only progress refresh can check confirmed account state. Pending network writes are never silently replayed. |
| Wi-Fi/cellular handoff | An `offline` event shows a persistent connection warning, and `online` triggers bounded **GET** probes against `/ready` and `/v1/skills` before declaring the API usable. The user can also select Retry connection. Network signals alone do not invalidate login or prove API reachability. |
| Mobile Back with navigation drawer open | A temporary same-URL history entry closes the drawer. Back closes a course dialog first if one is open, restoring its opener focus; unrelated form choices remain intact. Navigation does not require intercepting the system Back button outside these overlays. |
| Device rotated | Responsive CSS reflows the card grid and form controls without changing plan/account state; open mobile navigation closes when the viewport becomes wide. No orientation lock is requested. |
| Software keyboard opens | `visualViewport` checks whether the focused input is actually occluded by a reduced visible viewport; only then does it scroll the already-focused control into view. This does not redirect focus or disable pinch zoom. |
| Rapid double taps | Synchronous, in-memory action gates reject repeated generate/save/bookmark/progress events before React's disabled state has rendered. Locks are released after confirmed success or error. This supplements existing backend idempotency and revision checks. |
| Limited motion/data | Touch targets aim for at least 44px on coarse pointers, with separate visible focus states, safe-area insets, no horizontal overflow, and existing reduced-motion/slow-update shimmer suppression. |
| Browser tab evicted or reloaded | By default **no guest draft is stored**. An explicitly chosen temporary checkpoint allows manual restore while same-tab session storage remains available. No guarantee of recovery after app termination or browser data clearing. |

## Optional guest checkpoint: informed manual action only

On the guest Pathway builder, the user can choose **Save temporary copy on
this device**. That one explicit action writes a validated subset of the
guest `Plan` (career direction, target and known skill IDs, weekly study
hours and free-learning preference) to `sessionStorage`. It never writes
passwords, account email, bearer tokens, saved account progress, reviewed
catalog content, or the full generated pathway.

A versioned record has a **six-hour** expiry from the original save.
Malformed, oversized, unexpected-field, future-dated and expired records
are rejected and pruned on read. The UI does **not auto-restore** the copy:
after reload the user sees a labeled Restore draft / Discard copy choice.
Restoring the planning inputs requires generating the pathway again; no
network POST is triggered by the restore action. Signing in or confirming
a saved account pathway clears the temporary guest copy.

This is **not encrypted storage**. Other scripts running in the same
browser origin can access sessionStorage; use the feature only for
non-secret planning choices. `sessionStorage` is generally scoped to
the tab's browsing context, but its availability after iOS/Android OS
eviction is implementation-dependent. It can be unavailable in private
browsing or under storage restrictions. If storage fails, the form
remains usable without a checkpoint. A background event never
automatically writes a draft.

The six-hour expiry is checked during checkpoint reads and on visibility
resumption; no continuous background timer or network access is added.

## Automated validation

The PR includes pure tests for checkpoint validation, expiry, explicit
storage, refusal of extra fields, private-mode errors, and independent
per-action touch gates. Frontend source contracts check lifecycle
listener cleanup, viewport focus handling, Back behavior, safe areas,
reduced motion, and read-only reconnection.

The existing CI runs Python backend/security tests and frontend tests,
typecheck and Vite production build, then starts **`npm run dev`**
with a disposable FastAPI backend. On a runner with headless Chrome,
the browser smoke additionally exercises a mobile viewport, drawer
Back navigation, explicit draft save/reload/restore/discard, rotation
without horizontal overflow, throttled search, reduced-motion and
connection retry. CI cannot emulate a physical iOS keyboard or
guarantee OS lifecycle events.

## Real device acceptance — still pending

1. **Android Chrome:** Start a guest plan, background for several minutes,
   return, and check inputs persist while the same tab is alive. Repeat
   during slow pathway generation; do not show success until confirmed.
2. **iOS Safari:** Background, switch to another app, return, and try
   orientation changes. Check the focused input remains usable above
   the software keyboard. Repeat on a device with the home indicator.
3. **Network handoff:** Move from Wi-Fi to cellular and back; verify
   the banner and manual retry, account session preservation, and no
   duplicated saved pathway or milestone update.
4. **Browser Back:** Open mobile drawer, press Back; open course details,
   press Back/Escape and confirm focus and plan are preserved. Verify
   navigation leaves the app normally when overlays are closed.
5. **Touch targets:** Try rapid repeated taps on Generate, Save, Bookmark,
   and Mark completed. Confirm no duplicate server events or misleading
   success notifications.
6. **Guest privacy:** Before explicit checkpoint action, inspect browser
   storage: no draft key. After opt-in verify only planning fields are
   stored; restore only after explicit action, discard, expire and
   inspect after account sign-in.
7. **Accessibility:** Test light/dark, 320px viewport, 200–400% text/zoom,
   screen reader announcements, focus indicators, reduced motion,
   virtual keyboard and scroll visibility with real device hardware.
8. **Physical low-resource device:** Inspect animation smoothness, time
   to interaction and repeated navigation. Simulated Chrome CPU
   throttling does not certify older Android hardware.

These checks require recorded human evidence before Phase 41 acceptance
and before the independent eight-case UI quality register can be marked
reviewed. The ten production-release gates remain pending. All merges
are manual squash merges under existing Conventional Commits rules.
