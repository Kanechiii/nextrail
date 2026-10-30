# Nextrail learning studio

The React 19 + TypeScript + Vite + Tailwind web client lives in `apps/web`. It exposes three views: guest-first course discovery, prerequisite-aware pathway builder, and optional account-specific learning progress. Layout is responsive and relies on a subdued botanical-green visual language rather than fabricated analytics or popularity indicators.

## Local startup

Install dependencies from `apps/web` using `npm install`. Start the backend separately with `python -m uvicorn nextrail_api.main:app --app-dir services/api --host 127.0.0.1 --port 8000`. Run `npm run dev` for the local frontend. The Vite proxy maps `/api` to the loopback backend. `VITE_API_BASE_URL` optionally overrides the frontend request prefix; never place passwords or bearer tokens in public Vite environment variables. Run `npm run build` and `npm test` before reviewing changes.

## Guest access and evidence

The default course list is derived solely from the backend's approved-source `/v1/courses` endpoint. Synthetic UI examples are explicitly opted into and have no source links or bookmark actions. Empty catalogs show honest empty states and a link to pathway planning. Learning paths are produced by `/v1/pathways/preview`, not generated locally by a mock service. The new public `/v1/skills` endpoint surfaces reviewed catalog skills for planner options.

## Optional accounts

Login and registration use the existing server-side authentication service. Tokens are held in React memory state and are never written to local/session storage. Reloading the page therefore ends the local sign-in state. Saved pathways, milestone progress, and bookmarks use bearer-protected existing endpoints; the UI never sends an arbitrary owner identifier. Reset requests are presented accurately: email delivery is not enabled by default.

## Limitations

This phase does not add a public hosting deployment, a production identity provider, live source authorizations, certificate verification, free-course proofs, or cross-device synchronization services. The backend still requires production privacy, email verification, rate limiting, recovery delivery, and security hardening before a public account launch.

## Verification

`npm test` checks guest access boundaries and demo labeling. `npm run build` type-checks and produces a production bundle. GitHub Actions runs these checks alongside the existing backend test suite.
