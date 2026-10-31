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

- Marks come from a monthly forward curve per hub built from the latest licensed quotes:
  month quotes as quoted, months inside a quarter, season or year derived so that their
  day-weighted average equals the product price, and the current month from the prompt
  product. The **Mark** column shows the price and, on hover, how it was obtained. A month
  with no curve quote is marked flat at the hub's latest daily close and the warnings
  count it. Simulated prices are never used.
- VaR is historical simulation of price moves on the open position: no volume, basis,
  shape or credit risk. Your risk system remains the book of record.
- A leg priced in a currency other than its hub's mark is shown unvalued and counted, not
  converted silently.

## Controls

**Credit and mandates** (Portfolio → Exposure). Record each counterparty's approved line
(limit, collateral, rating, approval expiry, the supply contracts that face it and the
names it carries in the ETRM extract) and each trader's mandate (books, hubs, net MWh per
hub-month, tenor, physical/financial). Exposure is netted replacement cost at the ladder's
marks plus unpaid receivables less collateral; *watch* from 75 % used, *breach* above
100 %; an expired approval counts with the breaches. Only a REVIEWER can change a line or
a mandate, nobody can set their own, and every change is audited. Open-ended contracts
are valued to the ladder's 36-month horizon. Excel and PDF exports serve the credit
committee pack.

You cannot approve a decision you opened (four-eyes). Every grant, decision and setting
change is in the audit log (Administration → Audit, for reviewers).

## Books and reporting currency

Portfolio → Exposure rolls the ladder up by firm, legal entity, region, business or book
(*Roll up by*) and reports mark-to-market and VaR in one currency (*Currency*). Each hub's
own currency is converted at the latest ECB reference rate; a position without a rate is
left unvalued and named in the warnings. Middle office defines books and assigns contracts
and trades to them in the *Trading books* panel (operator role).
