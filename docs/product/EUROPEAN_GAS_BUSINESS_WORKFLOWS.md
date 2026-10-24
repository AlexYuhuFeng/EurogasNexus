# European gas business operating model and redesign acceptance

Owner direction: 2026-10-23. Target model; unsupported rows are not product claims.
Architecture authority: [business workflow redesign](../architecture/decisions/2026-10-23-business-workflow-redesign.md).
This refines, rather than discards, the existing [business acceptance matrix](TRADING_BUSINESS_ACCEPTANCE.md).

## Start with the business day

The trading desk begins with obligations, available rights/resources, delivery
windows, exceptions and open decisions. A gas day is an explicit calendar interval,
not a browser date. Valuation time, observation availability time, trading session
and delivery interval are separate. Days around daylight-saving changes require
calendar resolution; daily energy, hourly rate and total-period energy are not
interchangeable without the declared duration/profile.

The product must answer, in order:

1. What must we deliver or decide, for which delivery period, and by when?
2. What quantities and rights can we actually use, and what remains uncertain?
3. Which alternatives are physically, contractually and financially feasible?
4. What are their incremental economics and cash consequences on a common basis?
5. What changed since the last plan, who reviewed it, and what evidence supports it?

The UI is a workbench for answering these questions, with linked market, physical,
portfolio and research views. It is not a dashboard assembled from API endpoints.

## Business models and complete work units

| Business model | Essential objects and dependencies | Desk work unit | Acceptance result |
| --- | --- | --- | --- |
| Pipeline supply and downstream sale | Versioned supply/sale terms; delivery profiles; index/fixed pricing; delivery points; booked capacity, access rights, route tariffs, losses, tolerances and payment terms | Prepare tomorrow's resource plan, compare permitted destinations, record the selected plan for review | Shared energy conservation, binding constraints, incremental netback and full cost reconciliation; explicit unallocated quantity and reasons |
| Day-ahead / within-day adjustment | Prior plan, observed commitments and remaining availability; matching products; quotes versus indices; latest admissible observations; capacity windows and balancing assumptions | Investigate deviation or price move and compare the incremental adjustment against keeping the plan | Before/after quantities, changed constraints, incremental cost/margin, deadline and evidence; no double-use of the same resource |
| Location/time/product-basis research | Typed legs with venue/product, hub, delivery interval, quote side/mark type, units/currency, source and time availability; transport/carry assumptions where economic | Compare prices or test a hypothesis, then explicitly hand a supported result to a commercial scenario | Price expression and strategy semantics distinguished; mismatched periods/units exposed; historical comparability and model limits visible |
| Portfolio planning and exposure | Supply, sale and capacity obligations; separately evidenced imports/positions; scenario allocations; cash schedule, FX and funding assumptions | Assess the whole book over a chosen horizon, identify concentration/shortfall, compare scenarios | No false inventory ledger; contractual, committed, indicative and confirmed states separated; quantity and cash reconciliation across all models |
| LNG cargo / regas / downstream disposition | Cargo and purchase terms; arrival/discharge windows; terminal access, slot and inventory constraints; send-out profile; boil-off/losses; shipping/regas/storage/downstream rights and sale terms | Assess a cargo disposition or delayed-arrival scenario, compare title-transfer versus regas-and-deliver where supported | Cargo-to-send-out energy lineage; slot/capacity feasibility; netback denominator declared; dated cash/financing separate from profit; no implied slot booking |
| Storage flexibility where supported | Inventory evidence, injection/withdrawal limits, losses, tariffs, calendar, market alternatives and terminal inventory constraints | Compare retain/inject/withdraw research scenarios | Inter-period inventory conservation and boundary conditions; no operational dispatch or nomination submission |
| Tender / contract structuring | Versioned tender constraints, minimum commitment/take, optionality, validity, credit and delivery terms, full cost/risk assumptions | Prepare a bid ceiling or structured offer for internal review | Explicit objective, downside cases, feasibility and approvals; not available merely because a route-cost endpoint exists |
| Data quality / access operations | Source rights and freshness, series coverage, ingest lineage, affected run/case references, identity and group policy | Diagnose a blocked business decision and recover its inputs or route the incident | Business impact is visible; authorized remediation leaves an audit trail; no admin bypass of commercial rights |

## Quantity, economic and time invariants

- Contracted daily quantity is not reconciled remaining availability. Until a
  source-backed commitment/position model exists, show a declared scenario quantity
  and its evidence limitations. Never subtract unrelated imported screen orders
  merely because their hub labels match.
- An allocation inside one hypothetical scenario must conserve resources. Two
  alternative scenarios do not consume real inventory. A confirmed commitment
  belongs to a separately authorized, evidenced lifecycle; no execution is added.
- Example acceptance invariant: 100 MWh declared available with 40 MWh already
  committed on the same reconciled resource/interval leaves at most 60 MWh for
  additional commitments. Without reliable commitment evidence, remaining quantity
  is unknown, not automatically 100. This is an acceptance example, not a claim of
  an implemented commitment ledger.
- Purchased, transported, regasified and sold energy can differ due to losses.
  Every unit cost states its denominator. Applying a sale-price spread to purchased
  energy instead of delivered energy must be caught by an independent test case.
- Gross margin, contribution after incremental costs, allocated full-cost margin,
  MTM, realized PnL, cash balance, working capital and NPV are distinct outputs.
  Collateral cash is not automatically an expense; financing must not be counted
  both in a price and in a separate cost leg.
- Prices carry quote side, indicative/executable status, source timestamp,
  publication/availability time and delivery validity. Mid/index marks cannot
  silently become executable bid/ask. Historical selection must avoid look-ahead.
- A valid slot or capacity quantity needs its interval, direction, holder/right,
  status and applicable constraints. A terminal name alone establishes no access.
- Counterparty/legal amendments and external operational actions remain outside
  this product's internal-record and decision-support boundary.

## Workspaces built around responsibility

**Trader desk:** a prioritized daily queue and business-day plan, with quantity
and deadline context. Selecting a resource or exception opens linked alternatives,
costs, constraints and evidence in the same task. The map is available when route
or physical context matters, not a compulsory entry screen.

**Portfolio / structuring:** a shared book of versioned obligations and scenario
availability, with horizon, currency and valuation basis. Drill down from a
portfolio result to contributing contracts, capacity, cargoes and model outputs.
Do not present a research resource pool as a reconciled position book.

**Researcher:** instrument discovery → hypothesis/expression → signal and sizing
model → point-in-time dataset → experiment → comparison → evidence publication.
Simple and advanced workflows share typed semantics; advanced does not mean free
text identifiers. Users control their own strategy sharing (PRIVATE default,
PUBLIC read or named groups), independently of their presentation work mode.

**Reviewer:** a proposed decision, its changes from the prior version, major
assumptions/constraints, outcomes and evidence. The initial view answers what is
being proposed and why; detailed runs are drill-downs. An author's own comment
must not be labelled independent approval.

**Data operator / administrator:** two distinct responsibilities even when one
person holds both. Data operations shows incidents and commercial impact;
administration shows access, groups, deployment and audit. Neither grants implicit
access to licensed prices or private research.

## API/SDK and client contract

Existing canonical services remain authoritative. Introduce no second frontend
business model. Before implementing a new object, map it to current ontology,
persistence, lifecycle and APIs; identify actual gaps explicitly.

Every workflow binds a business objective, scope/interval, stable object IDs and
versions, selected evidence, explicit assumptions and model version. Browser,
desktop, SDK and batch evaluation must produce equivalent domain results from the
same inputs. The UI composes these services, saves drafts safely and explains
blockers; it does not calculate its own commercial answer.

Current foundations to reuse, subject to their exact boundaries:

- `domain/route_cost/resource_pool.py`: constrained single-scenario allocation,
  not a temporal portfolio commitment ledger.
- `domain/route_cost/lng_regas.py`: explicit regas readiness checks, not a complete
  cargo scheduling/custody/settlement system.
- `domain/research/lng_cash_valuation.py` and `cash_valuation.py`: explicit dated
  cash valuation, not automatically netback, margin or complete LNG economics.
- `domain/market_positioning.py`: read-only imported observations and indicative
  snapshots, not a unified internally reconciled book.
- `domain/strategy_lab/evaluation.py`: the legacy OCM/day-ahead paper model,
  not a generic index or multi-leg strategy engine.
- Existing frozen versions, snapshots, decision cases, owner sharing and
  entitlement checks: preserve and connect their lineage; do not duplicate them.

## Implementation order and acceptance

1. Reconcile quantities, calendars, pricing/cost semantics and object ownership
   across the business models; define a capability matrix with actual evidence.
2. Recompose the daily trader/portfolio workflow and shared context around one
   complete pipeline/day-ahead/within-day decision path.
3. Connect LNG cargo/regas economics using the same quantity, cost, evidence and
   review contracts, with explicit model-specific constraints.
4. Rebuild research and review workflows around typed supported models and frozen
   evidence, then data-operator/admin work queues and impact views.
5. Apply the common interaction system and test complete persona outcomes,
   negative cases, EN/ZH, keyboard flow, browser/native parity and numerical cases.

Ship criteria include business correctness and coherent interactions. Beautiful
screens, navigation presence, unit-test counts and successful synthetic runs alone
cannot prove commercial delivery. External provider/customer/regulatory and
platform release gates remain explicit; regional transport is deferred.
