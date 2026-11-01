# Verified course data pipeline — offline, human-reviewed publication

## Purpose and operating boundary

This backend-only phase compiles **locally supplied** JSON or curated RSS/Atom
snapshots into the existing v1 course catalog. It does not fetch, scrape, crawl,
call remote APIs, provision infrastructure or expose an automatic live-course
endpoint. The Nextrail guest API remains unchanged until a separate, explicitly
approved integration gate. No real provider has been approved by the sample
fixtures, and running the sample command produces **zero public courses**.

An “approved” source or reviewer record is an explicit *human assertion*, **not
independent proof** that a course, offer or credential is currently available.
A real reviewer must separately inspect the provider's official page, terms,
catalog rights, eligibility, prices and certificate conditions before approving
a record. A snapshot expires in practice: reviewers must revalidate availability
at least every seven days, course and certificate price claims within 30 days,
and the listing review within 90 days. These are fail-closed development policy
thresholds rather than a live guarantee.

## Pipeline order

1. Validate the versioned source registry and its exact HTTPS host allowlists.
2. Accept only explicitly approved **non-synthetic** source submissions. Source
   data must be supplied locally as manual/official-API JSON or bounded RSS/Atom
   bytes with curated skill annotations. The provider source registry alone never
   authorizes scraping or unsolicited API use.
3. Normalize known skills, prerequisites, stable provider/resource IDs, resource
   titles, allowed URLs and cost/evidence defaults using existing adapters.
4. Collapse exact duplicates while retaining all contributing source IDs.
   Conflicting resource metadata or identical URLs under different identities
   fail the whole publication. Query-parameter variants are not silently merged
   because they might represent different offerings.
5. Require a current, approved **listing review** with reviewer ID, provider-
   hosted evidence URL and timezone-aware timestamp.
6. Validate each claim separately through the existing evidence engine: current
   provider-hosted and reviewer-approved *available* status (7 days) plus
   **access-cost** classification (30 days) are mandatory to publish a course.
   The independent certificate-cost claim is optional and remains **unknown**
   unless currently approved; no unknown value is converted into “free”.
7. Output a catalog, per-resource provenance and a review report. No records from
   pending sources, synthetic samples, expired reviews, unavailable courses or
   unsupported claims enter the published catalog.

The v1 `evidence.status="verified"` on an output resource means the listing,
access cost and availability satisfied the *current reviewed evidence policy*.
It does not mean every possible course fact (including certificate fees) was
verified. The accompanying `claim_evidence` provenance records the exact
official review URL, timestamp and reviewer identifier for each trusted claim.

## Command-line dry run

Use a new, nonexistent output filename. From the repository root:

```powershell
python scripts/publish_course_catalog.py --base-catalog data/catalog.sample.json --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json --manifest data/course-publication.manifest.sample.json --listing-reviews data/course-publication.reviews.sample.json --claims data/evidence.sample.json --output data/course-publication-preview.json
```

Expected sample result: **0 published courses**. The example.org/example.net
data is synthetic, pending and fictional for test purposes.

For a real *authorized* manual/official-API JSON submission, the manifest's
`batches` entries have these fields:

```json
{"schema_version":"1.0.0","batches":[{"source_id":"reviewed-source-id","format":"manual","path":"reviewed-snapshot.json"}]}
```

For a local RSS/Atom snapshot with *explicit curated skill mappings*:

```json
{"schema_version":"1.0.0","batches":[{"source_id":"reviewed-feed-id","format":"rss","feed_path":"feed.xml","annotations_path":"annotations.json"}]}
```

All manifest file paths are relative to the manifest file's directory and
cannot escape it. The registry identifies which source IDs, methods and hosts
are approved. Listing-review JSON has `{"schema_version":"1.0.0","reviews":[]}`;
each review uses exactly these fields:

```json
{"resource_id":"approved-provider-course-id","source_id":"reviewed-source-id","status":"approved","reviewer":"reviewer-id","checked_at":"2026-11-01T00:00:00Z","evidence_url":"https://approved-provider.example/course"}
```

Use an **actual** provider's reviewed official URL instead of the illustrative
placeholder above. The claim file follows the established
`data/evidence.sample.json` ledger contract; it distinguishes
`access_cost`, `certificate_cost` and `availability`.

The output file is never overwritten. Treat the approval ledger and reviewer
provenance as review records: do not publish private contact information,
credentials or personally identifying reviewer details. Use pseudonymous
reviewer IDs. Do not commit or deploy a generated catalog until an authorized
reviewer checks every output and approves publishing it.

## Integration boundary

The output is *not* automatically served by the live guest API. A future
backend integration phase must implement an explicit, validated publication
loading gate with runtime freshness enforcement, atomic catalog replacement,
rollback and status reporting. Without such a gate, do not claim that running
this CLI makes real courses appear in the user-facing web dashboard.

## Validation

```powershell
python scripts/validate_discovery.py
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/evaluate_pathways.py
python -m compileall -q services/api/nextrail_discovery
```

The suite covers unapproved/synthetic sources, official-domain restrictions,
stale/missing/conflicting claims, duplicate IDs and canonical URLs, unknown
skills, no fabricated certificate charges, guest discovery over the reviewed
output, and the no-network CLI with exclusive output creation.

## Additional provider authorization preflight (Phase 25, Step 1)

The separate offline source-authorization contract validates an operator-maintained
review record against each approved source's exact provider ID, source URL,
integration method and allowed HTTPS hosts. It also requires a pseudonymous
reviewer ID, provider-hosted permission reference, explicit permission basis,
review date and finite expiration. Authorization entries for pending or
synthetic sources do not grant permission. An approved non-synthetic source
without a current matching authorization entry fails the entire preflight.

Run this **read-only**, offline sample check (expected zero real grants):

```powershell
python scripts/verify_source_authorizations.py --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json
```

## Publication-side permission gate (Phase 25 follow-up)

The **offline publisher CLI** now requires `--authorizations` on every invocation,
including synthetic sample dry runs. Before loading source batches it verifies the
review document against the complete registry and requires current, exact-scope
permission for every approved non-synthetic registry source. Unknown, revoked,
expired, pending or mismatched authorizations fail the operation without writing
an output file. Every manifest source must be among those approved. The separate
authorization JSON reader refuses symlinks, duplicate properties and oversized
documents. The sample still has zero approved real sources and publishes zero
courses. Existing low-level normalization and catalog compiler functions remain
available for isolated unit tests; external publication must go through the
gated CLI.

This remains an **offline operator assertion**, not signed proof of actual
provider permission. It cannot authorize remote scraping or fetching. Actual
provider terms, data rights, use restrictions and necessary consent still
require independent human review, and no real provider has been activated.
