# Client API Contract

## Scope

This contract applies to the Python SDK, CLI, web client, and Windows client
when they act as API consumers.

## Runtime Data Access Rule

PostgreSQL is the runtime source of truth, but clients must access that data
only through SDK/API boundaries.

Allowed data paths:

- Python SDK -> backend `/api/v1` -> backend repositories -> PostgreSQL.
- CLI -> Python SDK first, or backend `/api/v1` directly only when the SDK does
  not yet expose the selected route.
- Web client -> browser API client for backend `/api/v1`.
- Windows client -> packaged web workspace/API client for backend `/api/v1`.

No client may open a PostgreSQL connection, import backend DB/runtime-store
modules, or read backend local data files to retrieve runtime data.

## Base URL

Clients must target the backend API base URL configured by the operator.

Stable routes use:

```text
/api/v1
```

Compatibility route:

```text
/v1/health
```

New client code must use `/api/v1/health`, not `/v1/health`.

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

Future `/api/v1` responses should converge on this shape:

```json
{
  "data": {},
  "meta": {
    "request_id": "synthetic-request-id",
    "api_version": "v1",
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
| `GET /api/v1/health` | backend availability | active |
| `GET /api/v1/runtime/status` | DB/runtime/operator status | planned |
| `GET /api/v1/reference-network/nodes` | map nodes | active |
| `GET /api/v1/reference-network/edges` | map corridors/routes | active |
| `GET /api/v1/reference-network/facilities` | LNG, storage, terminals | active |
| `POST /api/v1/scenarios/validate` | scenario missing-input check | planned |
| `POST /api/v1/research/route-cost` | future research-only workflow | planned |
| `GET /api/v1/sources/live-status` | ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, weather, LLM posture | planned |
| `GET /api/v1/capacity/contracts` | capacity/contract context | planned |
| `GET /api/v1/market/signals` | market movement signals | planned |
| `GET /api/v1/weather/signals` | HDD/CDD and demand-pressure signals | planned |
| `POST /api/v1/research/shadow-run` | legacy workflow shell | active |
| `POST /api/v1/strategy-lab/evaluate` | strategy backtest/shadow/live-monitor paper evaluation | active |
| `GET /api/v1/analysis/ontology` | business ontology for analysis and glossary QA | active |
| `POST /api/v1/analysis/query` | DeepSeek-ready cited LLM/data analysis over backend snapshots | active |
| `POST /api/v1/reports/portfolio` | portfolio/resource/strategy/PnL report generation | active |
| `GET /api/v1/portfolio/screen-orders` | read-only imported screen/broker order observations | active |
| `GET /api/v1/portfolio/pnl-snapshots` | indicative portfolio/resource/strategy PnL snapshots | active |
| `GET /api/v1/portfolio/live-summary` | cockpit order/PnL/cash summary | active |
| `GET /api/v1/glossary/{term}/context` | glossary term operational context | active |
| `POST /api/v1/analysis/market-movement` | legacy market movement placeholder | planned |
| `GET /api/v1/glossary` | backend-served bilingual glossary | active |
| `GET /api/v1/glossary/{term}` | backend-served bilingual glossary detail | active |
| `GET /api/v1/route-cost/route-candidates` | DB-backed route candidates | active |
| `GET /api/v1/route-cost/uk/tariffs` | UK NTS tariff rows available in DB/fallback | active |
| `POST /api/v1/route-cost/calculate` | UK NTS route-cost calculation from tariff rows | active |
| `POST /api/v1/route-cost/uk/easington/options` | UK Easington option PnL | active |
| `POST /api/v1/route-cost/uk/easington/live-pnl` | UK Easington live bid-based PnL | active |
| `POST /api/v1/route-cost/lng-regas/assess` | LNG regas readiness assessment | active |
| `POST /api/v1/route-cost/resource-pool/optimize` | upstream portfolio/resource-pool allocation | active |

Planned endpoints must be mocked locally until backend contracts exist.

## Internal Import Route

`POST /api/internal/portfolio/import-observations` is an internal/operator route,
not a stable client route. It is available only when the API runs with the
`internal` profile. Release clients must not call it.

The route writes external screen-order observations and indicative portfolio PnL
snapshots into PostgreSQL after entitlement checks pass. Missing entitlement
denies the full batch and writes audit/ingestion-run evidence without writing
observation rows.

Read-only client surfaces remain:

- `GET /api/v1/portfolio/screen-orders`;
- `GET /api/v1/portfolio/pnl-snapshots`;
- `GET /api/v1/portfolio/live-summary`.

## Operational Glossary Context

`GET /api/v1/glossary/{term}/context` accepts:

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
route candidates, and linked upstream contracts. Hard-coded examples such as
`Easington Entry Point` are allowed as hints, but the client contract is not
limited to Easington/Bacton. Customer-loaded terms such as `St Fergus Entry
Point` must render when PostgreSQL contains matching runtime rows.

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

`/api/v1/portfolio/*` endpoints expose imported observation state only:

- screen and broker order records are read-only external observations;
- PnL snapshots are indicative valuation records for cockpit, SDK, and report
  context;
- live summary aggregates the latest imported observations for display.

These endpoints must not create, amend, cancel, route, submit, approve, book, or
capture trades/orders/nominations. Clients must label their output as
human-reviewed decision support.
