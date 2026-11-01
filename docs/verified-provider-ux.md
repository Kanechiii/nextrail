# Verified provider experience — Phase 34

The frontend displays **only the source-returned v1 course data** that Nextrail's
existing backend permits. This phase introduces *no* provider scraper, remote
connector, automated availability checker, paid service or real provider grant.

## Source integrity model

- `/v1/courses` is the guest-accessible discovery endpoint. The backend excludes
  synthetic resources and nonapproved providers by default; the existing reviewed
  publication loader and provider authorization checks remain authoritative.
- `evidence_status="verified"` means a *listing met the offline evidence-review
  policy* at publication time. It is not accreditation, an account entitlement,
  certificate verification or a guarantee of enrollment availability.
- The UI calls `reviewedCourseUrl()` on every official course link; only a
  **non-synthetic reviewed record with HTTPS URL and no embedded credentials or
  unexpected port** can expose a source URL. This defense does not replace
  backend domain/authorization validation.
- Guest illustrative examples remain separately labeled and never expose
  provider enrollment links or bookmarking.
- Unknown costs are never turned into a free claim. **Access cost and certificate
  cost are separate fields** on cards, comparisons, details and filters.
- A `conditional` access label states that eligibility is provider-dependent.
  The app does not claim GitHub Student Pack, Coursera aid, LinkedIn Learning
  institutional access, free trials or AWS student benefits are enabled.
  Learners must check the provider directly.

## Changes to the learning workspace

The Discover tab now says **Reviewed catalog** instead of “Live catalog,”
which would incorrectly imply live provider synchronization. Filter options
now include conditional access and a *separate certificate-cost filter*
matching the already-supported backend `certificate_cost` parameter. The
illustrative mode applies the same filters to locally defined examples
without contacting external providers.

Provider summary cards, comparisons and the landscape detail modal share
review-state text and conditional access guidance. Provider-specific
color accents are constrained to the existing static presentation palette;
providers do not inject CSS or arbitrary HTML. On reviewed records, links
open in a separate tab with `noopener noreferrer`. The user may still
discover and preview a pathway without an account.

All existing user data, saved progress, profile preferences, path previews,
account and guest-to-account continuity remain unchanged.

## QA and non-goals

Run `npm ci --no-audit --no-fund`, `npm test`, and `npm run build` from
`apps/web`. Node behavior tests exercise reviewed-source links, unsafe
URL rejection, cost and certificate independence, and safe labelling.
The repository's existing backend and intentionally blocked release
acceptance checks must continue to pass.

Manually verify the following before phase-level acceptance:

1. A source-authorized fixture with a reviewed listing shows the real
   provider name, reviewed status, separate costs and permitted HTTPS source.
2. Synthetic examples and unverified records display appropriate warnings
   and cannot open a fabricated enrollment link or be bookmarked.
3. Access-cost, certificate-cost, provider and skill filters can be combined;
   changing any filter clears the comparison selection.
4. Conditional access does not assert the user already qualifies for paid,
   student, trial, library or subscription benefits.
5. Light and dark modes preserve readable source badges, focus outlines,
   mobile layouts, reduced motion, and keyboard access.
6. The *sample repository catalog has zero reviewed real courses*, so no
   live provider results should be expected without approved source evidence.

This PR does not satisfy Phase 25 provider onboarding or Phase 29
pre-release authorization. Any real provider must undergo independent
permission, source, pricing, availability, certificate and security review
before it can be included. Do not bypass the backend authorization gate to
create attractive demo cards.

The next phases are independent Phase 35 browser/quality assurance and
Phase 36 safe demo and deployment documentation. No production deployment
or real-provider activation is authorized.
