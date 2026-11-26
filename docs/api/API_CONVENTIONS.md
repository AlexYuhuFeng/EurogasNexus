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

One style (`application/keyset_paging.py`, the audit retrieval's style made general):

- `limit` (default 1,000, at most 10,000), `cursor`, and the range `from_utc`/`to_utc`
  (ISO 8601 with an offset); rows newest first by `(timestamp, id)`.
- Every page states `meta.continuation = {anchor_utc, limit, returned, has_more, cursor}`;
  follow `cursor` until `has_more` is false. A cursor used with other filters is refused
  (400 `page_cursor_filter_mismatch`); a bound without an offset is refused (400
  `page_window_timezone_required`). A CSV page carries `X-Eurogas-Page-Limit`,
  `X-Eurogas-Has-More` and `X-Eurogas-Next-Cursor` headers.
- A caller that needs a whole range asks for the range; nothing fetches a whole table.

Paged this way: `/api/market/observations`, `/api/market/fx`, `/api/audit` (its own cursor
of the same shape). Older list endpoints take `limit` only and are being moved to this
style (backend audit A5); a calculation whose inputs exceed its read bound refuses with 422
`read_bound_exceeded` instead of using part of them.

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
