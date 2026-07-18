# Intraday Decision Feed

Mandarin companion: [INTRADAY_DECISION_FEED-CN.md](INTRADAY_DECISION_FEED-CN.md)

## Purpose

The intraday decision feed continuously compares compatible buy and sell quote
sides against a physically and commercially eligible gas route. It gives the
trader a time-limited candidate for review on the Network and Market workspaces.
It does not place orders, reserve capacity, submit nominations, capture trades,
or claim guaranteed profit.

The implemented data path is absolute:

```text
licensed or simulated adapter
  -> normalized L1 quote
  -> PostgreSQL market_quotes
  -> backend route/opportunity scan
  -> PostgreSQL intraday_opportunities
  -> GET /api/market/opportunities
  -> SDK, Web, Windows, and Linux clients
```

Clients never calculate spread economics and never connect to PostgreSQL or a
market-data provider.

## Runtime Contract

Alembic revision `0014_intraday_decision_feed` adds:

| Table | Authority |
| --- | --- |
| `market_quotes` | Normalized L1 bid, ask, last, visible depth, delivery window, event and receipt times, currency/unit, source identity, quality, and simulation state. |
| `company_tso_access` | Effective-dated company access status for each required TSO/operator. |
| `intraday_opportunities` | Immutable backend scan snapshots with quote IDs, route, economics, quantity limit, lineage, assumptions, blockers, warnings, and validity window. |

Apply migrations explicitly. Importing the API or running unit tests does not
connect to a database or execute a migration.

## Evaluation Rules

For each active route candidate, the backend selects the latest quote per
source, venue, and instrument. A pair is compared only when hub direction,
product, delivery start, delivery end, unit, and currency conversion are
compatible.

The calculation uses executable sides, never last or midpoint:

```text
gross spread = sell bid - converted buy ask
net margin = gross spread - route cost - trading cost - risk buffer
maximum quantity = min(buy ask depth, sell bid depth, route capacity)
indicative net value = net margin * maximum quantity
```

`ACTIONABLE_REVIEW` requires all of the following:

- current buy ask and sell bid;
- matching delivery window and product;
- known route tariff cost in a compatible unit/currency;
- confirmed TSO access;
- positive route capacity and visible quote depth;
- quote age within the configured maximum;
- net margin above the configured minimum.

Otherwise the result is `WATCH` or `BLOCKED` with machine-readable reasons.
When `valid_until_utc` passes, the API returns `EXPIRED` and adds
`OPPORTUNITY_EXPIRED`; a historical actionable snapshot never remains current
when the worker stops.

This remains an executable-spread *candidate*, not risk-free profit. Visible L1
depth does not guarantee simultaneous fill, route availability, balancing
outcome, clearing, settlement, or absence of latency and basis risk.

## Simulated And Licensed Sources

Until commercial subscriptions are configured, `EEX_Sim`, `ICE_OCM_Sim`, and
`Trayport_Sim` produce normalized L1 quote rows every 10 seconds. They use the
same `market_quotes` contract and downstream scanner as licensed adapters. All
simulated rows and derived opportunities remain visibly marked.

Replacing a simulator requires only a licensed source adapter that writes the
same normalized fields. It must preserve provider instrument identity, bid/ask,
visible depth, delivery period, event time, receipt time, deduplication key,
currency/unit, entitlement, quality, and source references. Domain, API, SDK,
and client code must not change.

Internet access is not required for the simulator. Internet and valid customer
credentials, licenses, and entitlements are required to implement and validate
live EEX, ICE OCM, Trayport, ICIS, or other commercial adapters.

## Operation

Set the runtime PostgreSQL URL and apply the migration, then run the explicit
worker process:

```powershell
alembic upgrade head
python scripts/ops/ingest_simulated_market_prices.py --loop
```

The worker writes one transaction per due source tick, records ingestion-run
status, writes normalized quotes, evaluates current routes, and persists the
result. The Web and desktop clients poll the API every 10 seconds while the
Network, Market, or Strategy workspace is open.

Operational interpretation:

- no rows: worker, route, tariff, access, or source setup is incomplete;
- `BLOCKED`: the candidate exists but mandatory evidence is missing or denied;
- `WATCH`: economics do not currently meet the review threshold;
- `ACTIONABLE_REVIEW`: inspect immediately and independently confirm execution
  and physical constraints;
- `EXPIRED`: no current backend snapshot exists for that candidate.

## API And SDK

Stable public endpoints:

```text
GET /api/market/quotes
GET /api/market/opportunities
GET /api/market/spreads
```

The spread endpoint is a compatibility summary derived from persisted
opportunities. New clients should use the quotes and opportunities endpoints.
The Python SDK exposes `fetch_market_quotes_result()` and
`fetch_intraday_opportunities_result()` so response metadata and warnings are
preserved.

## Release Boundary

R30B validates a route-specific cross-hub decision feed and its full DB/API/SDK
client chain. R31 remains responsible for portfolio-wide allocation over shared
capacities, alternate routes, local-sale options, and contract-level PnL
attribution. Authentication, commercial entitlement enforcement, durable
production scheduling, and licensed source certification remain later release
gates.
