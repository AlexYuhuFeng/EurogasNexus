# Source Failure Runbook

## Scope

A source is healthy only when access is configured, entitlement is valid,
certification state is known, the scheduler is operating, updates are arriving,
quality passed, freshness is inside SLA, and lineage is preserved. This runbook
covers failures of the PostgreSQL-backed data-operations scheduler and the
existing public-source ingestor.

## Symptoms

- `/api/runtime/source-operations` shows `sources_failed > 0`.
- Source Center shows circuit state `DEGRADED` or `OPEN_CIRCUIT`.
- `ingestion_runs` shows `FAILED` with `error_category`.
- Source freshness state is `LATE`, `STALE`, or `MISSING` while the calendar
  expects an update.

## Diagnostics

1. `GET /api/sources/{source_id}/health` — circuit, counters, next run, last
   success/attempt.
2. `GET /api/sources/{source_id}/runs` — structured run history and issues.
3. `GET /api/runtime/source-operations` — scheduler heartbeat and backlog.
4. `GET /api/runtime/metrics` — counters/gauges.
5. Inspect `error_category`:
   - `NETWORK_TRANSIENT`, `RATE_LIMITED`, `PROVIDER_UNAVAILABLE`: retry is
     policy-managed.
   - `AUTHENTICATION`, `ENTITLEMENT`: terminal until credential/contract is
     corrected.
   - `SCHEMA_CHANGED`: provider schema changed; compare adapter parser and
     recent raw archive hash (if retention permits).
   - `QUALITY_REJECTED`: inspect `ingestion_run_issues`.

## Safe actions

- Retry a failed run explicitly: `POST /api/sources/{source_id}/retry`.
- Disable a hammering source: `PATCH /api/sources/{source_id}/enabled`.
- Run now after a manual fix: `POST /api/sources/{source_id}/run`.
- Rotate a credential through the backend (plaintext is never returned).
- Wait for the recovery probe for `OPEN_CIRCUIT`; success resets the circuit.

## Unsafe actions

- Do not restart the scheduler loop indefinitely without reading the persisted
  error category.
- Do not mark a source `CERTIFIED` to make the error disappear.
- Do not edit `ingestion_runs` or `source_runtime_states` by hand.
- Do not run backfill instead of fixing a live feed.
- Do not treat historical rows as invalid just because the current feed is
  stale.

## Recovery verification

- New run is `SUCCEEDED` or `SUCCEEDED_WITH_WARNINGS`.
- Circuit state returns to `HEALTHY`; consecutive failures reset to zero.
- Freshness state returns to `FRESH` for the source's SLA.
- Downstream market/strategy/shadow surfaces show current evidence again.

## Escalation

Escalate to the data-operations owner when `SCHEMA_CHANGED`,
`ENTITLEMENT`, or `AUTHENTICATION` persists after one operator fix, or when a
scheduler heartbeat is missing for more than two scan intervals.
