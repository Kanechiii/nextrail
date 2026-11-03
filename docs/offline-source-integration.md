# Authorized offline source integration boundary — Phase 46

## Implementation scope

Nextrail already has strict manual/official-API-export and RSS/Atom
normalizers, a scoped authorization ledger, an offline reviewed publisher and
a manually pinned runtime catalog. This milestone adds an **adapter-only
readiness check** that validates operator-supplied *local* snapshots before
course listing, availability, price and certificate evidence is reviewed.

This is infrastructure preparation, **not a live integration with any real
provider**. No source is activated: all eight planned providers remain
pending in the Phase 45 rights dossier; the checked-in source registry and
authorization ledger contain **zero authorized real providers**. Do not
treat a passing preflight, a local copy of a course page, an official API
documentation page, or permission assertions inside fictional tests as proof
of actual reuse rights.

## Supported offline input contracts

Each source must be present in the source registry with an approved,
non-synthetic status and must have a current, exact-scope authorization in
the existing provider ledger. The registrar checks the source method and
official HTTPS host allowlist. It rejects missing, expired, revoked or
mismatched assertions before reading any local snapshot.

The input is a *local* `course-publication` manifest referring to snapshot
files in the same directory. No network fetch or crawl is performed.

| Source method | Locally supplied snapshot | Required curated input |
| --- | --- | --- |
| `manual` | JSON `{source_id, records}` file | Each record declares a slug external ID, title, official HTTPS URL, approved skill IDs and prerequisites |
| `official_api` | A **previously permitted and already exported** local JSON snapshot using the same normalized `{source_id, records}` contract | A human or separately approved tool must map provider fields into this contract; this phase implements no API client, tokens or endpoint calls |
| `rss` | Local bounded RSS 2.0 or Atom XML feed and curated JSON annotations | Every entry needs a skill/prerequisite mapping; entity/DTD expansion is forbidden |

The new `scripts/verify_offline_source_integration.py` reuses the existing
source registry, current authorization checks, strict bounded file readers,
manifest resolver, manual normalizer and RSS/Atom normalizer. It rejects
unsafe paths, malformed records, duplicate IDs/URLs, unknown skills,
unsupported formats, oversized inputs and non-regular files.

It reports only **source IDs, methods, safe status codes and candidate counts**.
The output never includes a title, course URL, legal permission URL, reviewer,
raw feed, access token or learner data. The audit never writes files or
modifies the database.

**A normalized candidate is not a published course.** It lacks verified
listing, availability, access price, certificate price and student eligibility
evidence. These must independently pass the existing offline reviewed
publisher and manually approved SHA-256 release process. An approved local
authorization ledger remains an *operator assertion*, not proof of actual
provider permission.

## Commands

Run in the repository root:

```powershell
python scripts/verify_offline_source_integration.py --base-catalog data/catalog.sample.json --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json --manifest data/course-publication.manifest.sample.json --expect-empty
```

The command must report `blocked_no_authorized_sources`, zero grants, zero
snapshots and zero candidates. To audit an **independently approved,
operator-supplied local package**, replace the four paths and omit
`--expect-empty`. The optional `--require-candidates` exits 2 if no
normalized records are available for human review, **not** if public release
is unapproved. Unsafe/invalid input exits 1; a valid offline audit exits 0
without granting rights.

## Deferred integrations

Provider-specific remote connectors, hosted API credentials, automated
course collection, scheduled refreshes, licensing agreements, caching
duration, branded content rights, attribution, region-specific availability,
student-benefit claims and fee verification are **not implemented** here.
Do not enable a real provider until an independent rights review permits the
exact method and data usage, all operator approvals are recorded, any
required agreements are executed and fresh metadata is verified.

The Phase 46 integration milestone remains operationally gated until there
is at least one independently authorized real source. Its adapter preflight
can be engineering-complete while real source integration remains blocked.

## Regression and release checks

CI preserves the zero-real-provider sample authorization gate, the pending
provider-rights dossier gate, the offline onboarding audit, backend contracts,
SQLite reliability, browser smoke, blocked UI quality acceptance and blocked
production acceptance. Fictional authorized-provider unit fixtures exercise
all three offline adapter methods, valid and denied permission states, stale
assertions, unsafe XML/paths, duplicate records and no-output behavior.

Before manually approving the PR, inspect the report for unintended source
activation; review full GitHub Actions at the **latest commit**. Manually
squash-merge only after review. Do not modify local worktrees, local stashes,
production settings or paid services.
