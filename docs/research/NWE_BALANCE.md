# North-west Europe gas balance

Market → Overview → *North-west Europe balance*, `GET /api/market/nwe-balance`, and the
domain model `src/eurogas_nexus/domain/fundamentals/balance.py`.

## What it answers

How much gas north-west Europe (GB, NL, BE, DE, FR, DK, LU) needs from its flexible
sources (Norwegian pipelines, LNG and storage) over the next two weeks, and therefore
how fast storage must draw or can fill. This is the number a desk compares with the
curve: a forecast draw above what storage delivered recently, or a Norwegian outage the
forward has not priced, is a trading signal.

## Method

The call is measured, not modelled, in history:

```
call = Norwegian entry flows (ENTSOG) + LNG send-out (GIE ALSI) + storage net withdrawal (GIE AGSI)
```

in GWh per gas day. Domestic production and other imports change slowly and sit inside the
call. Norwegian volumes are converted at a stated 11.0 kWh/m³; LNG and storage are already
energy.

Each component is forecast separately and every forecast day records its method:

| Component | Forecast | Next improvement |
|---|---|---|
| Call | Weather regression `a + b·HDD + weekend` when heating-degree-day forecasts are supplied; otherwise the seasonal normal (same days of the year in earlier years) plus the recent anomaly; else the 28-day average | Population-weighted HDD per country from ECMWF forecasts, and the gas-for-power burn from ENTSO-E load and renewables forecasts |
| Norway | 7-day average minus unavailable capacity from live REMIT outages in the Norwegian zone | Gassco nominations and maintenance calendar |
| LNG | 14-day average send-out | Cargo arrivals from a licensed source (Kpler) |
| Storage | Residual, rolled into inventory and fill against working capacity | Facility deliverability curves by fill level |

Flags: `withdrawal_above_recent_maximum` (the residual exceeds 125 % of the largest net
withdrawal in the last 28 days, so the balance needs more supply or demand destruction)
and `inventory_outside_capacity`.

## Why this shape

Desks at trading houses and utilities build balances from components they can each
defend and adjust, then overlay judgement; a single opaque model cannot be argued with
on a morning call. The component structure also lets the point-in-time dataset builder
(`docs/research/ML_READINESS.md`) train a statistical or machine-learning call model on
the same measured history and drop it in as the call method, with its backtest, when it
beats the regression.

## Limits

- Without HDD forecasts the call is seasonal, not a weather forecast; the warning says so.
- The Norwegian entry points are matched by name (Emden, Dornum, Zeebrugge ZPT, Dunkerque,
  St Fergus, Easington); Easington also lands non-Norwegian gas.
- Exports out of the region (to Italy, Central Europe, Ukraine) are inside the call.
