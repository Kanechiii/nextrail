# Responsive feedback refinement — Phase 39

This milestone extends the Phase 38 shimmer and toast system while preserving
the user-controlled PR merge process, synthetic-only provider fixtures,
account/session boundaries, and deliberately blocked production release.

## Debounced and cancelable public catalog search

The text input updates immediately, while a reviewed catalog API request
uses a **280 ms** debounced query. Every previous catalog request receives
an AbortController cancellation on new text input, mode change, or dependency
change; canceled requests are ignored, not treated as offline, and do not
overwrite more recent results. Course/source/cost filters still apply without
deliberately delaying their requests. Illustrative examples are filtered
locally with the immediate input and never trigger provider ingestion.

The typed API client now supports an optional external AbortSignal alongside
its existing bounded 12-second timeout. Explicit cancellation is reported
internally as `REQUEST_CANCELLED`, separate from `REQUEST_TIMEOUT`,
`NETWORK_UNAVAILABLE` and HTTP 429/503. The abort listener and timeout
are cleaned up. No network write is automatically retried.

## Delayed skeletons without artificial latency

A shared timer exposes skeleton artwork only after **150 ms** of actual
pending state. Requests always run immediately when eligible. Short
requests still have an accessible loading status without flashing a
multi-panel shimmer. Long requests show the existing course-card,
dashboard, preferences, progress, route or skill-selection skeletons.
They disappear on success or failure; empty/error states are never
confused with loading.

Shimmer remains light/dark compatible, avoids per-bar forced GPU
`will-change`, uses `contain:paint`, and is disabled under
`prefers-reduced-motion`, `update:slow` or reduced-data preference.
Real low-power hardware profiling remains necessary.

## Success transformations and notifications

Confirmed writes briefly show a checkmark and Saved/Updated label on
bookmarked course controls, profile Save, and route milestone updates
for **1.6 seconds**. Existing pending button spinners remain. Pathway
save and guest-plan transfer navigate to My learning and show a success
toast instead of delaying their confirmed navigation for animation.

The bounded toast queue keeps success/info and persistent error
messages, with polite/assertive live-region semantics. Toast arrival
does **not** grab focus. A keyboard user who dismisses a focused toast
is moved to another toast control or the persistent theme control
rather than losing focus to the document body. This is DOM-level
accessibility; an actual screen-reader review is still required.

## Persistent connectivity banner

The workspace shows a muted banner when transport fails or the API is
temporarily unavailable. A 429 response, a canceled request, an empty
reviewed catalog and invalid input do **not** imply an outage. The banner
offers an explicit **Retry connection** button. That action checks
`/ready` and `/v1/skills` using bounded timeouts and refreshes the
catalog upon success. No background polling, automatic writes,
paid connectivity service or provider crawling was added.

## Automated dev-server verification

After `npm ci --no-audit --no-fund`, run:

```powershell
Set-Location apps/web
npm test
npm run build
npm run test:dev
```

`npm run test:dev` starts an isolated localhost FastAPI process and
the **real** `npm run dev -- --strictPort` Vite process. It reads
`http://127.0.0.1:5173` and the proxied catalog and skills endpoints,
ensuring zero approved real sample courses. When Chrome/Chromium is
available, headless browser/CDP checks exercise rendered guest discovery,
rapid search keystrokes, delayed shimmer under simulated 4x CPU/slow
network, reduced-motion style, a confirmed guest-pathway toast and
keyboard focus, simulated offline state and manual reconnection.

The smoke test uses local disposable in-memory data, binds loopback only,
does not log account passwords, and terminates its child processes.
It is not a production load test or an actual screen-reader/user-hardware
session; simulated CPU slowdown is explicitly **not** equivalent to an
older laptop.

## Manual acceptance matrix (still required)

1. Desktop and mobile refresh using real backend and browser DevTools
   slow network. Verify first 150 ms has no flash and long loads
   show believable cards without fabricated provider content.
2. Type several queries quickly and inspect requests. Old requests
   should abort, final catalog must match the last query, and a 429
   should not show an offline banner.
3. Disconnect and reconnect FastAPI. Confirm persistent banner,
   manual retry, and retained guest choices and session state.
4. Confirm checkmark transitions after course bookmark, saved
   profile, and milestone progress; failed/uncertain writes must
   never show Saved/Updated.
5. Keyboard through toast dismissal and native course detail dialog;
   test live announcements in NVDA, VoiceOver or another actual
   screen reader on desktop/mobile.
6. Test an actual low-powered device, light/dark mode, 320px and
   wide screens, OS reduced-motion and low-data settings.
   Verify scrolling, nonblocking toast, CPU responsiveness, and
   animation preferences.

The previous Phase 35 manual UI evidence register and all ten formal
production release gates remain pending. Passing this PR's CI does not
approve public hosting or real-provider ingestion. Manual squash merge
and local sync are still mandatory.
