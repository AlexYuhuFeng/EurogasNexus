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

**One freshness rule for Today and the Data feeds popover (QA-R-07).** Today's
`stale_figures` and the Data feeds popover (market-context slices and the `data_sources`
rows of the market-context and portfolio-snapshot projections) judge with the same contract
and map its word once:

| Contract `state` | Projection `freshness.state` | Today |
|---|---|---|
| `current` | `FRESH` | not named |
| `late` | `LATE` | named, "late" |
| `stale` | `STALE` | named, "stale" |
| `never` | `MISSING` | named, "never" |
| `manual` | `NOT_EXPECTED` | not named |

- A feed is judged by its source's declared `FreshnessPolicy` and calendar
  (`freshness_contract.source_system_state`, which resolves a row's `source_system` to its
  connector manifest). A slice is as current as its least current declared source
  (`projections.freshness.contract_state_for_rows`). A slice whose rows name no declared
  source keeps the registry expectation rule (`evaluate_freshness`).
- Marks (daily closes) use the business-day rule `domain.monitoring.freshness.close_state`:
  the previous weekday's close is current, one weekday behind is late, more is stale.
- The mapping is `freshness_contract.PROJECTION_STATE`; `projection_state()` returns
  `UNKNOWN` for anything else.
- Consequence: a 10-minute-old EEX tick (policy: current within 1 minute, stale after
  3 days) is `LATE`, not `STALE`, and raises no `SOURCE_STALE` warning.

**Marks behind risk figures.** Credit exposure rows and position ladder rows carry
`marks_as_of` (the oldest of their hubs' newest closes) and `state` by the close rule (credit
rows also `freshness_state`, the projection word); mandate rows are measured in MWh and carry `marks_as_of: null`, `state: current`.
The ladder also gives `marks_as_of`/`marks_state` for its totals. When any priced credit row
is late or stale, the monitoring scan raises one `marks_stale` alert (category `limits`,
severity `warning`, scoped to the affected books, fingerprint `marks_stale:credit`). It is a
warning, never critical, so Today does not read it as a breach. The web Risk limits panel and
Position page state the marks date and its state in text ("stale · marks 18 Nov"), not colour
alone.

**One price per hub and period (P-08).** Every screen that states a hub price for a delivery
period reads it from one resolver (`domain/market/price_resolution.resolve_price`, loaded by
`application/price_resolver.open_price_book`): the Prices board (`/api/market/quotes`), Today
(key figures, My market front month, the book row's mark), the desk brief, the position
ladder marks, the spreads board's month-ahead legs, and the valuation snapshot behind the
opportunity scan and LNG cargo economics. The candidates for a hub, period and instant are:

| Class | `kind` | From | In date when |
| --- | --- | --- | --- |
| Live tick | `live_tick` | Newest two-sided (or one side) quote per source | The source's declared freshness policy (`receipt_state`; `current` within `normal_max_age`, `late` until `stale_after`); a source with no declaration falls back to its registry expectation, else `stale` |
| Settlement/close | `settlement` | Energy-price observations (settlements, closes, curve rows) | The business-day close rule (`close_state`: the previous weekday's close is `current`, one weekday behind `late`) |
| Firm mark | `firm_mark` | The firm's current marks (`operator-input`) | The same close rule on the mark's day |
| Derived | `derived` | A ladder figure the curve filled (`curve:<method>`) | The hub's newest close |

The rule, in order: the freshest in-date (`current` or `late`) tick or settlement, a tie going
to the tick; else the newest in-date firm mark (a mark never beats an in-date market price);
else an in-date derived figure; else the freshest candidate held, stated `stale`. Only sources
the caller is entitled to (`row_allowed`) are candidates; simulated (`_Sim`, demo) prices only
where demo marks are allowed, and a real price always beats a simulated one. Prices observed
after the instant are ignored. Screens read candidates observed in the last 10 days (the
valuation snapshot 400). Each screen adds `resolved_price` (`value`, `unit`, `value_mwh`,
`kind`, `source_system`, `as_of_utc`, `state`, `freshness_state`, `simulated`, `basis`,
`reference`) so the trader sees which price it is and how old. Today and the desk brief
resolve once per request and share the book, so every figure on one page is one instant.
Day-ahead figures still read the day-ahead close.

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
