# Public API Conventions

Stable unversioned `/api` surface conventions shared by Web, SDK, CLI,
Desktop, and the MCP server. These are the *defaults*; per-endpoint deviations
are documented in their OpenAPI operation.

## Envelope

Every public response is `{"data": ..., "meta": {...}}`.

`meta` carries:

- `research_only: bool` — always `true` in this preview product;
- `human_review_required: bool` — always `true` for decision-support outputs;
- `source_references: string[]` — provenance of the payload
  (`runtime-postgresql`, `operator-input`, `domain-contract`, ...);
- `warnings: string[]` — non-fatal condition codes (`UPPER_SNAKE_CASE`).

Decision-support meta may additionally carry `run_id`, `snapshot_id`, and
`decision_context` (`SANDBOX_SCENARIO` | `RUNTIME_DECISION`).

## Pagination

List endpoints accept optional `limit` (and only `limit` in V1):

- `limit`: `1..N` inclusive, endpoint-specific cap (100–2000).
  Omitted → endpoint default. Out-of-range → 422 by FastAPI validation.
- There is no `offset`/cursor in V1; lists are newest-first or
  repository-ordered and bounded.

Endpoints with `limit`: `/api/glossary`, `/api/ingestion-runs`,
`/api/market/*` (observations/quotes/spreads/normalized),
`/api/monitoring/alerts`, `/api/reference-network/*` (nodes/edges/facilities/
market-hubs/tso-access), `/api/review/decisions`, `/api/strategy-lab/runs`.

## Errors

Failures use HTTP status codes and a `detail` body:

- `422` — request validation / business-input rejection with
  `detail: {"code": "<UPPER_SNAKE>", "message": "...", ...}` or FastAPI's
  standard validation array (field-level).
- `401` — authentication missing (`public_api_token_missing`,
  `operator_principal_missing`).
- `403` — authentication invalid or policy denied (`entitlement_denied`,
  `export_denied`, `operator_principal_invalid`).
- `404` — unknown resource (`optimization_run_not_found`, ...).
- `503` — runtime DB unavailable (`runtime_db_unavailable`,
  `runtime_db_not_configured`, `public_api_token_not_configured`).

`detail` may carry extra structured fields (`code`, `message`,
`error_class`, `research_only`, `human_review_required`); clients should
treat `detail.message` (or `detail` string) as the human-readable fallback
and `detail.code` as the machine code.

## Status semantics

Optimizer/workflow `status` values map to the ontology `StatusKind`
(SUCCESS | PARTIAL | BLOCKED | UNKNOWN). Raw solver endpoints
(`/api/optimization/*`) return `optimal | feasible | infeasible` in `data`
and the mapped `StatusKind` in persisted runs.
