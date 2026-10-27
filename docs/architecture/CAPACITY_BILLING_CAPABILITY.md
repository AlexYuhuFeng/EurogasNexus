# Capacity Billing Capability

Status: **research decision support only — not booked rights, physical readiness,
invoice authority, settlement or trade execution.**

This document describes the reviewed exact capacity-billing primitive
(`src/eurogas_nexus/domain/research/capacity_billing.py`), its typed research API
(`POST /api/research/capacity-billing`), the Python SDK carriers, and the bounded
portfolio-network integration. It also records what remains unimplemented.

## 1. Scope

The capability answers one question:

> Given an explicit capacity tariff, an explicit booked-capacity quantity, an
> explicit billed-capacity energy, an explicit delivered energy and an explicit
> UTC billing window, what is the exact capacity charge and what is its cost per
> delivered MWh?

It does **not**:

- establish that capacity is booked, available, firm or physically deliverable;
- choose or retrieve a tariff from a source;
- infer a billing window, utilization, annualization, calendar convention or FX
  rate;
- allocate a capacity charge to a route, portfolio, invoice or settlement;
- persist anything or call a provider;
- create a trading, nomination or settlement instruction.

The domain primitive is the single arithmetic authority. The API and SDK contain
no duplicate formulas.

## 2. Supported units and exact formulas

Exactly three tariff bases are supported:

| `tariff_unit` | Allowed `currency` | Conversion to the billing currency |
| --- | --- | --- |
| `EUR/(MWh/h)/h` | `EUR` | rate × billed energy × 1 |
| `GBP/(MWh/h)/h` | `GBP` | rate × billed energy × 1 |
| `p/(kWh/h)/h` | `GBP` | rate × billed energy × 10 |

The pence factor is exact:

```text
1000 kWh/MWh ÷ 100 pence/GBP = 10
```

No FX conversion is applied inside the primitive. The rate and result currency
are explicit, and a unit/currency mismatch is refused.

### 2.1 Billing window and duration

`billing_start` and `billing_end` must be timezone-aware. The primitive converts
both to UTC and computes:

```text
duration_microseconds = exact integer UTC duration
duration_hours        = duration_microseconds / 3,600,000,000   (display, precision 34)
```

The exact integer microseconds are retained in the basis. The precision-34
`duration_hours` is a display value and is **never** used for the billed-energy
check.

### 2.2 Billed capacity energy

Billed capacity energy is validated by exact cross-multiplication:

```text
billed_capacity_energy_mwh × 3,600,000,000
    ==
booked_capacity_mwh_per_h × duration_microseconds
```

This is exact `Fraction` arithmetic. A repeating decimal duration rounded to 34
significant digits can make a fractional mismatch look equal; the cross-product
does not. A dedicated regression uses a 3,600,000,001-microsecond window and a
booked capacity whose precision-34 duration product rounds to the billed value,
while the exact product differs by `1/(3,600,000,000 × 10^18)` MWh. The domain
still refuses `BILLED_CAPACITY_ENERGY_INCONSISTENT`.

### 2.3 Full billed cost and per-delivered allocation

The full invoiced capacity cost is:

```text
total_exact = tariff_rate × billed_capacity_energy_mwh × unit_factor
total_cost  = total_exact rounded to 0.0001, ROUND_HALF_EVEN
```

The allocation to delivered energy is a separate calculation:

```text
cost_per_delivered_mwh =
    total_cost / delivered_energy_mwh
    rounded to 0.0001, ROUND_HALF_EVEN
```

`cost_per_delivered_mwh` is **not** an energy-price conversion and must not be
used as a market price. It answers only “what does this capacity charge cost per
unit actually delivered?” and is sensitive to utilization.

Example: 10 MWh/h booked for 23 hours at 2 EUR/(MWh/h)/h gives 230 MWh of billed
capacity energy and a full cost of 460 EUR. If 115 MWh are delivered, the
allocation is 4 EUR/MWh. Delivering only 92 MWh would give 5 EUR/MWh with the
same 460 EUR charge.

### 2.4 23-hour and 25-hour windows

The 23-hour and 25-hour examples are **billing-window durations**, not an
assumption that every gas day has that length:

- 10 MWh/h × 23 h = 230 MWh billed; at 2 EUR/(MWh/h)/h, full cost 460 EUR;
- 10 MWh/h × 25 h = 250 MWh billed; at 2 EUR/(MWh/h)/h, full cost 500 EUR.

The per-delivered allocation is 4 EUR/MWh in both examples only because the
delivered quantity scales with the window in that synthetic case. It is not a
constant.

### 2.5 Subsecond windows

Billing windows are exact to the microsecond. A one-microsecond window with
3,600,000,000 MWh/h booked and 1 MWh billed is consistent and bills exactly one
unit of capacity energy. The API returns the exact `duration_microseconds` and
the precision-limited `duration_hours` as separate values.

### 2.6 Rounding and bounds

- All money outcomes are rounded from an exact `Fraction` to `0.0001`,
  `ROUND_HALF_EVEN`.
- Arithmetic runs in a fresh local decimal context (`precision=34`,
  `ROUND_HALF_EVEN`) isolated from the ambient context.
- Input bounds are checked before arithmetic: rate ≤ 1e12, booked capacity ≤
  1e12 MWh/h, billed/delivered energy ≤ 1e18 MWh, duration ≤ 87,840 hours,
  at most 30 coefficient digits and absolute exponent 30, and the shared
  `MAX_ABS_CASH_AMOUNT` bound on the results.
- Zero tariff is valid **only when explicitly supplied**; it is never defaulted.

## 3. API contract

`POST /api/research/capacity-billing`

The endpoint follows the existing research sandbox conventions:

- caller-supplied scenario/tariff identifiers are data references, never
  resolved to persisted entities;
- the request model forbids unknown fields, so a body cannot smuggle
  `research_only`, customer approval, booked-rights or readiness claims;
- the shared research sandbox dependency labels `decision_context` as
  `SANDBOX_SCENARIO` and refuses `RUNTIME_DECISION`;
- the route remains under the existing `/api/research/` `GOVERNED` permission
  family and the existing commercial-data boundary; no permission rule or grant
  is changed by this slice;
- release-profile identity, role floors and anonymous refusal are unchanged;
- no database is read or written, no source is retrieved or activated and no
  provider is called.

### 3.1 Exact wire inputs

Every numeric field is a plain decimal **string**:

```json
{
  "scenario_id": "scenario-synthetic-1",
  "tariff_id": "tariff-synthetic-1",
  "tariff_rate": "2",
  "currency": "EUR",
  "tariff_unit": "EUR/(MWh/h)/h",
  "booked_capacity_mwh_per_h": "10",
  "delivered_energy_mwh": "115",
  "billed_capacity_energy_mwh": "230",
  "billing_start": "2026-01-01T00:00:00+00:00",
  "billing_end": "2026-01-01T23:00:00+00:00",
  "source_references": [
    "synthetic-test-input:booking-1",
    "synthetic-test-input:tariff-1"
  ]
}
```

JSON numbers, booleans, exponent notation, whitespace, `NaN`/`Infinity` and
other non-plain decimal text are refused. Naive timestamps are refused; both
bounds must carry an explicit offset. Provenance must be present and non-empty
after domain validation.

Refusals are `422` with stable codes:

- `capacity_billing_input_invalid` — wire syntax or timestamp awareness failed;
- `capacity_billing_refused` — the shared engine refused the supplied values,
  with its stable `codes` (for example `BILLED_CAPACITY_ENERGY_INCONSISTENT`,
  `TARIFF_UNIT_UNSUPPORTED`, `TARIFF_UNIT_CURRENCY_MISMATCH`,
  `SOURCE_REFERENCES_MISSING`).

### 3.2 Result envelope

`data` carries the model version, original explicit basis, exact duration
microseconds, exact decimal strings, UTC timestamps and:

```text
research_only = true
human_review_required = true
physical_readiness = "NOT_ASSESSED"
```

`meta` additionally states `decision_context=SANDBOX_SCENARIO`,
`caller_supplied=true`, `references_verified=false`,
`booked_rights_established=false` and `customer_approval=false`. Plain data
references do not claim verified source rights.

Decimals are serialized with the existing fixed-point string helper; no binary
float is used anywhere in the request or response path.

## 4. Python SDK contract

`packages/python-sdk/src/eurogas_nexus_sdk/capacity_billing.py` defines:

- `CapacityBillingRequest` — typed request with decimal strings and aware
  datetimes; unknown fields are refused;
- `CapacityBillingBasis` — the original explicit basis;
- `CapacityBillingResult` — all exact strings, datetimes, model version, basis,
  duration microseconds and research/readiness flags.

`eurogas_nexus_sdk.research.calculate_capacity_billing` posts exactly to
`/api/research/capacity-billing`, serializes the typed request and parses the
typed result. It performs no local financial arithmetic. Server refusals
propagate through the existing `httpx` error behavior (`raise_for_status`).

Usage:

```python
from datetime import UTC, datetime

from eurogas_nexus_sdk.capacity_billing import CapacityBillingRequest
from eurogas_nexus_sdk.research import calculate_capacity_billing

result = calculate_capacity_billing(
    "http://127.0.0.1:8000",
    request=CapacityBillingRequest(
        scenario_id="scenario-synthetic-1",
        tariff_id="tariff-synthetic-1",
        tariff_rate="2",
        currency="EUR",
        tariff_unit="EUR/(MWh/h)/h",
        booked_capacity_mwh_per_h="10",
        delivered_energy_mwh="115",
        billed_capacity_energy_mwh="230",
        billing_start=datetime(2026, 1, 1, tzinfo=UTC),
        billing_end=datetime(2026, 1, 1, 23, tzinfo=UTC),
        source_references=[
            "synthetic-test-input:booking-1",
            "synthetic-test-input:tariff-1",
        ],
    ),
)
assert result.total_cost == "460.0000"
assert result.cost_per_delivered_mwh == "4.0000"
```

## 5. Portfolio-network integration

Before this slice, `portfolio_network._money_to_gbp_mwh` converted
`p/(kWh/h)/h` to `GBP/MWh` by multiplying by 10 and then treated the result as an
energy fee. That was unsafe: it had no utilization, booked capacity or billing
window and could silently price a route with a fabricated per-MWh number.

The conversion helper now identifies all three capacity bases before any FX or
arithmetic step and returns:

```text
(None, {}, "TARIFF_CAPACITY_BILLING_REQUIRED")
```

The composed route then records a blocker such as:

```text
ROUTE_COST_CONVERSION_BLOCKED:TARIFF_CAPACITY_BILLING_REQUIRED:<route_id>
```

The blocked composition is not optimized, no zero charge is inserted and no fake
energy fee reaches the network-flow solver. Ordinary energy money (for example
`EUR/MWh` with as-of FX, or `GBP/MWh`) is preserved unchanged.

A composed-portfolio regression uses the published IUK
`p/(kWh/h)/h` annual-firm row and proves that the route blocks even though a
capacity tariff exists; it also proves `optimize_composed_portfolio_network`
refuses the blocked snapshot. This is a refusal path, not a capacity-billing
composition.

## 6. Synthetic examples

All examples are synthetic and do not describe a market, contract or invoice.

| Case | Basis | Full charge | Per delivered MWh |
| --- | --- | --- | --- |
| 23 h | 10 MWh/h, 2 EUR/(MWh/h)/h, 230 MWh billed, 115 MWh delivered | 460.0000 EUR | 4.0000 EUR/MWh |
| 25 h | 10 MWh/h, 2 EUR/(MWh/h)/h, 250 MWh billed, 125 MWh delivered | 500.0000 EUR | 4.0000 EUR/MWh |
| 24 h pence | 10 MWh/h, 0.035827 p/(kWh/h)/h, 240 MWh billed, 120 MWh delivered | 85.9848 GBP | 0.7165 GBP/MWh |
| 1 µs | 3,600,000,000 MWh/h, 2 EUR/(MWh/h)/h, 1 MWh billed, 1 MWh delivered | 2.0000 EUR | 2.0000 EUR/MWh |

The 23h/25h full charges differ because the billed capacity energy differs. The
allocation is a separate division by delivered energy, not a property of the
tariff.

## 7. Remaining work and explicit non-claims

This slice is **not full project delivery**. Remaining bounded work includes:

1. **Tariff date/version selection.** The API accepts a caller-supplied tariff
   id and rate; it does not resolve a tariff row, effective dates, gas year,
   product (annual/quarterly/monthly/daily), firmness, direction or point from
   PostgreSQL.
2. **Route/portfolio composition.** The portfolio network has no explicit
   capacity-billing inputs (booked capacity, billed capacity energy, delivered
   energy or billing window), so a capacity-tariff route remains blocked rather
   than being composed. A later slice must compose those inputs explicitly and
   keep the domain primitive as the only arithmetic authority.
3. **Billed-cost vs allocation policy.** The domain reports both the full charge
   and the per-delivered allocation; product/route policy for which one enters a
   PnL, and how under-utilization is attributed, is not defined here.
4. **Physical readiness and booked rights.** These remain `NOT_ASSESSED` and
   unestablished. No terminal, TSO, booking system or capacity auction is read.
5. **Web/Desktop integration.** The existing Portfolio Routes task now mounts a
   bilingual capacity form with exact strings, explicit basis and unknown
   readiness. Real browser golden/refusal/edit invalidation, Ctrl+Enter,
   success focus and 390px overflow checks pass. Installed native artifact
   verification and complete route/portfolio allocation policy remain open.
6. **Static contract census and docs.** The additive endpoint is declared in
   pinned API paths, measured route counts and contract evolution policy.
   Web transport and mounted panel provide actual surface reachability.
7. **Provider/source integration.** No tariff document retrieval, source
   activation, entitlement change, credential use or persistence is included.

## 8. Validation scope

Focused tests for this slice cover:

- the reviewed domain primitive, including the independent precision-34
  rounded-product regression;
- the composed-portfolio capacity-basis refusal and blocked-snapshot refusal;
- the API's exact decimal/timestamp contract, refusals, sandbox gate, exact
  serialization, permission declaration and release-profile role/anonymous
  behavior;
- the SDK's typed request/result and exact endpoint wire contract through
  `httpx.MockTransport`, plus server-refusal propagation.

These are automated development checks. They do not constitute supplier
acceptance, market-data licensing, booked-rights evidence, physical-readiness
evidence, invoice validation or production approval.
