# Gas Option Settlements (TTF, NBP, THE)

Status: **current** (delivered 2026-11-26 on `feature/option-prices`). The desk does not trade
options. Option settlements are **indicative evidence** (implied volatility, skew, smile and
positioning) for research and analytics. They are never a quote, never an order and never an
execution venue.

Implementation:

- `src/eurogas_nexus/domain/market/options.py`: Black-76, the implied-vol solver, the smile
  metrics, the ICE Endex TTF expiry rule and source precedence (pure, no I/O)
- `src/eurogas_nexus/ingestion/option_settlements.py`: the licensed-file parser
- `src/eurogas_nexus/ingestion/simulated_option_settlements.py`: the demo simulator
- `src/eurogas_nexus/db/models/option_settlement.py` and migration
  `alembic/versions/0077_option_settlements.py`: the `option_settlements` table
- `src/eurogas_nexus/application/option_surface.py`: per-day source choice and summaries
- `src/eurogas_nexus/api/routes/public/market_options.py`: the read API
- `scripts/ops/import_option_settlements.py` and `scripts/ops/seed_simulated_option_settlements.py`

Tests:

- `tests/unit/test_option_black76.py`
- `tests/unit/test_option_settlements_import.py`
- `tests/unit/test_option_settlements_migration.py`
- `tests/api/test_market_options_api.py`
- `tests/api/test_option_evidence.py`

## 1. Source, licence and cost

There is **no free option-settlement feed** for these products. This connector therefore takes
in a file that the desk licenses and exports itself. It never downloads one. The table below
records what the public documentation pages say. They were read on 2026-11-26; no price page
was opened and nothing was bought or signed up for.

| Source family | Products | Licence and cost (public documentation) |
| --- | --- | --- |
| `ICE_ENDEX` | TTF monthly options (futures-style margin), TTF daily options | ICE Report Center "End of Day Reports": a paid annual subscription covering ICE Endex futures and options, under a data usage agreement (https://ice.com/report-center/data-subscription) |
| `EEX` | THE and TTF futures-styled options | EEX Group DataSource "End of Day Prices": licensed. The internal usage licence is bought through the EEX webshop, fees are per price list, and usage is reported annually (https://www.eex.com/de/market-data/licensing-policies) |
| `CME` | TTF options listed by CME | CME DataMine end-of-day data, licensed. Its premium style was **not verified**, so the file must say it (section 3) |
| `Argus`, `Platts` | vendor assessments | Accepted as a vendor tier, but **no one has verified** that either publishes gas option settlements. Treat these as placeholders until a contract says so |

The public EEX file the app already reads (`TTF_NGP_15_Mins.csv`,
[EEX NGP source contract](EEX_NGP_SOURCE_CONTRACT.md)) holds the NGP index only. It contains no
options.

Product facts used by the parser come from public product and procedure pages:

- ICE Endex TTF options: product 71085679 (European, futures-style margin, €0.50 strikes) and
  product 83049138 (daily options, also futures-style).
- EEX gas options: the EEX Settlement Pricing Procedures v5.36 describe all EEX gas options as
  futures-styled.

**Raw licensed files are never committed.** Fixtures in the tests are synthetic. A licensed
row is readable only by principals that hold that source family's data scope (section 6).

## 2. File layout

The importer takes the CSV that the licensed export produces, one row per strike and call or
put. Headers are matched case-insensitively. Spaces and punctuation are folded to `_`, so
`Trade Date` and `Call/Put` are recognised.

| Column | Required | Meaning |
| --- | --- | --- |
| `trade_date` | yes | `YYYY-MM-DD` |
| `hub` | yes | `TTF`, `NBP`, `THE` or another known gas hub |
| `contract` | yes | a month, quarter, season, gas year or calendar year label (`Jan-27`, `Q1-27`, `Sum-27`) |
| `strike` | yes | positive, in the hub's unit |
| `option_type` | yes | `C`, `Call`, `P` or `Put` |
| `settlement` | yes | the settlement premium, ≥ 0 |
| `expiry` | where no rule is known | `YYYY-MM-DD`. Derived for ICE Endex TTF monthly options (section 4) |
| `underlying` | no | the futures settlement |
| `implied_vol` | no | the exchange's own volatility, in percent |
| `open_interest`, `volume` | no | lots, as published |
| `unit`, `currency` | no | default to the hub's unit (EUR/MWh; NBP GBp/th) |
| `style` | where no rule is known | `futures_style` or `premium` |

**A bad row refuses the whole file**, with a message such as `line 7: strike must be a positive
number`. The same applies to:

- duplicate keys (`first on line N`)
- an underlying that conflicts within one contract
- a mixed expiry, style or unit within one contract
- an expiry before the trade date or after delivery
- negative values
- a non-gas product

Up to 100,000 rows are accepted per file.

## 3. Premium style and discounting

- **Futures-style** (ICE Endex TTF; all EEX gas options): the premium is margined, not paid up
  front, so the discount factor is 1.
- **Premium-paid**: discount factor `exp(-r·T)`. Here `r` is the €STR, SONIA or SOFR fixing for
  the contract currency on the trade date, read from `interest_rate_observations` through
  `resolve_financing_rate`, restated ACT/365F and applied flat over the life of the option. If
  no fixing is stored, the row is stored without a volatility and with reason
  `no_discount_rate`.
- Where no rule is documented (CME, vendors), the file must carry `style`.

## 4. Expiry, underlying and implied volatility

- **Expiry, ICE Endex TTF monthly options**: 5 calendar days before the delivery month, moved
  back to the previous business day. If that day is also the futures expiry, it moves back one
  more business day. The importer knows weekends only, so pass exchange holidays where they
  matter, or carry `expiry` in the file.
- **Time to expiry**: ACT/365F from the trade date to the expiry date.
- **Underlying**, first available of:
  1. the file's `underlying` column
  2. the stored futures settlement for that hub, contract and day (in the hub's native unit)
  3. the median of `K + (C − P)/DF` over the strikes that have both a call and a put
- **Implied volatility**: Black-76, solved by Newton's method with a bisection safeguard on
  vol ∈ [0.1 %, 1000 %]. A price outside the no-arbitrage bounds gets no volatility and a
  reason: `below_intrinsic`, `at_intrinsic`, `above_upper_bound`, `expired`, `bad_input` or
  `vol_out_of_range`.
- **Exchange volatility**: when the file carries `implied_vol`, that value is stored. The
  solved value is kept in `metadata_json.solved_iv`. A difference above 2 vol points is
  reported as an import warning.

## 5. Smile metrics

These are computed per source, hub, contract and trade date. A smile is **never mixed** across
sources.

- **ATM IV**: ATM-forward volatility, interpolated linearly in strike between the strikes that
  bracket the underlying. There is no extrapolation.
- **Smile points**: each strike takes the out-of-the-money option's volatility (puts below the
  underlying, calls at or above it).
- **25Δ call and 25Δ put**: the delta is the undiscounted forward delta `N(d1)`. The 25Δ call
  is at call delta 0.25 and the 25Δ put at call delta 0.75, each interpolated linearly in
  delta.
- **RR25** = 25Δ call − 25Δ put, and **BF25** = (25Δ call + 25Δ put)/2 − ATM, in vol points.
- **Put/call OI ratio** = Σ put open interest / Σ call open interest.
- A metric the strikes cannot support is `null`, with its reason (for example
  `strikes_do_not_reach_25_delta` or `open_interest_not_published`).

## 6. Precedence, provenance and entitlement

1. **Entitlement first.** Rows are filtered by `filter_entitled_rows` before anything is
   compared. The simulator `ICE_ENDEX_Sim` maps to the `ICE_ENDEX` family, so it is gated by the
   same scope.
2. **Then precedence**, per hub, contract and day: exchange settlement (`ICE_ENDEX`, `EEX`,
   `CME`) over licensed vendor (`Argus`, `Platts`) over simulated (`*_Sim`). Within a tier the
   source with more strikes wins, then the alphabetically first name.
3. **Provenance**: every response names the chosen source, its tier, whether it is simulated,
   when it was received, and the alternatives that were not chosen. Every stored row keeps its
   `source_reference`, `source_record_id`, `underlying_basis`, `iv_basis` and pricing metadata.

Export of licensed option rows is denied (fail-closed), because `ICE_ENDEX` and `CME` are not
yet in `COMMERCIAL_SOURCE_FAMILIES`.

## 7. Simulated demo series

`scripts/ops/seed_simulated_option_settlements.py --days N` writes `ICE_ENDEX_Sim` rows. The
script only runs where `simulated_sources_allowed()` permits it. The simulator:

- writes TTF only, for four monthly contracts, ±12 strikes at €0.50, on business days only
- prices a synthetic futures level and smile with Black-76, rounded to the €0.005 tick
- flags every row `simulated: true` with freshness `simulated_daily` and a `sim:` source
  reference, and every API response carries a simulated-data warning

**These rows are not market prices.** They exist so that the screens and the dataset builder
can be exercised without a licence.

## 8. Using it

- **Import**: `python scripts/ops/import_option_settlements.py --source ICE_ENDEX --file
  eod_options.csv --source-reference "ICE Report Center EOD 2026-11-25"`. Add `--dry-run` to
  validate without writing. Rows are upserted on the natural key, and an ingestion run is
  recorded.
- **API** (entitlement-gated):
  - `GET /api/market/options/surface?hub=TTF&trade_date=YYYY-MM-DD` returns each contract's
    chosen source, its strikes and its metrics.
  - `GET /api/market/options/metrics?hub=TTF&tenor=M1&days=60` returns a daily series of ATM
    IV, RR25, BF25 and the put/call OI ratio for the rolling front month (`M1` to `M6`, by
    delivery among unexpired monthly contracts).
- **Dataset builder**: the series `options.<atm_iv|rr25|bf25|pc_oi_ratio>.<HUB>.M<n>`. The
  catalogue seeds the TTF M1 series and these features:
  - `TTF_OPT_ATM_IV_M1` and `TTF_OPT_ATM_IV_M1_CHG1` (day-on-day change)
  - `TTF_OPT_RR25_M1`
  - `TTF_OPT_BF25_M1`
  - `TTF_OPT_PC_OI_M1`

  Each value is observed at 18:00 UTC on the trade date and becomes available when it is
  received. It is approximate rather than certified, because the export carries no publication
  time.
- **Demo data in a dataset**: the default point-in-time policy refuses simulated data.
  Simulated option values enter only when `allow_simulated` is true, and are then marked
  `SIMULATED`. Under the standard 1-hour carry, weekend origins stay missing; they are not
  filled.

## 9. Limitations and follow-ups

- **NBP**: NBP options are an ICE Futures Europe product. They are imported under the
  `ICE_ENDEX` family for now, with an explicit `expiry` and `style`, until an ICE Futures Europe
  family is registered.
- **Vendor tier**: `Argus` and `Platts` are unverified, as noted in section 1.
- **Holidays**: the expiry rule knows weekends only.
- **Discounting**: a flat overnight fixing stands in for the term rate.
- **Model**: European Black-76 only. The model has no early exercise and no American options.
- **Data products and export**: no data product is defined in
  `domain/data_platform/products.py` yet. That needs `ICE_ENDEX` and `CME` in
  `COMMERCIAL_SOURCE_FAMILIES` first.
- **Web view**: none yet. The API is ready for one.
