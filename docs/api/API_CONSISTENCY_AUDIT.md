# API consistency audit (QA-03), 2026-11-15

Scope: every public path (244 paths, 264 operations; unchanged by this work). Method:
`scripts/ops/api_consistency_audit.py`, which reads the application's own OpenAPI document
and route modules (static pass), and calls every GET without a path parameter on the demo
desk (`scripts/demo/seed_demo_desk.py`) in a throwaway PostgreSQL schema (probe pass: 112
GETs; the three `/api/stream/*` server-sent event streams and the two OIDC redirects are
not probed). Checked: envelope (`data`/`meta`), error shape, pagination style, timestamp
format (ISO-8601 with `Z` or an offset), and money or price figures without a unit or
currency beside them.

Run it again with:

    python scripts/ops/api_consistency_audit.py --postgres <throwaway PostgreSQL URL> --json out.json

## Summary

| Area | Finding | Status |
|---|---|---|
| Envelope | Every probed 200 is `{data, meta}` except the four health probes | By design (liveness/readiness probes); proposal P5 |
| Error shape (top level) | Every failure has the same top level: `detail` plus `error`, `family`, `severity`, `recoverability`, `message_key`, `action_key`, `correlation_id` (`api/error_handlers.py`) | Consistent |
| Error shape (`detail`) | Three spellings: `{"code": ...}` (207 raise sites), `{"error": ...}` (65, mostly auth and entitlement dependencies), `{"error_code": ...}` (3), and a bare string (67 sites in 11 modules) | Proposal P1 |
| Pagination | 28 operations take `limit` only (truncate at the limit, no continuation); `GET /api/audit` uses `cursor` + `limit`; one revision list uses `limit` + `offset`; physical native reads refuse instead of truncating (`native_query_overflow`) | Proposal P2 |
| Timestamps | No timestamp without an offset in any probed response on PostgreSQL | Consistent |
| Timestamp-like names | `*_at` used for values that are not instants: `largest_at` ("NBP 2027-01", a month) in mandate usage, `daily_at` ("08:15", a time of day) in source schedules and freshness contracts | Proposal P3 |
| Money and units | `position-ladder`: `rows[].mark` and `curve[].price` had no unit (the hub's currency per MWh was implied) | **Fixed** (additive `mark_unit`, `curve[].unit`) |
| Money and units | Today: NBP price was shown per MWh in GBP although the desk's quotation is GBp/th | **Fixed** (Item 3; `unit` already present, value now native) |
| Bug | `GET /api/cost-observations/values` answered **500** whenever a runtime database was configured (the success path called the envelope helper without `warnings`) | **Fixed**, test added |
| Status for "no database" | Some reads answer 200 with empty `data` and a warning (`/api/desk/today`, cost observations, physical), others 503 `runtime_db_unavailable`/`runtime_db_not_configured` | Proposal P4 |

## Deviations

| # | Path(s) | Check | Deviation | Fix or proposal | Blast radius |
|---|---|---|---|---|---|
| D1 | `GET /api/cost-observations/values` | error / envelope | 500 `internal` on every call with a database | Fixed: `warnings=[]` passed; `tests/api/test_cost_observations_api.py` | None (was broken) |
| D2 | `GET /api/portfolio/position-ladder` | units | `rows[].mark`, `curve[].price` without unit | Fixed: additive `rows[].mark_unit`, `curve[].unit` (`EUR/MWh`, `GBP/MWh`); CSV export gains the `mark_unit` column | Additive; client ignores unknown fields |
| D3 | `GET /api/desk/today`, `POST /api/analysis/brief` | units | NBP shown in GBP/MWh | Fixed: shown in GBp/th through `domain/market/units.py`; marks and P&L stay per MWh | Value of NBP price figures changes (unit field already said which) |
| D4 | auth, entitlement, permission dependencies; parts of `access.py`, `analysis.py`, `auth.py` | error `detail` | `detail.error` instead of `detail.code` | P1: add `code` beside `error` in those dicts (additive), then deprecate `error` | Client and SDK read `detail.code` in places and `detail.error` in others; additive first step is safe |
| D5 | `strategy_registry.py` (22), `shadow.py` (12), `source_operations.py` (9), `research_data.py` (8), `agents.py` (5), `reference_network.py` (3), `cost_observations.py`, `review.py`, `strategy_lab.py` (2 each), `sources.py`, `weather.py` (1 each) | error `detail` | bare string `detail` | P1: `{"code", "message"}`; the top-level `error` code already classifies them | Breaking for any client that displays `detail` as text; needs client change in step |
| D6 | `access.py`, `portfolio.py` | error `detail` | `{"error_code", "message"}` | P1 | As D4 |
| D7 | 28 `limit` lists | pagination | silent truncation at `limit`, no `meta.truncated` or cursor | P2: add `meta.truncated` (additive) everywhere first; cursor only where the lists grow without bound (`/api/monitoring/alerts`, `/api/ingestion-runs`, `/api/jobs`, `/api/agent/runs`) | `meta` addition is additive; cursor changes SDK signatures |
| D8 | `/api/route-cost/upstream-contracts/{id}/revisions` | pagination | `offset` (the only one) | P2: keep; document | None |
| D9 | `/api/portfolio/mandate-usage` (`largest_at`), `/api/sources`, `/api/runtime/source-operations` (`daily_at`) | names | `*_at` for a month label and a time of day | P3: add `largest_month` / `daily_time` beside, deprecate later | Additive first step |
| D10 | `/api/health`, `/api/health/live`, `/api/health/ready`, `/api/dev/health` | envelope | no `data`/`meta` | P5: keep (orchestrator probes read them bare); list as exempt in the contract evolution policy | None |
| D11 | reads without a runtime database | status | 200 + warning on some, 503 on others | P4: one rule (503 `runtime_db_not_configured` for reads that need the store) | Breaking for screens that render the empty 200; client must handle 503 first |

## Not checked here

Operations with path parameters and non-GET operations are covered by the static pass only
(pagination, error raise sites). Money fields named with their unit (`*_gbp`, `*_mwh`) are
treated as carrying it. `row_limit`, `quality_score` and similar names the probe flagged as
money-like are not money and are not listed.
