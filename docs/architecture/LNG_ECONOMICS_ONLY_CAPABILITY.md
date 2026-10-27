# LNG Economics-Only Capability

Status: implemented bounded decision-support capability, 2026-10-27.
Source: [src/eurogas_nexus/domain/research/lng_cargo_economics.py](../../src/eurogas_nexus/domain/research/lng_cargo_economics.py)
Energy accounting: [src/eurogas_nexus/domain/research/lng_energy_balance.py](../../src/eurogas_nexus/domain/research/lng_energy_balance.py)

This note describes the actual implementation. Code and focused tests remain the
source of truth for current behaviour.

## Why the split exists

The legacy `compute_lng_cargo_economics` composition requires an
`LngRegasScenario` and delegates to `assess_lng_regas_readiness`. Missing
terminal access, slot, capacity or TSO inputs fail the valued result closed. That
is the correct strict physical-readiness path and remains unchanged.

A research question can be economics-only: can explicit purchase prices, sale
prices, invoiced cash costs and an explicit energy chain be composed without
fabricating a terminal slot, storage right or nomination? The new path answers
only that question. It cannot answer delivery feasibility.

## Public contracts

### Preserved legacy path

`compute_lng_cargo_economics(LngCargoEconomicsInput) -> LngCargoEconomicsResult`

- Model version remains `lng-cargo-economics/v1`.
- Input result dataclasses, field order, formulas, warning order, refusal codes
  and the existing readiness assessor are preserved.
- `LngCargoEconomicsResult.energy_loss_mwh` retains its original meaning:
  purchased energy minus delivered energy, i.e. total reduction. It is not the
  new physical-loss figure and it is not monetized.

### Economics-only path

`compute_lng_economics_only(LngEconomicsOnlyInput) -> LngEconomicsOnlyResult`

- Model version: `lng-economics-only/v1`; the result always carries this actual
  implementation version, never a caller-supplied string.
- No `LngRegasScenario` field exists on `LngEconomicsOnlyInput`.
- The regas readiness assessor is never called by this path.
- The result has no `readiness` field. It explicitly states:

  - `physical_readiness = "NOT_ASSESSED"`
  - `readiness_assessed = False`
  - `research_only = True`
  - `human_review_required = True`

- A mandatory warning states that profitable economics is not delivery
  feasibility, terminal/slot/storage rights or nomination authority.
- `LngEconomicsOnlyError` propagates stable cash-primitive and energy-balance
  refusal codes unchanged.

## Shared monetary implementation

Both public paths call the same private `_compose_cargo_economics` helper. It
contains the only implementation of:

- purchase outlay, sale proceeds and itemized total-cost formulas;
- `0.0001` / `ROUND_HALF_EVEN` quantization in an explicit local decimal context;
- unit netback and separate delivered sale basis;
- cargo margin, reconciliation gap and declared tolerance;
- cash amount magnitude bounds;
- zero-leg omission and disclosure;
- cash-leg construction and delegation to the existing
  `compute_lng_cargo_cash_valuation` / shared `cash_valuation` engine.

The helper consumes structural economic fields and already validated cash
items. It does not assess physical readiness and does not construct fake
physical evidence. The new path does not reimplement any monetary arithmetic.

## Explicit energy stages

`LngEnergyBalanceInput` contains purchased energy, delivered energy, one declared
energy-basis reference, an explicit `MWh` unit and an ordered tuple of
`LngEnergyStage` values. Each stage carries:

- unique `stage_id` and a declared `LngEnergyStageKind`;
- exact finite `Decimal` input, output, consumed and physical-loss MWh;
- non-empty source references.

Validation is deterministic and exact:

- stage count is bounded at 32;
- magnitude is bounded at `1e12` MWh; non-zero amounts are at least `1e-12` MWh;
- coefficient width is limited to 34 digits and decimal exponent to `[-64, 64]`
  before conservation arithmetic;
- input and output are positive; consumed and physical loss are nonnegative;
- int, float, bool and non-finite values are refused, never coerced;
- each stage must satisfy exactly
  `input = output + consumed + physical_loss`;
- stages must be exactly adjacent (`previous.output == next.input`);
- the first stage input must equal purchased energy and the final stage output
  must equal delivered energy;
- total reduction (`purchased - delivered`) must equal total consumed plus total
  physical loss.

No conservation difference is quantized away. No stage, fuel percentage,
loss, volume conversion or FX rate is inferred. A one-stage chain with explicit
zero consumption and zero loss is valid; an omitted stage or omitted loss is not
treated as zero.

The result reports `total_consumed_energy_mwh`, `physical_loss_energy_mwh` and
`total_reduction_energy_mwh` separately. Neither consumed nor lost energy is
added to cash costs or monetized automatically.

## Costs and in-kind charges

The economics-only cost type is `LngEconomicsOnlyCostInput`. It requires an
explicit `charge_basis` in addition to the existing item fields:

- `INVOICED_CASH` is accepted and produces exactly one cash leg;
- `IN_KIND` is refused as a cash charge because consumed/lost energy belongs in
  the explicit energy stages;
- `UNKNOWN` or a non-enum value is refused.

Provenance (`source_reference`) remains mandatory. Included purchase-cost
categories cannot be itemized again; duplicate cost ids, purchase/sale leg
categories and duplicate included categories are refused using the existing
checks. Sell and purchase prices may be negative or zero; zero legs are omitted
with disclosure. EUR is the only supported reporting currency.

## Synthetic golden

Inputs:

- purchased 100 MWh at EUR20/MWh;
- delivered 90 MWh sold at EUR30/MWh;
- one separately invoiced EUR150 downstream cost, paid at the valuation date;
- purchase paid at the valuation date; sale paid on an explicit future date with
  explicit discount factor 0.975.

Monetary result:

| Item | EUR |
| --- | ---: |
| purchase outlay | 2,000.00 |
| sale proceeds | 2,700.00 |
| downstream cash cost | 150.00 |
| cargo margin / undiscounted cash | 550.00 |
| NPV | 482.50 |

Energy stages:

1. 100 -> 96, consumed 3, physical loss 1
2. 96 -> 90, consumed 4, physical loss 2

Totals: consumed 7 MWh, physical loss 3 MWh, total reduction 10 MWh.
`physical_readiness` remains `NOT_ASSESSED`; no terminal, slot, right or
readiness evidence exists in this example.

A separate test builds an independently valid legacy `LngRegasScenario` and
compares the economics-only monetary fields and cash leg valuations with the
preserved strict path. The legacy golden test file is unchanged.

## Validation evidence

- `tests/domain/research/test_lng_cargo_economics.py` — existing strict-path
  tests, unchanged.
- `tests/domain/research/test_lng_energy_balance.py` — explicit stages,
  conservation, adjacency, duplicates, missing/zero/negative/non-finite/float/
  huge/tiny/exponent cases, unsupported units and versions, and ambient decimal
  context isolation.
- `tests/domain/research/test_lng_economics_only.py` — never-calls-readiness
  guard, strict missing-readiness refusal, golden margin/NPV, loss versus
  consumption separation, strict-path monetary parity, signed prices, zero-leg
  disclosure, duplicate/in-kind/unknown charge refusals, discount/date refusals,
  source provenance and ambient context isolation.

## Deliberately not included

- No API route, Python SDK method, Web client transport, page, store slice or
  browser workflow. Those are next integration work and require their own
  authentication, permission, wire-contract and UI gates.
- No official terminal, slot, storage, TSO, fuel-retention or nomination data
  reference is resolved or certified. Callers supply all references.
- No physical-readiness result is inferred. The explicit `NOT_ASSESSED` status
  is not a successful readiness assessment and does not authorize delivery,
  nomination or settlement.
- No persistence, audit record, provider lookup, FX conversion, volume
  conversion, market-price lookup or discount-curve construction.
- No trade execution, order entry, nomination or settlement semantics.

## Subsequent API/SDK/Web integration evidence

The additive sandbox route `POST /api/research/lng-economics-only` and typed SDK
now consume this single domain authority. Existing Contracts workbench includes
an EN/zh-CN form with explicit stage, cost and discount rows and exact readback.
Independent API/SDK/census selection:33pass; source SDK and distinct-role real
HTTP golden/refusals pass. Actual EN/zh-CN browser golden (margin550 EUR,
NPV482.5 EUR, consumed7MWh/loss3MWh/reduction10MWh), Ctrl+Enter, success focus,
390/1440px overflow, edit invalidation and conservation refusal pass. These are
labelled synthetic inputs, not live provider, booked-right or native acceptance.
Full Web regression after integration:988pass/3existing skips; TypeScript pass.
