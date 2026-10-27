# Tariff Applicability Capability

Status: implemented in the bounded TARIFF-APPLICABILITY slice. Focused tests
are authored; this worker could not execute them because the harness shell lock
failed before process start (see **Validation**). No pass is claimed here.

## Problem

`select_latest_tariff` matched an exact tariff key and then took the best
`tariff_status` in row order. It ignored `effective_from` and `effective_to`,
so two FINAL rows for the same point could resolve differently depending on
database read order. `gas_year` is an exact-match key, not a calendar date: it
cannot prove which dated source row applied on a particular day.

## Contract

### Request carrier

`RouteCostScenario` gains one additive optional field:

```text
tariff_applicability_date: date | None = None
```

- It is the only date used to assess tariff applicability.
- `POST /api/route-cost/calculate` receives it through the existing
  `RouteCostScenario` body. There is no new endpoint and no separate request
  mapping in the route module.
- The Python SDK's `calculate_route_cost` accepts it as an explicit keyword and
  serializes a `date` as an ISO `YYYY-MM-DD` string. The SDK also exposes the
  effective bounds on `RouteCostTariff`.
- `RouteCostResult` echoes the supplied date (or `None`) so the selection basis
  is visible in the result. The field is additive; older callers and servers
  keep working.

A plain calendar date is required. A `datetime` is not silently truncated to a
date; a direct domain call with one is refused with
`TARIFF_APPLICABILITY_DATE_INVALID`, and the API's Pydantic `date` field
enforces the same boundary at the wire.

### Exact key

Selection still requires exact equality on:

- country;
- TSO;
- source point name;
- direction;
- gas year;
- capacity product;
- firmness.

When the leg declares a `market_area`, the route-cost service filters the
candidate set by exact `market_area` before selection. No candidate from a
different key or market area is ever substituted.

### Explicit-date algorithm

1. Refuse a non-calendar applicability value.
2. Keep only exact-key candidates.
3. Refuse the whole selection if any exact-key candidate has an inverted
   interval (`effective_to < effective_from`). The source set is not
   trustworthy enough to pick another row silently.
4. Collapse fully identical duplicate rows that share a `tariff_id`.
   The same `tariff_id` with different row content is refused
   (`TARIFF_DUPLICATE_ID_CONFLICT`); row order is never used to choose one.
5. Keep rows whose bounds include the date, inclusively:
   `effective_from <= date` and (`effective_to is None` or
   `date <= effective_to`). `effective_to = None` is open-ended, not unknown.
6. Within that eligible set, preserve the existing status priority:
   FINAL, INDICATIVE, PROVISIONAL, DRAFT, SIMULATOR_ONLY.
7. If two or more different candidates share the highest priority and both
   cover the date, refuse as `TARIFF_APPLICABILITY_AMBIGUOUS`. Status priority
   may prefer FINAL over INDICATIVE, but it cannot break a FINAL-vs-FINAL tie.
8. Select the single remaining authoritative row. A selected non-FINAL row
   still carries the existing `TARIFF_STATUS_<STATUS>` warning and requires
   human review.

Inclusive boundaries are deliberate: the first and last effective day are
applicable. A gap, a date before the first interval or a date after a closed
last interval is `TARIFF_NOT_EFFECTIVE_ON_DATE`.

### Legacy path without a date

When `tariff_applicability_date` is `None`, the previous status-priority,
first-row-wins selection is preserved for wire compatibility. The selection
always carries:

```text
TARIFF_APPLICABILITY_NOT_ASSESSED
```

and `human_review_required = True`. The result does not claim the row was
verified for any date, and the route result does not claim applicability was
assessed. This is a compatibility path, not a verified business workflow.

## Route-cost propagation

The service passes the scenario date into every leg selection unchanged. It
never reads `created_at`, the current clock, `gas_year`, or a source retrieval
timestamp as a date proxy.

When a leg's explicit-date selection fails, the failure code is prefixed with
that leg id, for example:

```text
TARIFF_NOT_EFFECTIVE_ON_DATE:bbl-forward
TARIFF_APPLICABILITY_AMBIGUOUS:leg-b
TARIFF_EFFECTIVE_BOUNDS_INVALID:leg-a
TARIFF_DUPLICATE_ID_CONFLICT:leg-a
```

A route with an explicit-date applicability failure is `BLOCKED`; its
`total_cost`, `currency` and `unit` are `None`, even if another leg was priced.
The priced components remain visible for diagnosis, but they are not presented
as a partial route charge. The route-level warning
`ROUTE_BLOCKED_BY_TARIFF_APPLICABILITY` is added. This is stricter than a plain
missing tariff: a date the caller declared but the source cannot resolve is a
hard refusal, not an invitation to use a neighbouring row.

No money, unit, FX or capacity formula was changed. The service still sums only
compatible currency/unit triples and still refuses a capacity-tariff basis
without the separate exact capacity-billing primitive. `portfolio_network`'s
capacity-billing guard is untouched.

## Stable codes

| Code | Kind | Meaning |
| --- | --- | --- |
| `TARIFF_MISSING` | missing input | No exact-key row exists at all. |
| `TARIFF_NOT_EFFECTIVE_ON_DATE` | missing input | Exact-key rows exist, but none covers the explicit date. |
| `TARIFF_APPLICABILITY_AMBIGUOUS` | missing input | Two or more different rows at the highest status cover the date. |
| `TARIFF_EFFECTIVE_BOUNDS_INVALID` | missing input | At least one exact-key row has `effective_to < effective_from`. |
| `TARIFF_DUPLICATE_ID_CONFLICT` | missing input | One tariff id exists with different row content. |
| `TARIFF_APPLICABILITY_DATE_INVALID` | missing input | The supplied value is not a plain calendar date. |
| `TARIFF_APPLICABILITY_NOT_ASSESSED` | warning | No explicit date was supplied; legacy selection only. |
| `TARIFF_STATUS_<STATUS>` | warning | A non-FINAL row was selected and needs review. |
| `ROUTE_BLOCKED_BY_TARIFF_APPLICABILITY` | warning | At least one leg failed explicit-date applicability; route total suppressed. |

## Remaining integration gaps for root

These carriers are outside this slice's write scope and were deliberately not
edited:

- `RouteRecommendationRequest` and `route_optimizer.recommend_route_allocation`
  have no applicability-date carrier. They call `calculate_route_cost` without
  one, so recommendation route costs disclose
  `TARIFF_APPLICABILITY_NOT_ASSESSED` and require review. Root should add the
  date to that workflow before claiming recommendation costs are
  date-verified.
- `portfolio_network.compose_portfolio_network` pre-filters tariffs by its
  `gas_day`, then calls `calculate_route_cost` without the explicit date
  carrier. The service therefore still discloses
  `TARIFF_APPLICABILITY_NOT_ASSESSED` for those route-cost results, and the
  composition does not gain inverted-bound or same-status overlap detection
  from this slice. Root can pass the carrier after extending that call path
  without changing the capacity-billing guard.
- `application/resource_pool.candidate_route_cost` (used by
  `GET /api/route-cost/resource-pool/options` and the PortfolioSnapshot
  projection) also constructs `RouteCostScenario` without an applicability
  date. Its route costs will disclose `TARIFF_APPLICABILITY_NOT_ASSESSED` and
  require review until root adds an explicit date source to that composition.
- The DB repository `list_tso_tariffs` returns all stored rows; no SQL-level
  date filter was added. Selection remains in the domain layer so one code path
  owns applicability.
- Web/Desktop request builders were not edited in this slice. A client that
  omits `tariff_applicability_date` receives the disclosed legacy path; root
  must add the field to any business workflow that claims date-verified route
  costs.
- Only `CapacityTariff.effective_from` / `effective_to` are available on the
  route-cost path. `TariffSourceDocument.effective_from` / `effective_to` are
  not threaded into route cost, and document-level applicability is not
  inferred from the row dates or vice versa.
- Tariff values remain the existing `float` source representation. This slice
  makes no claim that a float is an exact monetary source; it performs no new
  arithmetic and changes no rounding or conversion rule.

## Tests authored

`tests/unit/test_route_cost_tariff_applicability.py` covers:

- first and last effective day inclusive;
- before/after period and an internal gap;
- overlapping FINAL ambiguity;
- status priority within eligible dates and non-FINAL warning/review;
- inverted bounds;
- identical same-id duplicates versus conflicting same-id rows;
- rejection of a `datetime` as an applicability date;
- no-date legacy selection plus `TARIFF_APPLICABILITY_NOT_ASSESSED`
  disclosure;
- real `calculate_route_cost` propagation, result echo, leg-specific block
  codes, no substitute charge, multi-leg total suppression, and the
  `market_area` filter.

`tests/unit/test_route_cost_tariff_selection.py` now supplies explicit dates to
its existing FINAL-row assertions and keeps the no-substitution gas-year test.
`tests/api/test_route_cost_api.py` covers the HTTP request carrier, an
out-of-period leg block and no-date disclosure. `tests/sdk/test_route_cost_client.py`
covers ISO serialization of the explicit date and result echo.

## Validation

Focused commands:

```text
python -m pytest tests/unit/test_route_cost_tariff_applicability.py tests/unit/test_route_cost_tariff_selection.py tests/api/test_route_cost_api.py tests/sdk/test_route_cost_client.py -q
python -m ruff check src/eurogas_nexus/domain/route_cost/tariff_selection.py src/eurogas_nexus/domain/route_cost/schemas.py src/eurogas_nexus/domain/route_cost/route_cost_service.py packages/python-sdk/src/eurogas_nexus_sdk/route_cost.py tests/unit/test_route_cost_tariff_applicability.py tests/unit/test_route_cost_tariff_selection.py tests/api/test_route_cost_api.py tests/sdk/test_route_cost_client.py
```

This worker's shell calls failed at the harness temp-lock ACL before process
execution. The tests and Ruff command above are therefore **not run here**;
root must execute them and review the actual results before accepting the
slice.
