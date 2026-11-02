# Provider onboarding readiness — Phase 43

This phase adds a deterministic, **read-only** onboarding audit on top of the
existing offline reviewed catalog publisher and manually pinned runtime release
gate. It does not discover provider pages, grant permission, fetch/scrape
courses, automatically activate a bundle, contact external APIs, or authorize
public deployment.

## Baseline: no real-provider approval

The checked-in registry uses fictional `example.org` and `example.net`
sources marked synthetic and pending. The provider authorization ledger is
empty, and the publication manifest contains no batches. Consequently the
correct audited state is **0 approved real-source assertions and 0 reviewed
course candidates**. This is not a failure of guest-first course discovery;
the public catalog must remain empty without actual reviewed evidence.

Any real integration of Microsoft Learn, GitHub Skills, AWS Skill Builder,
Claude Academy, Coursera, freeCodeCamp or LinkedIn Learning must go through a
separate review of the source's published terms, allowed reuse and attribution,
permission scope, credentials (if any), source access restrictions, regional and
student eligibility claims, pricing, certificate costs and review cadence.
No rights to these sources are presumed by mentioning their names here.

## Read-only operator command

From the repository root, run:

```powershell
python scripts/audit_provider_onboarding.py --base-catalog data/catalog.sample.json --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json --manifest data/course-publication.manifest.sample.json --listing-reviews data/course-publication.reviews.sample.json --claims data/evidence.sample.json --expect-empty
```

The result is structured JSON printed to standard output. It includes
source IDs and non-sensitive status codes, counts and exclusion reasons;
it does **not** include reviewer identity, contact information, raw
permission URLs, private snapshots, account data or tokens.

The sample must report `status="blocked_no_reviewed_courses"`,
`authorized_source_assertions=0`, `reviewed_course_candidates=0`,
`catalog_files_written=0`, `remote_requests_performed=0`, and
`runtime_activation_performed=false`. No file or database is created.

For a user-supplied **local, independently authorized** onboarding package,
replace all six arguments with corresponding local inputs and omit
`--expect-empty`. The audit reuses the publication pipeline and authorization
preflight; it rejects invalid or expired permissions, unapproved source
submissions, stale listings, unsafe URLs and unsupported claims.

`--require-candidates` makes the command return status **2** unless at
least one course meets the *existing offline reviewed-candidate policy*.
It does not certify actual course availability or source rights.
`--expect-empty` makes the command fail status **1** if a sample has a
real-source authorization assertion or a reviewed course candidate, guarding
against accidental non-sample data in CI. Missing/malformed permissions and
unsafe inputs return status **1**.

### Source-status definitions

| Status | Meaning |
| --- | --- |
| `synthetic_excluded` | Fictional preview/test source, ineligible for real public courses |
| `source_approval_pending` | Source not approved in the registry; no ingestion |
| `authorized_snapshot_missing` | Operator asserted current scoped permission, but supplied no local snapshot |
| `offline_snapshot_submitted` | A locally supplied batch passed existing strict normalization; per-course listing, access-price and availability evidence are separately checked |

A report with reviewed course candidates has status
`manual_independent_review_required`; it never uses "approved for launch",
"verified live", or any equivalent claim. An exact provider-authorized,
human-reviewed release package requires explicit publication and a separate
operator-approved SHA-256 pin before API activation.

## Revalidation and source governance

Reviewers must independently confirm these items for each proposed source:

1. **Permission scope:** Provider terms or direct permission actually allow
   the intended collection method, display, caching, title/URL use and
   commercial/noncommercial operating mode. Use only the officially permitted
   domains and explicit methods in the source registry.
2. **Data capture:** A local manual/API-export/RSS snapshot is collected by
   authorized means. This phase does not add remote connectors. No provider
   credentials are stored in a catalog file.
3. **Stable identity and attribution:** Verify official HTTPS course and
   evidence URLs, provider and resource IDs, exact host allowlists, skills,
   prerequisites, attribution, source timestamps and duplicate handling.
4. **Current course claims:** Verify listing review within 90 days, availability
   within 7 days and course access-cost claims within 30 days. Certificate
   cost is reviewed **independently** within 30 days or remains unknown.
5. **Learner eligibility:** Do not assume free student benefits, subscription
   access, credential entitlement, or that free course access includes a
   certificate. Where access is conditional, preserve that classification.
6. **Decision and revocation:** A pseudonymous reviewer documents the
   permission basis and expiration. Expired, revoked or scope-mismatched
   grants fail closed. Revalidate when terms or eligibility change.
7. **Publication and runtime:** Run the offline publisher, inspect the
   entire result, verify the checksum and explicitly configure a local
   pinned release. Do not automatically merge catalog data into the
   website or change a production environment.

## Input hardening

The publisher and auditor share one strict bounded JSON reader.
Duplicate keys (including nested objects), nonfinite numbers, symlinked JSON
files, oversized inputs and malformed UTF-8 fail before catalog output.
Manifest-supplied snapshot paths cannot traverse outside the manifest
directory or pass through symlinks. RSS/XML snapshots are read with a hard
byte bound. Output remains exclusive-create in the existing publisher,
preventing accidental overwrite.

These are local-file defenses, not cryptographic assertions of provider
permission. A SHA-256 digest pins bytes only; it does not authenticate the
reviewer.

## Automated QA and manual acceptance

CI executes the zero-real-provider onboarding audit as an explicit
nonactivation guard, full backend and frontend regressions, source contract
checks, intentionally blocked release/UI acceptance checks, and the existing
Vite dev-server smoke.

The new offline tests also create **fictional disposable** sources with
explicit test-only permission assertions to verify candidate reporting,
missing/expired/revoked grants, stale availability, no overwrite, symlinked
file paths, duplicate JSON properties, nonfinite data and snapshot bounds.
They never make third-party requests or publish their fixtures.

Still required before a real-source onboarding phase can be accepted:
independent current provider-rights review, operator evidence records,
actual provider sample snapshots under those rights, evidence and cost
validation, reviewed SHA-pinned release, desktop/mobile QA, and manual
review/merge. Source rights and the ten production-release gates remain
unapproved. The user has final approval authority; this PR never merges
automatically.
