# Offline SQLite restore rehearsal — Phase 27

Nextrail can already create no-overwrite SQLite backups and inspect their
integrity. The separate restore-rehearsal check now demonstrates that a
**pinned backup can be restored to a disposable database file**, with complete
logical table contents and schema compared to the original backup. It then
removes the disposable copy. No existing database or backup is replaced.

## Preconditions and operation

Use only an operator-approved **disposable local database** for test runs.
The command requires an existing active SQLite database in WAL mode, an
independent consistent SQLite backup, an exact lowercase SHA-256 pin of that
backup, and a freshness policy (24 hours by default).

The command first executes the Phase 27 active/backup integrity and freshness
preflight, requiring compatible learning/account/preference schemas, append-only
audit guards and any optional shared rate-limiter metadata. Next it:

1. Calculates an internal, non-displayed logical fingerprint of all backed-up
   tables, rows and schema definitions.
2. Uses SQLite's consistent backup API to restore the backup to a **new file
   in an automatically cleaned operating-system temporary directory**.
3. Verifies restored integrity, schema and all logical table contents against
   the pinned backup, without revealing accounts, tokens, emails, or row hashes.
4. Rechecks the backup's SHA-256 to detect changes during the rehearsal.
5. Removes the temporary copy and emits non-sensitive pass/fail metadata.

No restore is performed onto the active SQLite file, and the database,
backup, filesystem paths, private learner records, or credentials are not
included in output. The command makes no provider, network or cloud calls.

## Run in PowerShell (with an existing disposable test database)

From the repository root, replace the two input paths with a local test
database and a fresh backup that you explicitly created for this purpose:

```powershell
$database = "data/nextrail-local.sqlite"
$backup = "data/nextrail-disposable-backup.sqlite"
$pin = (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()

python scripts/rehearse_database_restore.py --database $database --backup $backup --backup-sha256 $pin --max-backup-age-hours 24
```

The command does **not** create either input file. Both must exist and must
be different regular files. The backup must be recent and integrity checked;
the active database must already have the supported tables. If either file
is missing, do not overwrite a live database to make the check pass.
Use the existing `scripts/database_recovery.py backup --source ... --destination ...`
command to create a new uniquely named backup, never an existing filename.

The full offline backend unittest suite exercises successful rehearsals,
tampered files, outdated backups, altered restored rows, unsupported schemas,
shared-limiter metadata, and cleanup after failures, using synthetic
throwaway databases.

## Limits and production boundary

This is **not** a full disaster-recovery certification. It does not prove
storage encryption, secure secret management, cloud backup durability,
independent backup authenticity, recovery-time objective (RTO), recovery-
point objective (RPO), simultaneous live writes, operational restoration,
off-site recovery, availability under failures, access controls, or
multi-host deployment correctness.

It proves only that the supplied, operator-pinned local backup is recoverable
and logically consistent under the tested environment. The pre-release
acceptance gate remains blocked; do not mark Phase 27 complete or expose
production account data based only on this check.

After a manually approved squash merge, synchronize and test only the
existing local checkout:

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

Stop if Git reports local conflicts or unexpected modifications. Do not
create extra worktrees, reset or clean existing changes, pop stashes, enable
paid infrastructure, or merge this PR automatically.
