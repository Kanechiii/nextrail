# Guest API and optional account authentication

The FastAPI application factory is in `services/api/nextrail_api`. The default database is ephemeral, and no production host or paid provider is configured. Guest endpoints `GET /v1/courses` and `POST /v1/pathways/preview` operate without accounts. Sample catalog entries are synthetic and are excluded from public discovery. Guest pathway generation uses deterministic mode.

Account endpoints include registration, login, logout, self-profile, saved pathways and their progress, saved course references, and audit events. Private routes derive the owner ID exclusively from verified bearer sessions, never from a client-supplied owner field. Stored session tokens and reset tokens are hashed; passwords use salted PBKDF2-SHA256. Sessions expire after 24 hours; password-reset tokens expire after 15 minutes. Failed login attempts are throttled by normalized email. Password resets revoke existing sessions.

An isolated authentication schema is added transactionally beside the existing v1 learning tables, without resetting their user_version or deleting legacy records. A password-reset request always returns a generic acknowledgment. Delivery of reset links is dependency-injected and **not configured in the default application**; without an approved delivery service the endpoint does not issue a token. Production use requires approved delivery, per-IP throttling, email verification, account deletion and privacy controls, server-side logging policy, TLS and origin policy, browser CSRF mitigation if cookie sessions are later introduced, and additional security review. The default bearer-only model does not issue cookies.

No deployment, cloud service, hosted account provider, or fee-based integration is enabled. Tests exercise registration, authentication, session expiry, cross-account authorization, and guest access.

To run locally after installing API dependencies: `uvicorn nextrail_api.main:app --app-dir services/api`. Avoid exposing a development server to the internet.
