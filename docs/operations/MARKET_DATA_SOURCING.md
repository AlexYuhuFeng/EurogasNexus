# Market data sourcing: licensed connectors first, public data where it is free to use

A trading house buys market data centrally and lets people use it under that licence. The
product follows the same pattern: the market-data team holds the vendor contracts and
credentials on the server, administrators grant data scopes to people against those
licences, and every price row is filtered by its source family. Nobody enters a vendor
password in their own preferences.

Administrators record each licence in the licence register (Administration → Access →
Catalogue); granting a licensed data scope to a person is refused unless an active licence
covers their office and has a free seat. See
[ADMIN_AND_OPERATIONS.md](../guides/ADMIN_AND_OPERATIONS.md#market-data-licences).

## Priority: licensed sources to connect

| Priority | Vendor / product | Covers | Licence | Route into the product today |
|---|---|---|---|---|
| 1 | **ICE Endex** (futures, Report Center) | TTF, NBP, EUA, UKA, API2 coal, NL/BE/GB power settlements | Exchange data licence (non-display for analytics) | `import_settlements.py --source ICE_ENDEX`; connector shell `src-ice-endex` |
| 1 | **EEX DataSource** | THE, PEG, TTF, ZTP, PSV gas; EUA spot, futures and auctions; German, French power | EEX DataSource licence | `import_settlements.py --source EEX`; `src-eex` |
| 1 | **Trayport** (Joule/Gateway) | OTC broker screens for every European hub | Trayport + broker licences | `import_market_quotes.py --source Trayport` (screen export) |
| 2 | **Kpler** | LNG cargoes, arrivals, Norwegian and Russian flows | Kpler subscription | registered `src-kpler`; needed for LNG send-out forecasts |
| 2 | **Argus / Platts** | API2 index, JKM, assessments | Price-reporting agency licence | registered `src-argus`, `src-platts` |
| 3 | **CME DataMine** | NYMEX Henry Hub futures | CME licence | `import_settlements.py --source CME`; `src-cme` |
| 3 | **NGX** | AECO-C/NIT for a Canada desk | NGX licence | `import_settlements.py --source NGX`; `src-ngx` |

A direct connector replaces the file import once the licence names this installation and
the vendor's API credentials are issued; the stored rows and entitlements stay the same.

## Free and public data used without a licence

| Source | Data | Terms | In the product |
|---|---|---|---|
| ENTSOG, GIE AGSI/ALSI | Flows, capacity, storage, LNG | Public reuse with attribution | Scheduled |
| ENTSO-E Transparency | Power prices, load, wind, solar, gas generation | Reuse with attribution; free token | Scheduled hourly (`src-entsoe`) |
| ECB, Bank of England, NY Fed | FX, €STR, SONIA, SOFR | Public | Scheduled daily |
| EIA open data | Henry Hub daily spot | US public domain; free key | Scheduled daily (`src-eia`) |
| REMIT inside-information platforms | Outages (UMMs) | Publication duty; check each platform's reuse terms | File import |
| ECMWF open data, National Gas | Temperature forecasts, GB demand | CC BY 4.0 / open licence | Scheduled scripts |
| EEX public reference file | TTF NGP reference index | As published by EEX | Bounded download, labelled as an index |
| World Bank Pink Sheet | Monthly coal (Australia, South Africa, Colombia) | CC BY 4.0 | Long-term reference only (not a daily price) |

## What the product does not do

It does not scrape exchange or vendor web pages. The delayed prices and volumes on
exchange websites (including EEX's market-data pages) are shown for information under
website terms that exclude systematic extraction and commercial reuse; a trading house
that relied on them would breach those terms and fail a vendor audit, and the numbers can
change format without notice. Where an exchange publishes a dataset for reuse (EEX's TTF
reference file, auction results published under the EU Auctioning Regulation) the product
uses it as published and labels it for what it is. When no licensed price exists, the
product shows the gap rather than a substitute (AGENTS.md rules 17 and 18).

## How the desks use these

- **Carbon and coal** set where gas sits in the power merit order: the clean spark spread
  against the clean dark spread, and the gas price at which coal and gas plants cost the
  same (Market → Overview → Gas for power, `GET /api/market/gas-for-power`).
- **Henry Hub and JKM** set LNG arbitrage against TTF and NBP.
- **AECO, Alberta power and TIER credits** are defined in the market model for a Canada
  desk (status *planned*): adding their ingestion is a source entry and a parser.

Settlement import columns and examples: `src/eurogas_nexus/ingestion/commodity_settlements.py`.
