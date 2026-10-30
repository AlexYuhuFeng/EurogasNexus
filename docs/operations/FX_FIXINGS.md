# FX benchmark fixings (ECB, WM/Reuters, Bloomberg BFIX)

Gas and LNG prices are converted with a *named* FX fix. Using a different fix from
the one the contract names leaves a visible difference against the counterparty invoice.

| Source | Fixing id | Fix | Licence | How rows arrive |
|---|---|---|---|---|
| ECB | `reference` | ECB euro reference rate (concertation 14:10 CET) | public | `ingest_public_sources.py` |
| WMR | `WMR_1600_LDN` (default) | WM/Reuters 4pm London closing spot (LSEG) | licensed | operator import |
| WMR | `WMR_1100_LDN` | WM/Reuters 11am London intraday spot | licensed | operator import |
| BFIX | `BFIX_1600_LDN` (default) | Bloomberg BFIX 4pm London | licensed | operator import |
| BFIX | `BFIX_1400_CET` | Bloomberg BFIX 2pm CET | licensed | operator import |

LNG SPAs and cargo confirmations most often name the WM/Reuters 4pm London closing spot
rate, sometimes as the arithmetic average of the daily fixes over the pricing period.
Pipeline desks commonly use ECB.

## Importing a licensed export

The application never fetches WMR or BFIX. Export the fixes from your own entitled
service (LSEG Workspace/DataScope, Bloomberg Terminal/Data License) as CSV with a
date, a pair and a rate column. `Date`/`value_date`, `Pair`/`RIC`/`Ticker` and
`Rate`/`Mid`/`Fix` headers are accepted. RICs such as `EURUSDFIXM=WM` and tickers such
as `EURUSD F160 Curncy` are reduced to their pair. Then run:

```bash
python scripts/ops/import_fx_fixings.py --source WMR --file wmr_4pm.csv --dry-run
python scripts/ops/import_fx_fixings.py --source WMR --file wmr_4pm.csv
python scripts/ops/import_fx_fixings.py --fixing BFIX_1400_CET --file bfix.csv
```

Rows are upserted by (fixing, pair, value date), so re-importing a file is safe. Bad
dates, non-positive rates and duplicate pair/date rows refuse the whole file.

## Entitlement

`WMR` and `BFIX` are commercial source families. A principal sees those rows, in
`/api/market/fx` and in conversions, only with the matching `data_scopes` grant (or
`*`). Grant them only to users your LSEG/Bloomberg licence covers. Redistribution
outside the licence is your organisation's responsibility.

## Using a fix

`GET /api/market/price-conversion?value=10&from_unit=USD/MMBtu&to_unit=EUR/MWh&fx_source=WMR`
uses the latest WMR 4pm fix. Add `fx_date=2026-10-28` for a given day, or
`fx_average_from=2026-10-01&fx_average_to=2026-10-31` for the monthly average: the
per-pair mean of the daily fixes, with EUR crosses taken from the averaged pairs. The
response echoes the fix, the value dates and the number of fixes used.
