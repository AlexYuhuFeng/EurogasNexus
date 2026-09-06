# Commercial Decision Workflow Specification — CR-08

Status: accepted CR-08 architecture. This document owns the consolidated
Portfolio → Resource → Route → Scenario → Optimization → Review workflow.

## 1. User jobs

Professionals need to answer: what resources are available; where can gas
move; what is route cost and destination value; what is indicative margin;
which constraints bind; what changes under scenarios; how should volume be
allocated; why did the optimizer choose an allocation; what is attributable
PnL; what evidence is weak; and what should a human reviewer inspect.

## 2. Current fragmentation (audit)

Audit of `ContractWorkbench`, `ScenarioWorkspace`, `ReviewWorkspace`,
`MarketPositioningWorkspace`, portfolio model, optimizer DTOs and tests:

- Portfolio currently has two technical pages: Resource Terms and read-only
  positioning context. They do not share a resource overview or route
  comparison surface.
- `ContractWorkbench` is a professional resource editor but its impact view
  is dependent on current optimizer state; resource identity is contract id.
- `ScenarioWorkspace` combines route list, economics inputs and both
  optimizer/recommendation actions in one page; there is no explicit
  scenario identity or base-vs-scenario comparison.
- `ReviewWorkspace` consumes current mutable frontend result state rather
  than a persisted review pack; decision states are only
  `accepted|rejected|needs_attention` and no run immutability is shown.
- `MarketPositioningWorkspace` uses order/PnL vocabulary, inconsistent with
  research-only product boundary.
- Route candidates are displayed as name + TSO access only in Scenario;
  capacity, tariff, cost and margin are not visible in a comparison table.
- Optimizer result is visible in Scenario/Review but binding constraints,
  unallocated-volume reasons, alternatives and attribution are fragmented
  across components.
- TSO access blockers exist in the model but are not visually first-class in
  route comparison.
- No scenario persistence or manifest; scenarios are transient contract
  draft numbers.
- No portfolio identity exists; the real operating scope is the resource
  pool. CR-08 does not invent a portfolio master.

## 3. Portfolio model

Portfolio is the current persisted resource pool/operating scope. No fake
portfolio names are created. Portfolio tasks:

- `OVERVIEW`
- `RESOURCES`
- `ROUTES`
- `EXPOSURE`

All share trader context and selected resource.

## 4. Resource semantics

Stable `resource_id` is the source of truth. The editor displays identity,
quantity, pricing, delivery, tolerance, capacity/access, costs and evidence
separately. Current backend supports one current availability concept
(`available_quantity_mwh_per_day`); UI labels it precisely as “current
contractual/resource availability”, not technical vs commercial
availability.

## 5. Cost stack

Resource cost stack is presented from persisted DTO fields only:

- contract cost;
- variable cost;
- tolerance risk allowance;
- balancing allowance where available;
- all-in source cost.

No authoritative addition is recomputed in React beyond displaying the
backend-provided values that already compose the optimizer input.

## 6. Route semantics

`RouteCandidateDTO` remains the route identity contract. Route comparison
shows origin/destination, route name, required TSO access, source systems,
route legs count and whether route recommendation exists. Backend-owned
economics remain the only authoritative economics.

## 7. Route feasibility

UI-derived feasibility labels are conservative and evidence-bound:

- `FEASIBLE` — recommendation/allocation exists with no missing inputs;
- `FEASIBLE_WITH_WARNINGS` — result exists with warnings;
- `BLOCKED` — TSO access missing, no recommendation, or pool blockers;
- `UNKNOWN` — no economic result yet.

Unknown is never displayed as feasible.

## 8. TSO / capacity / tariff rules

Missing required TSO access is a visible blocker chip on every route row.
Unknown capacity is `n/a`; route decision logic remains backend fail-closed.
Tariff provenance stays in the backend route/tariff surfaces.

## 9. Scenario model

CR-08 establishes typed structured scenario state in the frontend and the
optimization-run manifest already persisted by backend. Scenarios are named
BASE, UPSIDE, DOWNSIDE, CUSTOM, but direction is explicit text, not
automatic market meaning. Full scenario table persistence is deferred.

## 10. Scenario shocks

Structured overrides only:

- destination sale price shift (GBP/MWh);
- resource volume shift (MWh/d);
- source cost shift (GBP/MWh);
- route capacity reduction (%);
- tariff/cost shift (GBP/MWh).

No generic “shock everything” control.

## 11. Optimizer inputs

The existing persisted optimizer request remains the input contract. The UI
shows resource count, sale options, readiness blockers, route candidates and
the current scenario assumptions before run.

## 12. Optimizer outputs

Totals: allocated volume, unallocated volume, net indicative PnL, route
costs, warnings. Allocations: resource, destination/option, quantity, cost,
margin. All values are backend-owned.

## 13. Constraints

Binding constraints are derived from backend warnings/blockers and displayed
as a compact table. If a blocker exists, the corresponding route/resource is
marked blocked. No constraint is silently relaxed.

## 14. Infeasibility

If `resourcePoolResult.status` is not `OPTIMAL`/`FEASIBLE`, the UI shows a
professional `INFEASIBLE/BLOCKED` state with missing inputs, not a normal
allocation table.

## 15. Attribution

The optimizer result exposes per-allocation `net_pnl_gbp_per_day`,
`net_margin_gbp_mwh` and route cost. CR-08 displays resource attribution and
route attribution directly from those backend fields. No FX/balancing
attribution is fabricated where the current backend does not isolate it.

## 16. Alternatives

Alternative comparison is presented as adjacent rows: selected/highest
margin allocation, other allocations, blocked candidates. Labels are
“Optimizer-selected allocation”, “Alternative allocation”, never “Best
Trade”.

## 17. Review evidence

The review panel consumes persisted/current run references (resource ids,
route ids, optimizer run id, warnings, assumptions, source refs) rather than
mutable frontend objects. Review does not alter optimizer results.

## 18. Human review states

Non-execution states only: `accepted`, `rejected`, `needs_attention`. UI copy
explicitly says analytical/governance review, not trade approval.

## 19. Cross-workspace handoffs

- Portfolio → Market (`Show market context`);
- Portfolio → Strategy (`Inspect in Strategy Lab`);
- Scenario → Review (`Open in Review`);
- Scenario → Market (`Inspect market assumptions`);
- Review → Scenario (`Reopen scenario`).

Stable ids/context are passed; no large objects are serialized.

## 20. Persistence

Existing backend persistence is reused: upstream contracts/resource pool,
route candidates, optimization runs, review decisions. Scenario persistence
and a new portfolio master are deferred.

## 21. Reproducibility

Optimization runs remain immutable and backend-owned. CR-08 does not mutate
historical runs. Determinism remains covered by existing optimizer tests.

## 22. Precision

UI displays backend values without changing precision. MWh displayed with up
to 2 decimals, GBP/MWh 2–4 decimals from API, totals rounded only for
display. No intermediate solver inputs are recomputed.

## 23. Accessibility

Task tabs keyboard navigation, labelled forms/tables, visible focus,
non-color status, error summaries, units visible. Route data remains
accessible without a map.

## 24. Performance

Overview renders bounded lists (resources/routes capped at 25/50). Existing
optimizer calls are user-triggered. No N+1 API calls are introduced.

## 25. Limitations

- No persisted scenario table in CR-08.
- No solver shadow prices/dual values exposed.
- Attribution limited to components already isolated by backend.
- No true portfolio master identity; current resource pool is the scope.
- No visual-regression runner locally.
