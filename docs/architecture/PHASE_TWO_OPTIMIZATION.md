# Phase-Two Optimization Layer

## Purpose

The phase-two optimization package adds deterministic decision-support engines
for four European gas commercial problems:

1. resource-pool allocation;
2. capacity-feasible route selection;
3. transport-capacity booking;
4. upstream contract dispatch.

The implementation is available under:

```text
src/eurogas_nexus/optimization/
```

The stable application facade is:

```python
from eurogas_nexus.optimization import PhaseTwoOptimizer
```

## Public API

The optimization facade is exposed through the public API:

```text
POST /api/optimization/route
POST /api/optimization/resource-pool
POST /api/optimization/capacity
POST /api/optimization/contracts
```

The existing `/api/route-cost/*` endpoints remain available for compatibility
with the current route-cost and resource-pool workflow. The new optimization
namespace provides a stable common DTO surface for phase-two capabilities.

## Product Boundary

These engines produce decision-support outputs. They do not submit orders,
nominate gas, book capacity with a TSO, amend contracts, or create official
approvals. Every result carries `human_review_required=True`.

## Current Optimization Models

### Resource-Pool Optimization

The resource-pool engine allocates upstream resources to sale options by unit
margin. It schedules contractual minimum-take quantities before discretionary
positive-margin volume and respects:

- resource availability and configured maximum take;
- minimum take;
- sale-option capacity;
- resource and destination TSO-access requirements;
- purchase cost, sale price, and variable route/sale cost.

The current model is a separable linear allocation model. It is exact for that
model but does not yet represent shared pipeline-edge capacities across several
simultaneous routes.

### Route Optimization

The route engine uses a capacity-filtered minimum-cost path model. A network edge
is eligible only when:

- the edge is enabled;
- available capacity covers the requested quantity;
- the company has access to the edge TSO, when a TSO access set is supplied.

The objective is minimum aggregate tariff in GBP/MWh. The output also reports
the route bottleneck capacity.

### Capacity Booking Optimization

The capacity engine selects the lowest-cost combination of capacity products
that covers required capacity. It supports:

- fixed booking cost;
- throughput-linked variable cost;
- firm and interruptible products;
- optional exclusion of interruptible capacity.

The MVP performs exact subset enumeration and is intended for a curated product
set. A larger auction universe should later use a mixed-integer solver.

### Contract Dispatch Optimization

The contract engine schedules minimum-take quantities first, then fills remaining
demand with positive-margin discretionary volume. It reports:

- mandatory and discretionary quantities by contract;
- unit margin and PnL;
- unmet minimum take;
- unserved demand and unused resource volume.

## Validation

Focused tests:

```bash
pytest -q tests/optimization tests/api/test_optimization_routes.py
```

Full repository acceptance:

```bash
ruff check .
pytest -q tests
```

## Next Model Extensions

The next optimization increment should add:

- shared edge-capacity constraints across a portfolio of routes;
- multi-period storage injection and withdrawal decisions;
- gas-day nomination and renomination windows;
- take-or-pay accumulation across contract periods;
- stochastic price and outage scenarios;
- CVaR or other downside-risk objectives;
- solver adapters for HiGHS, OR-Tools, SCIP, or Gurobi;
- Web scenario controls and explainable result panels.
