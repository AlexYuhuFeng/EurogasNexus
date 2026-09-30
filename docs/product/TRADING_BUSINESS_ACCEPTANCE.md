# European Gas Trading Business Acceptance

Status: required target scope from the October 1 user direction; not a claim
of implemented coverage or commercial approval. This extends the user jobs in
[Commercial decision workflow](COMMERCIAL_DECISION_WORKFLOW_SPEC.md), and is
subject to the existing [release gates](../release/GA_RELEASE_GATES.md) and
[pilot blocker register](../release/FIRST_CUSTOMER_PILOT_PLAN.md).

## Product Boundary

Support preparation, valuation, monitoring, internal commercial records and
human-reviewed decisions. Do not submit tenders, execute exchange or bilateral
trades, reserve capacity externally, send nominations or settle payments.
Internal contract changes must not imply amendments to a legally binding
agreement or a connected counterparty system. Power remains future scope.

The following are business acceptance scenarios, not requests for one page per
scenario. Compose existing Portfolio, Market, Decision Center and Strategy Lab
tasks around shared ontology-backed services. Presentation persona never grants
backend authority. Product terminology and legal obligations require expert
review for the actual customer, jurisdiction, agreements and delivery boundary.

## Required Journeys

| Journey | Required commercial inputs and constraints | Decision and evidence to demonstrate |
| --- | --- | --- |
| Pipeline-gas or LNG tender bid preparation | Versioned tender terms, quantity and delivery profiles, pricing/index formula, currency, delivery point and period, payment schedule, validity, tolerances, minimum commitments, transport or shipping, capacity/access, losses, applicable fees/taxes, financing and credit assumptions | Complete cost stack, maximum bid or break-even on explicit objective, cash schedule, margin versus discounted cash value, downside sensitivities, physical feasibility and reviewable assumption pack; never submit a bid |
| Daily management of awarded supply | Linked contract/resource entitlement and remaining availability, hub versus beach delivery, daily flexibility, market tenor/time basis, confirmed capacity and TSO access, balancing regime, payment timing and credit constraints | Compare retain, redirect or sell alternatives against the same inventory and valuation time; show incremental and allocated costs separately, resource conservation, blocked routes, unresolved obligations and decision history |
| LNG regas and downstream sale | Cargo and terminal identities, slot/window, vessel/terminal compatibility where required, unloading/storage/send-out constraints, purchased versus delivered energy, boil-off and other losses, shipping/regas/capacity costs, downstream access and payment dates | Trace cargo to slot to send-out to destination; coherent netback, margin and discounted cash value with explicit denominator; constraint and delay sensitivities; no fictitious terminal position or available slot |
| Contract, capacity, access and slot lifecycle | Gas supply/sale, transportation capacity, TSO access and LNG regas rights with stable IDs, effective dates, versions, counterparty references, units, costs, conditions and evidence | Authorised create/edit/retire workflow; validation, concurrency handling and audit trail; referenced or active records cannot silently disappear; historical runs retain the version used; no external cancellation implied |
| Financing and clearing alternatives | Bank offer validity, borrowing currency, rate basis/day count, fees, collateral/haircuts, credit limits and dated cash needs; clearing, margin and settlement cash assumptions from the actual agreement/product | Compare all-in funding cost and liquidity requirements on a common basis; distinguish collateral cash from expense and initial/variation margin from trading profit; avoid double-counting financing already included in a price |
| Exchange and physical arbitrage research | Verified EEX/ICE product identity and specifications, delivery period, currency/unit, lot size, timestamps, executable versus indicative price status, bid/ask, fees, clearing/funding, transport and access | Rank feasible opportunities net of complete incremental costs; distinguish location, time and product-basis trades; show price age, leg mismatch and execution/liquidity assumptions; do not call an indicative index an executable offer |
| Strategy design, shadow run and comparison | Versioned strategy, linked contracts/resources, point-in-time inputs, cost/slippage/funding assumptions, common evaluation dates, constraints and risk budgets | Reproducible no-execution shadow runs, comparable curves and attribution, realised versus modelled cash/PnL labels, drawdown and exposure, leakage controls and frozen run evidence; no unaudited live-performance claim |
| Abnormality and risk monitoring | Source freshness/quality, prices/spreads, volume/capacity changes, outages, contract utilisation, cash/credit headroom and model confidence where supported | Explain affected resource and commercial impact, severity and evidence; deduplicate, acknowledge, assign and escalate under permissions; distinguish missing input from normal conditions and resolve alerts without losing history |

## Shared Capability Rules

- Reuse canonical IDs and relationships for contracts, resources, delivery
  points, capacity/access rights, cargoes, slots, cash-flow legs and model runs.
  Missing ontology concepts need an explicit reviewed mapping, not parallel
  frontend-only business types.
- Shared cash valuation, FX, energy conversion, cost allocation and risk
  capabilities own calculations in the backend. Each business model composes
  them with explicit versioned inputs, units, time conventions and provenance.
- Separate economic margin, dated cash flow, NPV, working-capital need,
  collateral and accounting/realised PnL. A financing allowance is not a
  substitute for an explicit payment schedule and discount basis.
- Costs must carry applicability, basis, currency, timing, source and treatment:
  incremental, sunk, allocated or contingent. Unknown is not zero. Scenarios may
  use explicit user assumptions, visibly qualified and preserved in run lineage.
- Real-source ingestion is subject to rights, product semantics and quality
  gates. Synthetic acceptance fixtures remain labelled and cannot establish
  provider rights, live liquidity or customer data acceptance.

## Persona and HMI Acceptance

Walk each applicable journey as trader, researcher, risk/reviewer and
administrator using persisted identities and scoped data. Verify both permitted
and denied actions, not only navigation labels. Administrator access alone is
not evidence that trader permissions work.

The primary view should expose the decision, binding constraints, essential
inputs and outcome. Keep evidence drill-down accessible without burying urgent
risks. Use comparable rows/tables for alternatives and consistent control
semantics. No irrelevant editable inputs, duplicated actions or empty metric
panels that look like completed analysis. Every money/energy value needs its
currency, unit, period and relevant valuation basis; percentages need a basis.

Test keyboard flow, focus recovery, validation near the affected field, loading,
empty, stale, failed and unauthorised states, EN/ZH and supported viewport sizes.
Changing contract version, scenario inputs or market context must invalidate or
clearly mark old results. Details disclosure cannot hide critical warnings.

## Evidence Required Before Claiming Support

For every journey record implemented modules/endpoints, ontology mappings,
actual permissions, input completeness, independently checked numerical cases,
API integration tests, populated persona walkthroughs, screenshots, deployment
SHA and remaining limitations. A menu item, DTO, unit test or illustrative
screenshot alone does not prove the business journey works.

Coverage is currently unverified against this expanded matrix. Existing cash
valuation and LNG primitives are foundations, not completed end-to-end journeys.
The implementation inventory must precede coverage claims and prioritise missing
business contracts before extra UI. Reconcile evidence with existing release
gates rather than creating a second approval mechanism.
