# Learning Route Workspace — bounded Anime.js motion

This Phase 31 frontend milestone extends the existing Learning Route Workspace
without changing the guest/account flow, course-source approval, backend
schema, paid-service policy, or the blocked production-release register.

## Motion approach

- Pin **Anime.js v4.5.0** (stable v4) in both `package.json` and
  `package-lock.json`. Animation is implemented with documented
  `animate`, `stagger`, `createScope` and SVG `createDrawable` APIs.
  No hosted animation service or paid dependency is introduced.
- Use a React-scoped animation controller for the workspace. It limits
  first-entrance and navigation animation to the visible section; no
  perpetual loops or global selector ownership. On view transitions and
  component cleanup, scoped animation state is reverted.
- The Discover learning-map SVG path draws once when that view becomes
  active. Selected navigation icons, section headings, and up to eight
  currently displayed course card bodies receive restrained entrance motion.
  The Pathway builder animates at most twelve milestone rows.
- In My learning, the accessible progress indicator derives its percentage
  **only from the existing stored progress response**. It animates the
  visual fill from the left and optionally provides small completion-icon
  feedback. Course completion is still user-reported, not verified learning.
- Course details retain a **native HTML dialog**, existing cost/evidence
  disclaimers, Escape behavior, and synthetic-resource restrictions. The
  landscape visual and a few fact rows receive a scoped entrance effect.

Animations are decorative and last less than a second. They do not delay API
requests, create hidden enrollment links, bypass source evidence, change
auth/session data or animate whole pages indefinitely. Element selection is
local to the current workspace/dialog. Targets are capped to limit CPU and
memory load on modest devices.

## Accessibility and failure handling

Both the workspace and course dialog consult
`prefers-reduced-motion: reduce`. When it matches, JavaScript animation is
not created and the existing CSS reduced-motion rules remain in effect.
Workspace animations also respond to live OS preference changes: active
scopes are reverted when reduced motion becomes enabled. All content
remains present and readable without animation.

The progress bar exposes `role="progressbar"`, a label, and numeric
`aria-valuenow`/minimum/maximum, and its value is also written as text.
Progress-toggle buttons expose `aria-pressed`, with visible focus states.
There are no application-wide keyboard shortcuts.

The theme toggle remains manual and local to the page session.
No animation settings, session tokens, or learner data are stored in
`localStorage` or `sessionStorage`.

## Manual desktop/mobile QA

Before approving the PR, review at desktop and narrow mobile widths in
both light/dark themes:

1. Switch among Discover, Pathway builder and My learning; confirm
   navigation, layout stability, and readable typography.
2. Open and close synthetic course details with keyboard and pointer;
   ensure no fabricated enrollment URL or save action is shown.
3. Generate a valid guest pathway and verify milestone order and descriptions
   are unaffected by animation.
4. With a disposable test account, save a pathway and mark a milestone;
   confirm the text percentage, accessible progressbar, and icon agree with
   the API response (do not use a production account).
5. Enable reduced motion before opening the page, then toggle it while the
   page is open. Content must remain visible, keyboard focus should remain
   usable, and no animation should continue under the reduced setting.
6. Check reasonable CPU and rendering performance on a low-powered
   device. This PR does not claim full browser accessibility certification.

Run `npm test` and `npm run build` within `apps/web`, plus the established
backend and release-blocking regressions from the repository root.
After manual squash merge, use only the existing local `main` checkout,
without extra worktrees, branch resets, or touching preserved stashes.

## Remaining roadmap

This is the Phase 31 advanced motion foundation. Phase 32 dashboard
interactions and route visualizations, Phase 33 account experience,
Phase 34 reviewed source UX, and Phase 35/36 release work remain separate.
Production activation and real-provider onboarding are still blocked by
the independent Phases 25–29 acceptance requirements.
