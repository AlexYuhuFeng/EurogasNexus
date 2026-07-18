# Client API Contract

## Scope

This contract applies to the Python SDK, CLI, web client, and Windows client
when they act as API consumers.

## Runtime Data Access Rule

PostgreSQL is the runtime source of truth, but clients must access that data
only through SDK/API boundaries.

Allowed data paths:

- Python SDK -> backend `/api` -> backend repositories -> PostgreSQL.
- CLI -> Python SDK first, or backend `/api` directly only when the SDK does
  not yet expose the selected route.
- Web client -> browser API client for backend `/api`.
- Windows client -> packaged web workspace/API client for backend `/api`.

No client may open a PostgreSQL connection, import backend DB/runtime-store
modules, or read backend local data files to retrieve runtime data.

## Base URL

Clients must target the backend API base URL configured by the operator.

Stable routes use:

```text
/api
```

Compatibility route:

```text
/api/health
```

New client code must use `/api`, not legacy `/v1` paths.

## Forbidden Access

Clients must not access:

- PostgreSQL directly;
- backend DB/session/runtime-store modules directly;
- backend local files directly;
- raw vendor files;
- connector credentials;
- `.env` values;
- historical Desktop project folders;
- internal Python modules.

## Required Client Behavior

Clients must:

- show backend connection state;
- show degraded and unavailable states;
- show source, warning, missing-input, freshness, and lineage metadata when the
  backend provides it;
- treat unknown entitlement/export status as restricted;
- preserve `research_only` and `human_review_required` flags visibly;
- avoid official recommendation, order, nomination, or execution language.
- label research trading ideas and rankings as human-review decision-support,
  not official trading recommendations.

## Standard Envelope

Future `/api` responses should converge on this shape:

```json
{
  "data": {},
  "meta": {
    "request_id": "request-id-example",
    "api_surface": "stable",
    "source_references": [],
    "lineage": [],
    "assumptions": [],
    "missing_inputs": [],
    "warnings": [],
    "freshness": null,
    "data_quality": null,
    "research_only": true,
    "human_review_required": true
  }
}
```

Existing bootstrap routes may return a smaller shape. Client code must handle
both bootstrap and full-envelope responses during transition.

## Endpoint Readiness Matrix

| Endpoint | Client Use | Status |
| --- | --- | --- |
| `GET /api/health` | backend availability | active |
| `GET /api/runtime/status` | DB/runtime/operator status | planned |
| `GET /api/reference-network/nodes` | map nodes | active |
| `GET /api/reference-network/edges` | map corridors/routes | active |
| `GET /api/reference-network/facilities` | LNG, storage, terminals | active |
| `POST /api/scenarios/validate` | scenario missing-input check | planned |
| `GET /api/sources/live-status` | ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, weather, LLM posture | planned |
| `GET /api/capacity/contracts` | capacity/contract context | planned |
| `GET /api/market/observations` | DB-backed gas price, assessment, index, FX-like observation rows | active |
| `GET /api/market/fx` | DB-backed ECB FX reference rows | active |
| `GET /api/market/quotes` | normalized DB-backed L1 bid/ask/depth quotes | active |
| `GET /api/market/opportunities` | persisted route-adjusted intraday candidates, blockers, lineage, and expiry | active |
| `GET /api/market/spreads` | compatibility summary derived from persisted opportunities | active |
| `GET /api/market/signals` | market movement signals | planned |
| `GET /api/weather/signals` | HDD/CDD and demand-pressure signals | planned |
| `POST /api/research/shadow-run` | legacy workflow shell | active |
| `POST /api/strategy-lab/evaluate` | strategy backtest/shadow/live-monitor paper evaluation | active |
| `GET /api/analysis/ontology` | business ontology for analysis and glossary QA | active |
| `POST /api/analysis/query` | DeepSeek-ready cited LLM/data analysis over backend snapshots | active |
| `POST /api/reports/portfolio` | portfolio/resource/strategy/PnL report generation | active |
| `GET /api/portfolio/screen-orders` | read-only imported screen/broker order observations | active |
| `GET /api/portfolio/pnl-snapshots` | indicative portfolio/resource/strategy PnL snapshots | active |
| `GET /api/portfolio/live-summary` | cockpit order/PnL/cash summary | active |
| `GET /api/glossary/{term}/context` | glossary term operational context | active |
| `POST /api/analysis/market-movement` | legacy market movement placeholder | planned |
| `GET /api/glossary` | backend-served bilingual glossary | active |
| `GET /api/glossary/{term}` | backend-served bilingual glossary detail | active |
| `GET /api/route-cost/route-candidates` | DB-backed route candidates | active |
| `GET /api/route-cost/tso-tariffs` | DB-backed TSO tariff rows, including BBL/IUK/NTS where loaded | active |
| `GET /api/route-cost/upstream-contracts` | persisted upstream resource contracts for resource-pool construction | active |
| `POST /api/route-cost/upstream-contracts` | persist EFET-style upstream resource terms as decision-support inputs | active |
| `GET /api/route-cost/resource-pool/options` | DB-backed portfolio resources and priced sale options for the map cockpit | active |
| `POST /api/route-cost/calculate` | explicit-leg European route-cost calculation from tariff rows | active |
| `POST /api/route-cost/recommend` | capacity-constrained route/sale allocation recommendation | active |
| `POST /api/route-cost/lng-regas/assess` | LNG regas readiness assessment | active |
| `POST /api/route-cost/resource-pool/optimize` | upstream portfolio/resource-pool allocation | active |

Planned endpoints must return explicit unavailable/degraded states from the
backend until their contracts exist. Clients must not invent local runtime data
for planned endpoints.

## Contract Resource Boundary

`POST /api/route-cost/upstream-contracts` is a decision-support persistence
route for upstream resource terms. It stores the EFET-style resource attributes
needed by the resource-pool optimizer and returns `research_only=true` and
`human_review_required=true`.

Clients may use this route to save resource inputs, then refresh:

- `GET /api/route-cost/upstream-contracts`;
- `GET /api/route-cost/resource-pool/options`.

This route must not be described as trade capture, order entry, nomination,
approval, settlement, or an ETRM contract master.

## Internal Import Route

`POST /api/internal/portfolio/import-observations` is an internal/operator route,
not a stable client route. It is available only when the API runs with the
`internal` profile. Release clients must not call it.

The internal route requires:

- backend env `EUROGAS_NEXUS_INTERNAL_API_TOKEN`;
- request header `X-Eurogas-Internal-Token`;
- request header `X-Eurogas-Principal`.

The route fails closed before DB access if the token is not configured, missing,
invalid, or if the principal is blank. This V1 token gate is not company
SSO/OIDC and must not be used by Web, Windows, SDK, or CLI release clients.

The route writes external screen-order observations and indicative portfolio PnL
snapshots into PostgreSQL after entitlement checks pass. Missing entitlement
denies the full batch and writes audit/ingestion-run evidence without writing
observation rows.

Read-only client surfaces remain:

- `GET /api/portfolio/screen-orders`;
- `GET /api/portfolio/pnl-snapshots`;
- `GET /api/portfolio/live-summary`.

## Operational Glossary Context

`GET /api/glossary/{term}/context` accepts:

- `lang=en|zh|zh-CN`;
- `duration_start_utc`;
- `duration_end_utc`.

The response is additive and must remain backward compatible with the earlier
`description`, `capacity`, `capacity_usage`, `related_prices`,
`related_routes`, `related_sources`, and `warnings` fields. New clients should
also read:

- `description_en` and `description_zh_cn`;
- `requested_duration`;
- `entity_summary`;
- `matched_entities`;
- `metrics`;
- `related_contracts`;
- `live_market_marks`;
- `context_sections`;
- `data_quality`.

The backend must derive context from matching glossary terms, aliases, related
terms, capacity profiles, flow observations, price observations, live marks,
route candidates, and linked upstream contracts. Customer-loaded terms such as
`Zeebrugge Entry Point`, `TTF`, `GATE LNG`, or any other properly loaded
European gas asset must render when PostgreSQL contains matching runtime rows.

For `ICIS Heren`, the response must carry licensed-data warnings unless the
customer runtime DB supplies entitled records. Clients must display these
warnings near the price section.

## Error Handling

Clients must classify failures as:

- backend unavailable;
- unauthorized or restricted;
- missing input;
- stale data;
- incomplete backend feature;
- validation failure;
- unexpected error.

Unexpected errors must not reveal secrets or full URLs.

## Retry Policy

For V1 clients:

- retry idempotent `GET` requests at most once after a short delay;
- do not retry mutation-like requests automatically;
- show manual retry controls;
- preserve the last visible warning state until a fresh response arrives.

## Configuration

Web client:

- backend base URL comes from build/runtime config chosen by the web milestone;
- browser must not store credentials or secrets.

Windows client:

- backend base URL may be stored as local UI preference;
- no database URL or vendor API secret may be stored in the desktop client.

Live source and LLM provider credentials are backend/operator concerns. Web and
Windows clients may submit provider keys only to the backend credential API over
the approved API boundary, and must never store, log, display, cache, or return
plaintext provider credentials.

## Portfolio Positioning Boundary

`/api/portfolio/*` endpoints expose imported observation state only:

- screen and broker order records are read-only external observations;
- PnL snapshots are indicative valuation records for cockpit, SDK, and report
  context;
- live summary aggregates the latest imported observations for display.

These endpoints must not create, amend, cancel, route, submit, approve, book, or
capture trades/orders/nominations. Clients must label their output as
human-reviewed decision support.
