# Advanced Learning Dashboard — route timeline and course comparison

This Phase 32 frontend milestone expands Nextrail's Learning Route Workspace
using only the current course, skill, pathway and account-progress APIs. It does
not change provider authorization, account security, the catalog contract,
backend storage, paid-service rules, or the blocked production release gate.

## Interactions added

**Discover — compare up to three returned resources.** Each course card has
an accessible Compare control. The in-page comparison surface displays only
existing API fields: provider, access cost, separate certificate cost, skill
coverage, evidence status, and an official source URL if supplied by an approved
non-synthetic record. It never generates ratings, fees, course duration,
certificates or new URLs. Compare buttons indicate their selection with
`aria-pressed`, refuse a fourth selection and can remove individual choices
or clear the list. Searches, filters and catalog-mode switches clear the
transient comparison state to avoid mixing stale or unrelated results.
`Illustrative preview` comparisons are prominently labeled as fictional and
contain **no enrollment links**. The side-by-side table has proper column and
row headings and is horizontally scrollable with keyboard focus on small
screens. Nothing is stored in browser local or session storage.

**Pathway builder — inspect a real prerequisite-ordered timeline.** The
frontend displays the exact milestones returned by `/v1/pathways/preview`
using an ordered route. Each disclosure shows rationale, prerequisite names
available in the skill catalog, and the number of referenced resources. It
does not infer duration per step, automatically mark achievements, or invent
resource links when only a resource ID is available. The guest preview clearly
states that progress is not saved.

**My learning — inspect and update saved progress.** The same timeline
reads the selected, authenticated saved route, joins self-reported progress
from the existing account endpoint by skill ID, and offers explicit
Mark completed / Mark as not started actions. The application continues to use
the original authenticated progress-update request, then refetches progress
from the server. The completion display and accessible numeric progressbar
use that server-derived information. Saved resource cards display titles and
provider details only when the current catalog response includes those
records; otherwise the original saved ID is shown without inventing metadata.

## UI/UX and accessibility

- Keep the existing botanical soft-light/dark theme and restrained Anime.js
  motion system. New route nodes use a vertical connector, distinct milestone
  states, expandable details, and visible focus outlines.
- Comparison uses a single responsive panel instead of a blocking overlay;
  table headers and independent cost rows remain readable when horizontally
  scrolled. No global keyboard shortcuts are introduced.
- Route disclosures use native buttons with `aria-expanded` and
  `aria-controls`; comparison is announced through its live region. Native
  focus and reduced-motion preferences remain effective.
- Do not interpret progress labels as educational certification, and do not
  interpret an approved-source display as permission to ingest or publish
  content outside the existing backend contracts.

## Verification and limitations

Run `npm ci --no-audit --no-fund` when a local checkout still lacks the
Anime.js 4 dependency after the previous Phase 31 merge. A stale
`node_modules` directory can cause `TS2307: Cannot find module 'animejs'`
even though the committed package and lock files are correct.
Do not delete the package lock or force-install unrelated packages.

Run `npm test` and `npm run build` from `apps/web`. CI also executes
the entire unchanged backend and intentionally blocked pre-release suite.
Node source-contract tests do not replace rendered-browser interaction tests.

After manual squash merge, verify on desktop and mobile, in both themes:

1. Discover: select two and three courses; compare costs, skills and evidence;
   verify fourth selection is disabled, removal works, and changing filters
   clears the selection. Check horizontally scrolled table by keyboard.
2. Illustrative preview: compare synthetic examples. Verify both the compare
   panel and course detail dialog explicitly warn that they are examples and
   expose no official enrollment links.
3. Guest pathway: generate a real preview with the running API, expand
   different steps, verify prerequisite ordering and that no save/progress
   changes occur until the user chooses to authenticate.
4. Saved route: with an approved disposable test account, change completion
   on the selected route and confirm the timeline and percentage reflect the
   refetched authenticated API response.
5. Saved resources: verify missing catalog items display the original
   reference without fabricating metadata or URLs. Test with the API offline.
6. Verify pointer/keyboard navigation, focus visibility, reduced-motion,
   narrow-screen wrapping and no horizontal page overflow.

Local synchronization, from the existing checkout only:

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
python scripts/evaluate_storage_concurrency.py --workers 4 --steps 3
python scripts/validate_discovery.py
python scripts/verify_source_authorizations.py --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json
python scripts/verify_pre_release_acceptance.py --manifest data/pre-release-acceptance.sample.json --expect-blocked

Set-Location apps/web
npm ci --no-audit --no-fund
npm test
npm run build

Set-Location ../..
git status --short
git rev-parse HEAD
git rev-parse origin/main
git stash list
```

Stop on unexpected Git state instead of resetting, cleaning, or modifying
preserved stashes. Approval requires manual browser QA, a passing latest-head
CI run, manual PR squash merge and explicit phase-level confirmation.
Production deployment and real-provider activation remain blocked by
the outstanding Phases 25–29 requirements.
