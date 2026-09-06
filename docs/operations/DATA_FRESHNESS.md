# Data Freshness Runbook

## Scope

Freshness is backend-owned and deterministic:
`FRESH | LATE | STALE | MISSING | NOT_EXPECTED | UNKNOWN | RESTRICTED`.
The frontend never computes authoritative freshness.

## Symptoms

- Market/Strategy/Shadow surfaces show stale or degraded evidence.
- Runtime workspace reports stale/missing sources.
- A DA source appears critical during a calendar-closed window (this must be
  `NOT_EXPECTED`, not a failure).

## Diagnostics

- `GET /api/sources/{source_id}/health` for state, age, last observed, last
  success and last attempt.
- `GET /api/runtime/source-operations` for aggregate late/stale/backlog.
- Compare `source_age_seconds` (provider age), `ingestion_lag_seconds`
  (provider -> persisted) and `pipeline_lag_seconds` (run duration).

## Rules

- One threshold per source, not one global "older than 24h".
- `MISSING` means expected but never succeeded; `NOT_EXPECTED` means the
  calendar/schedule says no update is due (e.g. ECB weekend).
- `RESTRICTED` means credential/certification blocks evaluation, not "stale".
- A stale current feed never rewrites historical runs; historical runs stay
  valid evidence at their recorded cutoff.

## Safe actions

- Trigger a manual run: `POST /api/sources/{source_id}/run`.
- Retry a failed run: `POST /api/sources/{source_id}/retry`.
- Disable an unmaintained source so it is not counted overdue.
- Review market calendar/schedule mismatch before changing SLA values.

## Unsafe actions

- Do not edit `observed_at_utc` to make rows look fresh.
- Do not let the UI hide stale state.
- Do not make stale current data appear current in downstream screens.
- Do not treat a provider-closed window as ingestion failure.

## Recovery verification

- Freshness state returns to `FRESH` (or `NOT_EXPECTED` for closed windows).
- Source age is inside the source's `normal_max_age_minutes`.
- Downstream live candidate views show current evidence.

## Escalation

Escalate when a source is `STALE` for two consecutive expected updates and
operator actions above have not recovered it.
