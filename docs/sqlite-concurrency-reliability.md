# Offline SQLite contention and fault-recovery baseline — Phase 28

This milestone adds a **bounded, synthetic, single-host SQLite concurrency gate**.
It does not run against real learner records, start the network API, provision a
database, activate a provider, enable paid services, or approve production.

## What the gate actually verifies

From the repository root, the CI-compatible command is:

```powershell
python scripts/evaluate_storage_concurrency.py --workers 4 --steps 3
```

It creates a new SQLite database inside an automatically cleaned operating-system
temporary directory. It initializes Nextrail's existing v1 learning, account,
preferences, and optional shared-throttle tables with **synthetic test inputs**.

- Four threads open **distinct SQLite connections inside their own threads**;
  no connection is transferred across threads. All workers begin synthetic
  transactions together. Each worker performs three unique course saves,
  adding one append-only audit event per committed save.
- Workers also use the same preconfigured, HMAC-backed fixed-window quota.
  At the configured quota, exactly 12 requests and 12 audit events are expected;
  an additional request must receive HTTP 429.
- A second, short-lived lock test holds a writer transaction and confirms an
  unrelated WAL reader sees only previously committed rows. A competing write
  with a short busy timeout must return HTTP 503 (fail closed).
- After rolling back the held write, the previously refused request succeeds
  **exactly once**, proving that contention did not consume a hidden rate-limit
  budget. The temporary database must still pass the existing SQLite integrity
  and schema-version checks.
- An additional unittest races four attempts to save the *same* course and owner
  in separate connections, and requires one saved row and one audit event,
  with three idempotent responses.

Outputs contain only aggregate test counts and booleans. The synthetic client
IP address, HMAC key, database location, account identifiers and row contents
are not included. All temporary files are automatically removed. The included
HMAC key is a **static test fixture**, never an operational key.

## What this does not verify

This is a bounded **offline functional concurrency check**, not a production
load benchmark, fault-injection infrastructure service, or performance SLO.
It does not establish:

- Database behavior with hundreds of simultaneous users, several ASGI workers
  with large request volumes, multiple hosts, or external network latency.
- Real hardware latency or throughput, long-run memory consumption, sustained
  write contention, read/write mix, database migration under traffic, live
  backup under peak load, or Windows service restart recovery.
- Production TLS, email verification, access control deployment, logging
  pipelines, encrypted/off-site backup handling, rate limiting across hosts,
  RPO/RTO or disaster recovery procedures.

Do not use this script against production SQLite files. Its thread count is
restricted to 1–4 and steps per thread to 1–8 by design. No load testing of
public third-party services is performed.

## Verification and manual gate

GitHub Actions runs the gate along with all backend unittests, guest API
performance smoke checks, provider permission preflight, blocked-release
acceptance register, and unchanged frontend tests/build.

After manually reviewing and squash-merging this phase PR, use the existing
local checkout only:

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
npm test
npm run build

Set-Location ../..
git status --short
git log -1 --oneline
```

If Git reports local changes or conflicting history, stop without cleaning,
resetting, overwriting, or modifying a preserved stash. Phase 28 still needs
representative load evaluation, operational monitoring, recovery/alert drills,
and a human phase-level acceptance checklist. The formal pre-release gate
remains **blocked** regardless of a successful synthetic concurrency run.
