# Central data platform: how Eurogas Nexus subscribes to the firm's data

## The model

Systematic trading firms keep one central data platform. Vendor feeds, exchange data, ETRM
trades, nominations and fixings arrive there once, are normalised and licensed once, and every
application subscribes to the part it needs. Firms such as Jane Street and Hudson River Trading
do not publish their internal designs. The public pattern across the industry is a central
tick or time-series store with a subscription layer, not each desk tool pulling vendors on
its own.

Eurogas Nexus fits that model as one subscriber:

```
 vendors, exchanges, TSOs, ETRM ──► central platform (firm-owned) ──► egn_* views
                                                                         │ read-only
                                                                         ▼
                              scripts/ops/sync_central_platform.py ──► runtime store (PostgreSQL)
                                                                         │
                                                                         ▼
                                                     Eurogas Nexus API, web and desktop
```

- The runtime store holds only what this application reads. Its tables are the product's
  contract and are not shared write targets for other programs.
- Other programs publish into the platform, not into the runtime store. A program that needs
  Eurogas Nexus results reads them through the API or the report exports (Excel, PDF, CSV).
- The platform may live on the same PostgreSQL server (another schema) or elsewhere. The
  sync needs only a read-only login (`EUROGAS_NEXUS_CENTRAL_PLATFORM_URL`).

## Feeds and their view contracts

The platform publishes one view per feed, with the importer's column names. Extra columns
are ignored and column names are case-insensitive.

| Feed | Columns | Importer and rules |
|---|---|---|
| `etrm-trades` | `trade_id, trade_time, book_id, hub, side, delivery_start, delivery_end, quantity, quantity_unit, price, price_unit[, status, counterparty]` | `ingestion/etrm_trades.py`. Keyed by (system, trade id); a cancelled status removes the trade; unknown books are refused. |
| `deliveries` | `contract_id, gas_day, nominated_mwh, allocated_mwh[, tso, point]` | `ingestion/contract_deliveries.py`. Keyed by (contract, gas day); an empty allocation stays missing, never zero. |
| `quotes` | `timestamp, hub, product, bid, ask[, ...]` | `ingestion/licensed_quote_import.py`. The source family (`--source`) is kept, so only holders of that licensed data scope see the rows. |
| `fx` | `date, pair, rate` | `domain/market/fx_fixings.py` (WMR, BFIX). |

Run each feed once or on a poll:

```bash
EUROGAS_NEXUS_CENTRAL_PLATFORM_URL=... RUNTIME_STORE_DATABASE_URL=... \
  python scripts/ops/sync_central_platform.py --feed etrm-trades \
  --view central.egn_etrm_trades --system Endur --watch 300
```

Every load is safe to repeat. A view name is the only input taken from the command line; the
script never runs free SQL. A view returning more than 200,000 rows is refused, so a bounded
(for example, rolling-window) view has to be published.

## Rules that do not change

- **Licensing:** licensed data comes only through the customer's own entitlement. The platform
  passing a feed through does not grant a data scope; risk and admins grant scopes against the
  licence register (AGENTS.md rule 18).
- **Read-only:** nothing is written back to the platform, and no trade, nomination or
  settlement leaves the product (AGENTS.md rule 8).
- **Provenance:** every row keeps its source system and reference, and the Data Sources page
  shows its freshness like any other connector.
