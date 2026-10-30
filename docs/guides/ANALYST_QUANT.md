# Analyst and quant guide

**You land on Market → Curves (analyst) or Strategy Lab → Design (quant).**

## Research workflow

1. **Explore a relationship:** Strategy Lab → Spread. Weighted spreads of two to four
   series, z-score, percentile and half-life, and a declared rule backtest without look-ahead.
2. **Build a strategy:** Strategy Lab → Design, freeze a version, Backtest, Compare, then
   Shadow to watch it on live data.
3. **Build a training dataset:** System → Research Data. Point-in-time datasets over prices
   (every hub), power (`power.*`), storage (`storage.*`), LNG (`lng.*`) and flows
   (`flow.mcm_d.*`), with declarative features (lags, changes, rolling mean and dispersion,
   linear combinations) and walk-forward folds with an embargo. Export to Parquet.
   See [ML_READINESS.md](../research/ML_READINESS.md) and
   [FEATURE_REGISTRY.md](../research/FEATURE_REGISTRY.md).
4. **Fundamentals:** GB weather-adjusted demand and gas-for-power
   ([GAS_POWER_COUPLING.md](../research/GAS_POWER_COUPLING.md)).

## Python SDK

```python
from eurogas_nexus_sdk import research
series = research.list_spread_series("https://nexus.example.com")
result = research.analyse_spread("https://nexus.example.com",
    legs=[{"hub": "THE", "tenor": "month-ahead", "weight": 1},
          {"hub": "TTF", "tenor": "month-ahead", "weight": -1}])
```

Train models in your own environment and bring forecasts back as forecast vintages, so
they enter datasets and shadow evaluation like any other source.

## Rules that protect your results

Every value is used only after it was available; simulated sources are labelled; exports
respect licence terms (exchange data usually needs a derived-data licence for models).

## Balance and gas for power

Market → Overview shows the north-west Europe balance (the call on Norway, LNG and storage,
measured and forecast, with REMIT outages applied; method in
[NWE_BALANCE.md](../research/NWE_BALANCE.md)) and the gas-for-power view per bidding zone
(clean spark and dark spreads with EUA/UKA and API2, implied gas burn). Both are in the API
(`/api/market/nwe-balance`, `/api/market/gas-for-power`) for notebooks.

