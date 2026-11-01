# Controlled Nextrail local demo and deployment-readiness handoff

This is a **localhost-only preview**, not a hosted demo, production release,
real-provider activation, or approval to use learner records. The repository
remains local-first, free-only, guest-first and intentionally fail-closed
against incomplete production acceptance evidence.

## Local demo safeguards

Before starting a demo, from the existing checked-out Nextrail repository
root run:

```powershell
python scripts/verify_local_demo.py
python scripts/verify_source_authorizations.py --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json
python scripts/verify_pre_release_acceptance.py --manifest data/pre-release-acceptance.sample.json --expect-blocked
```

The first command is a **read-only offline** check. It refuses to give a
local-demo PASS when any `NEXTRAIL_*` or `VITE_API_BASE_URL` environment
variable is configured, when the Vite host or API proxy is not loopback,
when a sample resource or source has been activated as real, when any sample
provider grant exists, or when a production sample acceptance gate has been
marked approved. It never starts a service, writes a database, contacts a
provider or authorizes public deployment.

After Phase 35 is merged, also run:

```powershell
python scripts/verify_ui_quality.py --manifest data/ui-quality-acceptance.sample.json --expect-blocked
```

This expected BLOCKED result confirms that desktop/mobile browser acceptance
has **not** been silently declared complete. It is not permission to skip the
review. All eight QA scenarios and ten production gates require separate
independent human verification before their respective release decisions.

## Two-terminal localhost walkthrough

Use a fresh, disposable terminal session with **no external/production
environment variables** configured. No paid service or cloud account is
required. The following installation commands use Python packages available
under ordinary open-source licensing.

**Terminal A — FastAPI** (repository root):

```powershell
python -m pip install "fastapi>=0.115,<1" "httpx>=0.27,<1" "uvicorn>=0.30,<1"
python -m uvicorn nextrail_api.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

Check `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/ready`
from the same workstation.

**Terminal B — Vite** (from repository root):

```powershell
Set-Location apps/web
npm ci --no-audit --no-fund
npm run dev
```

Open `http://127.0.0.1:5173/` locally. Vite's approved configuration
binds only to `127.0.0.1:5173` and proxies `/api` to
`127.0.0.1:8000`. Do not add `--host 0.0.0.0`, tunnel the service, configure
an external port forward, or activate hosted resources to show the demo.

The default API uses in-memory SQLite. **Optional test accounts and saved
progress do not persist across server restarts.** Never demo with real
passwords, private student records, production providers, or a reused
account database. If a process is already using either port, stop and
inspect the existing service rather than exposing a different interface.

## Suggested 5-part product walkthrough

1. **Discover as guest.** Explain that approved-provider listings and
   fabricated examples are intentionally separate. The synthetic sample
   has no approved real courses. Switch to the explicitly labeled
   Illustrative preview to demonstrate visual card treatment without
   suggesting real enrollment is available.
2. **Compare course information.** Select two or three illustrative cards
   and inspect source-review labels, independent access versus certificate
   costs, unknown/conditional prices and the absence of fake provider links.
3. **Build a learning pathway.** Select approved sample skill IDs and
   generate the deterministic prerequisite-aware route. Expand milestones,
   inspect rationale and explain that guest preview requires no account.
4. **Optional account and progress.** With a disposable local account,
   demonstrate explicit guest-plan saving, private learning preferences,
   milestone completion, saved-route overview and logout. Explain that
   progress is **self-reported**, not a certificate or third-party completion
   receipt.
5. **Safety and next steps.** Show the source authorization preflight,
   blocked browser QA register and blocked production acceptance inventory.
   State that no real provider ingestion, paid AI, hosted identity, encrypted
   backup or production deployment has been authorized.

## What should be shown in a project presentation

The source-of-truth project claims are: **guest-first route discovery**,
deterministic prerequisite-aware learning paths, optional saved account
progress, reviewed source-data contracts, and explicitly labeled sample
illustrations. Do not claim working live synchronization with Microsoft,
GitHub, Coursera, AWS, Anthropic, LinkedIn or any other provider.

Display a concise visual of the existing monorepo:

- `apps/web`: React/TypeScript/Vite Learning Route Workspace,
  provider-aware muted themes and bounded Anime.js motion.
- `services/api`: FastAPI with deterministic planning, verified-source
  contracts, optional accounts and SQLite safety.
- `data`: synthetic sample fixtures, permission registers and reviewed
  publication format. Real provider grants remain empty.
- `scripts` + `.github/workflows`: offline quality, reproducible builds,
  recovery and release-blocking checks.

Use only existing built functionality. No fabricated testimonials,
adoption metrics, live catalog totals, provider partnerships, course
ratings, certificates or system uptime claims.

## Production deployment is a separate gated decision

Future work may prepare free, reversible deployment architecture but must
not create a live hosted endpoint or issue credentials until a human
explicitly approves the cost, security, legal and operational scope.
At minimum validate:

- **Provider rights:** exact official-source permissions, authorization,
  reviewed catalog publication, freshness and allowed enrollment URLs.
- **Account protection:** production verified email ownership, recovery
  delivery, session management, rate limiting, privacy and erasure.
- **Infrastructure:** HTTPS, trusted reverse proxies, controlled secrets,
  durable protected backups, encryption, restore drills, rollback and
  incident response.
- **Performance and accessibility:** representative load, device-based
  browser QA, actual screen-reader testing, monitoring and observability.
- **Human approval:** all ten production acceptance evidence gates
  independently reviewed, with final sign-off after the preceding reviews.

A merge or successful CI run is not deployment authorization.

## Existing checkout maintenance after manual squash merges

From the repository root in PowerShell, inspect local changes first:

```powershell
git status --short
git fetch origin
git switch main
git pull --ff-only origin main
python scripts/verify_local_demo.py
python scripts/verify_pre_release_acceptance.py --manifest data/pre-release-acceptance.sample.json --expect-blocked
python -m unittest discover -s scripts -p "test_*.py" -v
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

Stop if the working tree contains unexpected changes or Git reports a
conflict. Never force-reset, clean, delete a preserved stash, or
automatically merge PRs. The existing checkout is the only intended
development workspace.
