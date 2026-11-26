# Demo data audit

Where the self-hosted demo shows demo or simulated data, what a desk would use instead, and what
this branch did about it. Read on 2026-11-26 from the local demo database, the demo seed
(`scripts/demo/seed_demo_desk.py`), the demo starter (`scripts/demo/start_public_demo.py`), the
ingestion connectors and `docs/DATA_SOURCE_TERMS.md`.

## Classes

- **a**: a public source exists and the repo has a connector for it, but the demo didn't use it. A bug; fixed here unless noted.
- **b**: a public source exists but there is no connector. Noted; not built here.
- **c**: the data needs a licence this deployment doesn't hold. The demo value stays, and the
  screen says it is simulated because the licence isn't held.
- **firm**: the firm's own records (desk, book, limits). Fictional in a demo by design.

## What the local demo held

Every market table held simulated rows only, because live sources were off and no keys were
set: market observations 35,050 (`DEMO_Sim`), market quotes 276 (`DEMO_Sim`, `EEX_Sim`), flows
25,802, storage 15,730, LNG send-out and stocks 13,175, power 14,880, FX 574, rates 858, REMIT
2, TSO tariffs 34, LNG terminal terms 3, screen orders 2 (`DEMO_EXCHANGE`), weather forecast 2
(`WEATHER_UAT_Sim`), LNG cargoes 5 (`Kpler_Sim`), regas slots 1, capacity observations 0.

## Table

| Area | Screen | Data | Today's source | Class | Fix status | Source / licence notes |
|---|---|---|---|---|---|---|
| Rates | Settings > Data, Deals (discounting) | €STR, SONIA, SOFR | `DEMO_Sim` unless live sources on | a | Fixed: run with no key in `auto` | ECB, Bank of England and New York Fed publish them openly; connectors exist |
| FX | Book, Deals, Reports | ECB reference rates | `DEMO_Sim` unless live sources on | a | Fixed: run with no key in `auto` | ECB reference rates, reuse permitted with attribution; connector exists |
| UK supply and demand | Market fundamentals, Today | National Gas supply and demand | `DEMO_Sim` | a | Fixed: run with no key in `auto` | National Gas Data Portal open data; connector exists |
| UK power | Market fundamentals | Elexon generation and prices | `DEMO_Sim` | a | Fixed: run with no key in `auto` | Elexon Insights, open; connector exists |
| Outages (REMIT) | Today, Alerts | ENTSOG UMMs | `DEMO` | a | Fixed: run with no key in `auto` | ENTSOG transparency platform; the product classes UMMs as needing no approval (`classify_source`); connector exists |
| Pipeline flows, capacity, tariffs | Market fundamentals, Capacity, Cargo costs | ENTSOG flows, firm capacity, tariffs | `DEMO_Sim`; capacity empty | a | Fixed: run after an admin approval of ENTSOG, or with `on` | ENTSOG terms need an admin approval (`APPROVAL_REQUIRED_SYSTEMS`); the simulated tariffs are retired once real ones arrive |
| Weather | Today, Forecast | Temperature forecast | `WEATHER_UAT_Sim` | a, not small | Not fixed | ECMWF open data (CC-BY 4.0); a connector exists but the demo has no point bindings or GRIB decoder in its catch-up |
| Storage | Market fundamentals, Today | GIE AGSI+ stocks, injection, withdrawal | `DEMO_Sim` | a, key needed | Unchanged: the operator adds a free GIE key | Free registration we don't hold; the simulated rows retire once real ones arrive |
| LNG terminals | Market fundamentals, Cargo | GIE ALSI send-out and stocks | `DEMO_Sim` | a, key needed | Unchanged: needs the GIE key | As above |
| Outages (REMIT, GIE IIP) | Today, Alerts | GIE inside information | `DEMO` | a, key needed | Unchanged: needs the GIE key | As above |
| Power (continental) | Market fundamentals | ENTSO-E load and prices | `DEMO_Sim` | a, key needed | Unchanged: the operator adds an ENTSO-E token | Free registration we don't hold |
| Henry Hub spot | Market, Spreads | EIA Henry Hub spot | `DEMO_Sim` | a, key needed | Unchanged: the operator adds an EIA key | Free registration; EIA stopped publishing futures after April 2024, so the forward stays c |
| LNG price assessment | Cargo, Spreads | DES NWE LNG | `DEMO_Sim` | b | Noted | ACER LNG price assessment and benchmark (daily, REMIT 7a–7e). Its pages give no reuse licence ("Stakeholders may use the LNG benchmark voluntarily"); terms to confirm with ACER before a connector |
| UK balancing prices | Market | SAP, SMP buy and sell | `DEMO_Sim` | b | Noted | National Gas Data Portal publishes them as open data under its licence duty; reuse terms not found (`DATA_SOURCE_TERMS.md` says not established) |
| German balancing prices | Market | THE imbalance prices | `DEMO_Sim` | b | Noted | Published by THE; terms not read |
| Regas slots | Cargo | Slot offers | `DEMO_Sim` | b | Noted | Terminal operators publish secondary slot offers; no connector |
| Hub prices | Market, Today, Book, Spreads, Reports | TTF, NBP, THE, PEG, ZTP day-ahead and curve | `DEMO_Sim`, `EEX_Sim` | c | Label says no exchange price licence is held | ICE Endex, EEX, Trayport, ICIS. No free source permits reuse: see below |
| Month-ahead history | Market, Reports | Settlement history | `DEMO_Sim` | c | Same label | As above |
| Exchange screen | Market | Screen orders, demo exchange feed | `DEMO_EXCHANGE` | c | Same label | Trayport, ICE |
| Henry Hub forward | Spreads | NYMEX curve | `DEMO_Sim` | c | Same label | CME licence |
| FX fixes | Deals | WMR / BFIX fixes | `DEMO_Sim` | c | Kept | Refinitiv / Bloomberg licences; the ECB rate above is public |
| Vessels | Cargo | Cargo positions | `Kpler_Sim` | c | Handled separately | Kpler licence |
| LNG terminal tariffs | Cargo costs | Regas tariffs | Simulated terms | c | Handled separately | Fluxys and Elengy publish tariffs, but reuse needs the operator's permission |
| Cargo & netback | Cargo & netback | Cargoes, netbacks, costs | Demo seed | — | Handled separately | Another session owns this screen |
| Desk | All | Desk, traders, book, deals, limits, credit lines, mandates | Demo seed | firm | Kept | The firm's own records; fictional in a demo by design |

Counts: a 12 (6 fixed here, 1 not small, 5 waiting on a free key the operator must register),
b 4, c 7 (4 labelled here, 3 kept or handled separately), Cargo & netback handled separately,
firm 1.

## The fix (a)

`EUROGAS_NEXUS_DEMO_LIVE_SOURCES=auto`, the default, ran no public source at all when no key was
set, although rates, FX, National Gas, Elexon and the ENTSOG UMMs need no key. `auto` now runs
the catch-up always. It still records no source approval by itself: that takes `on` or a key, as
before. ENTSOG reads (flows, capacity, tariffs, history) wait for an admin approval of ENTSOG or
`on`, so the demo never reads ENTSOG on terms nobody accepted. `off` still runs nothing. See
`docs/deployment/SELF_HOSTED_DEMO.md` and `tests/unit/test_start_public_demo.py`.

## Hub prices

No free, public source permits reuse of TTF, NBP, THE, PEG or ZTP prices in this product:

- EEX publishes a TTF and THE natural gas price (NGP) CSV, but its website terms allow personal,
  non-commercial use only. The connector (`--source eex-ngp`) exists and stays gated.
- Exchange settlement prices come under EEX DataSource or ICE Endex data licences.
- TSO balancing prices (National Gas SAP/SMP, THE) are not hub trading prices and their reuse
  terms are unverified (b above).

So the prices stay simulated, and the Market banner, the Today banner, the top bar, the Spreads
banner and the demo-prices help now say they are simulated because no exchange price licence is
held. Real prices come through the firm's own entitlement (operator quote import).

## Still open

- ECMWF point forecasts in the demo catch-up.
- GIE, ENTSO-E and EIA keys: free registrations the operator has to make.
- ACER LNG benchmark, National Gas SAP/SMP and THE imbalance price terms, before any connector.
- Licence decisions on hub prices belong to the owner.
