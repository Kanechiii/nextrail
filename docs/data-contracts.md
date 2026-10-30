
# Nextrail Data Contracts

## Contract Version

Current contract version: 1.0.0

The catalog and pathway contracts are stored in
`packages/schemas`.

Breaking changes require a new version and migration
assessment before existing data can be transformed.

## Provider Registry

Every resource references a provider by provider ID.

Providers have an authorization state and an access method.

A provider's presence in the registry does not establish
permission to scrape, crawl, or use a proprietary API.

Authorization must be assessed against the applicable
official terms and access controls.

## Catalog Resources

A resource contains a unique ID, title, provider ID,
official URL, skill outcomes, prerequisites, cost
classifications, provenance evidence, and synthetic flag.

Resource IDs must remain stable across catalog refreshes.

## Cost Classification

Access costs and certificate costs are separate fields.

Unknown prices must remain unknown.

Conditional access does not mean universally free.

A verified free-course claim requires supporting evidence
for the specific claim and an appropriate recheck policy.

## Evidence and Provenance

Evidence records have a verification status, source URL,
and timestamp.

The current contract records general resource evidence.
Later phases must introduce claim-level evidence, review
history, and verification expiration policies.

A verified status does not automatically prove every claim
about a course or its certificate.

## Synthetic Data

All development fixtures are synthetic.

They must never be treated as publicly verified courses.

Reserved example domains are used in the fixture catalog.

## Skill Graph

Skills may have prerequisite skills.

All references must resolve to known skill IDs.

Cycles are forbidden.

Resource prerequisites and skill outcomes must reference
known skills.

## Pathway References

Pathways use catalog resource IDs and skill IDs.

Later generation services must validate milestone ordering,
resource availability, and prerequisite satisfaction.

An AI model must not invent resource IDs.

## Persistence

SQLite persistence and migration handling belong to the
database implementation phase.

This phase defines data contracts and validation only.

## Guest and Account Data

Guest discovery and pathway generation are available
without registration.

Persistent account ownership and synchronized progress
require authenticated authorization in later phases.

Do not include learner personal information in catalog
fixtures or version-controlled datasets.

## Versioning and Compatibility

Contract changes require documented compatibility checks.

Avoid silently changing required fields or enum values.

All future adapters must normalize external resources into
the approved contract before recommendation processing.