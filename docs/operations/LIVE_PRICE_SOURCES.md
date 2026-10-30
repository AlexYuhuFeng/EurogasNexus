# Live hub prices

## Why the product ships no live price feed

European hub prices (TTF, NBP, THE, PEG, ZTP, PSV) are licensed per subscriber by
the venues and the broker platform: ICE Endex, EEX/Powernext and Trayport. No feed
exists that is free, real-time and cleared for commercial use. Free commodity APIs either exclude
commercial use or do not state terms for it, and scraping venue websites breaches
their terms. Eurogas Nexus therefore uses **your** entitlement and never ships
prices.

| Option | Latency | What you need |
|---|---|---|
| **Operator quote import** (available now) | Seconds to minutes | Your Trayport / ICE / EEX screen exported to CSV, once or on a timer |
| Direct Trayport connector | Real time | Trayport API access and documentation from your Trayport account manager; build against their spec |
| ICE / EEX market-data connector | Real time or end of day | A market-data licence and the venue's API credentials |
| EEX public TTF NGP reference index (implemented) | Daily | Display/internal use; redistribution needs an EEX licence |

## Operator quote import

Export the market view you already trade from: a Trayport Joule export, or an
Excel/RTD sheet saved as CSV on a timer. Columns, case-insensitive:

```
Timestamp,Hub,Product,Bid,Ask,Last,Bid Qty,Ask Qty,Unit
2026-10-30T08:59:58Z,TTF,DA,31.575,31.625,,30,25,
2026-10-30T08:59:58Z,NBP,Day Ahead,82.50,82.80,,25000,25000,p/th
2026-10-30T08:59:58Z,TTF,Nov-26,32.10,32.15,,60,60,
```

```bash
python scripts/ops/import_market_quotes.py --source Trayport --file trayport.csv --dry-run
python scripts/ops/import_market_quotes.py --source Trayport --file trayport.csv
python scripts/ops/import_market_quotes.py --source Trayport --file trayport.csv --watch 5
```

- Products use Trayport names: `WD`, `DA`/`Day Ahead`, `WE`, `BOM`, `Nov-26`,
  `Q1-27`, `Sum-27`, `Win-27`, `GY-27`, `Cal-27`. Each is resolved to its gas-day
  delivery window.
- Units: each row's `Unit`, or else the hub's quoting convention (NBP p/th,
  continental hubs €/MWh), overridable with `--nbp-unit`. p/th prices are stored as
  GBP/MWh and therms/day volumes as MWh, with the native values kept in the row's
  metadata.
- A bad row (naive timestamp, unknown hub, crossed bid/ask, expired product) refuses
  the whole file, so a half-imported screen never shows.
- Rows are stored under the licensed family (`Trayport`, `ICE_OCM`, `EEX`). Only users
  with that data-scope grant see them, and the intraday spread scan runs on each import.
- Your Trayport/venue licence governs who inside the company may see these prices.
  Grant the data scope accordingly.

## Simulated sources

`EEX_Sim`, `ICE_OCM_Sim`, `Trayport_Sim` and `ICIS_Sim` generate synthetic numbers for
development and demos. They are disabled in `trial` and `release` environments. When
any simulated price is on the hub board, the board shows a **Simulated prices**
banner. Do not enable them in a deployment that has a real feed.
