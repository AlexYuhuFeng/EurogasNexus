# Data Freshness Runbook

## Scope

Freshness is backend-owned and deterministic:
`FRESH | LATE | STALE | MISSING | NOT_EXPECTED | UNKNOWN | RESTRICTED`.
The frontend never computes authoritative freshness.

## Freshness contract (FRESH-01)

Every dataset declares its expectation in its connector manifest
(`src/eurogas_nexus/domain/connectors/builtin/*.py`): the scheduler's schedule (cadence and
time), the receipt thresholds (`FreshnessPolicy`: current within `normal_max_age_minutes`,
late up to `stale_after_minutes`, stale beyond) and, for each stored dataset, how old its
newest period may be (`DatasetFreshness`: `period_late_hours`, `period_stale_hours`, and
the provider's publication in words). Nothing else holds an age threshold: the
data-quality report (`scripts/ops/data_quality_report.py`) reads the period thresholds
from the same declaration.

One service, `application/freshness_contract.py`, returns per dataset:

| Field | Meaning |
|---|---|
| `expected` | schedule, calendar, receipt thresholds, period thresholds, publication |
| `last_received_at_utc` | the later of first receipt and a provider revision (`last_received_column`) |
| `next_expected_at_utc` | the scheduler's own `next_run_at_utc` (basis `scheduler`), or what it would set on first sight (`schedule`); `next_expected_overdue` when that time has passed without a run |
| `state` | `current`, `late`, `stale`, `never`; `manual` for a manual register (TSO tariffs), a file import, a vendor template or a model service |

It is served on `GET /api/sources` as `freshness_contract` on each source (no new route),
and the Sources page shows it in the source's detail. A weekday-only source (ECB, the rate
administrators, EIA) does not count a weekend against its age. A schedulable source's
`normal_max_age_minutes` is at least its schedule's cadence
(`tests/unit/test_freshness_contract.py`); GIE moved from 360 to 1,500 minutes for that
reason (one read a day at 09:00 Brussels).

**TSO tariff registers** (`src-national-gas-nts`, `src-bbl`, `src-iuk`, `src-gts`,
`src-natran`, `src-german-tso`, `src-fluxys-belgium`, `src-cnmc-enagas`) are
`integration = manual_register`: the Sources page labels them "Manual register", the
freshness engine returns `NOT_EXPECTED`, and no late or stale alarm fires for them. The
category's next action is "update the register when the TSO publishes".

**Published TSO tariffs from ENTSOG** (`src-entsog`, route `entsog-tariffs`, dataset
"TSO tariffs (ENTSOG)") are read, not kept by hand: the reserve prices ENTSOG's
`tariffsfulls` dataset publishes for every interconnection point route pricing crosses and the
corridor, LNG and Norwegian landing points of `reference_data/tariff_scope.py`
(`ingestion/entsog_tariffs.py`), for the current and next gas year and every standard product,
one point per query 2 s apart, each point committed as it is read. A point read within
`--entsog-tariffs-max-age-hours` (24 in the scheduler, the reference worker of
`deploy/runtime/compose.yaml` and the demo start-up) is skipped, so each point is re-read at
most daily and a stopped or retried run resumes at the first point it had not finished. What
the register holds per crossing is printed by `scripts/ops/tariff_coverage.py`. A
tariff period opens once a year, so the newest period is late after 13 months and stale after
25 (`DatasetFreshness` in the ENTSOG manifest).

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
