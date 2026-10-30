# Strategy Lab

A strategy is a long-lived research identity. Versions are immutable once
frozen. Runs are immutable evaluations of one exact version.

## Spread (start here)

The Spread task answers the everyday desk question without saving anything first:
*what is THE–TTF month-ahead doing, is it stretched, and would a simple rule on it
have paid?*

1. Pick two to four legs from the drop-downs. Each lists hub, tenor, source, unit and
   how many daily closes exist. Weights default to +1 / −1; use other weights for
   ratio or crack-style spreads (for example 1 × NBP − 1 × TTF, both in EUR/MWh).
   Legs in different units are refused; convert first.
2. Read the statistics: last, mean ± σ, z-score now, percentile now, half-life
   (how fast the spread has mean-reverted, from an AR(1) fit) and range.
3. Choose a rule: **mean reversion** (enter at |z| ≥ entry, exit at |z| ≤ exit over
   a lookback) or **fixed bands** (buy below, sell above). Set volume (MWh/d) and a
   cost per position change.
4. **Analyse.** The position is set at the close of day *t* and earns from *t* to
   *t+1*, so there is no look-ahead. You get rule P&L, trades, hit rate, maximum
   drawdown, annualised Sharpe, three charts (spread, z-score, cumulative P&L) and
   the trades table. The analysis id is a hash of inputs and result, so the same
   question gives the same answer.

Why rules and not user code: a declared rule can be validated, reproduced, reviewed
by risk and explained to a trader in one sentence; arbitrary code in a shared server
cannot (sandboxing, look-ahead and licence leakage are all on the reviewer). Quants
who need more use the Python SDK (`eurogas_nexus_sdk.research.list_spread_series`
and `analyse_spread`, or the dataset builder) in their own notebooks, and bring a
rule worth keeping back as a Design version so it is frozen, backtested and shadowed.

## Governed path for rules worth keeping

1. **Design**: create a strategy and a draft version; define components,
   resource scope, risk controls, and economic assumptions. Resolve every
   BLOCKER before saving.
2. **Freeze**: freezing makes the version immutable. To change it, fork a new
   draft; you cannot edit a frozen version.
3. **Backtest**: configure period and policies, run the evaluation, and
   inspect PnL, drawdown, events, attribution, provenance, and data quality.
4. **Compare**: select two or more runs and read the compatibility
   classification and caveats.
5. **Shadow**: start monitoring on a frozen version with an explicit baseline.
   A blocked evaluation means required evidence is missing; it never invents
   a candidate.

All outputs are research candidates, not trade instructions.
