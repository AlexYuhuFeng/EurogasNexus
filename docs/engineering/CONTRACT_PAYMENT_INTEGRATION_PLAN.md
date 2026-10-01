# Contract Revision and Explicit Payment Terms — Integration Plan

Status: **PROPOSED for architecture review; not approved and not implemented.** Bounded preparation from [Architecture V2 execution state](ARCHITECTURE_V2_EXECUTION_STATE.md) and the [European Gas Trading Business Acceptance](../product/TRADING_BUSINESS_ACCEPTANCE.md) matrix, audited at repository baseline `509e703`. No code, migration, dependency, DB write, checkpoint, commit or release artefact is part of this plan.

Scope: contract/right lifecycle for pipeline-gas and LNG tender decision support, plus explicit payment-term semantics feeding the shared dated cash valuation. Boundary: decision support only — no trade execution, tender submission, capacity reservation, nomination or settlement; an internal revision is never an amendment to a legally binding agreement.

## 1. What the code does today (read-only audit)

| Area | Implemented now | Evidence |
| --- | --- | --- |
| Contract CRUD | `GET`/`POST /api/route-cost/upstream-contracts`; POST inserts or **overwrites in place by `contract_id`**; no version, effective dates, retire, delete, concurrency check or audit row | `api/routes/public/route_cost.py::list_upstream_contracts`, `::upsert_upstream_contract`; `db/repositories/route_cost.py::upsert_upstream_contract`; `db/models/route_cost.py::UpstreamResourceContractRecord` |
| Contract fields | Quantity/price/tolerances/capacity/allowed exits/eligible modes are columns; `variable_cost_gbp_mwh`, `regas_fee_gbp_mwh`, `fuel_loss_allowance_pct` live inside the `notes` JSON | `db/repositories/route_cost.py::_merged_contract_notes`, `::_STRUCTURED_NOTE_FIELDS`; `clients/web/src/app/contractPayload.ts::buildContractPayload` |
| Capacity/TSO rights | `capacity_profiles` has `valid_from_utc`/`valid_to_utc` but only a repository read; `company_tso_access` is ops-seeded; no write API | `db/models/route_cost.py::CapacityProfileRecord`; `db/repositories/route_cost.py::list_capacity_profiles` |
| Versioning precedent | Strategy identity plus immutable versions: unique `(strategy_id, version_number)`, `content_hash`, `frozen_at_utc`, `parent_version_id`; draft edits refused once FROZEN (409); freeze/fork | `db/models/strategy.py::StrategyVersionRecord`; `api/routes/public/strategy_registry.py` |
| Audit precedent | Append-only `audit_events` (principal, action, resource, outcome, correlation id, before/after summaries); monitoring acknowledgement writes state and audit in one transaction | `db/models/observation.py::AuditEventRecord`; `db/repositories/audit.py::record_audit_event`; `api/routes/public/monitoring.py::acknowledge_alert`, `::_record_acknowledgement_audit` |
| Recorded vs effective precedent | Cost observations carry `effective_from_utc`/`effective_to_utc` and are superseded, never deleted | `db/models/cost_observation.py::CostObservationRecord` |
| Payment/financing today | Contract holds two lag integers and `annual_financing_rate_pct`; the optimiser adds an early-cash allowance `base_cost × rate × max(upstream_lag − screen_lag, 0)/365` per bid; no payment anchor, calendar, day count, FX date rule or curve provenance | `db/models/route_cost.py::UpstreamResourceContractRecord`; `domain/route_cost/resource_pool.py::_early_cash_value_gbp_mwh` |
| Shared cash engine | Requires explicit `CanonicalId` context, valuation date, reporting currency, signed dated legs (category, `payment_date`, amount, currency, `source_reference`, explicit FX rate/`as_of`/source) and one explicit discount factor per payment date (`factor`, `curve_reference`, `source_reference`, `as_of`); refusals are whole-input and stable-coded; results carry no wall clock | `domain/research/cash_valuation.py::CashValuationInput`, `CashValuationLegInput`, `CashValuationFxInput`, `CashValuationDiscountFactorInput`, `compute_cash_valuation`; `api/routes/public/research.py::post_cash_valuation`; [capability doc](../architecture/CASH_VALUATION_CAPABILITY.md) |
| LNG composition | Delegates to the shared engine; payment dates are caller-supplied plain dates at/after the valuation date; every declared date needs an explicit factor; readiness missing inputs refuse fail-closed | `domain/research/lng_cash_valuation.py`; `domain/research/lng_cargo_economics.py::LngCargoEconomicsInput`, `::_validate_payment_date`, `::_validate_discount_coverage`; `domain/route_cost/lng_regas.py::assess_lng_regas_readiness` |
| Permissions | Contract upsert/list is GOVERNED inside the commercial-data prefixes; admin-alone refused; `/api/contracts/` stays READ; research valuation is GOVERNED | `security/permissions.py`; `api/dependencies/commercial_access.py` |

Missing: stored contract revisions and revision citation on valuations; effective-date/retire semantics; governed capacity/TSO/slot write paths; explicit payment terms (anchor, calendar, business-day adjustment, day count, quantity basis, FX date rule, curve provenance); concurrency and audit on contract mutation; composition from a frozen revision into `CashValuationInput`.

## 2. Proposed design

### 2.1 Identity, economic revision, mutable metadata

- `upstream_resource_contracts` keeps stable identity plus mutable metadata only: `contract_id`, display name, operator notes, document/evidence references, tags, `current_revision_id` (pattern: `StrategyRecord.current_version_id`).
- New revision entity (working name `upstream_contract_revisions`): `contract_revision_id` PK, `contract_id` FK, unique `revision_number` per contract, `schema_version`, status `DRAFT|FROZEN|SUPERSEDED`, `effective_from`/`effective_to`, `recorded_at_utc`/`recorded_by`, `content_hash`, `parent_revision_id`, the economic fields (quantity, price, tolerances, capacities, allowed points, eligible modes, variable cost, regas fee, fuel loss, payment terms), `research_only`, `human_review_required`.
- Frozen revisions are immutable; an edit forks a new DRAFT with `parent_revision_id` (precedent: strategy freeze/fork). Mutable metadata never changes a valuation. The `notes`-embedded economic fields move to revision columns when the write path ships, without breaking current read payloads.

### 2.2 Optimistic concurrency and audit

- Draft mutations carry a separate monotonically increasing `expected_edit_version`; the repository conditionally updates and increments it atomically. A revision number alone cannot detect two edits within the same draft. A mismatch returns 409 `contract_revision_conflict` with entitled current-version metadata; nothing partial is written. Publishing also compares the stable identity's current-revision pointer to prevent competing publications.
- Accepted create/freeze/retire writes, in the same transaction, `record_audit_event(resource=f"upstream_contract:{contract_id}", action=…, before_summary=…, after_summary=…)` with the authenticated principal and request correlation id; audit failure rolls the change back (precedent: `monitoring.py::acknowledge_alert`).

### 2.3 Effective dates vs recorded dates; no hard deletion

- `effective_from`/`effective_to` say when the economics applies; `recorded_at_utc`/`recorded_by` say when the desk captured it. Neither is derived from the other; a later-recorded revision with an earlier effective start is disclosed, never silently re-dated.
- No hard deletion. Retirement is a separate auditable lifecycle event with its own effective and recorded dates; it does not rewrite a frozen revision's economic validity window or content hash. Supersession links to a successor and is distinct from retirement without a successor. A revision cited by a persisted valuation/run/snapshot is FK-restricted and cannot be removed even by a future admin API.
- Capacity/TSO/slot rights can reuse identity and revision patterns, but need separate validation of units, directions, overlapping rights and resource-specific terms; existing validity columns alone do not establish an adequate write contract.

### 2.4 Explicit payment terms (no inferred dates)

Terms are part of the frozen revision and all-or-nothing; composition refuses when anything required is absent rather than defaulting. Working field names; vocabularies are review decisions, not claims here.

| Semantic | Field (working name) | Rule |
| --- | --- | --- |
| Absolute date | `payment_date` (ISO date) | Accepted only when the schedule states a date |
| Anchor | `anchor_event` (closed reviewed set, e.g. invoice date, delivery-period start/end, meter read, explicit date) + `anchor_date` when explicit | No default; `upstream_payment_lag_days` alone is not an anchor |
| Offset | `anchor_offset_days` | Explicit, `>= 0`, applied only per the reviewed anchor definition |
| Calendar / roll | `calendar_reference`, `business_day_convention` (e.g. none/following/modified following) | Required when adjustment matters; no implicit weekend/holiday rule |
| Quantity basis | `quantity_basis_reference` | Declared invoiced/scheduled/delivered basis; never assumed |
| Day count | `day_count_convention` | Required whenever an annual rate becomes a period amount; no 365 default |
| FX | leg currency, `rate`, `as_of`, `source_reference` | Already required by `CashValuationFxInput`; never defaulted |
| Discount | per-date `factor`, `curve_reference`, `source_reference`, `as_of` | Already required by `CashValuationDiscountFactorInput`; every leg date covered |

The end-of-window-plus-lag construction must not become a default convention (the acceptance document's review note); a delivery window alone produces no payment dates. The revision stores the declared rule; composition records the values actually used.

### 2.5 Reuse the shared cash capability; funding vs discounting

- Composition builds `CashValuationInput` from the frozen revision plus explicit caller inputs and calls `compute_cash_valuation`; no leg math or NPV is re-implemented in a route, optimiser or client. The response cites `contract_revision_id` + `content_hash` and echoes `source_references`/`lineage`.
- Funding cost and discounting are distinct. For an explicitly selected simple-interest model, funding may use dated principal, rate and declared accrual fraction; other financing terms require their own model. Discounting applies supplied factors to dated cash. The composition must declare its valuation basis and detect a duplicated funding adjustment between explicit legs, the optimiser allowance and a curve spread. There is no blanket prohibition on discounting financing cash flows: treatment requires an explicit model policy, not a guessed market convention. This slice must not change the existing optimiser arithmetic.

### 2.6 Ontology mapping before new types

Reuse: `UpstreamResourceContract` (bound to `upstream_resource_contracts` in `domain/ontology/bindings.py`), `CapacityProfile`, `CompanyTsoAccess`, `TsoTariff`, `FxObservation`, `LngRegasScenario`, `RouteCandidate`, plus semantic-kernel `CanonicalId`, `ExternalIdentifier` (with `valid_from`/`valid_to`), `Money`, `Measure` (`domain/ontology/semantic_kernel.py`).

Gaps: no contract-revision, payment-terms or valuation-citation concept exists. Preferred order: (1) express revision as bound data (id + number) with slots on the existing `UpstreamResourceContract` binding; (2) only if a distinct entity is unavoidable, register `ContractRevision`/`PaymentTerms` through ontology review (`bindings.py` slot→column maps; the enum/ontology gate records reviews). Cash-flow categories are the frozen research vocabulary `CashFlowLegCategory` in `cash_valuation.py`, not ontology; clients must not define parallel business types.

## 3. Smallest incremental slices

1. **S1 — revision foundation**, split into independently reviewed tasks: first define the immutable payload and compatibility mapping, then an additive migration/backfill with upgrade tests, then guarded write/read transitions and audit. Do not drop existing economic columns or replace all CRUD in one change. Define the first captured legacy revision honestly as migration-time evidence, not historical reconstruction. Freeze/retire and PostgreSQL concurrency acceptance follow before valuation citation is enabled.
2. **S2 — explicit payment terms** on the revision, with refusal codes and read-only exposure in the revision payload.
3. **S3 — composition**: frozen revision + valuation date + explicit delivery window/quantity basis + explicit FX and discount inputs → `compute_cash_valuation`; cite revision/hash; refuse when terms are absent.
4. **S4 — existing Decision workspace wiring**; no new top-level page, no client arithmetic.
5. **S5 — capacity/TSO/slot rights write path** reusing S1/S2 semantics.

Each slice is reversible, keeps existing routes/permissions intact and adds no datastore beyond PostgreSQL tables.

## 4. Deterministic acceptance fixtures

- **F1 engine reuse**: revision-cited schedule with EUR purchase −100 at the valuation date (DF 1), USD sale +150 at DF 0.95 with EUR/USD 0.8, EUR storage −10 at DF 0.95 → undiscounted cash 10, NPV 4.5 (already asserted in `tests/domain/research/test_cash_valuation.py`); composition returns the same digits and cites the revision.
- **F2 missing-input refusal**: revision without payment terms → composition refuses (`payment_terms_missing`, nothing returned); engine codes already exist (`NO_CASH_FLOW_LEGS`, `DISCOUNT_FACTOR_MISSING_FOR_LEG_PAYMENT_DATE`, `FX_RATE_MISSING_FOR_CROSS_CURRENCY_LEG`, `LEG_PAYMENT_DATE_BEFORE_VALUATION`).
- **F3 edit-after-valuation reproducibility**: freeze rev 1 → value and record `contract_revision_id`/hash → freeze rev 2 with a changed price → the new valuation changes while replaying rev 1 inputs reproduces the exact original decimals (the result carries no wall clock).
- **F4 no lag inference**: delivery window 2026-11-01..2026-11-30 plus `upstream_payment_lag_days=20` but no anchor/calendar/day count → refuse; the system must not produce 2026-12-20.
- **F5 concurrency**: two writers update the same draft with the same `expected_edit_version` → exactly one succeeds and increments the counter, the other gets 409; one successful-mutation audit row. Also test competing publications against the same current-revision pointer, and audit-write failure rollback. Use a disposable PostgreSQL database with an explicit test opt-in.
- **F6 funding vs discounting**: the same schedule valued (a) with an explicit financing leg and explicit discount factors versus (b) unfunded with discount factors only → the financing case shows the funding leg as its own disclosed amount and no duplicated funding effect appears in NPV.

## 5. Missing-input policy

Unknown is not zero: a missing term, date rule, calendar, day count, FX rate/date or discount factor refuses the whole computation with stable codes and no partial payload. Caller assumptions are accepted only when labelled and preserved in run lineage; inputs are never silently coerced or defaulted.

## 6. Persona authority and test strategy

- Writes (revision create/freeze/retire, payment terms) must be declared GOVERNED before any READ family, stay inside the commercial-data prefixes and keep the admin-alone refusal (`security/permissions.py`, `api/dependencies/commercial_access.py`). Trader reads keep working; no permission is widened.
- Focused tests: extend `tests/api/test_route_cost_api.py` and `tests/integration/test_route_cost_db_api.py`; new revision/payment-terms unit and security-registry tests; `tests/security/test_permissions_registry.py` and route-profile tests for new paths; PostgreSQL concurrency test; Markdown link test for this document.
- Persona evidence: a persisted trader/risk/admin walkthrough is required before any acceptance claim; passing unit/API tests alone are not journey acceptance.

## 7. Reconciliation with the prior payment proposal

The acceptance document's earlier CS-1 milestone and its rejection note remain binding; this plan is the replacement design and does not adopt CS-1's end-of-window-plus-lag payment date, ACT/365-only rate→factor convention or hash-citation-instead-of-versioning. Here the hash is an integrity check on an immutable revision that must exist first, and payment semantics are explicit on that revision. A short cross-reference was added in [TRADING_BUSINESS_ACCEPTANCE.md](../product/TRADING_BUSINESS_ACCEPTANCE.md); no other document is rewritten. **Not approved for implementation.**

## Open decisions (parent/reviewer)

Review constraints: the semantic kernel's `Money`/FX magnitudes use floats; reuse identifiers and vocabulary, not those numeric representations for exact cash arithmetic. Preserve Decimal/string transport. Mutable metadata and document references must be snapshotted when cited as valuation evidence. The proposed lifecycle vocabulary must distinguish retirement from supersession before implementation.

1. Anchor vocabulary, calendar, business-day convention and day-count set — require commercial/legal review; none is asserted here.
2. Revision numbering per contract versus per right (capacity/TSO/slot).
3. Whether valuation citations need a persisted run record or the existing analysis-snapshot/decision-case lineage suffices.
4. Whether `ContractRevision`/`PaymentTerms` become ontology concepts or slots on the existing binding.
5. Migration path for `notes`-embedded economic fields without breaking current read payloads.
