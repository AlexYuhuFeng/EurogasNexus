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
- fixtures;
- development fallback.

Trial and release modes must not silently fall back to local files.

## Test Data

Tests must not use real vendor data. Use fixtures, synthetic examples, and
dry-run mode. Tests must not call live external APIs, live connectors, or LLM
providers.

## Commercial Data

Vendor entitlement and export policy must fail closed for unknown commercial
data. Unknown provenance means the data must not be exported or treated as
permitted.

## Lineage

Future data records and analysis outputs should preserve source references and
lineage sufficient for audit, debugging, and human review.

