# Dashboard review and local setup

## Review branch

Run these commands from your existing repository after committing or stashing any unrelated local work. Do not reset or clean your repository to switch branches.

```powershell
git status --short
git remote -v
git fetch origin
git switch --track origin/feat/dashboard-experience
git pull --ff-only origin feat/dashboard-experience
Set-Location apps/web
npm ci
npm test
npm run build
Set-Location ../..
```

If the local branch already exists, use `git switch feat/dashboard-experience` instead of creating its tracking branch again. Node 24 matches the repository CI runtime. Keep your existing Python virtual environment and database configuration.

## Run locally

Backend terminal, from the repository root:

```powershell
python -m pip install "fastapi>=0.115,<1" "httpx>=0.27,<1" "uvicorn>=0.30,<1"
python -m uvicorn nextrail_api.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

Frontend terminal, from the repository root:

```powershell
Set-Location apps/web
npm run dev
```

Open http://127.0.0.1:5173. The default API uses an in-memory database unless `NEXTRAIL_DB_PATH` is configured; accounts and saved progress in that default database disappear when the backend stops. Preserve any existing database setting and backups. The sample catalog contains synthetic records and may show an empty live catalog. Illustrative preview is explicitly labeled and must not offer enrollment links.

## Isolated browser automation

Playwright starts its own temporary API on `127.0.0.1:18000` and Vite preview server on `127.0.0.1:15173`. The API forces an in-memory test database even if your ordinary development terminal specifies a persistent database. Automated browser accounts therefore do not change your saved local learning data. The test servers do not reuse applications on the normal development ports (8000 and 5173).

From `apps/web`, after installing dependencies, run:

```powershell
npx playwright install chromium
npm run test:e2e
```

If a dedicated test port is already occupied, stop the conflicting process and retry. E2E tests need Python and the FastAPI dependencies in the current terminal environment, as well as the Chromium browser runtime. No AWS, cloud inference or external course source is required. Test results are written under ignored local Playwright paths.

## Windows local test reliability

The browser test suite runs one browser worker at a time on local computers and allows a 90-second test deadline to accommodate slower Windows browser startup and Python password hashing. CI continues to run two workers with a 45-second deadline. The guest pathway test verifies the HTTP preview response before asserting that a route was generated, so API failures produce an explicit HTTP status rather than a misleading heading timeout.

**Screenshots are optional locally**: functional checks run first, and images are captured only in CI by default. The route screenshot is taken after successful functional assertions; all review captures use the viewport and disable motion to avoid stalling account-save interactions.

From `apps/web`, run:

```powershell
npm run test:e2e
```

To inspect an individual workflow with an interactive browser:

```powershell
npx playwright test e2e/dashboard.spec.ts --project=desktop --grep "guest route" --headed --trace on --workers=1
```

To capture local screenshots as well:

```powershell
$env:NEXTRAIL_E2E_SCREENSHOTS = "1"
npm run test:e2e
Remove-Item Env:NEXTRAIL_E2E_SCREENSHOTS
```

If a test still fails, inspect the generated `test-results/.../error-context.md` or run `npx playwright show-trace` with the saved trace ZIP. Do not delete existing project work or databases to troubleshoot a browser timeout.

## Acceptance review

Review light, dark and system themes at desktop and mobile widths. Generate a guest pathway, inspect milestones, and verify prerequisites. Browse illustrative cards, hover into their landscape previews, dismiss with Escape, open details by keyboard and compare courses. Confirm cost fields remain separate and unknown facts remain unknown.

Create a local test account, save the guest route, mark and undo completion, switch saved routes, sign out and sign in again. Verify private progress is not shown to guests. Check loading, empty and unavailable API states, focus restoration and reduced motion. Custom keyboard shortcuts are intentionally excluded.

## Regression checks

```powershell
python scripts/validate_repository.py
python scripts/validate_catalog.py
python scripts/validate_discovery.py
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/evaluate_pathways.py
git diff --check
git status --short --branch
```

## After manual merge

Only after the PR is reviewed, checks pass and you merge it:

```powershell
git status --short
git fetch origin
git switch main
git pull --ff-only origin main
Set-Location apps/web
npm ci
npm test
npm run build
Set-Location ../..
git status --short --branch
```

Do not delete the review branch or alter existing history automatically. No AWS, paid inference or deployment setup is required.
