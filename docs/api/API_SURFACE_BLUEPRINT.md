# API Surface Blueprint

## Purpose

This document defines the target `/api` route surface for Eurogas Nexus. It
is a blueprint for future implementation; planned routes must not be exposed
until their milestone creates tests, contracts, and DB/runtime support.

## Prefix Policy

Stable client routes:

```text
/api
```

Internal routes:

```text
/api/internal
```

Development routes:

```text
/api/dev
```

Hidden legacy compatibility:

```text
/api/v1/*
/v1/health
```

New SDK, CLI, web, and Windows code must target `/api`.

## Response Envelope

Full research-capable responses should converge on:

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
    "entitlement": null,
    "research_only": true,
    "human_review_required": true
  }
}
```

Small health/readiness routes may return smaller payloads. Client code must
tolerate both compact and full-envelope shapes during transition.

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
| `GET` | `/api/health` | backend health | active |
| `GET` | `/api/runtime/status` | API, DB, Alembic, source posture | planned |
| `GET` | `/api/runtime/readiness` | release/trial readiness | planned |

### Source And Ingestion

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/sources` | source registry | planned |
| `GET` | `/api/sources/{source_id}` | source details | planned |
| `GET` | `/api/sources/live-status` | ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, weather source posture | planned |
| `GET` | `/api/ingestion/runs` | ingestion runs | planned |
| `GET` | `/api/ingestion/runs/{run_id}` | ingestion run details | planned |
| `POST` | `/api/ingestion/runs/validate` | validate configured job without live fetch | planned |

Live fetch routes are not allowed until an ingestion connector milestone
explicitly approves them.

Required source families are defined in
`docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`.

### Reference Network

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/reference-network/nodes` | topology/market/geometry nodes | planned |
| `GET` | `/api/reference-network/facilities` | LNG, storage, terminals, assets | planned |
| `GET` | `/api/reference-network/segments` | pipelines, corridors, edges | planned |
| `GET` | `/api/reference-network/mappings` | geometry-topology-market mappings | planned |

### Market And Physical Context

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/market/observations` | prices/spreads/FX metadata | planned |
| `GET` | `/api/market/venues` | EEX, Trayport, ICE OCM and other venue/product metadata | planned |
| `GET` | `/api/market/signals` | research market movement signals for map/client display | planned |
| `GET` | `/api/flows/observations` | flow/capacity/outage context | planned |
| `GET` | `/api/lng/observations` | LNG/regas/sendout context | planned |
| `GET` | `/api/storage/observations` | storage inventory/injection/withdrawal | planned |
| `GET` | `/api/weather/observations` | weather/HDD/CDD context | planned |
| `GET` | `/api/weather/signals` | HDD/CDD, forecast delta, demand-pressure signals | planned |

### Capacity And Contract Context

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/capacity/contracts` | capacity contract inventory for research context | planned |
| `GET` | `/api/capacity/availability` | booked/available capacity context | planned |
| `GET` | `/api/capacity/route-eligibility` | route and tenor eligibility context | planned |
| `GET` | `/api/contracts/exposure` | contract exposure linked to routes/assets | planned |

### Scenario And Research

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `POST` | `/api/scenarios/validate` | validate scenario inputs | planned |
| `GET` | `/api/route-cost/route-candidates` | DB-backed route templates and candidate paths | active |
| `GET` | `/api/route-cost/tso-tariffs` | DB-backed public tariff rows | active |
| `GET` | `/api/route-cost/resource-pool/options` | DB-backed portfolio resources and priced sale paths for the map cockpit | active |
| `POST` | `/api/route-cost/calculate` | explicit-leg route cost calculation | active |
| `POST` | `/api/route-cost/recommend` | capacity-constrained sale-route recommendation | active |
| `POST` | `/api/route-cost/resource-pool/optimize` | portfolio resource-pool allocation | active |
| `POST` | `/api/research/netback` | indicative netback output | planned |
| `POST` | `/api/research/feasibility` | feasibility output | planned |
| `POST` | `/api/research/allocation` | allocation scenario output | planned |
| `POST` | `/api/research/nowcast` | weather-adjusted pressure nowcast | planned |
| `POST` | `/api/research/backtest` | strategy backtest | planned |
| `POST` | `/api/research/shadow-run` | paper shadow run | planned |
| `POST` | `/api/research/briefs` | research brief generation | planned |
| `POST` | `/api/research/map-candidates` | map-ready research route candidates | planned |

All research routes must return `research_only: true` and
`human_review_required: true`.

### Monitoring And Alerts

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `GET` | `/api/monitoring/status` | monitoring status | planned |
| `GET` | `/api/monitoring/alerts` | research alerts | planned |
| `GET` | `/api/monitoring/anomalies` | anomaly candidates | planned |

Alerts are research flags, not execution instructions.

### LLM Analysis And Glossary

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `POST` | `/api/analysis/market-movement` | LLM-assisted cited market movement analysis | planned |
| `POST` | `/api/analysis/route-explanation` | cited route/signal explanation | planned |
| `GET` | `/api/glossary/terms` | glossary term list | planned |
| `GET` | `/api/glossary/terms/{term_id}` | glossary term detail | planned |

LLM analysis routes must consume structured backend data snapshots and return
citations/source references. They must not call live market sources directly or
produce official recommendations.

### Governance And Audit

| Method | Path | Purpose | Status |
| --- | --- | --- | --- |
| `POST` | `/api/governance/entitlements/evaluate` | entitlement check | planned |
| `POST` | `/api/governance/export/evaluate` | export policy check | planned |
| `GET` | `/api/audit/events` | audit event query | planned |

Unknown commercial data must fail closed.

### SDK/CLI Support

The SDK and CLI consume the same `/api` routes. Do not create separate
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
