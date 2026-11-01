# Learning workspace and progress API — Phase 17

## Scope and guarantees

This backend-only phase extends the existing FastAPI app and the current
`nextrail_storage` package. There is no new database schema, backend service,
UI rewrite, hosted storage, live provider integration or paid subscription.

Guests retain `GET /v1/skills`, `GET /v1/courses` and
`POST /v1/pathways/preview` without registration. Every new learning endpoint
requires a valid bearer session and derives the owner solely from that session.
No caller-supplied owner identifier is used to look up another account's data.

## Routes

| Method | Route | Description |
| --- | --- | --- |
| GET | `/v1/me/learning/summary` | Account-scoped page of saved pathway progress |
| GET | `/v1/me/pathways/{pathway_id}/workspace` | Saved milestones with current prerequisite readiness |
| DELETE | `/v1/me/pathways/{pathway_id}` | Permanently remove one owned saved pathway and its progress |

The summary endpoint accepts `limit` (1–50, default 20) and an optional
`after_id` cursor. Results sort by `created_at DESC,id DESC`, which remains
stable even when several routes share a timestamp. The response exposes
`next_cursor`, `saved_pathway_count` and `saved_course_count`. A nonexistent
or another account's cursor returns HTTP 404 without revealing ownership.
Invalid page sizes and cursor formats return HTTP 422.

Each summary item contains the saved pathway ID, creation time, career goal,
generation mode, completed and total milestones, and an integer completion
percentage. Results include **only the authenticated account's saved data**;
guest previews never write to the account database. The summary is a bounded
page; counts reflect the full account at the time of the request.

The workspace projection returns milestone order, skill labels (when still in
the current skill catalog), saved resource IDs, statuses, prerequisite IDs,
blocking skill IDs, and a deterministic next-ready skill. Possible readiness
values are `ready`, `blocked`, `prior_knowledge_unconfirmed`,
`catalog_skill_missing` and `completed`.

**Important truthfulness boundaries:**
- Completion means **self-reported** progress. It is not a provider-issued
  certificate, attendance verification or credential.
- Prerequisite status is computed from the **current** skill catalog. Any
  prerequisite absent from the saved route is **unconfirmed prior learning**,
  not automatically assumed completed. A saved skill removed from the current
  catalog is labeled missing rather than being fabricated.
- Saved course IDs are snapshot references, **not evidence** of current
  availability, pricing, provider rights or credential eligibility. The
  Phase 16 offline catalog pipeline is not activated by this change.
- Existing `PUT .../progress/{skill_id}` behavior remains compatible and
  user-controlled. Readiness indicators do not silently change or discard
  previously stored completion statuses.

Deleting a saved pathway is irreversible from the API. Milestone progress rows
are removed before the parent record in one transaction, and a minimal
append-only `pathway/deleted` audit entry is stored in that same transaction.
Audit details contain the count of milestones but no private goal text. If the
audit insert fails, the deletion rolls back completely. Deleting another user's
pathway or a missing pathway returns 404, without leaking its existence.

Deletion is not full account erasure. Account lifecycle, audit retention,
export, privacy policies and secure account deletion remain Phase 18 work.
SQLite persistence is limited to the configured local database; cross-device
synchronization requires separately reviewed hosted infrastructure.

## Local validation and repository synchronization

After the PR is opened, **fetch and switch to the phase branch before running
local tests**. In PowerShell from the repository root:

```powershell
git status --short --branch
git fetch origin
git switch --track origin/feat/learning-pathway-progress-api
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/evaluate_pathways.py
python -m compileall -q services/api
```

If the branch already exists locally, use `git switch` and a fast-forward-only
`git pull` instead. Do not reset or discard unpublished local changes.

Optional manual API review runs on the current backend:

```powershell
$env:NEXTRAIL_DB_PATH = "data/nextrail-local.sqlite"
$env:NEXTRAIL_REQUIRE_DURABLE_STORAGE = "true"
python -m uvicorn nextrail_api.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

Use `http://127.0.0.1:8000/docs` to authorize with a test account and
inspect the new endpoints. Test deletion with a **disposable local account**;
do not delete irreplaceable learning records. For durable account recovery,
use the non-destructive Phase 15 backup utility and keep its backups private.

After the user manually squash-merges this PR, wait for successful post-merge
`main` CI and synchronize the user's local checkout:

```powershell
git fetch --prune origin
git switch main
git pull --ff-only origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

The last two hashes must match. We cannot verify the local checkout from
GitHub alone; the user must confirm the PowerShell output. Only then close
Phase 17 or start Phase 18.

## Acceptance boundaries

The complete existing backend regression suite, the new authorization and
readiness tests, deterministic planning evaluation, and the unchanged
frontend tests/build must all pass. No UI files, paid services or deployments
are modified. No phase is merged automatically.
