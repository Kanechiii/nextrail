# Local SQLite durability and recovery

## Why this backend phase exists

Nextrail's guest discovery and pathway previews must remain usable without
authentication or persistent storage. Registered accounts, saved courses, learning
preferences and progress, however, require a durable database for data to survive
backend restarts. The FastAPI entry point intentionally defaults to `:memory:` for
offline tests and demos, so **durability must be configured explicitly**.

## Configure local durable storage

From the repository root, ensure the `data` directory already exists. For the
current PowerShell process, set the local database path and require durability:

```powershell
$env:NEXTRAIL_DB_PATH = "data/nextrail-local.sqlite"
$env:NEXTRAIL_REQUIRE_DURABLE_STORAGE = "true"
python -m uvicorn nextrail_api.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

The require-durability flag rejects the default in-memory path at startup rather
than silently losing account progress. This flag is **not** a production-security
switch and does not activate hosting or guarantee cross-device availability.
SQLite URI paths, missing parent directories, and database symlinks are rejected.
The database and WAL sidecar files remain Git-ignored.

## Inspect and back up safely

Backup files can contain account email addresses, password hashes, session-token
hashes, saved pathways, preferences, progress and audit history. Treat backups as
**sensitive private user data**: choose a protected local backup directory, restrict
access with OS filesystem permissions, avoid screenshots or cloud syncing of
backups, and store encrypted copies only under an explicitly approved process.

The commands below must be run from the repository root. An output target must
**not already exist**. Existing files are never replaced.

```powershell
python scripts/database_recovery.py inspect --source data/nextrail-local.sqlite
python scripts/database_recovery.py backup --source data/nextrail-local.sqlite --destination data/nextrail-backup-20261101.sqlite
python scripts/database_recovery.py inspect --source data/nextrail-backup-20261101.sqlite
```

The tool opens the source read-only, checks SQLite integrity and foreign keys,
verifies all required learning/authentication/preferences schema tables and
versions, and uses SQLite's online backup API to capture a committed snapshot,
including committed changes in WAL mode. The snapshot is checked again before an
exclusive no-overwrite publish. It never logs account records or issues
credentials, never requires a cloud service, and never schedules backups itself.

Use a fresh backup filename for every independent backup. Do not run SQLite file
copy operations directly against a live WAL database.

## Recovery drill without overwriting data

Stop the backend before changing which database path it uses. Restore an approved
backup **only to a new, nonexistent file**:

```powershell
python scripts/database_recovery.py restore --source data/nextrail-backup-20261101.sqlite --destination data/nextrail-restored.sqlite
python scripts/database_recovery.py inspect --source data/nextrail-restored.sqlite
```

Start a separate local backend session with
`NEXTRAIL_DB_PATH=data/nextrail-restored.sqlite` and
`NEXTRAIL_REQUIRE_DURABLE_STORAGE=true`. Confirm the expected account and
progress information through authenticated routes in the local demo. Never expose
a restored copy publicly while its historical sessions are present. Restore
copies of an auth database can contain active session hashes; revoke or rotate
sessions before any use beyond isolated local recovery testing.

Do not replace the original database automatically. A production recovery
process needs a separately reviewed retention, encryption and incident-response
policy.

## Validation gates

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/evaluate_pathways.py
python -m compileall -q services/api
```

Tests exercise WAL snapshots, account preferences, learning progress, backups,
fresh-location restores, schema failures, corrupt files, missing files, rejected
overwrites, and explicit durability configuration. Existing guest endpoints must
continue to work in the default offline test setup.

## Follow-up boundaries

This is a **local database reliability foundation**, not a production launch:
multi-process connection management, account recovery delivery, secure hosted
database migration, offsite encrypted backup retention, data deletion/export,
service-wide rate limiting and observability remain subject to later review.
The reverted themed UI PR is outside this backend phase.
