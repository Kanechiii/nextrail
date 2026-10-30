# Course discovery and source integration

## Scope

The first course-discovery layer is account-free, deterministic, and offline by default. It provides a reusable search and filtering service for later API and website integration, but does not yet expose an HTTP endpoint or web interface.

## Authorization gate

Every source has an explicit method, authorization state and allowed host list. Pending sources cannot enter ordinary discovery. Synthetic sources can only be loaded through an explicit preview mode and are always omitted from ordinary search. A provider registry entry alone does not grant permission to scrape.

No adapter makes outgoing network requests. Manual and official API records must be supplied as reviewed JSON snapshots; RSS/Atom content must be supplied as bounded bytes plus explicit skill annotations. Adding future network acquisition requires separate authorization, rate-limit and source-policy reviews.

## Data normalization

Normalization checks source identifiers, allowed HTTPS hosts, resource IDs, reviewed skill mappings, duplicates and record bounds. Import data defaults to unknown course and certificate costs, and to unverified source evidence. Normalization never fabricates prices or verification timestamps.

Normalized data uses the existing v1 catalog schema. A separate provenance map preserves source ID, source URL, external ID, method and verification state without changing the catalog contract.

## Guest discovery

The search interface requires no account and supports query, provider, skill, access-cost and certificate-cost filters. It returns stable and deterministic ordering. Synthetic records are excluded by default.

The synthetic sample fixtures use example.org and example.net and are not real courses. Free-course filters return no results for records whose cost has not been verified.

## Boundaries

The phase does not perform live website crawling, external API calls, unapproved RSS downloads, course price verification, persistent database writes, personalization, authentication, or a public frontend. Full source rights, freshness and claim-level review must be implemented before claiming public verified course availability.

## Validation

Run `python scripts/validate_discovery.py` and `python -m unittest discover -s scripts -p "test_*.py" -v`.
