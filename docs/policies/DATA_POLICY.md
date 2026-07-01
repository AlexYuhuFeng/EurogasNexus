# Data Policy

## Source Of Truth

PostgreSQL is the runtime source of truth for Eurogas Nexus V1.

## Local Files

Local files may be used only as:

- import templates;
- raw archives;
- canonical archives;
- generated reports;
- snapshots;
- test fixtures.

Trial and release modes must not silently fall back to local files or generated
runtime data.

## Runtime Source Policy

Official or licensed reference and infrastructure data must flow through:

```text
official/source API or published source -> PostgreSQL -> /api or SDK -> clients
```

V1 treats the following as source-ingested runtime data when available:

- ECB FX reference rates;
- ENTSOG operational flows, connection points, and TSO access metadata;
- GIE AGSI storage and ALSI LNG observations;
- public TSO tariff rows loaded from audited published statements.

The following categories require customer credentials, entitlement, or operator
entry before use:

- EEX, ICE OCM, Trayport, Kpler, Platts, ICIS, Argus, broker, and other
  commercial price or screen feeds;
- customer contracts, resource pools, capacity ownership, TSO access rights,
  and strategy parameters;
- LLM provider execution keys.

## Test Data

Tests must not use real vendor data. Use source-shaped fixtures and dry-run
mode. Tests must not call live external APIs, live connectors, or LLM providers
unless the test is explicitly marked as a live-source/operator test.

Preview runtime rows are allowed only when an operator explicitly runs a seed
script against a local test PostgreSQL database. Preview rows must be marked
with explicit source provenance and must not be shipped as customer data. Price
preview rows must use the simulated source systems `EEX_Sim`, `ICE_OCM_Sim`,
and `ICIS_Sim` in `market_observations`; they must not use ad hoc demo price
source names.

Production runtime modules and clients must not generate fallback business data.
If source data, contracts, market prices, tariffs, or capacity are missing, the
API must return a degraded/unavailable state with blockers.

## Commercial Data

Vendor entitlement and export policy must fail closed for unknown commercial
data. Unknown provenance means the data must not be exported or treated as
permitted.

## Lineage

Future data records and analysis outputs should preserve source references and
lineage sufficient for audit, debugging, and human review.

