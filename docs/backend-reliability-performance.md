# Backend reliability and performance — offline baseline

This is a **backend-first Phase 28 milestone**, not approval for production
hosting. The runtime retains guest-first routes and existing authentication
contracts. No frontend changes, paid infrastructure or external provider
requests are introduced.

## Database-aware readiness

`GET /health` remains a lightweight process-liveness endpoint and returns
`{"status":"ok"}` even when the database is unavailable.

`GET /ready` now also checks the active SQLite connection for the expected
learning and auth schema versions. It returns HTTP 503 with a generic,
non-sensitive error if the connection is closed, inaccessible or missing the
required metadata. The existing reviewed-catalog freshness gate still runs:
a stale reviewed catalog also fails readiness. This is a constant-work probe;
it is **not** a full SQLite integrity check. Use the separate offline
`scripts/verify_database_readiness.py` command for database and backup
validation. Existing read/write account endpoints retain their current
contracts and are not converted into new transaction or retry systems.

## Synthetic guest performance smoke gate

Run from the existing repository root:

```powershell
python scripts/evaluate_api_reliability.py --iterations 12 --max-p95-ms 3000
```

The tool uses FastAPI's in-process TestClient with an in-memory synthetic-only
catalog and no account records, network calls, worker pool or external services.
It exercises five guest routes: liveness, readiness, skills, courses and
deterministic pathway preview. It checks expected HTTP 200 responses,
`Cache-Control: no-store`, a fixed request count and per-route p95 response
latency. Output consists only of aggregate route-level counts and timing
statistics; response bodies, tokens, email addresses and credentials are not
logged. The route count is bounded to 1–20 iterations to avoid guest preview
rate-limit exhaustion. The CI budget is a generous 3000 ms per-route p95
**smoke threshold**, not a service-level objective, capacity guarantee or
cross-machine performance comparison.

The metric uses the nearest-rank p95 statistic, which is noisy with a
small sample. Collect separately approved representative hardware and staging
baselines before setting production SLOs or interpreting microsecond-scale
differences. Real concurrency, reverse proxies, load shedding, database lock
contention, fault injection, memory growth, distributed rate limiting,
multi-host scaling and operational telemetry must be evaluated before launch.
Do not use real users' accounts or actual provider data for stress tests.

## Local sync after manual squash merge

Do not create extra worktrees, change preserved stashes, or force a merge.
Run the established validation sequence in the existing Nextrail directory:

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

Set-Location apps/web
npm test
npm run build
Set-Location ../..
git status --short
git log -1 --oneline
```

If git reports conflicts, uncommitted changes or divergent history, stop and
inspect without resetting, cleaning or popping stashes. This does not
authorize the separately outstanding Phase 25 real-source integration,
Phase 26 production authentication, Phase 27 hosted infrastructure or
the final pre-release security/production gate.
