# Offline course catalog quality and freshness — Phase 47

## Purpose and authorization boundary

The **read-only** quality audit extends the Phase 46 offline adapter preflight
and the Phase 16 reviewed-course compiler. It does not collect provider data,
grant collection/display rights, approve new courses or publish/activate a
release. The checked-in sample remains at **zero approved real-provider
authorizations, zero reviewed real courses and zero source snapshots**.

The operator runs `scripts/audit_catalog_quality.py` on six **existing
local** inputs: skill catalog, source registry, scoped authorization ledger,
manifest, listing reviews and course claim evidence. It calls the existing
`compile_local_bundle` and inherits its strict local file reader,
authorization verification, scoped host validation, duplicate rejection,
course-normalization rules and fail-closed eligibility decisions.

Do not interpret a synthetic fictional test fixture or a valid JSON document
as legally verified provider access. Independent provider rights remain
unverified until an operator completes the source-specific review. The
existing SHA-256 pinned release approval also remains a separate manual step.

## Policy inherited from reviewed publication

| Review or claim | Maximum age | Effect when missing, unapproved or expired |
| --- | --- | --- |
| Course listing review | 90 days | Exclude that course |
| Course availability `available` | 7 days | Exclude that course; no assumption it is live |
| Course access price | 30 days | Exclude that course; do not imply it is free |
| Certificate cost | 30 days, independent of access | Continue only if other claims pass; display certificate cost as `unknown` |

A record must also match the official HTTPS provider domain, authorized source,
course ID, stable normalized URL and reviewed skill references. Conflicting
duplicate identities are rejected rather than picking a winner; exact
duplicate contributions may be collapsed with source attribution preserved.

The `--refresh-window-hours` flag (default **48**, allowed 0–168) **only
creates an advisory warning for evidence that is still eligible but will
expire within the requested number of hours**. It never extends the original
expiry limits or renews evidence automatically. A reviewed course can appear
in the refresh queue while remaining eligible pending human action.

The audit reports only status codes, counts, resource IDs, non-sensitive
exclusion reasons and due claim types. It intentionally excludes reviewer
names, permission and course URLs, credentials, raw claim values and course
titles. It is not a source of verified course data for the public website.

## Operator commands

From the repository root:

```powershell
python scripts/audit_catalog_quality.py --base-catalog data/catalog.sample.json --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json --manifest data/course-publication.manifest.sample.json --listing-reviews data/course-publication.reviews.sample.json --claims data/evidence.sample.json --expect-empty
```

Expected: `status=blocked_no_reviewed_courses`, zero real authorization
assertions, zero candidates, zero refresh warnings, no network calls, no
files written and no runtime activation.

With an **independently authorized, privately reviewed** local input set,
replace all six paths and omit `--expect-empty`. Optionally specify
`--refresh-window-hours 24` or `--require-reviewed-candidates` to require at
least one course **eligible for further human release review**, not one
approved for publication.

Exit codes: `0` = valid offline report; `1` = rejected unsafe, invalid or
unexpected nonempty sample; `2` = no reviewed candidates when explicitly
required. An exit status `0` is not publication authorization.

## Quality report fields

The report includes `candidate_count`, `reviewed_course_candidates`,
`excluded_course_count`, `excluded_reasons`,
`exact_duplicates_collapsed` and `certificate_cost_unknown_count`. The
advisory `refresh_due_counts` separates listing, availability, access cost
and certificate cost. Each `refresh_queue` item includes a non-sensitive
resource ID and `checks_due` categories only; it does not carry or mutate
evidence, and warnings are never treated as proof that remote data changed.

A valid local package with nonzero eligible courses reports
`manual_release_approval_required`, **not** production-ready. A course
with stale availability or access price is excluded, and an old certificate
price falls back to unknown rather than being shown as free. Provider
permission status and certificate entitlement cannot be inferred from
course availability or a successful refresh warning check.

## Tests and review gate

CI adds an explicit `--expect-empty` quality check alongside the Phase 45
pending-provider rights gate, Phase 46 empty adapter gate and existing
source-authorization, reviewed-publication, backend security, blocked UI and
production-release checks. Fictional tests cover current and expiring
evidence, independent certificate expiration, stale availability/prices,
stale or absent listings, duplicate metadata, revoked/missing permissions,
invalid refresh windows and the read-only contract.

Before manually merging, inspect the latest-head CI run and the code/test
changes. Verify the checked-in provider authorization ledger still contains
no real rights and the production acceptance gates remain explicitly
blocked. Manual squash merge and local synchronization require user
approval. No cloud service, paid dependency, provider crawling, account
change, stash changes or public release is included.
