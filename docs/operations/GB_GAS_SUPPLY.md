# GB storage and LNG (National Gas data portal)

What it loads: Great Britain storage stock, storage withdrawal and injection, LNG tank
stock and LNG send-out into the NTS, one row per gas day, in TWh. Storage goes to
`storage_observations` (facility `GB-NTS-STORAGE`), LNG to `lng_observations` (terminal
`GB-NTS-LNG`), both with `country = 'GB'` and `source_system = 'NATIONAL_GAS'`. GIE
AGSI/ALSI publish GB rows with no values; these rows fill that gap. The NW Europe balance
(`/api/market/nwe-balance`) picks them up by country.

Source: `https://data.nationalgas.com/api/find-gas-data-download`, CSV, no account or key,
one request for all items. Open data; attribute National Gas Transmission. Values are kWh.

| id | Data Item | stored as |
|---|---|---|
| PUBOBJ330 | Storage, Daily Aggregated Stock level, D+1 | storage `inventory_twh` |
| PUBOBJ336 | LNG, Daily Aggregated Stock level, D+1 | LNG `inventory_twh` |
| PUBOBJ517 | Allocations, Energy, Storage Entry Total, D+2 | storage `withdrawal_twh_d` |
| PUBOBJ521 | Allocations, Energy, Storage Exit Total, D+2 | storage `injection_twh_d` |
| PUBOBJ518 | Allocations, Energy, LNG Importation Total, D+2 | LNG `send_out_twh_d` |
| PUBOBJ1149 | Nominations, Aggregate Prevailing Nomination, Storage Entry Total | provisional withdrawal |
| PUBOBJ1155 | Nominations, Aggregate Prevailing Nomination, Storage Exit Total | provisional injection |
| PUBOBJ1150 | Nominations, Aggregate Prevailing Nomination, LNG Importation Total | provisional send-out |

## Rules

- **Stock label shift.** The two "Stock level, D+1" items are labelled with the
  publication day. Applicable For X is the closing stock of gas day X-1 and is stored on
  X-1. Check: storage stock fell 437.6 GWh between the labels 10/11 and 11/11/2026; the
  storage entry allocation for gas day 10/11 was 437.3 GWh.
- **Allocation first, nomination provisional.** The D+2 allocation is used when
  published. Before that, the end-of-day prevailing nomination (published D+1 04:00) is
  used and the field's basis is `nomination_provisional`; `metadata_json.provisional` is
  true. Nominations tracked allocations within about 0.1%. A nomination applicable on
  the gas day itself is within-day and is never used.
- **Send-out is importation into the NTS**, not the LNG inflow/outflow items (those are
  net tank change and include cargo unloading).
- `metadata_json` records, per field, the basis (`allocation`, `nomination_provisional`,
  `stock_level_d_plus_1`), the publication id, the Applicable At and any quality flag.
- An unknown Data Item label or a header change fails the run.

## Running

```bash
# Dry run: parse and print the last 7 completed gas days
python scripts/ops/ingest_national_gas_supply.py
# Store the last 10 completed gas days
python scripts/ops/ingest_national_gas_supply.py --days 10 --commit
```

Re-running is safe and is how values firm up: rows are upserted by `observation_id`, so a
nomination-based value is replaced by the allocation and stock published later fills in.
`observed_at_utc` keeps the first time the gas day was seen. The scheduler runs it every
3 hours over the last 5 gas days (source `src-national-gas-supply`, enabled by default).

## Limits

- No working capacity is published, so there is no GB fill percentage. The balance's
  inventory and fill use only facilities that publish a working capacity; GB stock is
  not in them.
- Allocations are D+2; the latest day is nomination-based until then. Stock is D+1
  afternoon, so the latest gas day often has flows but no stock.
- The balance sums a day only when every reporting storage/LNG source has it, so the GB
  days that arrive before GIE's do not show until GIE catches up.
- GB is one aggregate per table, not per site.
