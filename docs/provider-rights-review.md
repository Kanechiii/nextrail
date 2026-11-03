# Provider rights and evidence review — Phase 45

## Decision boundary

This is a **read-only planning and review queue**, not legal sign-off, an
authorization grant, a source connector or a public catalog. The checked-in
provider dossier is entirely **pending**; the independent source registry and
provider authorization ledger remain unchanged. Do not infer permission from a
publicly viewable page, a repository being open source, a public API reference,
a course being described as free, or a passing CI check.

Review the intended usage separately: collecting course **metadata**, publicly
displaying it, **caching** snapshots, commercial distribution, provider
attribution/branding, API or RSS access and operational restrictions. Any
publisher content, full course text, thumbnails, trademark or API credential
requires its own evidence and terms review. Never commit private permission
emails, secret tokens, learner data, account details or legal attachments.

## Scope of the review queue

The file `data/provider-rights-review.sample.json` registers eight intended
targets with `review_state=pending`, `proposed_method=undetermined`, unknown
rights, unverified course claims and empty legal evidence. These are *planning
targets*, not entries in the runnable provider source registry.

| Intended source | Reviewer questions and public starting points |
| --- | --- |
| Microsoft Learn | Examine the [Microsoft Learn Terms of Use](https://learn.microsoft.com/en-us/legal/termsofuse), any specifically licensed metadata API and the intended display/caching scope. General personal noncommercial access is not an integration license. |
| GitHub Skills | Examine [GitHub site policies](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service), applicable GitHub Skills licenses and allowed use of individual repository metadata. |
| GitHub repository roadmaps | **Each third-party repository is separately licensed**. Check its license and maintainer rights; GitHub's general terms do not replace individual authors' rights. Do not infer that all roadmap repositories share one license. |
| Claude Academy | Examine the provider's [official academy](https://academy.claude.com/) and applicable terms/permission for course metadata. Public availability does not imply Nextrail caching or redistribution rights. |
| AWS Skill Builder | Check current AWS Training/Skill Builder terms, content license, possible access conditions, approved API or manual method and brand restrictions. An AWS account or free course does not imply metadata reuse rights. |
| Coursera | Check the current [Coursera Terms of Use](https://www.coursera.org/about/terms). Its published terms address content reuse and restrict scraping without prior written consent. Seek the applicable direct permission before considering an automated collection method. |
| freeCodeCamp | Inspect the [current freeCodeCamp repository and licenses](https://github.com/freeCodeCamp/freeCodeCamp) **by content type**: software and educational material may have different licenses, attribution and share-alike duties. Do not assume a general GitHub code license covers the curriculum. |
| LinkedIn Learning | Read the [Learning API access documentation](https://learn.microsoft.com/en-us/linkedin/learning/getting-started/request-access). Access can depend on an approved partner arrangement or an organization license; the existence of API docs does not grant tokens or redistribution rights. |

These links are only investigation starting points, **not legal clearance**.
Terms are mutable. Review them again on the operator's actual decision date
and document the exact contract, source host, access scope and expiry locally.

## Local reviewer dossier and state machine

The sample dossier has `schema_version=1.0.0` and
`review_purpose=planning_only`. Each provider has a stable lowercase ID,
official website, proposed method, review state, five rights determinations,
permission-evidence assertion and four separate course-claim checks.

- `pending`: no method, permissions or claims asserted; all evidence empty.
- `blocked`: an operator has decided not to proceed; remains excluded.
- `evidence_submitted`: local reviewer assertions were entered for possible
  **independent human** review; never the same as `approved`.

The executable dossier audit reports `requires_independent_signoff` only
after a proposed method and non-expired legal evidence, permission rights and
separate availability/access/certificate/student-eligibility reviews are
asserted complete. A prohibited metadata collection/display/caching right
blocks the proposed publishing design; unknown details remain unresolved.
The output intentionally omits reviewers, permission URLs, provider names,
credentials and raw evidence. It prints only stable provider IDs, status
codes and counts. It does **not** verify who signed the terms or whether the
terms legally permit use.

Use a **private, local copy** of the dossier for actual human review, not the
checked-in sample. Keep provider correspondence, internal reviewer evidence and
signed permission artifacts outside the repository. This audit stores nothing.
Do not add `authorization=approved` to `data/sources.sample.json` or put an
entry into `data/provider-authorizations.sample.json` because a dossier looks
complete. Existing source-authorization checks remain the only technical
preflight for an independently approved future registry.

## Read-only commands

From the repository root:

```powershell
python scripts/audit_provider_rights.py --dossier data/provider-rights-review.sample.json --expect-pending
python scripts/audit_provider_rights.py --dossier data/provider-rights-review.sample.json --require-review-ready
```

The first command must pass with eight pending providers, zero signoff-ready
dossiers, zero authorization writes, zero network calls and no activation.
The second is intentionally blocked with exit status **2** because the
checked-in sample has no independent evidence to review.

For an authorized local reviewer dossier, substitute its explicit local path,
omit `--expect-pending`, and inspect the returned non-sensitive statuses.
Exit **1** signals an invalid or unsafe dossier. Exit **2** signals no evidence
complete enough for independent sign-off. Exit **0** only means syntax and
asserted evidence completeness passed; it is **never permission to ingest**.

## Independent reviewer acceptance

For each individual provider/source, the reviewer must record and verify:

1. Provider identity and a lawful evidence domain, with a pseudonymous
   reviewer ID, review date, expiry and official published terms or direct
   permission that explicitly covers the **actual intended use**.
2. Legal distinction among manual exports, approved official APIs, RSS and
   prohibited scraping; permitted hosts, API authentication/rate limits,
   caching duration, permitted fields and attribution/trademark obligations.
3. Course listing existence and availability, course access price and
   certificate cost **independently**, student benefit or subscription rules,
   region/account conditions and the freshness of those claims.
4. Commercial versus noncommercial scope and whether the intended public
   use is authorized. If usage is denied or unclear, keep it blocked.
5. A separately reviewed, explicit source-registry and authorization-ledger
   change using the existing 90-day authorization preflight, then a reviewed
   offline snapshot, verified release and manually controlled SHA-256 pin.

No private evidence, API keys, provider approval, scraped data, scheduled
collector, hosted service or paid plan belongs to this phase. Guest pathway
generation and optional-account behavior stay unchanged; the real course
catalog and all production acceptance gates remain blocked by default.

## Tests and merge gate

CI checks the sample dossier has only pending entries and independently
retains the zero-provider onboarding, source authorization, blocked UI and
production acceptance gates. Unit tests use a **fictional** provider to
exercise the evidence-submission state without granting any real rights.

Before merging, examine the report contract, code and test suite, ensure
latest-head CI success and manually verify that the independent provider
authorization ledger remains empty. The user reviews and squash-merges the
PR manually. No local worktree, stash, public deployment or paid services
are modified.
