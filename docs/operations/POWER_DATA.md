# Power data (ENTSO-E Transparency Platform)

What it loads: day-ahead prices (document A44), actual load (A65) and actual generation by
fuel (A75: gas, solar, onshore and offshore wind) for NL, DE-LU, BE, FR, AT, IT-North
and ES. Values go to `power_observations`. Great Britain is no longer on the platform; it
comes from Elexon (see the last section).

## Access

1. Register at transparency.entsoe.eu and request API access (free; e-mail the
   Transparency Platform service desk with the account address).
2. Set `ENTSOE_SECURITY_TOKEN` in the server environment. The token is sent as a query
   parameter and never printed.
3. The source appears as `ENTSOE` in Sources (category Power). It is in the public baseline
   family, so analysts can use it without a commercial grant. Attribute ENTSO-E where its
   data is shown or exported.

## Running

```bash
# Parse and report without writing (dry run), last two days, default zones NL, DE_LU, BE, FR
python scripts/ops/ingest_power.py
# Store a week for NL and DE-LU
python scripts/ops/ingest_power.py --zone NL --zone DE_LU --days 7 --commit
# Store a document saved earlier (for example from the platform's web export)
python scripts/ops/ingest_power.py --file a75_nl.xml --commit
```

Re-running is safe: a value already stored is unchanged; a revised value replaces it.
The data-ops scheduler runs it hourly (source `src-entsoe`, last two days, NL, DE-LU,
BE and FR) once an administrator enables the source in Source Center with the token set; a
failed document fails the run so it is retried and shows as late rather than complete.

## Availability (point-in-time)

The platform's `createdDateTime` is when the response was generated, so a backfill would
look as if history became known today. Each value's availability is the earlier of that
time and the publication deadline in Regulation (EU) 543/2013: day-ahead prices and load
forecasts by 12:00 Brussels the day before delivery; actual load and generation one hour
after the period. Datasets mark these values `TEMPORAL_APPROXIMATE`.

## Great Britain (Elexon)

ENTSO-E returns nothing for the GB zone. GB comes from the Elexon Insights Solution
(BMRS), which is public and needs no account or key:

| Elexon dataset | Stored metric | Note |
|---|---|---|
| `FUELHH`, CCGT + OCGT | `gas_generation` (MW, half-hourly) | Observed gas-fired generation |
| `FUELHH`, WIND | `wind_generation` (MW) | Transmission-metered, onshore and offshore together |
| Demand outturn, INDO | `load_actual` (MW) | Initial national demand outturn |
| Market index, APX | `market_index_price` (GBP/MWh) | Within-day reference, not the day-ahead auction |

```bash
python scripts/ops/ingest_power_gb.py --days 7 --commit
```

The scheduler runs it every 30 minutes (source `src-elexon`, on by default, last two
days). Limits to know:

- Solar is embedded generation and not in `FUELHH`; it is absent, not zero, so GB residual
  load is demand less wind only.
- The GB day-ahead auction price (N2EX, EPEX) is licensed. Until the customer's own feed
  supplies it, the gas-for-power view uses the market index, marks each row
  `power_price_basis: market_index`, and warns that spark spreads on it are indicative.
- Attribution wherever the data is shown or exported: "Contains BMRS data © Elexon
  Limited copyright and database right".
