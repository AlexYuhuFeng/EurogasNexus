# GIE SDK payload parity

Status: bounded implementation note. This is not live-source acceptance, a
certification record, an entitlement decision or a claim that GIE was contacted.

## Scope

The typed Python SDK carriers must consume the payloads the current backend
actually emits:

| SDK module | API routes |
| --- | --- |
| `packages/python-sdk/src/eurogas_nexus_sdk/storage.py` | `GET /api/storage/sites`, `GET /api/storage/observations` |
| `packages/python-sdk/src/eurogas_nexus_sdk/lng.py` | `GET /api/lng/terminals`, `GET /api/lng/observations` |

Before this change the models required a `lat`/`lon` pair and either mcm
capacity/volume or an `observation_type` that these routes never return. A real
GIE row therefore failed Pydantic validation at the typed boundary.

## Actual carriers

The models now expose the API field names directly.

- Storage site: `site_id`, `name`, `country`, `working_capacity_twh`,
  `fill_pct`, `observed_at_utc`, `source_system`, `status`.
- Storage observation: `observation_id`, `source_dataset`, `facility_id`,
  `facility_name`, `country`, `inventory_twh`, `working_capacity_twh`,
  `fill_pct`, `injection_twh_d`, `withdrawal_twh_d`, `period_start_utc`,
  `period_end_utc`, `observed_at_utc`, `source_system`, `source_reference`,
  `freshness`, `research_only`.
- LNG terminal: `terminal_id`, `name`, `country`, `inventory_twh`,
  `send_out_twh_d`, `dtmi_twh`, `observed_at_utc`, `source_system`, `status`.
- LNG observation: `observation_id`, `source_dataset`, `terminal_id`,
  `terminal_name`, `country`, `inventory_twh`, `send_out_twh_d`, `dtmi_twh`,
  `period_start_utc`, `period_end_utc`, `observed_at_utc`, `source_system`,
  `source_reference`, `freshness`, `research_only`.

Nullable API measurements (`inventory_twh`, `working_capacity_twh`,
`fill_pct`, `injection_twh_d`, `withdrawal_twh_d`, `send_out_twh_d`,
`dtmi_twh`) stay `None` when the API returns `null`. They are never replaced
with `0`.

The routes always publish the observation identity, facility/terminal
identity, country, period bounds, source metadata and `research_only` flag.
Those actual-only fields remain optional in the Python models solely so an
explicitly constructed legacy object does not break; parsed API rows populate
them.

## Compatibility

The old names and units are retained only as explicit legacy carriers:

- `StorageSite.lat` / `lon` and `LngTerminal.lat` / `lon` are optional and
  default to `None`.
- `StorageSite.working_capacity_mcm`,
  `LngTerminal.capacity_mcm_d`, `LngTerminal.storage_capacity_mcm`,
  `StorageObservation.volume_mcm` and `LngObservation.value_mcm` are optional
  legacy fields.
- `StorageObservation.site_id` / `site_name` are accepted as legacy input and
  mirrored from `facility_id` / `facility_name` so existing attribute access
  still works.
- `StorageObservation.observation_type` and `LngObservation.observation_type`
  are optional legacy fields and stay `None` for API rows.

No legacy field is synthesized from an actual field.

## Unknown geography

`/api/storage/sites` and `/api/lng/terminals` publish no coordinates. The SDK
does not infer a country centroid, a facility location or any other point:
`lat` and `lon` remain `None` unless a caller explicitly supplies a legacy
value. A `None` coordinate means "not published", not "zero degrees".

## Units and conversions

All actual energy measurement fields are in the API's TWh or TWh/day units;
`fill_pct` is the percentage published by the API. The SDK does not convert
TWh to mcm, mcm to TWh, GWh to TWh beyond what the backend has already
published, or a rate to a stock. In particular, an API row with
`working_capacity_twh` does not populate `working_capacity_mcm`, and an
inventory row does not populate `volume_mcm` or `value_mcm`.

## Regression evidence

`tests/sdk/test_gie_payload_parity.py` builds synthetic AGSI/ALSI database rows,
routes them through the actual FastAPI storage/LNG handlers and a TestClient,
captures the exact JSON, then replays that JSON into `fetch_storage_sites`,
`fetch_storage_observations`, `fetch_lng_terminals` and
`fetch_lng_observations` through `httpx.MockTransport`. The existing test
deployment-token fixture authenticates the TestClient, and the SDK requests
assert the same bearer credential.

The test asserts the actual payload does not contain `lat`, `lon`, mcm or
`observation_type` keys, so it cannot pass by constructing dictionaries in the
SDK's shape. It also asserts null API measurements stay `None` and that
credentials are preserved.

No real database, provider endpoint or external network is used. The synthetic
rows are not a live GIE response, and this note makes no claim about current
provider schema, entitlement or certification.

## Verification status

The worker's shell was unavailable because of the environment's ACL lock
(`Win32 5`, `dsh-acl-locks`); `pytest` and `ruff` were therefore **not run by
the worker**. Root must run the focused test module, the existing storage/LNG
adjacent SDK tests and Ruff against the changed files. Static review only is
claimed here.
