# Learning route workspace

## Approved direction

The dashboard enhancement follows the user-approved learning route workspace for guests and registered learners. Editorial spacing supports reading; a dense console was rejected because first-time learners need a clear next action. This is a separate UI enhancement phase; deployment phase numbering is unchanged and canceled Bedrock work remains excluded.

## Design and implementation plan

1. Replace the promotional discovery opening with route planning and selectable milestones. Preserve anonymous discovery, deterministic generation, account ownership and memory-only authentication tokens.
2. Introduce light, dark and system themes with persistent theme preference. Use quiet emerald surfaces and restrained gold achievements. Energy 2, rhythm 2, motion 2. Use system typography for readable familiar controls without external font requests.
3. Extract accessible course cards, landscape details, comparison and shared dialogs. Hover previews must remain hoverable, dismissible and viewport-contained; explicit activation provides a modal dialog. Mobile details stack vertically.
4. Keep course access and certificate costs independent, use only available catalog facts, and distinguish synthetic demonstrations. Provider branding requires verified values; unknown providers use the neutral emerald fallback.
5. Preserve guest drafts through sign-in, expose saved routes and actual progress, resolve bookmarks where data is available, and provide removal controls and honest unavailable states.
6. Add URL discovery filters, loading placeholders, error/retry states and accessible status feedback. Course comparison is available to guests. Custom keyboard shortcuts are excluded.
7. Use existing Lucide icons, CSS feedback and Anime.js v4 for scoped route transitions. Reduced motion disables movement. Completion feedback follows successful server updates.
8. Verify build, backend regression tests, pathway evaluation, behavioral tests, desktop/mobile browser flows and both themes before merge.

## Verification focus

Guest routes remain anonymous. Signing in must not discard the draft. Account changes must not display previous account progress. Hover previews must not steal focus or disappear while the pointer enters them. Unknown catalog fields must not become fabricated ratings, descriptions or durations. Filter history must restore with Back/Forward. Theme and motion preferences must not affect data correctness.

## Delivery boundary

Use focused Conventional Commits and one reviewable PR with Summary, Motivation, Scope, Verification and Goals only. No automated merge, deployment, paid service or Bedrock activation. Only completed goals may be checked. Record verification limitations honestly.
