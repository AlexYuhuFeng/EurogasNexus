# Shared Cash Valuation Capability

Status: implemented bounded capability (decision-support boundary), 2026-09-30.
Source: [src/eurogas_nexus/domain/research/cash_valuation.py](../../src/eurogas_nexus/domain/research/cash_valuation.py)

This is the descriptive capability note for the shared calculation. It does not
redefine the code contract; repository code and tests remain the source of
truth for current behaviour.

## Purpose and single implementation

`cash_valuation.py` is the repository's one implementation of the dated cash
valuation primitive: explicit signed cash-flow legs -> explicit per-leg FX into
one reporting currency -> explicit per-payment-date discount factors -> total
undiscounted cash and net present value. It owns:

- the `Decimal`-only arithmetic and the 0.0001 / ROUND_HALF_EVEN quantization,
  independent of the ambient decimal context;
- the deterministic refusal codes carried by `CashValuationError.codes`;
- the cash-flow-leg vocabulary `CashFlowLegCategory` (single reviewed
  definition; the ontology review entry lives in
  [test_domain_enum_ontology_gate.py](../../tests/contract/test_domain_enum_ontology_gate.py)).

Business modules must not re-implement any of this. The LNG adapter
(`domain/research/lng_cash_valuation.py`) and the cargo economics composition
(`domain/research/lng_cargo_economics.py`) delegate to this engine.

## Inputs and outputs

- `CashValuationInput`: `business_context` (non-empty tuple of `CanonicalId`
  references), `valuation_date`, `reporting_currency`, signed dated `legs`
  (`CashValuationLegInput`), explicit per-date `discount_factors`
  (`CashValuationDiscountFactorInput`) and `model_version`.
- `CashValuationResult`: echoed context/date/currency, per-leg
  `CashValuationLegValuation` (cash amount, present value and the applied FX
  and discount provenance), `total_undiscounted_cash_reporting_ccy`,
  `net_present_value_reporting_ccy`, assumptions, warnings, sorted
  `source_references`, `lineage`, `research_only`, `human_review_required`.
- Version: `cash-valuation/v1` (lineage token `cash-valuation`).

## Boundaries and refusals

- Future cash only: past-dated legs and past-dated discount factors are
  refused; DF(valuation date) must be exactly 1.
- FX exists only as an explicit `rate_reporting_per_leg` with source and as-of;
  rates are never defaulted and same-currency legs must not carry FX.
- Discount factors exist only as explicit per-date inputs with curve, source
  and as-of provenance; no curve, day-count convention or source is inferred.
- No market/FX/curve provider is called and no entitlement or default grant is
  introduced.
- Amounts, rates and factors are `Decimal` only; floats, ints, booleans and
  strings are refused instead of converted.
- Outputs are "undiscounted cash" and "NPV" only: never netback,
  mark-to-market, margin, accounting, custody or settlement.
- The result is always `research_only=True` and `human_review_required=True`.

## Ontology reuse and boundary

Reused ontology surface:

- `CanonicalId` (`domain/ontology/semantic_kernel.py`) carries the typed
  business context (`concept:value`) without creating a datastore, table or
  graph; duplicate references and plain strings are refused.
- `ActionKind.COMPUTE_CASH_FLOW` (`ANALYTICAL`) is the existing action-taxonomy
  entry for this calculation; nothing new was added to the action vocabulary.
- `CashFlowLegCategory` reuses the value strings of the reviewed research cost
  taxonomy (`fuel`, `transport`, `regas`, `storage`, `other`) and adds only the
  cargo cash categories that taxonomy does not cover.

Documented boundary (deliberately not reused):

- `Money.amount`, `PriceBasis` and `FxConversionRef.rate` are `float`-based;
  routing the exact `Decimal` cash arithmetic through them would be lossy, so
  the engine keeps `Decimal` fields and references the semantic kernel only
  through `CanonicalId`. Reconciling that boundary belongs to a later audited
  API integration.

Open gaps for future audited API integration:

- `domain/research/ontology.py::CanonicalEntityType` has no cargo (LNG cargo)
  entity class; the LNG adapter therefore carries `cargo_id` as
  `CanonicalId("cargo", ...)`. Adding that entity class is an ontology-review
  decision.
- No API route, persistence, scheduler or live source is wired: the capability
  is a pure domain function and must pass through the existing
  permission/entitlement gates when an application surface is added.
- The capability composes only caller-supplied values; it does not resolve
  market prices, FX or discount curves, and it is not an accounting or
  settlement figure.

## Business adapters

| Adapter | Business-context mapping | Model version / lineage | Notes |
| --- | --- | --- | --- |
| `domain/research/lng_cash_valuation.py` | `contract_id` -> `CanonicalId("contract", ...)`, `cargo_id` -> `CanonicalId("cargo", ...)`, `terminal_id` -> `CanonicalId("terminal", ...)`, `resource_id` -> `CanonicalId("resource", ...)` | `lng-cargo-cash-valuation/v1`, lineage `lng-cargo-cash-valuation` | Validates the four mandatory LNG references first, then delegates; contains no arithmetic; maps the shared result back to the original LNG dataclasses, model version, lineage and assumptions. |
| `domain/research/lng_cargo_economics.py` | Composes the LNG adapter with the existing regas readiness assessor; EUR-only | `lng-cargo-economics/v1` | Explicit energy/price/cost composition; the cash primitive remains the single validating implementation of discounting. |

## Validation evidence

- `tests/domain/research/test_cash_valuation.py` — a pipeline/portfolio and a
  storage context value the same hand-calculated schedule without any LNG
  identifier (undiscounted cash 10, NPV 4.5); changing the business context
  does not alter the arithmetic; refusal, provenance, determinism and
  single-implementation checks.
- `tests/domain/research/test_lng_cash_valuation.py` — the unchanged LNG cases
  plus adapter re-export, mandatory-reference, result-mapping and
  error-compatibility tests.
- `tests/domain/research/test_lng_cargo_economics.py` — the composition is
  unchanged.

Ownership: [Module Ownership Matrix](MODULE_OWNERSHIP_MATRIX.md).
