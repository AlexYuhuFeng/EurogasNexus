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
