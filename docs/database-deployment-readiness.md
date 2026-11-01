# Offline database deployment readiness

This backend-only preflight is a **single-host SQLite readiness check**, not
a production-launch approval, hosted database migration, or backup scheduler.

It verifies a non-symlink active SQLite file, existing learning/auth/preferences
schema versions, integrity and foreign keys, active WAL journal mode, required
append-only audit guards and any opted-in shared rate-limit metadata. It
requires a separate, recent, integrity-checked backup with an operator-supplied
lowercase SHA-256 digest; backup and active schema versions must match. The
command performs no write, restoration, cloud call, migration or data publication.

## Local PowerShell procedure

Run from your existing Nextrail repository after manually synchronizing main.
Use an **existing disposable SQLite test database**, not the live account
database. The backup's destination filename must not exist.

```powershell
python scripts/database_recovery.py inspect --source data/nextrail-local.sqlite
$backup = "data/nextrail-readiness-{0}.sqlite" -f [guid]::NewGuid().ToString("N")
python scripts/database_recovery.py backup --source data/nextrail-local.sqlite --destination $backup
if ($LASTEXITCODE -ne 0) { throw "Backup creation failed" }
$pin = (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()
python scripts/verify_database_readiness.py --database data/nextrail-local.sqlite --backup $backup --backup-sha256 $pin --max-backup-age-hours 24
if ($LASTEXITCODE -ne 0) { throw "Database readiness validation failed" }
```

For a missing local database, create and test a separate disposable SQLite file
through the existing API test/development flow first. Do not initialize an
unapproved replacement for an existing account database.

The backup SHA-256 pin protects file consistency against accidental changes; it
does not prove that the backup was made by an authorized operator. File
modification time is a bounded freshness heuristic, not authenticated backup
metadata. An attacker who controls the file and matching expected hash can
forge evidence; independent backup access controls remain required.

A separate `scripts/rehearse_database_restore.py` command now provides an
**offline disposable restore rehearsal** after the active/backup readiness check.
See `docs/database-restore-rehearsal.md`; it creates a verified temporary
restore without overwriting the active database or backup. Neither preflight
authorizes production.

A successful result does **not** verify OS ACLs, storage or transport
encryption, remote replication, key management, disaster-recovery objectives,
secure backup disposal, multi-host database behavior, delivery of account
recovery messages, or compliance/retention policies. These require later
reviewed implementation and testing. Phase 26 security controls also remain
separate. No paid provider, hosting, automatic restore or live ingestion is
activated.

## Post-merge local sync and regression

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
python scripts/validate_discovery.py
python scripts/verify_source_authorizations.py --sources data/sources.sample.json --authorizations data/provider-authorizations.sample.json
Set-Location apps/web
npm test
npm run build
Set-Location ../..
git status --short
git log -1 --oneline
```

Stop if Git reports local changes, divergence or failed verification. Never
force-reset, clean, overwrite backup files or pop a preserved stash as part
of routine synchronization.
