# Power data (ENTSO-E Transparency Platform)

What it loads: day-ahead prices (document A44), actual load (A65) and actual generation by
fuel (A75: gas, solar, onshore and offshore wind) for GB, NL, DE-LU, BE, FR, AT, IT-North
and ES. Values go to `power_observations`.

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
# Parse and report without writing (dry run), last two days, default zones GB, NL, DE_LU
python scripts/ops/ingest_power.py
# Store a week for GB and NL
python scripts/ops/ingest_power.py --zone GB --zone NL --days 7 --commit
# Store a document saved earlier (for example from the platform's web export)
python scripts/ops/ingest_power.py --file a75_gb.xml --commit
```

Re-running is safe: a value already stored is unchanged; a revised value replaces it.
The scheduler has no ENTSO-E job yet, so run this from cron or the task scheduler,
hourly for actuals and once after 13:00 Brussels for day-ahead prices.

## Availability (point-in-time)

The platform's `createdDateTime` is when the response was generated, so a backfill would
look as if history became known today. Each value's availability is the earlier of that
time and the publication deadline in Regulation (EU) 543/2013: day-ahead prices and load
forecasts by 12:00 Brussels the day before delivery; actual load and generation one hour
after the period. Datasets mark these values `TEMPORAL_APPROXIMATE`.
