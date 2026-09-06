# Temporal Data Model (CR-14)

Source: `src/eurogas_nexus/domain/research/temporal.py`.

## Three timestamps, three meanings

| Timestamp | Meaning | Used for event time? |
|---|---|---|
| `observed_at` | The fact time: when the value was observed / is valid for | Never alone for historical eligibility |
| `available_at` | When the value became legitimately visible to a decision maker | Yes: positive proof for point-in-time eligibility |
| `ingested_at` | When our system physically received/stored the row | Never used as event time |

Rules:

- `available_at <= cutoff` is the only positive proof of historical
  visibility.
- `ingested_at <= cutoff` is ingestion time and never makes a row eligible.
- A row with no `available_at` is ineligible in `STRICT` mode. In
  `EXPLORATORY` mode it may be approximated from `observed_at` only when the
  source declares `TEMPORAL_APPROXIMATE` or `TEMPORAL_INSUFFICIENT`.

## Observation kind

`ACTUAL`, `FORECAST`, `ASSESSMENT`, `MODEL_OUTPUT`, `SIMULATED` are distinct
and stored on each evidence record. The point-in-time policy decides whether
simulated inputs and forecast vintages may enter a dataset:

- `allow_simulated=False` (default) excludes `SIMULATED` rows from feature
  construction.
- `allow_forecast_vintages=True` (default) selects the latest forecast
  vintage; an actual/realized row must never overwrite a historical forecast.
- Target labels use actuals by default; simulated labels are allowed only
  when the policy opts in and are flagged `is_simulated=true`.

## Forecast vintages

Vintages are selected by the latest `available_at` that is `<= cutoff`
(tie-broken by `observed_at`), not by the latest valid time. Persisted
forecast rows are versioned by `forecast_issued_at` plus
`forecast_valid_start/end`; earlier vintages are retained in
`forecast_observations`.

## Dataset modes

| Mode | Missing `available_at` | Temporal integrity |
|---|---|---|
| `STRICT` | Rejected; feature row becomes a leakage blocker | `TEMPORAL_APPROXIMATE` and `TEMPORAL_INSUFFICIENT` block |
| `EXPLORATORY` | May approximate from `observed_at` with a warning reason | Insufficient rows warn; approximate rows are permitted and visible in quality report |

## Integrity states

- `TEMPORAL_VERIFIED`: historical availability is reconstructed from
  evidence.
- `TEMPORAL_APPROXIMATE`: availability is inferred/proxied.
- `TEMPORAL_INSUFFICIENT`: no defensible availability exists.

## Cutoff helpers

- `as_of_eligible(record, cutoff, policy)` is the single eligibility gate.
- `as_of_cutoff_for_origin(origin, min_availability_delay_seconds)` derives
  an explicit cutoff before a research decision origin.
- `forecast_vintage_at(...)` selects one vintage at a cutoff.

Gas-day/timezone semantics remain owned by the existing calendar module
(`EU-CAM-UTC-2025`); the research builder uses UTC origins and does not
duplicate calendar logic.
