# Bedrock integration — offline approval gate

This implementation contains only an offline, mock Amazon Bedrock Converse request/response adapter. It cannot create SDK clients, query credentials, discover AWS resources, call a live model, configure infrastructure or spend money. The default Nextrail service remains deterministic, and optional local Ollama support remains unchanged. The mock is available only to developer tests and **must never be presented as real model output**.

## Bounded contract

The offline adapter generates a Converse-shaped request from a reviewed career goal and eligible skill IDs, with a maximum output-token configuration. It accepts only an explicitly documented example model identifier and Region for payload-shape testing. Neither identifier is an authorization to invoke the real model; availability and pricing of these choices must be verified separately before any live design approval. Mock responses must contain exactly one eligible skill ID. Unknown model IDs, unapproved Regions, invented resources, excessive responses, or incomplete outputs are rejected.

## Financial and operational restrictions

No AWS billing activation, IAM policy, access key, boto3 dependency, production endpoint, Bedrock subscription, automatic fallback or AWS CI secret is permitted. Configuration values requesting live mode or approved spending are rejected. No cloud network transport exists in the adapter. Cloud invocation requires a future separately approved code change, precise model and Region selection, IAM policies, account eligibility and charges review, application quotas and budget monitoring. Cloud spending must never be inferred from free-tier labels or promotional credits.

AWS budget alerts are monitoring tools, not guaranteed hard real-time spending caps. No live use is approved in this phase.

## Validation

Run `python -m unittest discover -s scripts -p "test_*.py" -v`, `python scripts/evaluate_pathways.py` and `python -m compileall -q services/api/nextrail_bedrock`. The mock tests include strict configuration, output grounding and no-network assertions.

## Follow-up gate (not authorized)

A later phase review may consider a real SDK transport with explicit approval, model-specific pricing, permitted Regions, least-privilege IAM, cost monitoring, request ceilings, privacy review and measured comparison to deterministic/Ollama results. Do not activate or deploy this from the offline PR.
