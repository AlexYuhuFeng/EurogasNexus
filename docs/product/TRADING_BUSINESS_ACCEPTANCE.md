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

## Implementation Inventory (read-only audit at `7ce64b0`)

This inventory records what the repository implements at baseline `7ce64b0`, not
what this document requires. It was produced by reading the backend
domain/application/API/storage layers and Alembic history, the ontology, the web
actions/models/components, the focused tests and the existing specs
([Commercial decision workflow](COMMERCIAL_DECISION_WORKFLOW_SPEC.md),
[Shadow runtime](SHADOW_RUNTIME_SPEC.md)). No tests, build or runtime mutation
were executed for this audit; "covered" below means a focused test file exists
at this baseline for the parent to re-run. Absence statements were traced across
`src`, `clients`, `tests`, `alembic` and `scripts` (symbol, table and route
references), not inferred from a single search; they are code-level absences,
and the contents of any customer runtime database were not inspected, so seeded
rows may carry values the models do not.

Levels used: **primitive** = domain math + unit tests only; **API** =
authenticated backend contract exists; **UI** = a product surface calls it;
**persisted** = runtime database rows; **reviewed** = persisted human decision or
acknowledgement with an actor. Each journey is labelled with the highest level
reached, which is not an end-to-end claim.

### Coverage by journey

| Journey | Highest implemented level | Primary code evidence | First broken link in the end-to-end journey |
| --- | --- | --- | --- |
| Pipeline-gas or LNG tender bid preparation | Primitive / API (adjacent only) | Route cost ([route_cost.py](../../src/eurogas_nexus/api/routes/public/route_cost.py)), cost observations incl. `AUCTION_BID` ([cost_observation.py](../../src/eurogas_nexus/domain/economics/cost_observation.py), [resolver.py](../../src/eurogas_nexus/domain/economics/resolver.py)), LNG readiness ([lng_regas.py](../../src/eurogas_nexus/domain/route_cost/lng_regas.py)) | No tender/offer/award object exists: `tender` appears nowhere in `src`, `clients`, `tests`, `alembic` or `scripts` — no concept, table, route or surface. No bid/break-even objective exists (only `MAX_DAILY_PNL`, [resource_pool.py](../../src/eurogas_nexus/domain/route_cost/resource_pool.py)); the cost stack has no tax, minimum-commitment or shipping item (explicit fees exist only as variable cost and regas fee fields), and the editor itself marks minimum take as not modelled ([ContractWorkbench.tsx](../../clients/web/src/components/ContractWorkbench.tsx)) |
| Daily management of awarded supply | API + UI + persisted job (no position ledger) | Min-cost-flow optimiser and tracked run ([resource_pool.py](../../src/eurogas_nexus/domain/route_cost/resource_pool.py), `POST /api/route-cost/resource-pool/optimize`), DB-composed inputs ([resource_pool.py](../../src/eurogas_nexus/application/resource_pool.py)), operating board ([CapacityWorkspace.tsx](../../clients/web/src/components/CapacityWorkspace.tsx)), nomination windows and day board ([nomination_windows.py](../../src/eurogas_nexus/domain/market/nomination_windows.py), [dayBoardModel.ts](../../clients/web/src/app/model/dayBoardModel.ts)) | No position/consumption ledger: availability is the static contract field `delivery_quantity_mwh_per_day` read per run; nothing records awarded volume, prior allocations or remaining availability across days, and the pool has no retain/hold alternative (sale options only; storage dispatch is a separate engine in [storage_nomination_composition.py](../../src/eurogas_nexus/application/storage_nomination_composition.py)). Conservation itself is implemented: allocated/unallocated are computed and warned (`PORTFOLIO_VOLUME_UNALLOCATED`), unknown TSO access or capacity fail closed ([test_resource_pool_optimization.py](../../tests/unit/test_resource_pool_optimization.py)) |
| LNG regas and downstream sale | Primitive + API (readiness) + persisted observations | Readiness (`POST /api/route-cost/lng-regas/assess`), composed dated-cash cargo economics ([lng_cargo_economics.py](../../src/eurogas_nexus/domain/research/lng_cargo_economics.py) over [cash_valuation.py](../../src/eurogas_nexus/domain/research/cash_valuation.py)), GIE terminal reads ([lng.py](../../src/eurogas_nexus/api/routes/public/lng.py)), storage/nomination masters ([storage_nomination.py](../../src/eurogas_nexus/db/models/storage_nomination.py)) | The cargo-economics composition has no caller (`compute_lng_cargo_economics` is referenced only by its own module and tests), and no cargo/slot/right entity is persisted: cargo, terminal and slot are request strings, and `LNG_SLOTS`/`LNG_AUCTIONS` connectors are skeletons ([cost_source.py](../../src/eurogas_nexus/ingestion/connectors/cost_source.py)). Cargo → slot → send-out → destination cannot be stored or replayed; readiness checks are caller-asserted |
| Contract, capacity, access and slot lifecycle | Persisted (gas contracts), read-only (capacity/access) | Contract upsert + list (`GET`/`POST /api/route-cost/upstream-contracts`), editor ([ContractWorkbench.tsx](../../clients/web/src/components/ContractWorkbench.tsx)), capacity read ([contracts.py](../../src/eurogas_nexus/api/routes/public/contracts.py), [CapacityContractBook.tsx](../../clients/web/src/components/CapacityContractBook.tsx)), TSO access read path ([resource_pool.py](../../src/eurogas_nexus/application/resource_pool.py)) | Lifecycle is missing. `upstream_resource_contracts` is overwritten in place by `contract_id` with no version, effective dates, retire/delete, concurrency check or audit record ([route_cost.py](../../src/eurogas_nexus/db/repositories/route_cost.py)); several editor fields are persisted only inside a JSON `notes` string ([contractPayload.ts](../../clients/web/src/app/contractPayload.ts)). Capacity profiles and `company_tso_access` have no create/edit/retire API at all — rows are written by an ops seed script ([seed_preview_runtime_data.py](../../scripts/ops/seed_preview_runtime_data.py)); no LNG slot entity exists. Ontology concepts `UpstreamResourceContract`, `CapacityProfile`, `CompanyTsoAccess` exist ([concepts.py](../../src/eurogas_nexus/domain/ontology/concepts.py), [bindings.py](../../src/eurogas_nexus/domain/ontology/bindings.py)) |
| Financing and clearing alternatives | Primitive (single scalar) | Early-cash value from `annual_financing_rate_pct` and payment/sale lag days ([resource_pool.py](../../src/eurogas_nexus/domain/route_cost/resource_pool.py)); explicit discount factors in the cash engine; financing-rate provenance disclosure ([scenarioInputProvenance.ts](../../clients/web/src/app/model/scenarioInputProvenance.ts)) | No bank offer, validity, rate basis/day count, fee, collateral, haircut, credit-limit or margin model exists. "Clearing"/"variation margin" appear only as glossary/vocabulary text ([glossary.py](../../src/eurogas_nexus/domain/glossary.py), [vocabulary.py](../../src/eurogas_nexus/domain/ontology/vocabulary.py)); no dated cash-need profile is produced, so no all-in funding-cost or liquidity comparison is possible |
| Exchange and physical arbitrage research | API + UI + persisted | Normalized quotes ([market_intelligence.py](../../src/eurogas_nexus/db/models/market_intelligence.py)), intraday engine with executable ask/bid, freshness, depth, FX and route access ([opportunity_engine.py](../../src/eurogas_nexus/domain/market_intelligence/opportunity_engine.py)), persisted opportunities + feed UI, mark-to-market of sale options ([live_markets.py](../../src/eurogas_nexus/domain/route_cost/live_markets.py)), EEX NGP parser with temporal gates ([eex_ngp.py](../../src/eurogas_nexus/ingestion/eex_ngp.py)) | Product/time-basis semantics are missing. The only opportunity type is `CROSS_HUB_TRANSPORT_SPREAD` (location); no time-basis or product-basis evaluation exists. The executable mark used to re-value sale options carries a free-text `product` and a mark time with no delivery window ([route_cost.py](../../src/eurogas_nexus/db/models/route_cost.py)); EEX NGP values are reference indices with unproven publication timezone and gas-day calendar (kept `pending_source_timezone`/refused, [EEX_NGP_SOURCE_CONTRACT.md](../data/EEX_NGP_SOURCE_CONTRACT.md)) |
| Strategy design, shadow run and comparison | Reviewed workflow (strongest journey) | Versioned registry with freeze/fork and reproducible runs ([strategy_registry.py](../../src/eurogas_nexus/api/routes/public/strategy_registry.py), [run_orchestration.py](../../src/eurogas_nexus/domain/strategy_lab/run_orchestration.py)), as-of backtest with leakage validation ([engine.py](../../src/eurogas_nexus/domain/backtest/engine.py), [leakage.py](../../src/eurogas_nexus/domain/research/leakage.py)), shadow monitor/evaluation/risk/alert/drift runtime ([shadow.py](../../src/eurogas_nexus/api/routes/public/shadow.py), [shadow_runtime.py](../../src/eurogas_nexus/application/shadow_runtime.py), [shadow models](../../src/eurogas_nexus/db/models/shadow.py)) | Realised vs modelled is not reachable: outcomes are only created as `MARK_TO_MODEL`, and `mature_outcome` has no runtime or API caller ([shadow repository](../../src/eurogas_nexus/db/repositories/shadow.py)). Slippage policy is `UNMODELED` ([registry.py](../../src/eurogas_nexus/domain/strategy_lab/registry.py)) and funding assumptions are not part of a strategy version. Shadow alert acknowledgement records the authenticated principal in `acknowledged_by` with an atomic audit row; the deprecated body `actor` is ignored, so a caller cannot attribute an acknowledgement to somebody else ([shadow.py](../../src/eurogas_nexus/api/routes/public/shadow.py), [audit repository](../../src/eurogas_nexus/db/repositories/audit.py)) |
| Abnormality and risk monitoring | API + UI + persisted | Deduplicated alerts with occurrence counts and enrichment ([monitoring_service.py](../../src/eurogas_nexus/application/monitoring_service.py), [monitoring model](../../src/eurogas_nexus/db/models/monitoring.py)), alerts API and Alert Center ([monitoring.py](../../src/eurogas_nexus/api/routes/public/monitoring.py), [AlertCenter.tsx](../../clients/web/src/components/AlertCenter.tsx)), day-board composition | Acknowledgement is a GOVERNED write declared before the READ `/api/monitoring/` family, and the transition plus its audit record are one transaction naming the authenticated principal, the alert and the request correlation id ([permissions.py](../../src/eurogas_nexus/security/permissions.py), [monitoring.py](../../src/eurogas_nexus/api/routes/public/monitoring.py)). There is no assign, resolve or escalate route; "resolved" is set only by the absence scan, and the client does not yet display the acknowledger |

### Permissions and scope actually enforced

- Every API profile requires identified callers (`require_public_api_auth`,
  `require_identity`, `require_route_permission`, `require_commercial_access`,
  wired in [app.py](../../src/eurogas_nexus/api/app.py)); the anonymous mode is
  an explicit deployment statement, not a profile default
  ([route_profiles.py](../../src/eurogas_nexus/api/route_profiles.py)).
- Commercial writes in scope are declared in the permission registry
  ([permissions.py](../../src/eurogas_nexus/security/permissions.py)):
  `/api/route-cost/upstream-contracts` is GOVERNED; `/api/contracts/` is READ;
  the research cash valuation and strategy-run creation are GOVERNED;
  shadow monitor lifecycle, shadow-alert acknowledgement and
  `/api/monitoring/alerts/{alert_id}/acknowledge` are GOVERNED, while the rest
  of `/api/monitoring/` stays READ.
- The platform-admin boundary is implemented: a path in the commercial-data
  list (`/api/monitoring/`, `/api/contracts/`, `/api/route-cost/`,
  `/api/strategy-*`, `/api/shadow-*`, `/api/research/`, `/api/optimization/`)
  refuses an identity holding administration alone
  ([commercial_access.py](../../src/eurogas_nexus/api/dependencies/commercial_access.py)).
- Row-level entitlement is applied on source/observation/LNG/route reads
  (e.g. [lng.py](../../src/eurogas_nexus/api/routes/public/lng.py)); the
  portfolio snapshot records the entitlement filter it ran
  ([portfolio_snapshot.py](../../src/eurogas_nexus/application/projections/portfolio_snapshot.py)).
- Not established here: no populated persona walkthrough (trader/ researcher/
  risk/administrator) was executed against a running deployment in this audit,
  so permitted/denied behaviour per journey is a registry/code reading, not
  observed acceptance. The permission registry is covered by
  [test_permissions_registry.py](../../tests/security/test_permissions_registry.py)
  and profile registration by
  [test_route_registration_profiles.py](../../tests/api/test_route_registration_profiles.py).

### Test coverage of the claims above

| Claim | Focused tests at this baseline | Limit |
| --- | --- | --- |
| Optimiser conservation and fail-closed access/capacity/currency | [test_resource_pool_optimization.py](../../tests/unit/test_resource_pool_optimization.py), [test_portfolio_network_composition.py](../../tests/unit/test_portfolio_network_composition.py) | Synthetic fixtures; no customer contract set |
| Contract upsert/read and resource-pool composition from DB | [test_route_cost_api.py](../../tests/api/test_route_cost_api.py), [test_route_cost_db_api.py](../../tests/integration/test_route_cost_db_api.py) | Upsert is tested for persistence, not for versioning/retire/concurrency because none exists |
| LNG readiness and dated-cash cargo composition | [test_lng_regas_readiness.py](../../tests/unit/test_lng_regas_readiness.py), [test_lng_cargo_economics.py](../../tests/domain/research/test_lng_cargo_economics.py), [test_cash_valuation.py](../../tests/domain/research/test_cash_valuation.py) | Engine-level exactness; no API caller, no persisted cargo/slot |
| Cash valuation transport contract (client) | [cashValuationTransport.test.ts](../../clients/web/tests/cashValuationTransport.test.ts) | Transport DTO only; no surface invokes it |
| Exchange opportunity semantics | [test_intraday_opportunity_engine.py](../../tests/unit/test_intraday_opportunity_engine.py), [test_live_market_decision_support.py](../../tests/unit/test_live_market_decision_support.py) | Location spread only; no time/product basis; simulated quotes allowed and labelled |
| Strategy runs and shadow runtime | [test_strategy_registry_api.py](../../tests/api/test_strategy_registry_api.py), [test_shadow_runtime_api.py](../../tests/api/test_shadow_runtime_api.py), [test_shadow_no_execution_boundary.py](../../tests/contract/test_shadow_no_execution_boundary.py) | Maturation path untested because unreachable; acknowledgement attribution, spoofing and audit-rollback are covered by the new focused cases |
| Monitoring alert lifecycle | [test_monitoring_service.py](../../tests/unit/test_monitoring_service.py), [test_monitoring_api.py](../../tests/api/test_monitoring_api.py), [test_monitoring_acknowledgement.py](../../tests/security/test_monitoring_acknowledgement.py) | Asserts list/acknowledge/enrichment plus permission floor, actor attribution, repeat/resolved/missing cases and audit-failure rollback; PostgreSQL concurrency case is guarded by the integration suite |
| Day board / operating board presentation | [dayBoard.test.ts](../../clients/web/tests/dayBoard.test.ts), [capacityOperatingBoardRead.test.ts](../../clients/web/tests/capacityOperatingBoardRead.test.ts) | Client model tests with fixtures; not populated deployment acceptance |
| Product boundary (no execution) | [test_product_boundary.py](../../tests/contract/test_product_boundary.py), [test_shadow_no_execution_boundary.py](../../tests/contract/test_shadow_no_execution_boundary.py) | Enforced at code/contract level |

### Ranked implementation gaps

1. **No deal-level dated cash answer, and the shared cash engine is unreachable
   from the product.** Payment timing exists only as two lag-day integers on a
   contract and an early-cash credit inside the optimiser; the dated-cash
   engine and its typed client transport have no caller. Every journey that
   must show a cash schedule, margin vs discounted value, netback or funding
   need is blocked here. Builds on: the shared engine, the sandbox route, the
   typed transport and persisted contract terms.
2. **No contract revision lifecycle and no write path for capacity/TSO/slot
   rights.** Gas contracts are overwritten in place without version, effective
   dates, retire, concurrency or audit; capacity profiles and TSO access are
   ops-seeded; no slot entity exists. This violates this matrix's evidence rule
   that historical runs retain the version used and that active records cannot
   silently disappear.
3. **No tender/offer/award object and no maximum-bid/break-even objective.**
   The flagship commercial workflow of the matrix cannot start; the cost stack
   also lacks tax, minimum-commitment and shipping items beyond the declared
   variable, regas and route-cost fields.
4. **No awarded-supply position ledger.** Remaining availability, prior
   allocations, retain/redirect alternatives and consumption against a contract
   are not persisted, so daily management cannot be defended beyond one run.
5. **No financing/clearing/collateral/credit model.** A single non-negative
   annual rate is not a funding policy; margin, haircuts, fees, day count,
   credit limits and dated cash needs are absent, and a financing allowance is
   presently the only capital-cost signal.
6. **Exchange semantics are location-only.** No time-basis or product-basis
   opportunity, no delivery-period identity on the executable marks used for
   re-valuation, and EEX NGP remains a gated reference-index adapter, so
   "verified executability" is not demonstrated for any real venue.
7. **LNG is primitive-only end to end.** The composed cargo economics engine
   has no exposed workflow and no persisted cargo/slot/terminal rights;
   auction/slot price sources are skeletons.
8. **Alert acknowledgement is attributable and permission-scoped, but the
   lifecycle is incomplete**: there is no assign, resolve or escalate action,
   "resolved" is only set by the absence scan, and the client does not display
   who acknowledged.
9. **Tender/LNG/financing cost completeness needs an explicit applicability,
   basis and treatment model** (incremental/sunk/allocated/contingent, unknown
   vs zero): cost observations carry scope/type/supersession, but the decision
   flows do not consume them with an applicability rule, and unknown values are
   not first-class in the optimiser beyond fail-closed pairs.

### Recommended next milestone (one)

**Parent disposition: proposal below is not approved for implementation.**
Parent live inspection found an enabled Compare Options action silently returning
403, plus a refused automatic optimiser request. Parent follow-up found the
local account has multiple persisted roles, including commercial capabilities;
the actual refusal was `origin_not_allowed` from the local launcher configuration,
not a commercial-role denial. An ADMIN display label is not the full role set.
The immediate milestone is permission-aware, action-specific pending/error/result
handling and separate successful-result context provenance. Backend permissions
must remain unchanged. This is a prerequisite to trustworthy persona workflows.

Parent source review had confirmed two security findings that outranked new
valuation features: general monitoring acknowledgement lacked a dedicated write
permission and actor attribution, and shadow acknowledgement trusted `body.actor`.
Both are addressed through existing permission/audit mechanisms (GOVERNED
acknowledgement routes, authenticated-principal attribution, one-transaction
audit rows) with focused regression coverage; reviewable alert workflows still
require the lifecycle gaps above.

For the cash proposal below, neither a lag integer nor a delivery window proves
the payment anchor, business-day adjustment, quantity basis or day-count rule.
The proposed end-of-window-plus-lag test must not become a default convention.
Any later composition requires explicit contractual semantics or caller-supplied
dated legs with preserved provenance and assumption labels. A hash citation is
not immutable contract history or a replacement for retained input snapshots.
Rate-to-factor conventions and a new commercial endpoint need separate review;
the existing exact-factor sandbox interface remains the current contract.

Correction to the inventory's cost-gap wording: `CashLegCategory.SHIPPING` and
itemised downstream costs already exist in the shared cash/LNG research
primitives. The gap is a connected, complete tender cost model, not absence of
every shipping-cost representation. The worker's absolute absence wording must
not be used as a design premise. All rows remain code-audit evidence only.

**CS-1 — Contract-revision-cited dated cash schedule in the existing Decision
workspace.** A trader selects a persisted upstream contract, an explicit
valuation date, an explicit delivery window and a declared discount basis
(annual rate + declared day-count), and the backend returns an exact dated cash
schedule and discounted value that cites the exact contract revision it read.

Why this and not gap 2 first: gap 1 is the greatest commercially answerable
increment that builds on the current architecture. The engine
([cash_valuation.py](../../src/eurogas_nexus/domain/research/cash_valuation.py)),
the sandbox route and the typed transport already exist; the missing link is
the composition from persisted contract terms plus a surface that shows it.
Without it the engine is exactly the "isolated calculator" the user rejected,
and no tender break-even, awarded-supply payment timing, LNG netback or
financing comparison can show a dated cash figure. Gap 2 (versioning/retire)
requires an architecture decision on version tables, effective dating and a
migration; CS-1 must not pretend that decision is made — it cites a canonical
revision hash plus `updated_at_utc` of the terms actually used and labels that
as revision citation, not version control. Contract lifecycle remains the next
milestone.

Scope (proposed files):

1. `src/eurogas_nexus/domain/research/cash_valuation.py` — one owner for
   rate → discount-factor derivation (explicit rate, declared day-count
   ACT/365, curve and source references; unknown conventions refused). No
   second discounting implementation anywhere.
2. `src/eurogas_nexus/application/contract_cash_schedule.py` (new) — read the
   persisted contract by id, map terms to signed dated legs and factor inputs,
   compute the canonical revision hash over exactly the fields used, and fail
   closed with stable codes on missing/unsupported terms. No persistence, no
   provider calls, no invented payment dates.
3. `src/eurogas_nexus/api/routes/public/route_cost.py` — `POST
   /api/route-cost/upstream-contracts/{contract_id}/cash-schedule`
   (GOVERNED), exact-decimal-string response (as the existing sandbox route),
   404 unknown contract, 503 unconfigured/unavailable runtime DB, and a tracked
   run through [jobs.py](../../src/eurogas_nexus/application/jobs.py) so the
   schedule can be cited by run id as decision-case evidence.
4. `src/eurogas_nexus/security/permissions.py` — register the new path; the
   `/api/route-cost/` family is already classified commercial data.
5. Web — `clients/web/src/api/client.ts` DTO (exact strings), an action in
   `clients/web/src/stores/api.ts`, and a disclosure inside the existing
   Decision or contract settlement surface (for example
   [ScenarioWorkspace.tsx](../../clients/web/src/components/ScenarioWorkspace.tsx))
   showing per-leg date/amount/currency/unit, discount basis, missing-input and
   refusal states, revision citation and decision-support labels. No arithmetic
   in React.
6. Docs — update the journey rows above to the level actually delivered, plus
   `docs/api/API_CONTRACT.md` and the surface blueprint for the new route.

Acceptance tests (exact):

- `tests/domain/research/test_cash_valuation.py` (extend): rate-derived factor
  exactness including a leap day; ACT/365 only; unknown convention refused;
  curve/source provenance required; no wall clock.
- `tests/unit/test_contract_cash_schedule.py` (new): payment date = delivery
  window end + declared lag; quantity × sold days; variable cost and fuel loss
  included exactly once; legs reconcile to margin within the declared
  tolerance; NPV equals the engine result; refusal codes for missing delivery
  window, missing discount basis, currency mismatch and non-positive quantity;
  deterministic output; revision hash stable on unchanged terms and changed by
  any cited-term edit.
- `tests/api/test_route_cost_api.py` (extend): unconfigured DB 503; unknown
  contract 404; invalid body 422; non-GOVERNED identity 403; exact decimal
  strings and revision citation present.
- `tests/integration/test_route_cost_db_api.py` (extend): upsert then compute
  from the persisted row; a second upsert changes the revision citation and the
  schedule; no non-persisted term is invented.
- `clients/web/tests/cashSchedule.test.ts` (new): DTO grammar; per-leg
  rendering with units; loading/empty/refusal/missing-input states; revision
  citation visible; source assertion that no client-side discounting math
  exists (same style as
  [test_trader_client_correctness.py](../../tests/contract/test_trader_client_correctness.py)).
- Regression gates: `tests/security/test_permissions_registry.py`,
  `tests/contract/test_surface_reachability.py`,
  `tests/contract/test_product_boundary.py`, the markdown link gate, focused
  Ruff, and the web type-check/build gates already required by the repository.

Non-goals: no tender/award object, no contract version table, no
capacity/TSO/slot write APIs, no financing/clearing model, no exchange
time/product-basis engine, no new persistence table, no new page, and no
submission, execution, nomination or settlement behaviour.

Open decisions for the parent before implementation: whether the schedule is
persisted as a first-class artefact or cited only by job run id plus
decision-case evidence; whether rate → factor derivation belongs in the shared
engine or a sibling domain module; whether the new route is commercially
available (GOVERNED) or gated for the pilot; and whether the revision-hash
canonicalisation becomes the compatibility contract the later contract
versioning milestone must preserve.
