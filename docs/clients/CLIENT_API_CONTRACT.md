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
| `GET /api/v1/reference-network/nodes` | map nodes | planned |
| `GET /api/v1/reference-network/segments` | map corridors/routes | planned |
| `GET /api/v1/reference-network/facilities` | LNG, storage, terminals | planned |
| `POST /api/v1/scenarios/validate` | scenario missing-input check | planned |
| `POST /api/v1/research/route-cost` | future research-only workflow | planned |
| `GET /api/v1/sources/live-status` | ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, weather, LLM posture | planned |
| `GET /api/v1/capacity/contracts` | capacity/contract context | planned |
| `GET /api/v1/market/signals` | market movement signals | planned |
| `GET /api/v1/weather/signals` | HDD/CDD and demand-pressure signals | planned |
| `POST /api/v1/research/shadow-run` | strategy paper evaluation | planned |
| `POST /api/v1/analysis/market-movement` | cited LLM-assisted market analysis | planned |
| `GET /api/v1/glossary/terms` | backend-served glossary | planned |

Planned endpoints must be mocked locally until backend contracts exist.

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
Windows clients must never store or transmit provider credentials except through
ordinary backend authentication approved by a future auth milestone.
