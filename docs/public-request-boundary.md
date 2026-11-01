# Opt-in public HTTPS request boundary — Phase 26 follow-up

This is a **configuration and request-validation safeguard**, not an approval
to expose Nextrail on the public internet. The current local/default API
remains unchanged. It does not provision a domain, TLS certificate, reverse
proxy, production account recovery delivery, or cloud infrastructure.

## Activation contract

The API entry point accepts an optional `NEXTRAIL_PUBLIC_ORIGIN` environment
variable, containing **exactly** one lowercase DNS HTTPS origin. Example
for illustration only: `https://learn.example.org`. It may not contain
credentials, a port, a path, query, fragment or IP literal. The example
does not identify a registered Nextrail domain.

When this mode is enabled at startup, the operator **must** also supply:

- `NEXTRAIL_REQUIRE_DURABLE_STORAGE=true`
- `NEXTRAIL_DB_PATH` pointing to an approved file-backed SQLite database
- `NEXTRAIL_RATE_LIMIT_HMAC_KEY` as a securely generated 32-byte lowercase
  hexadecimal key shared by workers using that database

Missing or malformed configuration fails at startup instead of silently using
in-memory account storage or per-process request throttling.

For an isolated **local controlled environment only**, from the repository
root after you have configured a disposable database:

```powershell
$env:NEXTRAIL_REQUIRE_DURABLE_STORAGE = "true"
$env:NEXTRAIL_DB_PATH = "data/nextrail-local.sqlite"
$env:NEXTRAIL_RATE_LIMIT_HMAC_KEY = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
$env:NEXTRAIL_PUBLIC_ORIGIN = "https://learn.example.org"
```

This is **not** a valid immediate local HTTP startup configuration: requests
arriving over HTTP will be rejected by design. Never test the public boundary
by trying to expose the demo API on the internet.

## Request behavior

When enabled, every request must arrive with the **ASGI scheme `https`**
and an exact `Host` matching the configured public origin (an explicit
`:443` port in the Host header is accepted). If an `Origin` header is
provided, it must exactly match the approved origin. A different origin,
plain HTTP, an unexpected Host, or an absent Host receives a generic
HTTP 403 response without a redirect. Successful trusted HTTPS responses
include `Strict-Transport-Security: max-age=31536000`.

`X-Forwarded-Proto` and `X-Forwarded-Host` are **not trusted by this
module**. The ASGI server's separate trusted-proxy configuration determines
whether it rewrites request scheme/host. If TLS is terminated at a proxy
but the application receives an HTTP ASGI scheme, the gate rejects the
request. Configure and audit any reverse proxy, trusted proxy addresses,
TLS and origin routing separately. Do not enable broad forwarded-header
trust as a workaround.

This boundary is not a CSRF, authentication, CORS, or credential-protection
replacement. Requests without an `Origin` header are still accepted if
they satisfy HTTPS and Host controls; non-browser clients often omit Origin.
No permissive CORS middleware is introduced and the existing bearer-token
ownership checks remain mandatory.

## Verification and outstanding blockers

The offline suite checks exact-host and origin mismatch rejection, HTTP and
forwarded-header spoofing, anonymous access, HSTS, privacy no-store headers,
invalid configuration, and unchanged local defaults.

```powershell
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/evaluate_api_reliability.py --iterations 12 --max-p95-ms 3000
```

Before a public release, independently finish account verification/recovery,
operational observability, TLS termination and trusted proxy configuration,
security review, data retention, backups, provider authorization, and
the ten formal pre-release acceptance gates. A successful unit test or
merged PR does not fulfill those requirements.

After manual squash merge, only synchronize the existing `main` checkout.
Do not create worktrees, discard local changes, reset branches, auto-merge,
or expose credentials in GitHub comments or committed source.
