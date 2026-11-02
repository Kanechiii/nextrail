# Desktop Reliability & Cross-Device QA — Phase 42

Nextrail is a responsive, guest-first web app. This milestone improves
multiple-tab reliability and keyboard/zoom recovery without adding a server
dependency, remote analytics, paid integrations, browser extension or native
app. It does **not** authorize a public release or external provider access.

## Progress changes across tabs

A valid signed-in account already uses a monotonic, opaque progress revision
and conditional `If-Match` writes, with an atomic SQLite 409 conflict when
the revision is stale (Phase 40).

This phase adds a **best-effort** `BroadcastChannel` signal following a
**confirmed** progress PUT. The message is the fixed, anonymous object
`{"kind":"confirmed-progress-updated"}`. It contains no account email,
pathway ID, skill, completion data, bearer token or progress revision.
Nothing is written to localStorage, sessionStorage, IndexedDB or a provider
service. Browser support or denial is handled safely: no channel means
relying on the existing server-side `If-Match` guard.

When a second same-origin tab receives a signal while a saved pathway is
selected, the tab shows a quiet **Progress may have changed** notice and
disables milestone writes. **Load latest progress** explicitly reads the
server state and clears the notice **only** after a successful GET.
A rejected or raced GET leaves the control blocked and preserves an error.
The latest state is never silently written over an account's progress.
A conflict HTTP 409 produces the same guarded recovery affordance.

A generic signal can originate from a different signed-in account in
another tab on the same browser origin. In that case the extra warning is
harmless; it does not reveal which account updated, and the current tab
reloads only its own authenticated progress on the user's request.

Limitations: BroadcastChannel is an *advisory* same-origin event, not
durable synchronization and not a substitute for ETags. Older API clients
can still omit `If-Match`. Requiring this header globally must be decided
in a separately reviewed API compatibility milestone.

## Desktop dialog and responsive accessibility

The optional account dialog now traps Tab/Shift+Tab within the overlay,
initially focuses the email field, supports Escape, and restores focus to
its original opener (or a stable theme control). Switching login/register
modes focuses the correct input. The dialog is bounded under a narrow
viewport and remains scrollable rather than pushing actions off screen.

Progress recovery banners wrap long text and provide 44px minimum button
targets, visible focus outlines, light/dark styles, high-contrast
`forced-colors` support and reduced-motion behavior. The backend does
not receive any additional private state through these changes.

## Verification gates

Automated CI should run the full offline Python backend regression and
source/privacy tests, frontend Node tests, TypeScript/Vite build and
`npm run test:dev` on localhost. When headless Chrome is available the
dev smoke test additionally checks:

1. Guest discovery, debounced search, skeletons, reduced motion, mobile
   Back navigation and the Phase 41 manual guest draft recovery.
2. Keyboard Tab/Shift+Tab focus containment and Escape/opener restoration
   in the optional account dialog.
3. A synthetic local account and saved pathway. A second API client
   commits a real milestone update using the correct `If-Match`.
   An anonymous invalidation reaches the UI, disables stale writes, and
   an explicit refresh retrieves the latest completed milestone.
4. A 320 CSS-pixel desktop viewport with no horizontal document
   overflow, approximating 400% zoom on a 1280px desktop.

This test simulates a separate tab's signal using another channel
instance; it is **not** an exhaustive two-real-browser-tab session or
an actual physical 400% zoom test.

## Manual cross-browser and assistive-technology acceptance

All remain pending until evidence is recorded:

1. Sign into the same disposable account separately in two desktop
   tabs. Change progress in tab A; verify tab B's banner, disabled
   controls and explicit latest-state refresh.
2. Repeat with BroadcastChannel unavailable to confirm the backend
   returns 409 rather than overwriting new progress; verify the
   error and recovery control remains usable.
3. Use two different accounts in the same browser origin and verify
   no account data is shown through the generic invalidation notice.
4. Use Windows Edge, Windows Firefox and Chrome for actual keyboard
   navigation, course dialog Escape/Back, account Tab cycling and
   return-to-opener focus.
5. Check zoom at 200%, 300% and 400% and at 320px CSS viewport, with
   screen-reader text enlargement; no hidden critical controls or
   horizontal page scroll.
6. Test NVDA + Edge/Firefox and VoiceOver + Safari for dialog naming,
   focus announcements, progress status, stale-update warnings and
   retry controls. Chrome CDP cannot certify these results.
7. Test dark/light themes, OS high-contrast/forced-colors and reduced
   motion with a real user device, plus slow/CPU-limited operation.
8. Repeat on Android Chrome and iOS Safari for Phase 41 lifecycle,
   orientation, visual keyboard and guest checkpoint privacy.
9. Verify the source authorization registry still rejects unapproved
   providers; reviewed catalog must remain empty without evidence.
10. Record manually reviewed outcomes in a **separate evidence copy**
    before changing any UI-quality or release-acceptance state.

The eight desktop/mobile UI-quality sample cases and ten production
release approval gates remain **pending** by design. Passing CI does not
advance those human gates. Only the user may approve a squash merge.
