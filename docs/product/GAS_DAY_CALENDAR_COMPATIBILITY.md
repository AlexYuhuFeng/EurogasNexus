# Gas-Day Calendar Compatibility Proposal

Status: accepted implementation policy for M0-P0 (2026-09-06). No historical
rows are rewritten by this policy.

## Problem

`EU-CAM-2025` was registered in code as 05:00 Europe/Berlin, yielding
04:00 UTC winter / 03:00 UTC summer. Regulation (EU) 2017/459 Article 3(16)
defines the gas day as 05:00 UTC winter / 04:00 UTC when daylight saving is
applied (06:00 CET / 06:00 CEST). The old rule is exactly one hour early
year-round and was persisted into period timestamps produced by earlier code.

## Versioning decision

- `EU-CAM-2025` is frozen with its historical rule. It must not be edited.
- `EU-CAM-UTC-2025` is the corrected Article 3(16) calendar and is the default
  for new backend computations, new GIE/simulated persisted rows, semantic
  value objects, and the web client boundary.
- Future regulation or DST rule changes add a new version; they never mutate
  an existing version id.

## Data policy

- New normalized rows produced by GIE AGSI/ALSI and simulated market
  generators record `metadata_json.calendar_version = "EU-CAM-UTC-2025"`.
- Existing rows are not updated or backfilled. Their period timestamps remain
  whatever earlier code wrote.
- Before GA, propose a first-class `calendar_version` column (Alembic
  migration) and an operator-approved recompute/annotate policy for rows
  produced with `EU-CAM-2025`. That is deliberately deferred until this M0
  evidence is reviewed.

## Compatibility rules

1. Callers needing historical reproducibility may still pass
   `calendar=EU_CAM_CALENDAR` explicitly.
2. Callers that omit the calendar get `EU-CAM-UTC-2025` for new computations.
3. Reports or runs persisted before this change remain immutable and must be
   reconstructed with their original code/dataset evidence, not silently
   re-marked.
4. The web client must not maintain an independent calendar implementation;
   the current TypeScript duplicate is corrected to match
   `EU-CAM-UTC-2025` and will be replaced by backend-owned context in the P1
   information-architecture milestone.

## Tests required before acceptance

- Legacy `EU-CAM-2025` remains 04:00Z winter / 03:00Z summer.
- Corrected default is 05:00Z winter / 04:00Z summer.
- Spring-forward gas day is 23h; fall-back gas day is 25h with corrected
  anchors.
- Naive timestamps are treated as UTC; unsupported calendar ids raise.
- GIE and simulated new rows carry `calendar_version` and corrected period
  bounds.
- Semantic `GasDayRef` defaults to `EU-CAM-UTC-2025`.
- Web `gasDayStartUtc`, `gasDayLabelForUtc`, and `marketMatchesTradingContext`
  use the corrected boundary and exact transition intervals.
