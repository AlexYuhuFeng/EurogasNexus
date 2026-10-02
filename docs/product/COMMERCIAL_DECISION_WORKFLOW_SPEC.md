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

Current implementation note (Decision workspace, Wave 9 and the September 30
input-provenance correction). The Scenario task's panel no longer edits "the
economics the actions send". Both of its actions compose from the persisted
resource-pool read (`GET /api/route-cost/resource-pool/options`): resource
volume, cost, location and TSO access; sale-option price, route cost and
capacity with each value's own currency and unit; and, for the comparison,
the first saved upstream contract's gas year. The one draft value the panel
may still edit is the annual financing rate the pool optimiser uses when no
saved upstream contract carries one, and the panel states that provenance
live next to the control. `nbp_sale_price_gbp_mwh` and
`physical_exit_sale_price_gbp_mwh` remain declared on the draft for import
back-compatibility, but nothing consumes them and they are not part of the
persisted contract payload, so they are neither editable nor shown as money.

## 10. Scenario shocks

Structured overrides only:

- destination sale price shift (GBP/MWh);
- resource volume shift (MWh/d);
- source cost shift (GBP/MWh);
- route capacity reduction (%);
- tariff/cost shift (GBP/MWh).

No generic “shock everything” control.

## 11. Optimizer inputs

The existing persisted optimizer request remains the input contract:
`PortfolioOptimizationScenario`, composed in the client by
`buildResourcePoolOptimizationRequest` from the persisted resource-pool read
(the resource and sale-option rows are passed through by reference) plus one
rate. The rate is the first saved upstream contract's
`annual_financing_rate_pct` when it carries one, otherwise the Scenario
panel's draft fallback; it is percent per year used for early-cash value
(`base_cost * rate / 100 * lag_days / 365`) and is never converted or scaled
in the client. The UI shows resource count, sale options, readiness blockers,
route candidates and the financing-rate provenance before run.

Compare Options (`buildRouteRecommendationRequest`) sends only the persisted
read: source and target points, the total pool volume, the first saved
upstream contract's gas year, and the sale-option candidates with their own
price/currency/unit and route-cost/currency/unit. No contract-draft value is
part of that request.

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
- The strategy lab's own result key (`strategyResultContextKey`) is stamped
  only by a successful answer and now carries the payload identity
  (section 27). The evaluate action exists in the model but no surface in the
  current build starts it; the strategy views read persisted runs and the
  summary, not this in-memory result.
- The Scenario panel only offers the one draft value an action consumes (the
  annual financing-rate fallback). `delivery_quantity_mwh_per_day`,
  `contract_price_gbp_mwh`, `delivery_tolerance_pct`,
  `nomination_tolerance_pct` and `screen_sale_cash_lag_days` are read from the
  persisted resource-pool rows; `nbp_sale_price_gbp_mwh` and
  `physical_exit_sale_price_gbp_mwh` have no consumer and are not persisted.
- No implicit FX: sale-option prices and route costs travel with their own
  currency and unit; the client never converts them, and no client-side FX
  rate is invented.

## 26. Action gate, run lifecycle and result provenance

Added 2026-10-01 (bounded repair of the Decision workspace's two governed computes).
An authenticated inspection found an enabled `Compare Options` whose click
produced a 403 no surface showed; an automatic pool run was also refused.
Parent verification found the local account has multiple persisted roles and
the `optimization.run` capability despite its ADMIN display label. The observed
refusal was `origin_not_allowed`, not a commercial-role denial. The local
launcher omitted the web client's explicit loopback origin. Administration-only
capability refusal is a separate tested case, not this live account's state.
Tracing the
report also found the shared result context key was stamped when a run
*started*, so a failed retry after a context change made the previous result
read as current, and one key served both actions, so a route comparison could
relabel a pool result.

`clients/web/src/app/model/decisionActionModel.ts` now owns the three rules:

- **Gate.** A run is offered and issued only when the identity's declared
  ExperienceProfile composition holds the capability the action's backend floor
  requires (`optimization.run`), the action's own inputs are ready, and no run of
  the same action is already in flight. The automatic pool run uses the same
  rule as the header action, so an identity without the capability is never sent
  a request on the user's behalf. This is presentation only: the backend
  re-authorises every request, the route registry is unchanged, and an absent or
  unparsed profile fails closed (the action is withheld, and the reason is shown
  as text rather than only in a tooltip a keyboard user cannot reach).
- **Lifecycle.** Each action has its own `idle -> pending -> success | failure`
  lane. Pending disables the control and refuses a duplicate submission; a
  refusal, validation failure or transport failure is rendered next to the
  action through the product error taxonomy with the backend's correlation id
  when it supplied one, and never as a raw exception string. These two actions
  no longer write the store's global `error` string either, because that string
  is rendered raw by the map's catch-all alert.
- **Provenance.** A result is stamped with the trading-context key of the
  request that *succeeded* - not the context in force when it started, and not
  by the other action. Both lanes are cleared with the identity. Every surface
  that presents these results (Scenario, Optimize, Review, Portfolio routes and
  the map's decision rail) either withholds them or names them stale once the
  context they were computed under no longer matches the context on screen;
  `selectScenarioRouteEconomics` and `classifyRouteFeasibility` are fed only
  results provenanced to the current context, so no stale payload is presented
  as a current verdict.

The request builders, their inputs and all arithmetic are unchanged, as are the
backend's permission, commercial-access and fail-closed gates. No page, panel or
datastore was added, and no execution, nomination or settlement semantics: both
actions remain analytical decision-support computations over the persisted
resource-pool read.

The automatic pool run is retained as it was found: for an identity that holds
the capability, the optimiser still runs automatically when the pool inputs'
signature changes (no click required), now through the same gate and the same
provenance; for an identity that does not hold it, no request is issued at all.

## 27. Input identity: result provenance beyond the trading context

Added 2026-10-02 (bounded follow-up to section 26). Parent/user direction:
changing a contract revision, scenario inputs or market context must invalidate
or clearly mark old results on **all** consumers, not only Scenario. Repository
inspection showed section 26's provenance key covered only `gasDay|product|hub`,
while the two governed computes are composed from the persisted resource-pool
read: an edited saved contract, a refreshed pool or market read, or a changed
financing input left the previous result displayed as current on the Portfolio
PnL strip, the Optimize task, the map's decision rail, Review and Scenario.

`clients/web/src/app/model/decisionResultProvenance.ts` now owns the input
identity, and `decisionActionModel.ts` keeps only the gate and lifecycle rules.

- **What is bound.** The caller-known effective inputs, canonicalised
  deterministically: the exact request object the client will send, the identity
  tokens of the saved upstream contracts the pool read is composed from
  (`contract_id@edit_token`, falling back to `updated_at_utc`, else a stated
  `unavailable` marker) and the market-read marks behind the sale options
  (`option_id`, price, observation instant, source system/reference, freshness,
  quality score, simulated flag). Object keys and explicitly unordered string
  collections (`required_tso_access`, `accessible_tsos`, ...) are sorted; every
  other array keeps its order; numbers, `null`, `false` and `0` are preserved (a
  recorded `null` is not an absent field).
- **What each action binds** (inventory of the request builders):
  - `Optimize Resource Pool` (`buildResourcePoolOptimizationRequest`): the
    persisted resource-pool read (all resources and sale options, by reference),
    plus `annual_financing_rate_pct` resolved as the first saved contract's rate,
    else the draft fallback; the request is refused, and no key composed, when
    neither records a rate.
  - `Compare Options` (`buildRouteRecommendationRequest`): the first resource's
    point and TSO access, the sale-option candidates (price, cost, capacity,
    access), the summed pool volume and the first saved contract's `gas_year`.
  - the strategy evaluation: the payload actually sent (scenario resource
    context, price observations, components, risk control, and the shadow PnL
    the run continues from).
- **What must not invalidate.** A draft field no request consumes (section 25's
  list) cannot change either identity, and a re-read that returns the same values
  yields the same identity by design. The draft financing rate is part of the
  optimiser identity only while it is the rate the request carries; when a saved
  contract rate governs, editing the draft is inert.
- **The one rule.** A run is stamped with `scope::trading-context::input-identity`
  only when it **succeeds**; `decisionProvenanceMismatch` marks a held result
  stale unless its key equals the key of the inputs the caller now knows, and an
  unknown key on either side is stale (a request that can no longer be composed
  has no current key, so the held result cannot be vouched for). The store
  stamps only what the caller passed at request time, so a run completing after
  an edit stays historical rather than being published against the new inputs.
- **The consumers.** `usePortfolioDecisionModel` derives
  `currentResourcePoolResult`, `currentRouteRecommendation` and
  `currentStrategyResult` (null while stale) and computes the Portfolio
  PnL/margin, sale/purchase/route-charge and first-strategy-target values from
  them. Scenario, Optimize, Review, the Portfolio overview/routes and the map's
  decision rail read those gated values, not the raw store lanes; a withheld
  payload is named stale and never replaced by `0` (the Optimize "unallocated"
  figure is `n/a`, not `0`, while no current run exists). Warnings and the
  review evidence pack are gated with the same rule. The strategy key is now
  stamped only by a successful answer, and the map's strategy signal shows
  `Stale` instead of `Live` while it does not match.

The strategy evaluation also carries its identity generation, like the two
governed computes: an answer that lands after a sign-out or a session
invalidation is dropped whole - no result, metadata, `loading`/`error` write or
summary/runs follow-up - and the caller receives no answer, so it stamps no
provenance. An evaluation started with caller overrides is stamped with the
identity of the payload actually sent; the model's current key is composed from
the default payload, so an overridden run is withheld as stale rather than
relabelled current. That is the conservative posture, not an equivalence claim
between the two payloads, and no surface in the current build passes overrides.

Limits, stated so they are not overstated:

- The backend exposes no immutable snapshot, revision hash or read token for the
  composed resource-pool payload or the market rows behind it. The identity
  proves which inputs the caller sent and believed; it is not server-verified
  proof of what the backend read or executed against, and no hash is presented
  as such.
- A saved row exposing neither an edit token nor `updated_at_utc` contributes a
  constant marker; the client cannot prove such a row unchanged.
- The route comparison request still falls back to `manual_cost: 0` for a sale
  option that carries no route cost (the existing backend contract default); the
  persisted read normally carries one.
- No backend route, permission, schema or datastore changed. This is a client
  provenance posture over the existing request contracts; the automatic pool run
  still starts from the existing input signature, and a result that goes stale
  is re-run by the user's action.
