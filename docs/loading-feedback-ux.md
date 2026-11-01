# Workspace loading and feedback — Phase 38

This standalone frontend enhancement improves perceived responsiveness
without inventing courses, changing the guest/account contract, introducing
hosted notification services or enabling paid infrastructure.

## Genuine loading states

- The reviewed-course catalog initially renders three layout-matched
  course-card skeletons, including artwork, title, controls, tags, source
  information and footer. On filter changes the skeletons return until
  the actual `/v1/courses` response resolves.
- A failed catalog fetch renders a **retryable error panel**, not the
  “zero courses available” state and not synthetic or fabricated results.
  Empty catalog output is shown only after a successful empty response.
  The synthetic illustrative tab displays its known locally defined
  examples immediately and remains unmistakably marked illustrative.
- Pathway generation shows a route timeline skeleton during the request;
  pending generation keeps the submit button disabled and provides a
  visible spinning icon and text. No pathway is considered ready until
  the API confirms it.
- When opening a signed-in workspace, stats/dashboard panels load as
  skeletons until account data resolves. Preferences and selected saved
  progress have separate skeletons. Input skill choices have loading
  placeholders until the skill catalog request settles.
- Existing error and retry flows from the prior backend recovery milestone
  remain active. Inaccessible or unavailable services cannot leave the
  interface perpetually “Loading…”.
- Pending account authorization, saved pathway, course bookmark, profile
  save, guest-plan save and milestone actions show text and a busy spinner.
  No optimistic success or automatic write retry has been added.

## Notification design

- A fixed, nonblocking toast region displays clear **success, error and
  informational** messages. To prevent visual overload, at most three
  distinct messages are visible, and repeated messages replace the prior
  notification with a newly generated ID.
- Success notifications disappear after 4.5 seconds, information after
  six seconds; errors stay until dismissed. A timer pauses on hover and
  keyboard focus, with cleanup on unmount.
- Each notice has a keyboard-operable dismiss button. Success/info use
  `role=status` and errors use `role=alert` for assistive technology.
  Notifications are not persisted and never include raw tokens, API
  stack traces, provider data or user passwords.
- A success toast occurs only after confirmed completion: saving a
  pathway/course, updating preferences, generating a route, or receiving
  confirmed progress. Failed POST/PUT or an unconfirmed follow-up progress
  read never produces a false success.
- Sign-out messaging says only that the current browser session ended,
  not that remote revocation succeeded if the backend was unavailable.
  No toast is shown for every keystroke, theme switch or trivial local
  selection change.

## Animation and accessibility

The shimmer is a muted CSS gradient sweep matching the real card and panel
geometry. Unlike perpetual spinner overlays, it is rendered **only while
data is genuinely pending** and uses no external animation library or
network request. It is lightweight (transform-based and opacity only),
responsive and compatible with both the existing light/dark palette and
provider-accented course cards. The existing Anime.js v4 route and
course-detail animations remain unchanged.

`prefers-reduced-motion: reduce` disables shimmer, spinner rotation and
toast entrance animation, but placeholders and readable labels remain.
Decorative skeleton shapes are hidden from the accessibility tree and
the loading container supplies concise status text. Focus-visible styling
is provided for toast dismissal.

## Desktop/mobile QA gate

CI tests the bounded toast queue, transitions from pending to success/error,
existing call/error contracts, accessibility semantics, build and regression
suite. Browser review remains separate:

1. Refresh with DevTools network throttling. See course-card skeletons
   before a real response and no empty state until success/failure.
2. Disconnect the backend and refresh. The catalog must end in a retryable
   error state; switching to illustrative mode must never fabricate live
   provider links.
3. Generate a guest pathway using a slow API response. The route timeline
   skeleton and pending button must stop on both success and failure.
4. Sign in with a disposable local account and test dashboard, profile and
   progress loading. Failed requests should retain the appropriate session,
   with explicit recovery controls.
5. Save a reviewed course or pathway, change progress, and save profile
   preferences. Confirm the spinner and success toast match the verified
   result. Simulate a failed write: do not show success.
6. Test toasts via pointer and keyboard: dismiss, pause on hover/focus,
   visible errors, and no focus disruption or dialog interference.
7. Verify light/dark modes on small and large viewports, plus
   `prefers-reduced-motion: reduce` (animations absent; content readable).
8. Confirm no paid service, unreviewed course URL, provider activation
   or production release setting was introduced.

## Additional considerations

Consider evaluating delayed skeleton reveal (100–150 ms) if very fast
responses produce unwanted flashing, but do not insert artificial API
latency. A future app-wide retry/pending pattern could be integrated
using a standardized request-state hook rather than duplicating state
per feature. Real browser/assistive-tech testing should confirm whether
toast announcements are overly verbose before adding more notifications.

Formal release blockers from Phases 25–29, the UI acceptance register,
and all branch/PR manual squash-merge rules remain unchanged.
