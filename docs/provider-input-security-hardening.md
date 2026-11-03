# Offline provider input safety — Phase 44

## Purpose

Tighten the local-only provider onboarding preflight and catalog publisher after
Phase 43. This is a defensive maintenance phase; it does not enable a new
source, crawl a provider, add a paid dependency, alter the account experience,
approve a release, or activate a real course.

## Input contract

All JSON supplied to `scripts/audit_provider_onboarding.py` and
`scripts/publish_course_catalog.py` is decoded with the shared strict reader.
The reader rejects:

- Duplicate properties at any nesting level.
- `NaN`, `Infinity` and `-Infinity`, including decimal exponents such as
  `1e999` that would otherwise overflow Python's float parser to infinity.
- Malformed UTF-8, missing files, unexpected extensions, oversized documents
  and non-regular files (for example, named pipes).
- Paths with symlink or junction components, including linked parent folders.
  On platforms that support it, a no-follow open flag adds protection for the
  final file component.

Offline RSS/XML feed snapshots use the same bounded regular-file reader, with
the existing 100,000-byte limit. Manifest paths must be relative, remain
within the manifest directory and avoid Windows drive/root and parent-directory
escapes. Legitimate bounded JSON numbers, manual snapshots and XML bytes
continue to work.

The path checks are local safeguards, not a sandbox against an attacker with
unrestricted concurrent filesystem mutation. Provider access, source licensing,
trusted review identity, signed evidence and release authorization must still
be established independently.

## Verification

The Python unittest suite covers exponent overflow through all seven local
JSON document positions, nested duplicate properties, Windows-style path
escapes, linked parents, non-regular inputs, oversized RSS and unchanged small
RSS bytes. Existing integration tests verify current permission enforcement,
auditor read-only behavior, exclusive-create publication and the empty sample
source registry.

Run the full regression suite in CI:

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/audit_provider_onboarding.py --base-catalog data/catalog.sample.json --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json --manifest data/course-publication.manifest.sample.json --listing-reviews data/course-publication.reviews.sample.json --claims data/evidence.sample.json --expect-empty
```

Only fictional test fixtures may assert approved providers. The checked-in
sample remains at zero approved real-source permissions and zero reviewed
courses. Successful tests do not authorize scraping, publishing external
content or public deployment.

## Manual review gate

Before squash-merging, inspect the input-reader code, confirm the latest-head
CI run is green, examine security-regression tests and verify the unchanged
blocked UI/production acceptance checks. Merge and synchronize `main` only
after explicit user approval. Do not modify local stashes or worktrees.
