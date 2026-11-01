# Backend integration and offline release gates — Phase 19

## Scope

This backend-only phase closes the gap between the Phase 16 offline reviewed
course compiler and guest-first FastAPI endpoints, using explicit **operator
approval** and fail-closed runtime validation. No UI files, paid provider,
cloud service, deployment, live scraping, scheduled delivery or external
network requests are introduced.

Default behavior is **unchanged**: with no reviewed-release environment
configuration, the API uses the checked-in synthetic skill catalog. It exposes
guest courses as an empty result, but retains guest pathway previews, skills
and all existing optional account features. Test apps that inject a catalog
directly are unaffected.

## Activation contract

A reviewed package is produced with the already-implemented
`scripts/publish_course_catalog.py` command. Activation is manual: an
operator must examine the publisher output and official provider review
records, independently verify authority to use each source, and pin the
**exact output bytes** with a SHA-256 digest before starting a new API process.

Set **both** environment variables:

- `NEXTRAIL_REVIEWED_CATALOG_PATH`: path to a local, existing, regular
  `.json` file containing the entire Phase 16 package.
- `NEXTRAIL_REVIEWED_CATALOG_SHA256`: 64-character *lowercase* SHA-256
  hex digest of that exact file.

If only one is set, the digest does not match, the file is a symlink,
the content is too large, the release format is malformed, or any required
record or provenance evidence is unsafe, **startup fails closed**. There is
no fallback to synthetic or previously loaded course data when a reviewed
release was explicitly requested.

A checksum is an operator-controlled **integrity pin**, not a digital
signature or proof that provider claims are true. Only authorized reviewers
should choose and approve the expected digest. The release package itself
does not cryptographically authenticate reviewers, provider approvals or
publication rights. It contains no secrets and should not be used as an
automatic deployment credential.

## Per-resource runtime verification

The snapshot loader reuses the existing orchestration catalog quality gate
and the Phase 16 evidence-age policies. The published catalog and its
provenance must agree exactly:

- Every displayed course has an approved provider and `synthetic=false`.
- Course, listing and claim evidence URLs must use credential-free HTTPS
  on the declared provider domain or a subdomain. Sources that legitimately
  use other domains need a separately reviewed provenance/allowlist contract
  before activation, not an exception configured by the frontend.
- Every course has a current approved listing review (90 days), reviewed
  available-state provenance (7 days), and reviewed access-cost evidence
  (30 days).
- Certificate price is `unknown` unless a separate certificate-cost
  review exists and remains current (30 days).
- Resource IDs, canonical URLs, referenced skills, parent prerequisites,
  provenance records and exclusion report counts must be consistent.
- Duplicate JSON keys, extra release properties, unsupported schema
  versions, unapproved providers, mismatched resource/evidence links,
  future timestamps and expired reviews reject the entire snapshot.

Only the validated reviewed release may grant free-course eligibility for a `zero_budget=true` pathway. The runtime derives a frozen set of free-access resource IDs from this validated package and passes it through both the prerequisite planner and the quality gate. Paid, conditional, unknown-price, synthetic, unapproved and stale courses cannot be advertised as free recommendations. Without explicit reviewed activation, zero-budget course suggestions remain empty rather than trusting a standalone catalog `free` flag. Course access and certificate fees are independent; a free-access recommendation never asserts a free certificate.

The pinned file is read once at process creation. Its validated content is
held in memory. No automatic remote data refresh or filesystem hot-swap is
performed; a later file edit does not silently alter the running release.

**Expiry is enforced on every catalog-dependent request**, not only at
startup. Once any included claim reaches its expiry boundary, the API
returns HTTP 503 for the catalog, skills, pathway preview and other routes
that require current catalog data. It does **not** silently display stale
verified courses or fall back to synthetic results. Account/session
authentication and the existing `/health` liveness probe remain available.
To restore readiness, a reviewer must compile and verify a fresh package,
explicitly pin its checksum, and restart the isolated development process.

## Liveness and readiness

- `GET /health`: unchanged, returns `{"status":"ok"}`. This reports
  API liveness, not catalog freshness.
- `GET /ready`: returns status, `catalog_mode` (`sample` or
  `reviewed_snapshot`), and a non-sensitive `reviewed_course_count`.
  It returns HTTP 503 if the activated reviewed package has expired.
  Do not use this as a public production-ready health guarantee.

## Offline preflight on Windows (no services purchased)

Run from `E:\Projects\nextrail` after switching to the Phase 19 branch.
First, optionally compile the **synthetic-only, zero-public-course** sample
as a no-risk dry run:

```powershell
$bundle = Join-Path $env:TEMP ("nextrail-phase19-review-{0}.json" -f [guid]::NewGuid().ToString("N"))

python scripts/publish_course_catalog.py --base-catalog data/catalog.sample.json --sources data/sources.sample.json --manifest data/course-publication.manifest.sample.json --listing-reviews data/course-publication.reviews.sample.json --claims data/evidence.sample.json --output $bundle
if ($LASTEXITCODE -ne 0) { throw "Offline catalog compilation failed" }

$pin = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
python scripts/verify_release.py --bundle $bundle --sha256 $pin
if ($LASTEXITCODE -ne 0) { throw "Pinned release preflight failed" }
```

Optional database validation of an **existing** durable account file:

```powershell
python scripts/verify_release.py --bundle $bundle --sha256 $pin --database data/nextrail-local.sqlite
```

The `--database` flag performs **read-only** schema/integrity inspection;
it refuses nonexistent or unsupported files and does not create or overwrite
databases. The bundle publisher requires a fresh nonexistent output filename.

To launch an isolated, local test on port `8019`:

```powershell
$env:NEXTRAIL_REVIEWED_CATALOG_PATH = $bundle
$env:NEXTRAIL_REVIEWED_CATALOG_SHA256 = $pin
$env:NEXTRAIL_DB_PATH = "data/nextrail-phase19-review.sqlite"
$env:NEXTRAIL_REQUIRE_DURABLE_STORAGE = "true"
python -m uvicorn nextrail_api.main:app --app-dir services/api --host 127.0.0.1 --port 8019
```

Use `http://127.0.0.1:8019/ready`, `/v1/courses` and `/docs`
to check the demo. With the provided sample registry, the correct reviewed
course count is **zero**. This is expected; the sample does not authorize
real-world course publication. Do not publish a fictional reviewed-course
fixture from tests to a public endpoint.

Remove the two `NEXTRAIL_REVIEWED_CATALOG_*` environment variables in
the **next** PowerShell session if you want to return to sample mode.
Existing active servers must be stopped/restarted to change release mode.

## Rollback and release gate

Rollback is **manual and non-destructive**: stop the review server,
select a previously vetted **still-fresh** package and its original
operator-approved SHA-256, run offline preflight, then restart.
No live file replacement, database rollback, automatic restart, remote
fetching or historical account-data deletion occurs.

Before manually merging the Phase 19 PR, confirm:

1. Full backend tests and security checks pass.
2. Deterministic pathway quality, catalog and discovery validation pass.
3. Frontend tests and build pass without modifying UI files.
4. Fresh approved package preflight passes and checksum tampering fails closed.
5. Explicit activation serves only reviewed records; expired claims return
   HTTP 503 instead of exposing stale courses.
6. Phase 15 database backup/restore checks remain intact and optional
   account data stays isolated.
7. Local Windows branch is synchronized and the preexisting stash remains
   preserved.

After the user manually squash-merges the PR and the post-merge GitHub
Actions workflow passes, from a clean working tree run:

```powershell
git fetch --prune origin
git switch main
git pull --ff-only origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git stash list
```

The two Git commit IDs must match. Do not merge, delete branches, force-reset
the repository, discard stashes or deploy without explicit authorization.

## Remaining production blockers

The project is still a local development system. Production hosting needs
separately reviewed source-rights validation, signed reviewer approval or
equivalent controlled release provenance, persistent distributed rate limiting,
connection pooling, secrets and encrypted backup management, multi-process
readiness checks, TLS, privacy/legal requirements and real user-acceptance
tests. No paid services are enabled in Phase 19.
