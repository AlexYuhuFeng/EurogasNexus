# Resource Pool And EFET-Style Contract Contract - EN

## Purpose

Eurogas Nexus treats purchase contracts as inputs to a portfolio resource pool.
The home cockpit and route optimizer must not be designed around one selected
purchase contract and one selected route. A trader owns a set of physical,
virtual, and LNG resources; the product evaluates where that pool can be sold
given contract terms, TSO access, terminal access, capacity, tariffs, live sale
prices, settlement timing, and risk controls.

## Resource Pool Rule

All active purchase contracts contribute available resource to a pool:

- beach or upstream offtake contracts;
- LNG regas or terminal title-transfer resources;
- hub purchase contracts;
- imported screen or broker purchase observations when persisted as portfolio
  records;
- customer-entered capacity rights and route eligibility.

The optimizer ranks sale options by executable marginal netback, not by the
contract that happened to create the volume. If the cheapest path has only partial capacity,
the optimizer allocates that capacity first, then re-evaluates the remaining gas
against local sale, other hubs, alternate cross-border paths, storage/LNG
options where modelled, or no-sale/hold states. It must not force all remaining
gas through an uneconomic reroute.

## PnL Rule

PnL is calculated in this order:

1. Pool-level sale allocation and total expected PnL.
2. Route-level contribution: quantity, sale price, route cost, capacity limit,
   early cash value, warnings, and source references.
3. Contract-level attribution: allocated quantity back to each purchase
   contract, cost basis, variable cost, tolerance/balancing allowance,
   settlement cash timing, and attributed PnL.

The UI must show total portfolio result first, then route cards, then
contract-level attribution. Contract-level PnL is an attribution of a pool
decision, not a separate route decision for every contract.

## Home Cockpit Rule

The home screen is resource-pool-native:

- map markers identify resource locations, not only network nodes;
- all recommended sale paths are visible together;
- right-side cockpit cards list each recommended path with allocated quantity,
  marginal netback, PnL contribution, capacity constraint, TSO access state,
  and warnings;
- the total PnL card aggregates all selected paths;
- blocked paths remain visible with explicit blockers such as capacity
  shortfall, missing TSO access, missing tariff row, stale data, missing price,
  missing terminal slot, or missing credential;
- detailed source, contract, strategy, and tariff investigation lives on
  separate pages so the home map stays clean.

## EFET-Style Contract Entry Rule

Contract entry should follow an EFET-style term-sheet structure so traders can
capture real commercial terms without turning Eurogas Nexus into an ETRM.

Required contract sections:

- Agreement: contract id, counterparty label, internal book/portfolio,
  governing form, source references, effective date, status.
- Product and term: gas year, delivery period, product shape, daily/monthly
  volume, make-up or carry-forward rule where applicable.
- Delivery: delivery point, balancing zone, physical or virtual delivery mode,
  title-transfer point, entry/exit requirement, nomination requirements.
- Quantity and tolerance: MDQ, minimum take, tolerance, nomination tolerance,
  interruption/force-majeure flags.
- Price: fixed price, daily index, monthly index, formula, Brent-linked, ICIS,
  Platts, TTF, NBP, other licensed index, currency, unit, premium/discount.
- Costs and allowances: variable cost, broker/execution fee, clearing fee,
  imbalance/balancing allowance, fuel/loss, terminal/regas fee, storage fee.
- Capacity rights: owned entry/exit capacity, TSO access, terminal access,
  slot/window, route eligibility, capacity product, firmness, expiry.
- Settlement and cash: settlement frequency, invoice lag, payment lag,
  screen-sale cash lag, early cash value eligibility, financing rate.
- Restrictions: permitted sale markets, prohibited TSOs/routes, delivery
  restrictions, internal risk limits, data-quality requirements.

The contract model must store these terms in PostgreSQL and expose them through
backend `/api` and SDK surfaces. Web and desktop clients do not read contract
tables directly.

## Current Release Support And Gaps (2026-09-01)

The current PostgreSQL/API/Web vertical slice supports:

- controlled resource type, resource id/name, counterparty evidence, gas year,
  delivery/title/beach/physical-exit points, daily available quantity,
  delivery and nomination tolerances, price basis, and settlement timing;
- resource cost, balancing allowance, variable cost, terminal/regas fee, and
  fuel/loss percentage. Variable plus regas cost flows into the optimizer's
  variable unit cost. Fuel/loss applies the delivered-unit uplift
  `base_cost / (1 - loss_fraction) - base_cost`;
- entry/exit capacity assumptions, terminal access evidence, allowed exit
  points, eligible sale modes, source evidence, and human-review state;
- API readback of the full notes evidence plus typed cost fields. PostgreSQL is
  the runtime source of truth; clients refresh resource terms and pool options
  after persistence;
- per-resource route eligibility through `eligible_resource_ids`, preventing a
  resource from borrowing another contract's permitted destination;
- resource-specific screen-sale cash lag in early-cash valuation.

Not yet supported in this vertical slice:

- minimum-take/take-or-pay, make-up and carry-forward obligations;
- effective-date/version history and status-based gas-day selection;
- governed mapping and enforcement of persisted eligible sale modes against
  route-candidate business models (allowed exit points are enforced now);
- structured currency/unit/premium fields beyond the current GBP/MWh resource
  cost contract;
- interruption/force-majeure logic, capacity product/firmness, invoice lag, and
  prohibited-route/TSO rules as typed optimizer inputs;
- typed SDK list/upsert methods for Resource Terms.

These gaps must remain visible in UI/docs and must not be approximated silently.
The separate phase-two optimization package contains minimum-take primitives,
but it is not yet the PostgreSQL-backed Resource Terms allocation path.

## Data Policy

Missing DB records must produce explicit empty states or blockers. The product
must not invent portfolio resources, sale prices, capacity, route costs, or PnL
for operational screens. Tests may create isolated source-shaped fixtures.

## Boundary

This contract supports decision-making and scenario review. It does not create
orders, nominations, bookings, trade captures, confirmations, invoices, or
official trading recommendations.
