# API Surface Blueprint

## Purpose

This document defines the target `/api/v1` route surface for Eurogas Nexus. It
is a blueprint for future implementation; planned routes must not be exposed
until their milestone creates tests, contracts, and DB/runtime support.

## Prefix Policy

Stable client routes:

```text
/api/v1
```

Internal routes:

```text
/api/internal
```

Development routes:

```text
/api/dev
```

Bootstrap compatibility:

```text
/v1/health
```

New SDK, CLI, web, and Windows code must target `/api/v1`.

## Response Envelope

Full research-capable responses should converge on:

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
    "entitlement": null,
    "research_only": true,
    "human_review_required": true
  }
}
```

Bootstrap routes may return smaller payloads. Client code must tolerate both
bootstrap and full-envelope shapes during transition.

## Error Model

Errors should classify as:

- `validation_error`;
- `missing_input`;
- `restricted`;
- `not_found`;
- `partial_feature`;
- `stale_data`;
- `runtime_unavailable`;
- `db_unavailable`;
- `source_unavailable`;
- `unexpected_error`.

Errors must not include secrets, full DB URLs, API keys, tokens, or `.env`
values.

## Route Groups

### Health And Runtime

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health` | backend health | active |
| `GET` | `/api/v1/runtime/status` | API, DB, Alembic, source posture | planned |
| `GET` | `/api/v1/runtime/readiness` | release/trial readiness | planned |

### Source And Ingestion

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/v1/sources` | source registry | planned |
| `GET` | `/api/v1/sources/{source_id}` | source details | planned |
| `GET` | `/api/v1/sources/live-status` | ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, weather source posture | planned |
| `GET` | `/api/v1/ingestion/runs` | ingestion runs | planned |
| `GET` | `/api/v1/ingestion/runs/{run_id}` | ingestion run details | planned |
| `POST` | `/api/v1/ingestion/runs/validate` | validate configured job without live fetch | planned |

Live fetch routes are not allowed until an ingestion connector milestone
explicitly approves them.

Required source families are defined in
`docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`.

### Reference Network

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/v1/reference-network/nodes` | topology/market/geometry nodes | planned |
| `GET` | `/api/v1/reference-network/facilities` | LNG, storage, terminals, assets | planned |
| `GET` | `/api/v1/reference-network/segments` | pipelines, corridors, edges | planned |
| `GET` | `/api/v1/reference-network/mappings` | geometry-topology-market mappings | planned |

### Market And Physical Context

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/v1/market/observations` | prices/spreads/FX metadata | planned |
| `GET` | `/api/v1/market/venues` | EEX, Trayport, ICE OCM and other venue/product metadata | planned |
| `GET` | `/api/v1/market/signals` | research market movement signals for map/client display | planned |
| `GET` | `/api/v1/flows/observations` | flow/capacity/outage context | planned |
| `GET` | `/api/v1/lng/observations` | LNG/regas/sendout context | planned |
| `GET` | `/api/v1/storage/observations` | storage inventory/injection/withdrawal | planned |
| `GET` | `/api/v1/weather/observations` | weather/HDD/CDD context | planned |
| `GET` | `/api/v1/weather/signals` | HDD/CDD, forecast delta, demand-pressure signals | planned |

### Capacity And Contract Context

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/v1/capacity/contracts` | capacity contract inventory for research context | planned |
| `GET` | `/api/v1/capacity/availability` | booked/available capacity context | planned |
| `GET` | `/api/v1/capacity/route-eligibility` | route and tenor eligibility context | planned |
| `GET` | `/api/v1/contracts/exposure` | contract exposure linked to routes/assets | planned |

### Scenario And Research

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `POST` | `/api/v1/scenarios/validate` | validate scenario inputs | planned |
| `POST` | `/api/v1/research/route-cost` | route cost research output | planned |
| `POST` | `/api/v1/research/netback` | indicative netback output | planned |
| `POST` | `/api/v1/research/feasibility` | feasibility output | planned |
| `POST` | `/api/v1/research/allocation` | allocation scenario output | planned |
| `POST` | `/api/v1/research/nowcast` | weather-adjusted pressure nowcast | planned |
| `POST` | `/api/v1/research/backtest` | strategy backtest | planned |
| `POST` | `/api/v1/research/shadow-run` | paper shadow run | planned |
| `POST` | `/api/v1/research/briefs` | research brief generation | planned |
| `POST` | `/api/v1/research/map-candidates` | map-ready research route candidates | planned |

All research routes must return `research_only: true` and
`human_review_required: true`.

### Monitoring And Alerts

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/v1/monitoring/status` | monitoring status | planned |
| `GET` | `/api/v1/monitoring/alerts` | research alerts | planned |
| `GET` | `/api/v1/monitoring/anomalies` | anomaly candidates | planned |

Alerts are research flags, not execution instructions.

### LLM Analysis And Glossary

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `POST` | `/api/v1/analysis/market-movement` | LLM-assisted cited market movement analysis | planned |
| `POST` | `/api/v1/analysis/route-explanation` | cited route/signal explanation | planned |
| `GET` | `/api/v1/glossary/terms` | glossary term list | planned |
| `GET` | `/api/v1/glossary/terms/{term_id}` | glossary term detail | planned |

LLM analysis routes must consume structured backend data snapshots and return
citations/source references. They must not call live market sources directly or
produce official recommendations.

### Governance And Audit

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `POST` | `/api/v1/governance/entitlements/evaluate` | entitlement check | planned |
| `POST` | `/api/v1/governance/export/evaluate` | export policy check | planned |
| `GET` | `/api/v1/audit/events` | audit event query | planned |

Unknown commercial data must fail closed.

### SDK/CLI Support

The SDK and CLI consume the same `/api/v1` routes. Do not create separate
business semantics for SDK/CLI.

## Forbidden Routes

Do not add routes for:

- order entry;
- order routing;
- trade execution;
- trade capture;
- nomination submission;
- official approval;
- official recommendation;
- legal advice;
- auto-trading;
- ETRM replacement records.

## Implementation Gate

A planned route may be implemented only when the milestone defines:

- owning module;
- request and response models;
- DB/runtime-store impact;
- data policy;
- entitlement/export behavior;
- tests;
- validation commands;
- rollback notes.
