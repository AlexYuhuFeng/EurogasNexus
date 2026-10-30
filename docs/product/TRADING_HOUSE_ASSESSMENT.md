# Assessment from a European gas trading house (2026-10-30)

How the product stands against what a trading house running NBP, TTF and continental hubs,
upstream supply, storage and LNG would expect, and what is still missing. It replaces
neither the risk system (ETRM/CTRM) nor the execution screen: it is the analysis, research
and decision-support layer between them.

## Verdict

Usable today as a **desk analytics and research workstation** for fundamentals, spreads,
route economics, positions and decision review, on the customer's own licensed prices.
**Not yet a complete trading-house platform:** live licensed price connectors are shells,
several fundamental feeds (outages, system prices, carbon/coal) are missing, and
forecasting covers GB demand and data preparation rather than a full balance model.

## Data sources: what is fetched, in what form, and where it is used

| Source | State | Format stored | Used in |
|---|---|---|---|
| ENTSOG Transparency (flows, capacity, points, interconnections) | Live, scheduled | Native rates with explicit units; flows in mcm/d | Network map, capacity, route costs, datasets (`flow.mcm_d.<point>.<dir>`) |
| GIE AGSI+ (storage) / ALSI (LNG) | Live, scheduled (customer key) | TWh, %, TWh/d per facility/terminal | Storage vs EU target, trader desk, datasets (`storage.*`, `lng.*`) |
| ECB reference FX, €STR | Live, scheduled | Daily fixings | Price converter, cash valuation |
| Bank of England SONIA, NY Fed SOFR | Live (script) | Daily fixings | Early-cash valuation, financing rate |
| ECMWF Open Data (IFS 2 m temperature) | Live (script) | GRIB → degree days | GB weather-demand model |
| National Gas (GB demand actuals) | Live (script) | Daily demand | Weather-demand targets |
| ENTSO-E Transparency (power prices, load, wind, solar, gas generation) | Parser and script (customer token) | MW, EUR/MWh per bidding zone | Gas-for-power, datasets (`power.*`) |
| EEX public TTF NGP file | Live (bounded download) | Reference index, 15-min | Reference index panel (not a quote) |
| Customer screen export (Trayport/ICE/EEX) | Operator import | L1 bid/ask in native units | Board, ladder, spread lab, position marks |
| WM/Reuters, BFIX fixes | Operator import | Fixings | FX conversions for LNG and contracts |
| Published TSO tariffs (NTS, BBL, IUK, GTS, NaTran, German TSOs, Fluxys, Enagás) | Curated tables | Tariff per point and gas year | Route costs, capacity billing |
| EEX DataSource, ICE, Trayport direct | **Connector shells** | — | Need the customer's licence and a connector build |
| Platts, ICIS, Argus, Kpler | **Registered, no connector** | — | Need licence and connector |

### Missing feeds a desk relies on

| Feed | Why it matters | Terms |
|---|---|---|
| REMIT UMMs (ACER inside-information platforms, Gassco UMM) | Norwegian and field outages move NBP/TTF within minutes | Public; check each platform's reuse terms |
| National Gas SAP/SMP, system imbalance, linepack | GB balancing prices and system length | Public (National Gas data portal) |
| THE/GTS/GRTgaz balancing signals | Continental system length | Public per TSO |
| EUA carbon and API2 coal prices | Fuel switching, spark/dark spreads | Licensed (ICE/EEX); customer entitlement |
| JKM, Henry Hub | LNG arbitrage | JKM licensed (Platts); Henry Hub spot public via EIA |
| Weather actuals and ensembles (ERA5, ECMWF ENS) | Model training and uncertainty | ERA5 CC-BY; ENS licensed |
| Hydro reservoir and French nuclear availability | Residual load and gas burn | ENTSO-E (A72 reservoirs, A77/A80 unavailability) |

## Forecasting and analytics

| Capability | State |
|---|---|
| GB weather-adjusted demand (ECMWF → degree days → National Gas demand) | Implemented, frozen model fits, numerical acceptance in CI |
| Gas-for-power (residual load, spark/dark, fuel switch, implied burn) | Implemented as calculations; not yet a fitted burn model |
| Point-in-time training datasets (prices, power, storage, LNG, flows; lags, rolling, walk-forward) | Implemented |
| Spread analysis and declared-rule backtests | Implemented |
| Strategy design, frozen backtests, shadow runs | Implemented |
| Position ladder, MtM on the forward curve, indicative VaR | Implemented (price risk only) |
| Supply/demand balance (NW Europe), storage trajectory forecast, LNG send-out forecast | **Missing** |
| Forward curve construction (months, quarters, seasons, years; optional seasonal shape) | Implemented; ladder marks use it, with a flagged flat fallback |
| Option or swing valuation, storage intrinsic/extrinsic | Storage dispatch assessment only; no extrinsic valuation |

## Components: effect and efficiency

| Component | Effect today | Assessment |
|---|---|---|
| FastAPI backend, one `/api` | All clients and the SDK go through it; RBAC, data scopes, audit | Sound. Some route modules are large and should be split by domain |
| PostgreSQL | Single source of truth, Alembic migrations | Sound. Time indexes added; partition when an observation table passes ~50M rows |
| Data-ops scheduler | Runs ECB, ENTSOG, GIE | Other ingestors are scripts that need cron; bring them under the scheduler |
| Projections (market context, portfolio snapshot) | One batched read per workspace | Efficient; measured latency budgets in CI |
| Web client (React) and desktop (Tauri) | One codebase, Windows and Linux | Works. A few very large files (API client, global CSS, store) slow change |
| Python SDK | Typed access for quants | Good coverage of research routes |
| LLM layer | Alert explanations, analysis with evidence | Provider-neutral; must stay advisory |
| CI | Unit, contract, PostgreSQL, browser (EN/ZH, axe), native builds, licence/CVE audits | Strong; catches real regressions |

## Priorities

1. **Licensed price connectors** on the customer's entitlement: EEX DataSource end-of-day
   and ICE Endex settlements first (curves for marks and VaR), Trayport streaming second.
2. **REMIT outage feed** and GB system prices: the two fastest-moving fundamentals.
3. **Carbon and coal** via the customer's ICE/EEX entitlement, completing the switching view.
4. ~~Forward curve builder~~ done (2026-10-30); next: feed it settlement curves from the
   licensed connectors in priority 1.
5. **NW Europe balance**: demand (weather, power burn) against supply (flows, LNG,
   storage), forecast daily for two weeks.
6. Bring all ingestors under the scheduler with the same freshness SLAs.
