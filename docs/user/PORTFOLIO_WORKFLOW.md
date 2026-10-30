# Portfolio Workflow

1. Open Portfolio and inspect resources, quantity, all-in cost, and access.
2. Open Routes to compare feasible/blocked alternatives and the reason each is
   blocked.
3. Open Scenario (Decision Center) and review the carried route. Run **Compare
   Options** from the workspace's primary action. It sends the saved
   resource-pool read - resource volume and cost, sale-option price, route
   cost and capacity with each value's own currency and unit, plus the saved
   gas year - not values edited in the Scenario panel.
4. Run **Optimize Resource Pool** from the Optimize task's primary action. It
   sends the same saved resources and sale options plus the first saved
   upstream contract's annual financing rate (shown read-only); only when that
   first contract has no rate does the Scenario panel's draft financing rate apply. The rate
   is percent per year for early-cash value and is never converted in the
   client.
5. Inspect allocations, unallocated volume, binding constraints, and PnL
   attribution.
6. Open Review to inspect the evidence pack, source references, assumptions,
   and record a human review decision.

The optimizer is an exact min-cost flow. It never executes anything; a
positive PnL is indicative and requires human review.

## Position ladder (Portfolio → Exposure)

One table for physical and financial positions, so a desk with upstream supply, cargoes and
hub sales alongside screen hedges sees how long or short it is, where and when:

- **Rows:** delivery month (Nov-26, Dec-26, …), then hub within the month.
- **Physical:** stored upstream contracts at their daily contract quantity over their gas
  year (supply long, sales short), placed at the hub named in the delivery point.
- **Financial:** filled screen trades spread over their delivery gas days (buys long, sells
  short).
- **Net**, a long/short bar, and **Hedged**: the share of the physical position offset by
  trades.
- **Summary:** net, physical, financial, overall hedge ratio, mark-to-market against the
  latest licensed daily close per hub (flat across months), and a one-day 95 % VaR by
  historical simulation of the open position.

The figures are indicative: price risk on the open position only (no volume, basis, shape
or credit risk), and never computed from simulated prices. Legs priced in a different
currency from the hub's mark are left unvalued and counted. The risk system remains the
book of record.

Who sees what first: management and risk land on Portfolio → Overview, which opens with
the same summary strip (net, hedge ratio, mark-to-market, VaR) above the resource
overview; traders land on Market → Curves and open the ladder when they need it.
