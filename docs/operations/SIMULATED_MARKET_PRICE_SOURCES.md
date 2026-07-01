# Simulated Market Price Sources

## Purpose

Before licensed EEX, ICE OCM, ICIS, broker, and Trayport subscriptions are
configured, Eurogas Nexus can inject simulated market prices into the runtime
database. The simulator uses the same normalized `market_observations` table and
`ingestion_runs` status path as real source connectors.

This is intentionally different from static demo data:

- rows are source-shaped and timestamped;
- source labels are `EEX_Sim`, `ICE_OCM_Sim`, and `ICIS_Sim`;
- rows include `metadata_json.simulated=true`;
- rows include tenor and timing metadata such as `within-day`, `day-ahead`,
  `month-ahead`, `instant`, and `daily_assessment`;
- `/api/market/observations`, `/api/sources`, resource-pool pricing, the Market
  terminal, and Strategy inputs all read the same runtime DB rows.

The simulator must not be used as a substitute for licensed commercial data in
production decisions. It is for validating ingestion, UI behavior, strategy
shadow runs, source health, and operational performance before subscriptions are
connected.

## Running The Simulator Worker

Set `RUNTIME_STORE_DATABASE_URL` or `DATABASE_URL` to the active PostgreSQL
runtime or test database, then run:

```powershell
python scripts/ops/ingest_simulated_market_prices.py --loop
```

The worker continuously upserts tick-bucketed rows into PostgreSQL. Do not run a
separate SQLite simulator database for normal project validation; the point of
the simulator is to exercise the same PostgreSQL ingestion path that real
connectors will use. Default cadence:

- `ICE_OCM_Sim`: every 15 seconds for within-day and day-ahead screen marks;
- `EEX_Sim`: every 60 seconds for spot/curve marks;
- `ICIS_Sim`: every 86,400 seconds for daily day-ahead assessments.

The cadence is a configurable simulation of market-data behavior. It preserves
real connector shape and operational pressure without claiming to reproduce an
entitled vendor feed byte-for-byte.

When the Web or Windows Market workspace is open, the client polls the backend
market observation, FX, and source-posture endpoints. It does not connect to
PostgreSQL directly. This lets the simulated worker exercise the same runtime
loop expected from licensed EEX, ICE OCM, ICIS, broker, or Trayport connectors:

```text
simulated source worker -> PostgreSQL -> /api/market + /api/sources -> Market terminal
```

The Market terminal must keep simulated rows visibly labeled and must show
tenor, timing, and cadence metadata so traders can distinguish instant OCM
marks, day-ahead assessments, and curve marks before using them in strategy
shadow runs or resource-pool decisions.

Override cadences when a faster local test is useful:

```powershell
python scripts/ops/ingest_simulated_market_prices.py --loop `
  --ice-ocm-interval-seconds 5 `
  --eex-interval-seconds 30 `
  --icis-interval-seconds 300
```

Bounded validation, suitable for CI or a quick smoke test:

```powershell
python scripts/ops/ingest_simulated_market_prices.py --loop --max-iterations 3
```

The same script without `--loop` writes one batch and exits. Use that only for
connectivity checks; the project runtime should use the long-running worker.

Each due tick writes:

- EEX-shaped spot/curve marks for TTF, NBP, THE, PEG, ZTP, and PSV;
- ICE OCM-shaped NBP within-day and day-ahead screen marks;
- ICIS Heren-shaped daily day-ahead assessments for the major hubs.

Each tick also writes succeeded `ingestion_runs` records so the Source Center can
show live-record counts, latest run status, and worker freshness.

## Price Basis Rules

The default resource-pool sale-price path prefers day-ahead or within-day rows
over month-ahead curve rows for spot-like route economics. Month-ahead marks are
still displayed in the Market terminal curve lanes because strategy analysis may
compare temporal price differences across tenors.

Strategy work should preserve the distinction between:

- instant/within-day screen marks;
- day-ahead exchange or assessment prices;
- weekend and balance-of-period products;
- month-ahead or curve products;
- FX reference rates.

## Weather Source Direction

Open weather data can support HDD/CDD, temperature deviation, demand-pressure,
and forecast-delta features:

- Open-Meteo is the first low-friction development source because it provides
  forecast and historical APIs without an API key for non-commercial use.
- Copernicus Climate Data Store and ERA5 are better for European historical
  reanalysis, model validation, and longer-running analytics.
- NOAA/NWS APIs are useful open references but are US-focused, so they are not a
  primary Europe gas trading weather source.

Any production weather provider must still be registered as a governed source
with freshness expectations, credential policy where required, and source
references in all derived HDD/CDD signals.
