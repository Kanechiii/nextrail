# Pre-release security and production acceptance — evidence inventory

This is an **offline, non-deployment release gate** for Nextrail. It consolidates
outstanding Phase 25–28 work without silently declaring those phases complete.
Nothing in this phase enables cloud infrastructure, a paid service, a provider
integration, account email delivery, production data processing or deployment.

## Required acceptance gates

The versioned contract contains exactly ten items:

1. `authorized_provider_integration`: official terms/permissions and enforcement
   at the real-source publication boundary, not just local synthetic fixtures.
2. `reviewed_catalog_publication`: approved-source provenance, fresh listing
   and cost claims, explicit reviewer activation and pinned release evidence.
3. `production_account_recovery`: verified account ownership and approved
   recovery delivery under actual production identity controls.
4. `transport_origin_and_abuse_controls`: TLS, trusted origin/proxy policy,
   safe sessions, rate limiting and abuse handling appropriate for hosting.
5. `privacy_retention_and_erasure`: approved data handling, account erasure,
   backup lifecycle, retention, audit and applicable notices.
6. `database_backup_and_restore`: protected durable storage, integrity-checked
   encrypted backups, demonstrated restoration and retention.
7. `reliability_load_and_observability`: representative concurrent-load and
   failure-recovery evidence, operational logging and monitoring.
8. `security_and_regression_validation`: latest relevant PR/main CI, local
   acceptance and independent security review.
9. `rollback_and_incident_response`: tested rollback, contingency runbook,
   alerts and response ownership.
10. `manual_release_approval`: explicit operator release decision after
    reviewing the actual evidence and every open blocker.

The initial `data/pre-release-acceptance.sample.json` intentionally marks
**every gate pending**. This is the correct state; merging the acceptance
contract does not complete any of these production requirements.

## Read-only validation

From the existing Nextrail repository root:

```powershell
python scripts/verify_pre_release_acceptance.py --manifest data/pre-release-acceptance.sample.json --expect-blocked
```

Expected result: an enumerated blocked register, zero approved records,
`production_approval=false` and a successful CI **test of the blocked baseline**.

Without `--expect-blocked`, an incomplete register exits with code 1. Invalid
JSON, stale assertions or tampered evidence exits with code 2. For a separately
reviewed, local register containing approved entries, supply the separate
`--evidence-dir` option. Approved records have an exact reviewer ID, timezone-
aware review timestamp no older than 90 days, distinct existing evidence file
(basename only, not a directory traversal) and its lowercase SHA-256 pin.
Files are read but never changed. A valid `evidence_complete` report still
includes `production_approval=false`.

## Final sign-off separation (Phase 29 hardening)

The last gate, `manual_release_approval`, now follows stricter, fail-closed
sequencing than the nine prerequisite checks:

- All nine prerequisite gates must have individual current approval records
  and distinct, SHA-256-matched local evidence files before the final release
  sign-off can be recorded. A final approval alongside any pending prerequisite
  is **invalid**, rather than silently counted as an approved release.
- The recorded final release reviewer must have a **different pseudonymous
  reviewer identifier from every reviewer** who approved a prerequisite gate.
  This provides a narrow separation-of-duties consistency check.
- The final review timestamp must be **strictly later than** all prerequisite
  review timestamps, after normalizing time zones to UTC. A stale, backdated,
  simultaneous, or prematurely recorded final sign-off is refused.
- The checker reports `manual_signoff_separated=true` only when this recorded
  separation and order is internally valid. This is **not proof of actual
  reviewer independence** and does not authorize deployment.

Reviewers' IDs and dates are operator assertions, not verified identities or
cryptographic signatures. One person could falsify two identities and a SHA-256
pin; this tool cannot detect that. Keep actual approvals and sensitive evidence
outside GitHub and independently verify the reviewers, provider permissions,
deployment boundaries, host security, backup recovery, incident response and
the current revision before authorizing a release. If an independent reviewer
is not available, **leave the final gate pending**. Do not fabricate an
approval to make the sample check pass.

**Do not place actual production approval evidence, real account records,
provider credentials, access tokens, private terms or encryption keys in
the repository.** Store sensitive evidence in a protected local/operator
location, and only provide redacted non-sensitive review material through
approved processes. An operator's assertion and a local SHA-256 check are not
independent proof of the substance of a provider's permission, security audit
or lawful data processing. Only a responsible human can authorize deployment.

The checker has no network access and cannot verify GitHub workflow status,
DNS, TLS, provider agreements, cloud database controls or a production backup.
Those must be reviewed independently before completing the release register.
For detailed local controls, continue using `scripts/verify_release.py`,
`scripts/verify_database_readiness.py`, the provider authorization preflight,
`scripts/evaluate_api_reliability.py` and the full regression suite.

## GitHub and local release process

Leave this PR open until the new negative tests and the full CI suite pass.
Review and manually squash-merge it; never treat a merge as release approval.
After the merge, run the following from the existing PowerShell checkout.
No additional worktrees or stash manipulation are required:

```powershell
Set-Location E:\Projects\nextrail
git status --short
git fetch origin
git switch main
git pull --ff-only origin main

python scripts/validate_repository.py
python scripts/validate_catalog.py
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/evaluate_pathways.py
python scripts/evaluate_api_reliability.py --iterations 12 --max-p95-ms 3000
python scripts/validate_discovery.py
python scripts/verify_source_authorizations.py --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json
python scripts/verify_pre_release_acceptance.py --manifest data/pre-release-acceptance.sample.json --expect-blocked

Set-Location apps/web
npm test
npm run build
Set-Location ../..
git status --short
git log -1 --oneline
```

Stop if Git reports local conflicts, a diverged branch, failing regression
checks or an unexpected acceptance result; do not force, clean, reset or
silently apply any preserved stash.

## Release decision boundary

The production acceptance gate remains **blocked** while earlier requirements
are incomplete. It cannot be closed simply because its own tests pass.
Formal release approval requires the completed evidence record, actual
independent validation, successful deployment rehearsal and an explicit
human phase-level sign-off. A passing sample preflight is proof only that the
software correctly refuses an incomplete release register.
