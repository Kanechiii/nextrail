# Security and deterministic AI release gates

This phase adds reproducible negative security tests and offline pathway evaluations. All checks are local and do not activate cloud inference, download models, or perform external course verification.

## API safety

API request bodies reject unexpected fields, and HTTP responses use no-store caching and restrictive framing, referrer, content-type and permissions headers. A bounded per-process fixed-window limiter protects guest previews, discovery, registration, login and password reset endpoints. It does not trust proxy-forwarded addresses and must **not** be treated as distributed production-grade rate limiting. Future deployments require trusted proxy setup, shared throttling, account-level abuse detection, HTTPS, production monitoring, session lifecycle and privacy checks.

## Deterministic evaluation

`python scripts/evaluate_pathways.py` uses the synthetic catalog and existing real orchestration engine to assess prerequisite ordering, no invented resource IDs, deterministic fallback, and prompt-injection-shaped career goals. No live model is evaluated; these tests do not establish generative-model accuracy or public course availability.

## Validation

Run `python -m unittest discover -s scripts -p "test_*.py" -v`, `python scripts/evaluate_pathways.py`, `python scripts/validate_repository.py`, `python scripts/validate_catalog.py`, and `python scripts/validate_discovery.py`. Run frontend `npm test` and `npm run build` from the web application workspace. Passing checks are necessary but not proof of full production security or real-world recommendation quality.

## Production release boundaries

No public account deployment, paid provider, live ingestion, email delivery or database migration is authorized here. Sensitive account production deployment remains blocked pending security review and operational controls.
