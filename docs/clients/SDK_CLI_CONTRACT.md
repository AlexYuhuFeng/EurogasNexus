# SDK and CLI integration contract

[简体中文](SDK_CLI_CONTRACT-CN.md)

## Current interface

The Python SDK is packaged with the repository's distribution under
`packages/python-sdk/src/eurogas_nexus_sdk`. It provides typed API clients for health,
market/physical observations, portfolio, research, strategy, review and operational
surfaces. The CLI entry point is `eurogas-nexus`, implemented in
`src/eurogas_nexus/cli/main.py`. Use the command help and SDK from the same release as
the installation.

The [SDK readme](../../packages/python-sdk/README.md) contains a native-flow example.
The [function catalogue](../api/DATA_SCIENCE_FUNCTIONS.md) describes analytical surfaces.

## Connection and authentication

SDK methods take the service origin, for example `https://nexus.example.com`; the health
client appends `/api/health`. The desktop deployment setting instead uses an API address
ending in `/api`. Use the format required by the particular interface.

Configure the credentials issued for the installation. Shared HTTP helpers read
`EUROGAS_NEXUS_PUBLIC_API_TOKEN` (legacy alias `EUROGAS_NEXUS_API_TOKEN`),
`EUROGAS_NEXUS_IDENTITY_BEARER` and, for the applicable operator context,
`EUROGAS_NEXUS_PRINCIPAL`. The backend validates identity, permission and source access.

A first read can use:

```python
from eurogas_nexus_sdk import fetch_health

health = fetch_health("https://nexus.example.com")
print(health.status, health.version, health.profile)
```

With the installed command:

```bash
eurogas-nexus --base-url https://nexus.example.com health
eurogas-nexus --help
```

The address is an example; use the origin supplied by IT. Health describes the service,
not successful ingestion or commercial-data coverage.

## Integration rules

- SDK/CLI runtime data access uses the backend API, not direct database or domain imports.
- Use documented methods and explicit request parameters; preserve result metadata,
  identifiers, source references, warnings and missing-input information.
- Keep credentials in the approved runtime configuration, separate from notebooks,
  shared examples and log output.
- Identify persisted operations separately from read/computation requests and verify their
  required permissions before using them in automation.
- Keep the service version, SDK version, request and returned evidence with a reproducible
  integration report.
- SDK tests live in `tests/sdk`; CLI tests live in `tests/cli`. Boundary tests check API use.

The design specifications remain [SDK](SDK_CLIENT_DESIGN_SPEC.md) and
[CLI](CLI_CLIENT_DESIGN_SPEC.md) references. Their earlier bootstrap milestones describe
historical scope, not the complete current method set.
