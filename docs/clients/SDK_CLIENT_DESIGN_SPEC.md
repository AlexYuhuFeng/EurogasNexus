# Python SDK Client Design Spec

## Objective

The Python SDK is the programmatic client for Eurogas Nexus. It wraps stable
`/api` routes with typed Python functions and models so internal scripts,
notebooks, automation, and future integrations can consume the backend safely.
The SDK is a required V1 product surface.

## Product Boundary

The SDK is an API client only.

Data path:

```text
Python SDK -> backend /api -> backend repositories -> PostgreSQL
```

It must not:

- import domain, application, runtime store, or DB internals;
- read PostgreSQL directly;
- read local backend data files;
- call vendor APIs;
- call LLM providers;
- create orders, trades, nominations, approvals, or execution records;
- hide missing inputs or data-quality warnings.

## Package Location

Current source package:

```text
src/eurogas_nexus/sdk/
```

Future distributable package:

```text
packages/python-sdk/
```

Do not move packaging into `packages/python-sdk` until an SDK packaging
milestone is selected.

## API Base URL

Every SDK client instance requires a backend `base_url`.

Default stable prefix:

```text
/api
```

The SDK must not default to historical `/v1` paths except for documented
bootstrap compatibility tests.

## Client Shape

Recommended future structure:

```text
src/eurogas_nexus/sdk/
  __init__.py
  client.py
  config.py
  errors.py
  health_client.py
  models.py
  runtime_client.py
  reference_network_client.py
  scenario_client.py
  research_client.py
  route_cost.py
  glossary.py
  strategy_lab.py
  portfolio.py
```

## Core Client Rules

- Use HTTPX or the repository-approved HTTP client.
- Set timeouts explicitly.
- Classify errors into connection, timeout, HTTP status, validation, restricted,
  missing input, partial feature, and unexpected.
- Preserve backend response metadata.
- Never print tokens, passwords, database URLs, or full secret-bearing URLs.
- Do not retry non-idempotent requests automatically.

## Required SDK Surfaces

### Health

Purpose:

- check backend availability.

Endpoint:

```text
GET /api/health
```

### Runtime Status

Purpose:

- expose backend/runtime/DB state to operators and clients.

Endpoint:

```text
GET /api/runtime/status
```

Status: planned.

### Reference Network

Purpose:

- fetch map and topology objects for clients.

Endpoints:

```text
GET /api/reference-network/nodes
GET /api/reference-network/facilities
GET /api/reference-network/segments
```

Status: planned.

### Scenario Validation

Purpose:

- submit research scenario inputs and retrieve missing-input/assumption state.

Endpoint:

```text
POST /api/scenarios/validate
```

Status: planned.

### Research Outputs

Purpose:

- retrieve route cost, indicative netback, feasibility, allocation, nowcast,
  strategy backtest, shadow run, and report outputs after those backend slices
  exist.

All methods must return metadata including assumptions, missing inputs,
warnings, source references, lineage, `research_only`, and
`human_review_required`.

### Route Cost And Live PnL

Purpose:

- compare DB/API-backed route economics and live market marks without direct DB
  access.

Current V1 endpoints:

```text
GET /api/route-cost/route-candidates
GET /api/route-cost/uk/tariffs
POST /api/route-cost/calculate
POST /api/route-cost/uk/easington/options
POST /api/route-cost/uk/easington/live-pnl
POST /api/route-cost/lng-regas/assess
POST /api/route-cost/resource-pool/optimize
```

Current V1 route-cost scope is UK National Gas NTS only. It must not be
hard-coded to Easington/Bacton examples; any UK NTS point may be used when
audited tariff rows exist in PostgreSQL. SDK methods must preserve backend
warnings and must not imply execution or official trading recommendation.

### Strategy Lab

Purpose:

- evaluate backtest, shadow-run, and live-monitor strategy inputs through the
  backend API;
- return paper allocation targets, risk-control status, missing inputs,
  warnings, and source references.

Current V1 endpoint:

```text
POST /api/strategy-lab/evaluate
```

SDK strategy methods must call the backend API only. They must not import
domain strategy modules, connect to PostgreSQL, call exchanges, or create
orders/trades/nominations.

### Portfolio Positioning

Purpose:

- fetch imported external screen/broker order observations;
- fetch indicative portfolio/resource/strategy PnL snapshots;
- fetch the cockpit live summary used by Web and Windows surfaces.

Required endpoints:

```text
GET /api/portfolio/screen-orders
GET /api/portfolio/pnl-snapshots
GET /api/portfolio/live-summary
```

SDK portfolio methods must be read-only API clients. They must not connect to
PostgreSQL, import backend DB/domain modules, call ICE OCM/EEX/Trayport/Kpler/
Platts directly, create orders, route orders, cancel orders, submit nominations,
or write local order/PnL files. Returned records are decision-support
observations, not an execution or trade-capture ledger.

### Glossary

Purpose:

- expose bilingual European gas trading vocabulary to scripts, CLI, Web, and
  Windows clients.

Current V1 endpoints:

```text
GET /api/glossary?lang=en
GET /api/glossary?lang=zh-CN
GET /api/glossary/{term}?lang=en
GET /api/glossary/{term}?lang=zh-CN
GET /api/glossary/{term}/context?lang=en&duration_start_utc=...&duration_end_utc=...
```

SDK models must include term ID, term, category, localized definition, English
definition, Mandarin Chinese definition, aliases, related terms, and source
references.

The analysis SDK must expose `fetch_glossary_context(base_url, term, lang=...,
duration_start_utc=..., duration_end_utc=...)`. Its model must preserve
`metrics`, `capacity_usage`, `related_prices`, `live_market_marks`,
`related_routes`, `related_contracts`, and `data_quality` so scripts and clients
can show Easington capacity usage, ICIS Heren price context, NBP hub context,
and ICE OCM live screen marks without reading PostgreSQL directly.

## Authentication

V1 bootstrap may run without company SSO/OIDC. Future auth must be injected into
the SDK through explicit configuration.

The SDK must not store long-lived secrets in source files, logs, reports, or
test fixtures.

## Testing

SDK tests live under:

```text
tests/sdk/
```

Required tests:

- SDK targets `/api`;
- SDK does not import internal backend modules;
- HTTP errors map to safe SDK exceptions;
- response metadata is preserved;
- no secrets appear in exception strings.

## First SDK Implementation Prompt

Use after backend runtime status and API response contracts are stable:

```text
Read AGENTS.md, docs/clients/SDK_CLIENT_DESIGN_SPEC.md, docs/clients/CLIENT_API_CONTRACT.md, docs/contracts/15_SDK_CLI_CONTRACT.md, and .agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md. Implement SDK M1 only. Keep the SDK as an API client for /api. Do not import backend internals, read DB/files directly, call vendor APIs, or add packaging until a packaging milestone is selected.
```
