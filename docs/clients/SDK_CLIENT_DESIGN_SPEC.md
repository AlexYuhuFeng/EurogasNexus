# Python SDK Client Design Spec

## Objective

The Python SDK is the programmatic client for Eurogas Nexus. It wraps stable
`/api/v1` routes with typed Python functions and models so internal scripts,
notebooks, automation, and future integrations can consume the backend safely.
The SDK is a required V1 product surface.

## Product Boundary

The SDK is an API client only.

Data path:

```text
Python SDK -> backend /api/v1 -> backend repositories -> PostgreSQL
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
/api/v1
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
GET /api/v1/health
```

### Runtime Status

Purpose:

- expose backend/runtime/DB state to operators and clients.

Endpoint:

```text
GET /api/v1/runtime/status
```

Status: planned.

### Reference Network

Purpose:

- fetch map and topology objects for clients.

Endpoints:

```text
GET /api/v1/reference-network/nodes
GET /api/v1/reference-network/facilities
GET /api/v1/reference-network/segments
```

Status: planned.

### Scenario Validation

Purpose:

- submit research scenario inputs and retrieve missing-input/assumption state.

Endpoint:

```text
POST /api/v1/scenarios/validate
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

- SDK targets `/api/v1`;
- SDK does not import internal backend modules;
- HTTP errors map to safe SDK exceptions;
- response metadata is preserved;
- no secrets appear in exception strings.

## First SDK Implementation Prompt

Use after backend runtime status and API response contracts are stable:

```text
Read AGENTS.md, docs/clients/SDK_CLIENT_DESIGN_SPEC.md, docs/clients/CLIENT_API_CONTRACT.md, docs/contracts/15_SDK_CLI_CONTRACT.md, and .agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md. Implement SDK M1 only. Keep the SDK as an API client for /api/v1. Do not import backend internals, read DB/files directly, call vendor APIs, or add packaging until a packaging milestone is selected.
```
