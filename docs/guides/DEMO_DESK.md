# Demo desk: a fictional book for demonstrations and training

`scripts/demo/seed_demo_desk.py` writes a small, believable gas desk for sales demos, user
training and manual screenshots. Nothing in it is real.

| What | Demo content |
|---|---|
| Firm | Northwind Gas Trading, legal entities `NWG-UK` and `NWG-NL`, books `demo-uk-nbp` and `demo-nl-ttf` |
| Supply contracts | Haldor (Easington, 24,000 MWh/d, evergreen), Brae North (St Fergus, 10,000 MWh/d, current gas year), Kestrel (TTF, 18,000 MWh/d, EUR) |
| Counterparties | Aldermoor Energy plc, Nordvik Petroleum ASA, Rhinmark Handel GmbH |
| Trades | One ETRM sale to Aldermoor; exchange hedges for `demo.trader` (NBP) and `demo.nl.trader` (TTF) |
| Deliveries | 90 gas days of nominations and allocations; Haldor under-delivers in the last week |
| Prices | A 38-month NBP and TTF curve and 45 days of month-ahead history, source `DEMO_Sim`, flagged simulated |
| LNG | Three demo terminals with demo regas, entry and port costs |

## Run it

```bash
# A development or demo environment only: the script refuses trial and release.
RUNTIME_STORE_DATABASE_URL=... python scripts/demo/seed_demo_desk.py
# Value the book against the demo prices (off by default, never in trial or release):
EUROGAS_NEXUS_DEMO_MARKS=true  # in the API's environment
```

Re-running replaces the demo rows only. Sign in as any principal with data scope `*`; the
risk screens need the REVIEWER role.

With `EUROGAS_NEXUS_DEMO_MARKS` on, the top bar shows **Demo prices** on every screen and
every valued response carries the warning "marks are simulated demo prices, not market
prices". Without it, the demo prices stay out of positions, credit and mandates, as every
simulated price does.

## What risk will see

The script does not type limits in. It values the demo book with the same credit function
the API uses and sizes each line from that, so on any day it runs:

| Counterparty | Status | Why |
|---|---|---|
| Aldermoor Energy | OK (about 55 %) | A one-gas-year supply, with sales to them netted against it |
| Nordvik Petroleum | Watch (about 86 %) | A large evergreen supply bought well below the curve; counted to the end of the gas year |
| Rhinmark Handel | Breach (about 115 %) | The TTF curve sits above the contract price; a EUR 2m letter of credit is held and is not enough |

## Reading a breach like the old walk-through data

Earlier walk-through data showed one counterparty at over 3,000 % of its line. Two things
caused it, and both are fixed:

1. **Data**: a £1.5m line against a 10,000 MWh/d supply contract. Buying gas £4/MWh under
   the market for a year is roughly £13m owed to the firm if the seller defaults; no risk
   function would approve a line that small for that deal.
2. **Model**: an open-ended contract was counted as firm for the whole 36-month credit
   horizon. It now counts to the end of the current gas year, because evergreen supply
   renews annually and either side can end it on notice. Trader mandates apply the same
   rule to tenor.

In live use, a breach like that is real and serious. It means the firm would lose more
than risk agreed if that counterparty failed today, and the desk would call for collateral
(a letter of credit or margin under the CSA), stop adding volume with them, or reduce the
position. The product flags it; what to do about it is the risk function's decision.
