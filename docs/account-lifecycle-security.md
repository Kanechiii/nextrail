# Account lifecycle and security — Phase 18

## Scope and principles

This backend-only phase adds account management to Nextrail's existing local,
optional account system. Guests still discover courses and preview learning
routes without registration. All private operations derive owner identity
exclusively from an unexpired, verified bearer token. No UI files, hosted
authentication, email services, paid providers, live crawling, or deployment
settings change.

New routes, all under the existing `/v1/me` authorization boundary:

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/v1/me/sessions` | Return the count of unexpired, nonrevoked sessions; no token identifiers |
| POST | `/v1/me/sessions/revoke-others` | Keep the current session; revoke all other active sessions |
| POST | `/v1/me/password` | Confirm current password, set new password, revoke all sessions and reset tokens |
| GET | `/v1/me/export` | Return an owner-only JSON export without credential hashes or bearer tokens |
| DELETE | `/v1/me/account` | Reauthenticate and permanently purge the current account's local records |

Existing `/v1/auth/login`, `/v1/auth/logout`,
`/v1/auth/password-reset/request` and
`/v1/auth/password-reset/confirm` remain backwards compatible.
Sessions expire after 24 hours. Password hash storage remains salted
PBKDF2-SHA256. Password change requires a different, valid 12–128 character
new password. Existing sessions, including the changing session, become invalid
immediately after password change. Login is required again.

Sensitive endpoints have the API's no-store response policy and separate
per-client development rate-limiter buckets. The rate limiter is in memory
and is **not** adequate for publicly exposed or multi-process deployments.

## Export

A successful export includes account identity, onboarding preferences, owned
saved pathways and per-milestone progress, saved course IDs, and scoped
append-only audit events. It never includes password hashes, bearer strings,
reset tokens, session hashes or other users' records.

An export is a sensitive personal-data document. Do not publish it in GitHub,
attach it to an issue, or sync it unencrypted to shared storage.

Synchronous exports fail closed rather than silently truncating after 500
saved pathways, 2,000 saved courses, 5,000 audit records or 2 MB serialized
JSON. Large accounts will require a separately approved paginated/bulk
export process. The API uses a read-consistent SQLite transaction.

## Account deletion

`DELETE /v1/me/account` requires a current bearer token, the account's
current password and the **exact** explicit confirmation string
`DELETE MY ACCOUNT`. It returns `{"deleted":true}` only after its SQLite
transaction commits. All sessions become unusable, and the same account
cannot be recovered by signing back in.

The purge deletes the selected account's local profiles, authentication
sessions, password reset records, saved learning routes, progress, saved
courses, login throttling records, and account-scoped audit history. It
must not remove any other account's data. To respect the established
append-only audit protection on ordinary operations, the service temporarily
lifts the **specific audit deletion trigger inside a single SQLite write
transaction**, deletes only that owner's data and recreates the exact original
trigger before commit. It checks the expected trigger definition beforehand.
Any SQL failure rolls back both the data erasure and trigger changes.
Tests verify the append-only trigger remains active and other accounts are
unaffected.

**Deletion is permanent for the active local SQLite database but not an
automatic wipe of separate backups.** Phase 15 encrypted/retained backups,
database copies, operating-system snapshots, exports and shared devices require
their own data retention/deletion plan before production use. The SQLite
file may also retain freed pages until secure database disposal or a
separately approved sanitization policy; no claim of forensic erasure is
made. The API never changes or deletes backup files.

Do not test account deletion using your real learning account. Use a
disposable local database and a newly registered test account. No email
confirmation or hosted recovery provider is configured.

## Local validation and mandatory synchronization

Run these commands from the repository root in VS Code PowerShell.
Preserve uncommitted changes first; do not run `reset --hard`,
`git clean`, or delete your existing stash.

```powershell
git status --short --branch
git fetch origin
git branch --list feat/account-lifecycle-security
```

When the local phase branch does not exist, run
`git switch --track origin/feat/account-lifecycle-security`.
If it exists, switch to it and run
`git pull --ff-only origin feat/account-lifecycle-security`.

Validate the entire repo:

```powershell
python scripts/validate_repository.py
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/evaluate_pathways.py
python scripts/validate_discovery.py
python -m compileall -q services/api
cd apps/web
npm ci
npm test
npm run build
cd ../..
```

For manual API checks, start a fresh local server with a **disposable,
nonexistent** database filename such as
`data/nextrail-phase18-review.sqlite`, then use
`http://127.0.0.1:8018/docs`. Test session count, revocation,
password change, export, and deletion using only that disposable account.
An existing local SQLite database may retain data from earlier tests, so
do not reuse it for destructive acceptance testing.

After the PR has been manually squash-merged and the **post-merge** GitHub
Actions run succeeds, synchronize local `main`:

```powershell
git fetch --prune origin
git switch main
git pull --ff-only origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git stash list
```

The two SHAs must match; any earlier local stash must remain intact unless
you explicitly choose otherwise. The branch PR stays unmerged until local
security and destructive-operation acceptance has passed.

## Remaining release blockers

Public account deployment still requires an approved email verification and
recovery provider, encryption/TLS and origin controls, persistent distributed
rate limiting, privacy/legal retention policy, authenticated deletion
confirmation UX, encrypted backup lifecycle, database sanitization and
multi-process connection management. This phase uses no paid services.
