# Strategy Lab

A strategy is a long-lived research identity. Versions are immutable once
frozen. Runs are immutable evaluations of one exact version.

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
