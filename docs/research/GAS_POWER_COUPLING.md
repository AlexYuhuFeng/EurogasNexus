# Gas and power: how electricity drives gas demand

## Why it matters to a gas desk

Power generation is one of the largest uses of gas in Europe, and its most volatile one.
Heating demand moves with temperature over days and seasons; gas burned for power can swing
by tens of GWh a day within a week, depending on how much wind and solar there is and on
whether gas or coal is cheaper to burn. A desk that forecasts residential demand well but
treats power burn as a constant misses much of the day-to-day surprise in NBP and TTF
balances.

## The mechanism

1. **Load.** Electricity demand follows temperature (heating in winter, cooling in hot
   summers), daylight, the calendar (weekdays, holidays) and economic activity.
2. **Residual load.** Wind, solar, nuclear, run-of-river hydro and imports serve load first,
   because their marginal cost is near zero or they cannot follow price. What is left is the
   *residual load* that dispatchable thermal plant must meet:
   `residual = load − wind − solar − must-run − net imports`.
3. **Merit order and fuel switching.** Residual load is met by the cheapest available
   thermal plant. Gas competes with coal (where coal remains): the **clean spark spread**
   (power − gas/η − CO2·EF/η) against the **clean dark spread** decides which runs first.
   The **fuel-switch price** is the gas price at which the two cost the same; carbon prices
   push it up.
4. **Gas burn.** Gas-fired output divided by plant efficiency is gas burned:
   about 2 MWh of gas per MWh of power at 50 % efficiency.

Weather enters twice: through load (temperature) and through supply (wind speed, solar
irradiance, river flows). A calm, cold, dark spell (*Dunkelflaute*) raises gas burn and
heating demand together, which is why it moves prices so sharply. Nuclear availability
(notably in France) and hydro reservoir levels shift residual load across borders through
interconnectors.

## What the product provides

| Need | Where |
|---|---|
| Day-ahead power prices, actual load, wind, solar and gas-fired generation by bidding zone | ENTSO-E Transparency ingestion, `power_observations` (see [POWER_DATA.md](../operations/POWER_DATA.md)) |
| Residual load, clean spark and dark spreads, fuel-switch price, implied gas burn, MWh→mcm | `domain/power/gas_for_power.py` |
| Power series in point-in-time training datasets (`power.<metric>.<zone>`) | dataset builder; availability from the publication deadlines of Regulation (EU) 543/2013 |
| Seeded features: `GB_RESIDUAL_LOAD`, `GB_GAS_GENERATION_LAG24H` | research catalogue |
| Weather (ECMWF temperature) and gas demand targets | existing weather–demand vertical |

## How to use it for forecasting

- **Short term (D+1 to D+7):** forecast load from temperature and calendar; take wind and
  solar from weather forecasts; residual load follows. Regress observed gas generation
  (ENTSO-E B04, where reported) on residual load with hour-of-day and day-of-week effects;
  the coefficient is the gas share of residual load. Gas burn is then generation / η.
- **Price signal:** when the clean spark spread is deep in the money, gas runs to capacity
  and burn tracks residual load; near the fuel-switch price, burn becomes sensitive to
  small moves in gas, coal and carbon.
- **Training data:** register the drivers as declarative features (lags, rolling means,
  linear combinations) and build datasets with walk-forward folds; see
  [ML_READINESS.md](ML_READINESS.md) and [FEATURE_REGISTRY.md](FEATURE_REGISTRY.md).

## Limits

- ENTSO-E actuals are revised; the store keeps the latest value. A dataset built as of an
  earlier time sees nothing rather than the old value for a revised period.
- Gas-fired generation is not reported for every zone at the same granularity; where it
  is missing, the residual-load method is an estimate and is labelled as such.
- Carbon (EUA) and coal (API2) prices are licensed exchange data and come only through the
  customer's own entitlement.
