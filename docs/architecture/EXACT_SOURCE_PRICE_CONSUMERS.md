# Exact Source Price Consumers

Status: **current bounded implementation** (2026-10-27). Scope: EEX TTF NGP
reference-index rows that already carry retained exact decimal metadata.

## 1. Problem

The EEX NGP adapter parses `IndexValue` and `IndexVolume` as `Decimal`, but the
canonical `market_observations.price` column is a `Float`. It therefore preserves
the operator-published strings in `metadata_json.index_value_exact` and
`metadata_json.index_volume_mwh_exact` while the persisted numeric field is the
rounded binary value.

Before this slice no downstream consumer read those strings. Normalization
converted `price` as a float, and strategy research had only the float columns.
A high-precision published index could therefore lose digits before any
research arithmetic without any payload saying so.

Implementation: [`source_price.py`](../../src/eurogas_nexus/domain/market_intelligence/source_price.py).
The parser and its source/rights/calendar refusals are unchanged:
[`eex_ngp.py`](../../src/eurogas_nexus/ingestion/eex_ngp.py) and
[`EEX_NGP_SOURCE_CONTRACT.md`](../data/EEX_NGP_SOURCE_CONTRACT.md).

## 2. Actual caller shape

The repository already selects `MarketObservationRecord` rows and builds
`MarketObservationInput` for normalization. The exact authority needs both the
row identity and the retained metadata:

| Source | Fields |
| --- | --- |
| `market_observations` row | `source_system`, `source_reference`, `source_record_id`, `price`, `unit`, `currency`, `metadata_json` |
| `metadata_json` (EEX NGP) | `source_system`, `source_reference`, `source_dataset`, `index`, `contract_type`, `price_type`, `executable_quote`, `simulated`, `index_value_raw`, `index_value_exact`, `index_volume_raw`, `index_volume_mwh_exact` |

The repository now passes the row-level identity into
`MarketObservationInput`; previously only the price, unit, currency, times and
metadata were forwarded. No DB migration is needed: the exact evidence is already
inside the existing JSON column.

## 3. Validation authority

`resolve_source_price(...)` is the one bounded authority. It returns a
`SourcePrice` with a stable status:

| Status | Meaning |
| --- | --- |
| `exact` | Canonical EEX NGP identity and a validated exact decimal. |
| `legacy_float` | Ordinary non-EEX row; float path retained with explicit legacy provenance. |
| `missing` | EEX NGP row with no exact metadata; normalized GBP price is not produced. |
| `invalid` | A claimed exact payload contradicts identity, raw text, volume or numeric price; normalized GBP price is not produced. |

A value becomes `exact` only when all of these hold:

1. The row is `source_system="EEX"` with
   `source_reference="eex-ttf-ngp-15-mins"`.
2. Metadata names the same source, reference and `ttf-ngp-15min` dataset, plus
   `index="NGP"`, `contract_type="index"`, `price_type="index"`,
   `executable_quote=false` and `simulated=false`.
3. The row unit is `EUR/MWh` and currency `EUR` when those fields are supplied.
4. `index_value_exact` and `index_value_raw` are both strings, both plain finite
   decimals, bounded in length/coefficient/adjusted exponent, and numerically
   equal.
5. When either volume key is present, both volume strings are validated the same
   way, agree, and the exact volume is positive. If neither volume key is
   present, the price can still be exact and the row reports
   `source_price_volume_status = missing`; a partial volume claim is invalid.
6. The canonical float equals `float(index_value_exact)`. A mismatch means the
   numeric JSON and the exact claim are not the same evidence.

The exact and raw strings are returned verbatim. No code path calls
`str(float)` to manufacture an exact value. Signed values are accepted because
the published index can be negative; zero/missing volume is not turned into a
zero price.

Stable refusal codes include `exact_source_identity_mismatch`,
`exact_metadata_source_mismatch`, `exact_metadata_reference_mismatch`,
`exact_metadata_dataset_mismatch`, `exact_metadata_not_reference_index`,
`exact_metadata_executable_quote_claim`, `exact_decimal_not_string`,
`exact_decimal_not_plain`, `exact_decimal_too_long`,
`exact_decimal_exponent_out_of_bounds`, `exact_raw_mismatch`,
`exact_numeric_price_mismatch`, `exact_volume_mismatch` and
`exact_volume_not_positive`. A missing exact claim is
`exact_source_price_missing`.

## 4. Normalization output

[`normalized_view.py`](../../src/eurogas_nexus/domain/market_intelligence/normalized_view.py)
keeps the existing float fields and adds evidence/provenance fields:

- `source_price_status`, `source_price_exact`, `source_price_raw`;
- `source_price_volume_mwh_exact`, `source_price_volume_raw`,
  `source_price_volume_status`;
- `source_price_provenance`, `source_price_issue`,
  `source_price_issue_detail`;
- `source_price_source_system`, `source_price_source_reference`,
  `source_price_source_dataset`;
- `price_float_provenance`, `price_semantics`, `executable_quote`.

The normalized row also carries `metadata_json`, already exposed by the
repository, so the verbatim source evidence remains available even when a
consumer only receives the normalized payload.

`price` remains the canonical float. A validated exact source value is used as a
`Decimal` before conversion to the existing `price_gbp_mwh` float. The FX rate
graph is still float-valued; each rate enters the Decimal calculation as its
exact binary value, but the result is labelled
`exact_source_decimal_times_float_fx_approximation` because the rate itself is a
float. It is never called an exact GBP price. `price_gbp_mwh_exact` is populated
only for a same-currency exact value, where no FX approximation enters the
arithmetic.

A missing or invalid EEX exact claim produces `price_gbp_mwh = null` plus the
issue code and a view warning. It does not silently use the float price. An
ordinary non-EEX row keeps its previous float conversion and reports
`source_price_provenance = legacy_float_approximation`.

The local conversion context is explicit (precision and exponent range), so a
caller's hostile ambient `Decimal` precision/traps cannot change the result or
make normalization raise.

## 5. Strategy research adapter

[`price_series.py`](../../src/eurogas_nexus/domain/strategy_lab/price_series.py)
now exposes `source_price_for_series(row)` and
`exact_source_price_decimal(row)`. They apply the same authority to a stored or
normalized row, so research can obtain the validated `Decimal` and its
provenance before financial arithmetic. The existing evidence-name helpers are
unchanged.

The strategy-lab evaluation models still consume float
`StrategyPriceObservation.price_gbp_mwh`; wiring an exact field through that
separate model/contract would be a follow-on task outside this bounded scope. No
model, route, SDK or Web contract was changed here.

## 6. Non-goals and preserved boundaries

- The NGP value remains a volume-weighted **reference index**, not a bid, ask,
  executable quote, settlement price or order/trade input. No bid/ask fields are
  created; `executable_quote` is `false` for a validated exact index.
- No source entitlement, certification, redistribution, publication-timezone or
  gas-day calendar rule is relaxed or bypassed. The helper reads no rights or
  time fields and the repository continues to return the stored intervals.
- No DB migration, Float-column change or wholesale API contract change. Exact
  evidence is additive strings; the existing approximate fields stay present and
  are labelled.
- The `_route_economics` tariff path, `opportunity_engine`, routes, Web, SDK and
  `research.py` are untouched.
- The parser's own refusal rules remain authoritative: only a canonical,
  fully priced EEX NGP row can ever carry the metadata this authority accepts.

## 7. Validation

Focused tests: [`tests/unit/test_exact_source_price.py`](../../tests/unit/test_exact_source_price.py).
They cover the real parser -> metadata -> normalized/repository consumer path, a
value whose exact digits are visibly lost through float, signed prices, hostile
`Decimal` context, malformed/non-string/NaN/exponent payloads, numeric JSON
instead of a string, forged source identity, contradictory raw/volume/numeric
provenance, missing exact metadata, ordinary non-EEX compatibility, and the
absence of quote/execution inference. Existing normalization, repository and
parser tests are retained.

Run (from the repository root):

```text
python -m pytest -q tests/unit/test_exact_source_price.py tests/unit/test_normalized_market_view.py tests/unit/test_market_intelligence_repository.py tests/ingestion/test_eex_ngp_csv.py
python -m ruff check src/eurogas_nexus/domain/market_intelligence/source_price.py src/eurogas_nexus/domain/market_intelligence/normalized_view.py src/eurogas_nexus/domain/strategy_lab/price_series.py src/eurogas_nexus/db/repositories/market_intelligence.py tests/unit/test_exact_source_price.py
```

The implementation worker could not execute these commands because the local
Harness shell failed its temporary-lock setup; the root session must run them.
No test pass is claimed here until that evidence exists.
