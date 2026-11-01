# Windows development-server smoke compatibility

This corrects the Windows process-launch failure introduced in the
`npm run test:dev` automation, without changing the application's
FastAPI, React, provider, account or production deployment behavior.

## Cause and resolution

The previous smoke test attempted to call `spawn('npm.cmd', ...)` from
Node.js. Modern Node.js on Windows cannot execute `.cmd` or `.bat`
command shims through `child_process.spawn` without a shell; that
raises `EINVAL`. Enabling `shell: true` would require extra
command-string quoting and can introduce command-injection risks.

Instead, the script obtains the npm CLI JavaScript path from
`npm_execpath`, automatically provided by the `npm run` lifecycle,
and executes it using the actual `process.execPath` (`node.exe`).
The existing npm script `dev`, Vite options, and loopback-only
settings are unchanged. Windows paths with spaces remain separate
argument array elements; no shell is involved.

This assumes a normal Node/npm installation. Run the test through
**`npm run test:dev`**, not by directly invoking the script using
`node tests/dev-server-smoke.mjs`.

## Windows local verification

From a PowerShell terminal in the existing synced Nextrail checkout:

```powershell
git status --short
git fetch origin
git switch main
git pull --ff-only origin main
Set-Location apps/web
node --version
npm --version
npm ci --no-audit --no-fund
npm test
npm run build
npm run test:dev
```

Ports **8000** and **5173** must be free. Stop other Nextrail
development servers before launching the smoke test. The test launches
a loopback FastAPI service and Vite dev server, validates their proxy
and React modules, and terminates its test processes. If supported
Chrome or Chromium can be discovered in PATH or `CHROME_BIN`, the
optional rendered-browser interaction suite also executes. Otherwise
the script reports a browser-skip rather than misrepresenting
automated browser validation as completed.

Success looks like `PASS: npm run dev served React, Vite transforms
and FastAPI proxy on loopback` followed by
`PASS: Development-server smoke finished without deployment or paid services`.

If Python, npm, Node, ports, Chrome, or local environment settings are
unavailable, the output will identify that independent prerequisite.
The exception `spawn EINVAL` should no longer result from the
Windows npm-launch path.

## Test scope and cost control

CI on the existing Linux runner now tests both the ordinary Unix
launch and a simulated Windows launcher branch with a space-containing
CLI path and `shell:false`. That is a source and cross-platform
process-contract check, **not a real Windows machine test**.

A Windows hosted-runner job was intentionally not activated for the
private repository to avoid unintended usage costs. The Windows
acceptance gate remains a manual run through the local checkout.

No paid service, provider source, account permission, git stash or
production release gate is changed. Merge only after user review.
