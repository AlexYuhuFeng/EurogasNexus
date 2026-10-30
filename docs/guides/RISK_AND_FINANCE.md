# Risk, middle office, finance and settlement guide

**You land on Portfolio → Exposure.**

| Task | Where |
|---|---|
| Physical and financial positions by hub and month, hedge ratio | Portfolio → Exposure → Position ladder |
| Mark-to-market and indicative one-day 95 % VaR | Position ladder summary |
| Screen orders and P&L snapshots | Portfolio → Exposure |
| Contract terms, payment terms, early-cash value with SONIA/€STR/SOFR | Portfolio → Resources |
| Capacity billing and route costs | Portfolio → Routes |
| Decisions to review (four-eyes) | Decision Center |

## How to read the risk figures

- Marks are the latest licensed daily close per hub, flat across months, until a forward
  curve is connected. Simulated prices are never used.
- VaR is historical simulation of price moves on the open position: no volume, basis,
  shape or credit risk. Your risk system remains the book of record.
- A leg priced in a currency other than its hub's mark is shown unvalued and counted, not
  converted silently.

## Controls

You cannot approve a decision you opened (four-eyes). Every grant, decision and setting
change is in the audit log (Administration → Audit, for reviewers).
