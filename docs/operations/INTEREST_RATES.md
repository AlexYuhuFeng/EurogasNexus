# Benchmark interest rates (SONIA, €STR, SOFR)

Contracts that credit early payment, charge late-payment interest or discount a
prepayment usually state the rate as **overnight benchmark + spread**, observed on a
stated date. Eurogas Nexus stores the administrators' published daily fixings and
resolves the all-in rate on request. It never interpolates or assumes a missing
fixing.

| Benchmark | Currency | Administrator | Day count | Public source |
|---|---|---|---|---|
| SONIA | GBP | Bank of England | ACT/365F | BoE Interactive Database, series `IUDSOIA` (CSV) |
| €STR | EUR | European Central Bank | ACT/360 | ECB Data Portal, `EST/B.EU000A2X2A25.WT` (CSV) |
| SOFR | USD | Federal Reserve Bank of New York | ACT/360 | NY Fed Markets API (JSON) |

All three are published free of charge, and the administrators permit commercial use
subject to their terms of use, which include attribution and no implied endorsement.
The attribution text is returned by `GET /api/market/interest-rates` and shown wherever
a resolved rate is displayed. Have legal confirm the current terms before production
use; they are the administrators' to change.

## Ingest

```bash
python scripts/ops/ingest_interest_rates.py --days 30            # all three, last 30 days
python scripts/ops/ingest_interest_rates.py --benchmark SONIA     # one benchmark
python scripts/ops/ingest_interest_rates.py --benchmark SOFR --file sofr.json   # saved payload
```

Schedule once per business day after 09:00 London (SONIA is published at 09:00 London
on T+1, €STR at 08:00 CET on T+1, SOFR at 08:00 New York on T+1). Fixings are upserted
by (benchmark, value date), and a published correction replaces the stored value and is
reported. The deployment's egress policy must allow `www.bankofengland.co.uk`,
`data-api.ecb.europa.eu` and `markets.newyorkfed.org`.

## Resolving a contract rate

`GET /api/market/financing-rate?benchmark=SONIA&spread_bps=150&as_of=2026-10-30` returns:

- the fixing with the latest value date on or before `as_of`, so weekends and holidays
  carry the previous business day;
- `all_in_pct` = fixing + spread on the benchmark's own day count;
- `all_in_act365_pct`, the same money rate on ACT/365F. The resource-pool early-cash
  term accrues `days / 365`, so this is the value to use there. For ACT/360
  benchmarks it is `all_in × 365/360`;
- `fixing_date`, `staleness_days`, source and attribution.

A fixing older than `max_staleness_days` (default 7 calendar days) is refused with
`422 financing_rate_unavailable`; ingest newer fixings rather than using an old rate.

In the web client, **Portfolio → Resources → Settlement & cash** has a *Financing rate
from benchmark* helper next to the contract's financing-rate field. It looks the rate up
and, only when you press *Use as financing rate*, writes the ACT/365F all-in rate into
the contract.

Compounding in arrears (daily-compounded SONIA over an interest period) is not applied.
Early- and late-payment adjustments in gas contracts run over lags of days to a few
weeks, where simple interest on the observed fixing is the contractual norm. A contract
that specifies compounded-in-arrears interest needs that calculation added before it is
valued here.
