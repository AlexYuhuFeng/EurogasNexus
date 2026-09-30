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
- The sandbox API route below exists; no persistence, scheduler, live source,
  audit record or UI/screen surface is wired. A typed web client transport
  method exists (see below); it carries no page, component, store slice or
  browser-stored input. The route is a pure function of its request and must
  keep passing the existing permission/entitlement gates.
- The capability composes only caller-supplied values; it does not resolve
  market prices, FX or discount curves, and it is not an accounting or
  settlement figure.

## API surface — `POST /api/research/cash-valuation` (sandbox-only)

The capability is reachable through the existing research sandbox route
(`src/eurogas_nexus/api/routes/public/research.py`). The route contains no
arithmetic: it reads the wire contract, delegates to
`compute_cash_valuation`, and serializes the engine result (Decimals as exact
strings, dates as ISO dates — no float encoder). It is covered by the existing
global gates: authentication, the `GOVERNED` (ANALYST floor) permission of the
`/api/research/` family and the commercial-data boundary. A persona or
work-mode value in the request is not part of the contract (unknown fields are
refused) and can never raise what a caller may do.

Exact request (every decimal is a string; a JSON number is refused):

```json
POST /api/research/cash-valuation
{
  "business_context": ["portfolio:portfolio-synthetic-1", "pipeline:pipeline-synthetic-1"],
  "valuation_date": "2026-09-29",
  "reporting_currency": "EUR",
  "legs": [
    {
      "leg_id": "supply-purchase-1",
      "category": "other",
      "payment_date": "2026-09-29",
      "signed_amount": "-100",
      "currency": "EUR",
      "source_reference": "synthetic-test-input:purchase-1"
    },
    {
      "leg_id": "hub-sale-1",
      "category": "other",
      "payment_date": "2026-11-30",
      "signed_amount": "150",
      "currency": "USD",
      "source_reference": "synthetic-test-input:sale-1",
      "fx": {
        "rate_reporting_per_leg": "0.8",
        "source_reference": "synthetic-test-input:fx-1",
        "as_of": "2026-09-28"
      }
    },
    {
      "leg_id": "storage-cost-1",
      "category": "storage",
      "payment_date": "2026-12-31",
      "signed_amount": "-10",
      "currency": "EUR",
      "source_reference": "synthetic-test-input:storage-1"
    }
  ],
  "discount_factors": [
    {
      "payment_date": "2026-09-29",
      "factor": "1",
      "curve_reference": "synthetic-test-curve:eur-usd-flat",
      "source_reference": "synthetic-test-input:df-1",
      "as_of": "2026-09-29"
    },
    {
      "payment_date": "2026-11-30",
      "factor": "0.95",
      "curve_reference": "synthetic-test-curve:eur-usd-flat",
      "source_reference": "synthetic-test-input:df-1",
      "as_of": "2026-09-29"
    },
    {
      "payment_date": "2026-12-31",
      "factor": "0.95",
      "curve_reference": "synthetic-test-curve:eur-usd-flat",
      "source_reference": "synthetic-test-input:df-1",
      "as_of": "2026-09-29"
    }
  ]
}
```

Exact response (`200`; abbreviated per-leg block shown for the sale leg):

```json
{
  "data": {
    "research_only": true,
    "human_review_required": true,
    "model_version": "cash-valuation/v1",
    "action": "compute_cash_flow",
    "business_context": ["portfolio:portfolio-synthetic-1", "pipeline:pipeline-synthetic-1"],
    "valuation_date": "2026-09-29",
    "reporting_currency": "EUR",
    "leg_valuations": [
      {
        "leg_id": "hub-sale-1",
        "category": "other",
        "payment_date": "2026-11-30",
        "currency": "USD",
        "signed_amount": "150",
        "cash_amount_reporting_ccy": "120.0000",
        "present_value_reporting_ccy": "114.0000",
        "discount_factor": "0.95",
        "discount_curve_reference": "synthetic-test-curve:eur-usd-flat",
        "discount_source_reference": "synthetic-test-input:df-1",
        "discount_as_of": "2026-09-29",
        "source_reference": "synthetic-test-input:sale-1",
        "fx_rate_reporting_per_leg": "0.8",
        "fx_source_reference": "synthetic-test-input:fx-1",
        "fx_as_of": "2026-09-28",
        "description": ""
      }
    ],
    "total_undiscounted_cash_reporting_ccy": "10.0000",
    "net_present_value_reporting_ccy": "4.5000",
    "assumptions": ["..."],
    "warnings": [
      "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
      "NPV_IS_NOT_NETBACK_MARK_TO_MARKET_OR_MARGIN"
    ],
    "source_references": [
      "synthetic-test-input:df-1",
      "synthetic-test-input:fx-1",
      "synthetic-test-input:purchase-1",
      "synthetic-test-input:sale-1",
      "synthetic-test-input:storage-1"
    ],
    "lineage": ["cash-valuation", "cash-valuation/v1"]
  },
  "meta": {
    "research_only": true,
    "human_review_required": true,
    "decision_context": "SANDBOX_SCENARIO",
    "caller_supplied": true,
    "references_verified": false,
    "customer_approval": false,
    "source_references": ["..."],
    "warnings": ["..."]
  }
}
```

Wire-contract rules and refusals:

- `business_context` entries are canonical `concept:value` strings, echoed
  back exactly. The backend never looks up, resolves, infers or entitles a
  reference; `meta.references_verified` is always `false`, and a fabricated
  reference values exactly like any other (this is a declaration of context,
  not an entity authority).
- Decimals must be plain decimal strings. A JSON number is refused by the
  request contract itself (`string_type`), and exponent notation, whitespace,
  underscores and non-finite `NaN`/`Infinity` text are refused with
  `422 cash_valuation_input_invalid` / `DECIMAL_STRING_INVALID`; dates must be
  `YYYY-MM-DD` (`DATE_STRING_INVALID`); categories must be declared
  `CashFlowLegCategory` values (`LEG_CATEGORY_INVALID`).
- Engine-level refusals (unsupported model version, missing/zero amounts,
  duplicates, past-dated flows, missing discount factors, FX direction,
  missing provenance, non-finite or out-of-range values) answer
  `422 cash_valuation_refused` with the engine's stable codes in
  `detail.codes` / `detail.violations`. Nothing is computed on refusal.
- Unknown request fields are refused (`extra="forbid"`), so `research_only`,
  `customer_approval`, persona or work-mode claims cannot be smuggled into a
  request the backend would otherwise ignore.

Limitations (explicit):

- No persistence, no database lookup, no provider/FX/curve fetch, no audit
  record, no scheduler and no UI surface is wired; the response carries no
  wall-clock field, so equal requests produce equal payloads.
- The output is undiscounted cash and NPV only — never netback,
  mark-to-market, margin, accounting, custody, approval, trade, nomination or
  settlement. `meta.customer_approval` is always `false`.

## Client transport (web) — foundation only

`clients/web/src/api/client.ts` carries the typed web transport:
`api.cashValuation(body, options)` posts to `/api/research/cash-valuation`
through the existing `post` helper, so auth headers, the base URL, the
`ApiError` envelope and the research conventions are the same as every other
call. `CashValuationRequestDTO`, `CashValuationLegInputDTO`,
`CashValuationFxInputDTO`, `CashValuationDiscountFactorInputDTO`,
`CashValuationResultDTO`, `CashValuationLegValuationDTO` and the
`CashValuationMetaDTO` envelope keep every amount, FX rate, discount factor,
total and present value a `string` in both directions. No client code parses
one, converts one to `number` or performs cash arithmetic; the leg-category
union mirrors the engine's declared vocabulary.

The request composes no `decision_context` claim. The sandbox dependency
refuses a `RUNTIME_DECISION` claim in the raw body, and the request contract
forbids the field entirely (`extra_forbidden`) — even the truthful
`SANDBOX_SCENARIO` value would be refused — so none is sent. The response's
`meta.decision_context` is what labels the run, always `SANDBOX_SCENARIO`,
beside `references_verified: false` and `customer_approval: false`.

What is deliberately **not** present yet: any page, panel or form, any store
slice or workflow, any persisted audit/customer record, any browser-stored
cash input, and any draft-to-request validation helper. The parent reviews the
authenticated UI before any visual change, and the backend remains the sole
numerical engine.

Validation: `clients/web/tests/cashValuationTransport.test.ts` drives the real
`api/client.ts` module over a stubbed `fetch` (the existing
`tests/support/apiStoreHarness.ts` loader): exact decimal strings beyond
JavaScript's safe integer range survive the request and response as raw text,
the sandbox context is sender-free and response-labelled, a typed refusal
rejects as `ApiError` with the engine's `codes`, transport failures still
reject, and the method composes no authority/persona field and writes nothing
to browser storage.

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
- `tests/api/test_research_cash_valuation_api.py` — the HTTP contract: golden case
  cash 10 / NPV 4.5 over exact strings, no-float payload, JSON-number refusal,
  missing fields, bounded lists, runtime-decision and authority-claim refusal,
  typed wire/engine refusals, provenance echo, fabricated-reference
  non-resolution, and the anonymous/role/commercial auth boundaries in which a
  persona claim never grants access.

Ownership: [Module Ownership Matrix](MODULE_OWNERSHIP_MATRIX.md).
