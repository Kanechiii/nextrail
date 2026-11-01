# Learning Route Workspace — adaptive theme and course detail enhancement

This frontend-only milestone follows the backend pre-release evidence gate.
It does **not** certify production readiness: real-provider integration,
hosted account-security work, infrastructure readiness and independent
production sign-off remain blocked under the separate acceptance register.

## Design and behavior

- Preserve the existing Learning Route Workspace views: Discover,
  Pathway builder, and My learning. Guests can discover and preview a route
  without sign-in; optional account state remains in React memory.
- Add a light/dark toggle in the workspace header. The initial appearance
  follows the OS color-scheme preference, and the manual choice applies for
  the current page session. The switch is not stored in browser storage.
- Use a soft daylight palette alongside the existing dark botanical
  palette. Buttons, filters, route/progress panels, sidebar and auth modal
  receive corresponding surface and foreground colors.
- Keep three-column course discovery on larger screens and responsive
  cards on mobile. Each card now has a **View details** affordance.
- Present a landscape course-detail dialog with a restrained provider-themed
  abstract motif. Its presentation-only mapping recognizes Microsoft Learn,
  GitHub, Coursera, AWS, Claude, freeCodeCamp and LinkedIn. It falls back to a
  neutral theme for unfamiliar providers and all synthetic examples.
- Present provider, actual returned skill tags, access price status,
  certificate price status and review status **separately**, without creating
  ratings, course durations, descriptions, enrollment URLs, or free-certificate
  promises not present in the approved API.
- Synthetic examples remain explicitly illustrative and cannot show a
  fabricated enrollment link or bookmark action. Saving a real course while
  signed out closes the dialog before opening the existing sign-in flow.
- Buttons and navigation icons use restrained hover motion. Reduced-motion
  preferences disable these transitions and dialog entrance effects.
- The dialog has a close button and native dialog dismissal behavior; no
  application-wide keyboard shortcuts are introduced.

All provider accents are static, muted UI colors and do not constitute a
certification of official brand palette values. Provider approval is controlled
exclusively by the backend. The UI cannot activate a source or elevate an
unreviewed course.

## Verification

After manual review and squash merge, use the existing local `main`:

```powershell
Set-Location E:\Projects\nextrail
git status --short
git fetch origin
git switch main
git pull --ff-only origin main

python scripts/validate_repository.py
python scripts/validate_catalog.py
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/evaluate_pathways.py
python scripts/evaluate_api_reliability.py --iterations 12 --max-p95-ms 3000
python scripts/validate_discovery.py
python scripts/verify_source_authorizations.py --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json
python scripts/verify_pre_release_acceptance.py --manifest data/pre-release-acceptance.sample.json --expect-blocked

Set-Location apps/web
npm test
npm run build

Set-Location ../..
git status --short
git log -1 --oneline
```

Also manually inspect mobile/desktop light and dark themes, native dialog
open/close, provider palettes, no-source synthetic disclaimers, guest auth
entry, and focus visibility with reduced-motion enabled. Existing browser
e2e scenarios should be rerun when that harness is available. Stop on local
Git conflicts; do not use temporary worktrees, force-reset or pop preserved
stashes.

## Remaining UI work

This enhancement does not introduce Anime.js v4, external course images, new
course-source adapters, real-provider artwork, multi-step account onboarding,
or paid UI libraries. Additional visual motion should be introduced only
with reviewed accessibility, performance and bundle-size tests.
