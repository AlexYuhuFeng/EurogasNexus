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

## Run-status vocabulary

`ingestion_runs.status` is stored in the canonical `IngestionRunStatus`
spellings (`QUEUED`, `RUNNING`, `SUCCEEDED`, `SUCCEEDED_WITH_WARNINGS`,
`FAILED`, `CANCELLED`). The source read also accepts the four legacy lowercase
spellings (`queued`/`running`/`succeeded`/`failed`) written by the pre-CR-09
public-source ingestor and simulator; any other stored value stays unknown.
Raw stored statuses are returned unchanged.

- `SUCCEEDED_WITH_WARNINGS` is a success and may set `last_success_at_utc`,
  but Source Center keeps it qualified with the
  `last_ingestion_succeeded_with_warnings` diagnostic.
- `QUEUED`/`RUNNING` show `last_ingestion_pending`, `CANCELLED` shows
  `last_ingestion_cancelled`, and an unrecognised stored status shows
  `last_ingestion_status_unknown`. None of these count as success or failure.
- `last_success_at_utc` / `last_failure_at_utc` are the completion instants of
  the newest successful/failed run, not the newest start time.

## Where the shared vocabulary applies

`src/eurogas_nexus/domain/dataops/run_status.py` owns the single compatibility
interpretation of `ingestion_runs.status` (canonical `IngestionRunStatus`
spellings plus the four legacy lowercase ones, nothing else). The source read,
the monitoring alert scanner, pipeline health and `/api/runtime/metrics`
classify through it; raw stored statuses stay raw in every payload.

- Monitoring (`application/monitoring_service.py`): the `ingestion_failed`
  alert fires only when the newest requested run classifies as failed, and its
  `consecutive_failures` counts the unbroken streak of classified failures.
  `FAILED` and `failed` count identically; success, pending, cancelled and
  unknown stored values interrupt the streak. Severity is `critical` from
  three consecutive failures.
- Pipeline health (`GET /api/runtime/pipeline-health`): the same streak rule;
  the per-source `status` field remains the raw stored value.
- Metrics (`eurogas_ingestion_failures_total`): counts every persisted run
  that classifies as failed, canonical or legacy spelling alike.

Known limitations, reported rather than fixed here:

- Monitoring and pipeline health read the newest 500 persisted runs **globally**
  (ordered by `started_at_utc`), not per source. Their `consecutive_failures`
  is a lower bound whenever a streak extends past that window, and a source
  with no run inside the window is absent from those payloads rather than
  reported as zero. The authoritative streak remains
  `source_runtime_states.consecutive_failures` (scheduler-owned, exposed as
  `eurogas_source_consecutive_failures` and by `/api/sources`); the two are not
  reconciled against each other today.
- Monitoring and pipeline health group runs by `source_name`; the source read
  groups by `source_id`. Rows written without a `source_id` (column default
  `''`) - the pre-CR-09 public-source ingestor, the simulated market-price
  writer and the market-positioning importer all write that way - can therefore
  drive a monitoring alert while staying outside the per-source source-read
  bucket, and free-text name variants would split one provider into separate
  alert streaks.
- The metrics exporter reads the full persisted run history per scrape: the
  counts are exact, not sampled, but the read is unbounded.
- `eurogas_source_rows_received_total` / `eurogas_source_rows_rejected_total`
  are unlabelled global sums although their HELP text says "by source".

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
