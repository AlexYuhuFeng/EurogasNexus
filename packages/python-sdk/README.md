# Eurogas Nexus Python SDK

Standalone Python SDK package for Eurogas Nexus.

The package is installed from `packages/python-sdk/src` as part of the
`eurogas-nexus` distribution in this repository. Import as:

```python
import eurogas_nexus_sdk
```

## Native flow and capacity history

`native_physical` preserves exact energy/volume rate strings and response metadata.
Use the deployment's existing authentication configuration. Pass both aware
`datetime` bounds, or omit both; naive, partial and reversed windows refuse before
HTTP. Reads include observations overlapping `[from_utc, to_utc)`, so a technical
capacity covering the whole window is included. No calorific conversion is made.

```python
from datetime import UTC, datetime
from eurogas_nexus_sdk.native_physical import fetch_native_flows_result

result = fetch_native_flows_result(
    "http://127.0.0.1:8000",
    point_id="ITP-00126",
    from_utc=datetime(2026, 10, 28, 5, tzinfo=UTC),
    to_utc=datetime(2026, 10, 29, 5, tzinfo=UTC),
    limit=200,
)
for row in result.data:
    print(row.native_rate_json.energy_kwh_per_day)
```

The point is an explicit example, not a coverage or source-activation default.
`fetch_native_capacity_result` accepts the same window; data-only variants omit
response metadata. Limit overflow refuses rather than truncating. Missing values
are not zero, and a flow/capacity ratio does not establish booked rights.
