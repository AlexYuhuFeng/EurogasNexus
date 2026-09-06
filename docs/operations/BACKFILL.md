# Backfill Runbook

## Scope

Backfill is explicit operator-triggered ingestion for a bounded historical
window. It never masquerades as live ingestion and never claims a scheduled
slot.

## Symptoms requiring backfill

- A documented provider gap (source was down) left a bounded data period
  missing.
- A schema/parser defect was fixed and affected rows must be re-ingested.
- Operator asks for a bounded historical window for review.

## Diagnostics before backfill

- `GET /api/sources/{source_id}/runs` — confirm the gap and last successful
  window.
- `GET /api/sources/{source_id}/health` — confirm circuit is not open or the
  source is deliberately enabled for recovery.
- Check raw payload archives (if retention permits) for the missing window.

## Safe action

`POST /api/sources/{source_id}/backfill` with `start_utc`, `end_utc`,
`reason`, and optional `dry_run`. The API enforces `start_utc < end_utc` and a
maximum 31-day window per request. Larger windows must be split into bounded
requests.

## Unsafe actions

- Do not use backfill to make a currently failing live feed appear active.
- Do not change provider `observed_at_utc` or `period_*` timestamps; only
  pipeline activity time changes.
- Do not run overlapping live and backfill jobs for the same source without
  operator review.

## Recovery verification

- A persisted `trigger_type=BACKFILL` run exists and reports
  `SUCCEEDED`/`SUCCEEDED_WITH_WARNINGS`.
- Missing-period rows exist with original observation/period timestamps.
- Duplicate count is zero or explicitly reviewed.
- Live scheduling remains untouched: `next_run_at_utc` and scheduled unique
  identity are unchanged.

## Escalation

Escalate to the data vendor owner if provider terms prohibit the requested
retention/backfill window; do not ingest beyond licensed retention.
