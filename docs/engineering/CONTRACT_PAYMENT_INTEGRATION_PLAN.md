# Contract Revision and Explicit Payment Terms — Integration Plan

Status: **S1a, S1b, S1c, S1d and the bounded S1e edit-token precondition are implemented (immutable economic payload definition with legacy compatibility mapping; additive revision storage with an explicit repository capture/read operation; the governed contract write that captures both sides of an overwrite with atomic attribution; the bounded, contract-scoped read surface over the captured evidence; and a stale-edit precondition on that governed write); the remaining slices are PROPOSED for architecture review and are not approved or implemented.** Bounded preparation from [Architecture V2 execution state](ARCHITECTURE_V2_EXECUTION_STATE.md) and the [European Gas Trading Business Acceptance](../product/TRADING_BUSINESS_ACCEPTANCE.md) matrix, audited at repository baseline `509e703`; S1a was implemented at baseline `1676b98` and is recorded in section 8, S1b at baseline `f396492` and is recorded in section 9, S1c after baseline `9271500` and is recorded in section 10, S1d after baseline `9160188` and is recorded in section 11, and S1e after baseline `6b5258d` and is recorded in section 13. The S1b migration is expand-only storage; there is no backfill, UI, valuation citation, checkpoint or release artefact beyond it. S1c is *not* a revision lifecycle or a complete history; its honest limits are listed in section 10, and S1e narrows only its write precondition (section 13) without turning it into a lifecycle. S1d reads evidence only — it captures nothing, changes no schema and asserts no payment terms.

Scope: contract/right lifecycle for pipeline-gas and LNG tender decision support, plus explicit payment-term semantics feeding the shared dated cash valuation. Boundary: decision support only — no trade execution, tender submission, capacity reservation, nomination or settlement; an internal revision is never an amendment to a legally binding agreement.

## 1. What the code did at the audit baseline (read-only audit at `509e703`)

| Area | Implemented now | Evidence |
| --- | --- | --- |
| Contract CRUD | `GET`/`POST /api/route-cost/upstream-contracts`; POST inserts or **overwrites in place by `contract_id`**; no version, effective dates, retire, delete, concurrency check or audit row. *Superseded for the write path by S1c (section 10): the same route now captures the replaced and the written economics and audits the mutation; there is still no version check, effective date, retire or delete.* | `api/routes/public/route_cost.py::list_upstream_contracts`, `::upsert_upstream_contract`; `db/repositories/route_cost.py::upsert_upstream_contract`; `db/models/route_cost.py::UpstreamResourceContractRecord` |
| Contract fields | Quantity/price/tolerances/capacity/allowed exits/eligible modes are columns; `variable_cost_gbp_mwh`, `regas_fee_gbp_mwh`, `fuel_loss_allowance_pct` live inside the `notes` JSON | `db/repositories/route_cost.py::_merged_contract_notes`, `::_STRUCTURED_NOTE_FIELDS`; `clients/web/src/app/contractPayload.ts::buildContractPayload` |
| Capacity/TSO rights | `capacity_profiles` has `valid_from_utc`/`valid_to_utc` but only a repository read; `company_tso_access` is ops-seeded; no write API | `db/models/route_cost.py::CapacityProfileRecord`; `db/repositories/route_cost.py::list_capacity_profiles` |
| Versioning precedent | Strategy identity plus immutable versions: unique `(strategy_id, version_number)`, `content_hash`, `frozen_at_utc`, `parent_version_id`; draft edits refused once FROZEN (409); freeze/fork | `db/models/strategy.py::StrategyVersionRecord`; `api/routes/public/strategy_registry.py` |
| Audit precedent | Append-only `audit_events` (principal, action, resource, outcome, correlation id, before/after summaries); monitoring acknowledgement writes state and audit in one transaction | `db/models/observation.py::AuditEventRecord`; `db/repositories/audit.py::record_audit_event`; `api/routes/public/monitoring.py::acknowledge_alert`, `::_record_acknowledgement_audit` |
| Recorded vs effective precedent | Cost observations carry `effective_from_utc`/`effective_to_utc` and are superseded, never deleted | `db/models/cost_observation.py::CostObservationRecord` |
| Payment/financing today | Contract holds two lag integers and `annual_financing_rate_pct`; the optimiser adds an early-cash allowance `base_cost × rate × max(upstream_lag − screen_lag, 0)/365` per bid; no payment anchor, calendar, day count, FX date rule or curve provenance | `db/models/route_cost.py::UpstreamResourceContractRecord`; `domain/route_cost/resource_pool.py::_early_cash_value_gbp_mwh` |
| Shared cash engine | Requires explicit `CanonicalId` context, valuation date, reporting currency, signed dated legs (category, `payment_date`, amount, currency, `source_reference`, explicit FX rate/`as_of`/source) and one explicit discount factor per payment date (`factor`, `curve_reference`, `source_reference`, `as_of`); refusals are whole-input and stable-coded; results carry no wall clock | `domain/research/cash_valuation.py::CashValuationInput`, `CashValuationLegInput`, `CashValuationFxInput`, `CashValuationDiscountFactorInput`, `compute_cash_valuation`; `api/routes/public/research.py::post_cash_valuation`; [capability doc](../architecture/CASH_VALUATION_CAPABILITY.md) |
| LNG composition | Delegates to the shared engine; payment dates are caller-supplied plain dates at/after the valuation date; every declared date needs an explicit factor; readiness missing inputs refuse fail-closed | `domain/research/lng_cash_valuation.py`; `domain/research/lng_cargo_economics.py::LngCargoEconomicsInput`, `::_validate_payment_date`, `::_validate_discount_coverage`; `domain/route_cost/lng_regas.py::assess_lng_regas_readiness` |
| Permissions | Contract upsert/list is GOVERNED inside the commercial-data prefixes; admin-alone refused; `/api/contracts/` stays READ; research valuation is GOVERNED | `security/permissions.py`; `api/dependencies/commercial_access.py` |

Missing: revision lifecycle (statuses, effective windows, freeze/retire/supersede), a current-revision pointer and revision citation on valuations; governed capacity/TSO/slot write paths; explicit payment terms (anchor, calendar, business-day adjustment, day count, quantity basis, FX date rule, curve provenance); optimistic edit-conflict detection on the existing contract write route; composition from a frozen revision into `CashValuationInput`. S1b (section 9) stores explicit capture events with atomic audit, S1c (section 10) makes the existing write route capture both sides of an overwrite under the authenticated actor, and S1d (section 11) exposes the captured evidence through bounded, contract-scoped reads, but none of them closes the remaining items.

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

1. **S1 — revision foundation**, split into independently reviewed tasks: first define the immutable payload and compatibility mapping (implemented, S1a), then additive storage with an explicit capture/read operation, upgrade tests and atomic audit (implemented, S1b — no backfill), then guarded write/read transitions on the existing routes (write transition implemented as S1c — section 10; bounded revision reads implemented as S1d — section 11; the optimistic edit conflict remains proposed). Do not drop existing economic columns or replace all CRUD in one change. Define a captured legacy revision honestly as capture-time evidence, not historical reconstruction. Freeze/retire and route-level PostgreSQL concurrency acceptance follow before valuation citation is enabled.
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

## 8. S1a implemented foundation — immutable economic payload (baseline `1676b98`)

Only the first half of slice S1 is implemented, as a pure domain contract with no persistence, route, permission, client or configuration change:

- Source: [`src/eurogas_nexus/domain/route_cost/contract_revision.py`](../../src/eurogas_nexus/domain/route_cost/contract_revision.py) defines `ContractDisplayMetadata` (display name plus raw operator notes; never hashed), `UpstreamContractEconomicSnapshot` (frozen/slots dataclass, schema version `upstream-contract-revision/v1`, stable `contract_id`), `LegacyContractSnapshot` and `map_legacy_contract_payload`. No new ontology concept or `StrEnum` is introduced.
- Captured economics: quantity, price, settlement frequency, the legacy payment and screen lags, both tolerances, tolerance risk allowance, annual financing rate, owned entry/exit capacity, ordered allowed exit points and eligible sale modes, and the three structured-notes costs (`variable_cost_gbp_mwh`, `regas_fee_gbp_mwh`, `fuel_loss_allowance_pct`) with the current parser's precedence (top-level payload field first, then notes).
- Honesty rules: missing optional values stay `null`, never `0`; non-JSON/non-object notes are recorded as `legacy_notes_not_structured_json` and do not erase an explicit cost; conflicting payload/notes values are recorded as `legacy_structured_value_conflict` and resolved with the current precedence; stored values (including negatives) are captured verbatim, not clamped.
- Numeric discipline: economic values are exact `Decimal` or `null`; `bool`, floats and non-finite values are refused. Legacy `float` → `Decimal` conversion is isolated in one mapping helper, uses the shortest round-trip decimal string, and labels the snapshot `legacy_float64` — the original decimal precision of a binary float is not recoverable and the label says so.
- Canonical replay: `canonical_document()`/`canonical_json()` serialize exact plain-notation decimal strings, preserve list order, and always include the schema version and `"payment_terms": null`. `content_hash()` is SHA-256 over that canonical JSON, independent of payload key order and of the ambient decimal context; `from_canonical_document()` decodes strictly (exact field set, decimal strings only, null payment terms).
- Explicitly not implemented by S1a: revision persistence model/table/migration/backfill, revision numbering, status lifecycle (`DRAFT|FROZEN|SUPERSEDED`), effective/recorded dates, `current_revision_id`, optimistic concurrency, audit rows, API/UI, payment-term vocabularies and values, valuation composition and citation. `payment_terms` is always `null` and no date, day count or calendar is derived from the lag integers. Persistence, explicit capture numbering and capture audit arrived later in S1b (section 9); no backfill exists and the lifecycle/concurrency/UI items remain proposed.
- Unchanged legacy behaviour: the optimiser payload path (`application/resource_pool.py`, including its absent-cost-as-zero handling) and all existing read payloads are untouched.
- Evidence: focused tests in [`tests/unit/test_contract_revision_payload.py`](../../tests/unit/test_contract_revision_payload.py) cover all fields, nested-mutation immutability, metadata-only vs economic changes, hash stability across key order and decimal context, legacy float provenance, null-vs-zero, ordered lists, malformed notes, non-finite/bool refusal and canonical roundtrip; a drift test pins the structured note field names to `db/repositories/route_cost.py`.

## 9. S1b implemented foundation — additive revision storage and explicit capture (baseline `f396492`)

Only the persistence half of slice S1 is implemented, and only as an explicit repository operation. There is no route, API, UI, client, startup hook or backfill: nothing captures revisions automatically, and the mutable legacy contract upsert still overwrites `upstream_resource_contracts` in place.

- Storage: [`0037_contract_revisions`](../../alembic/versions/0037_contract_revisions.py) is expand-only and creates `upstream_contract_revisions` with `contract_revision_id`, `contract_id`, `revision_number`, `schema_version`, `capture_origin`, `snapshot_json`, `display_metadata_json`, `content_hash`, `recorded_at_utc` and `recorded_by`; a unique `(contract_id, revision_number)` key, an `ON DELETE RESTRICT` FK to the contract row, and one read index. The migration imports no domain code and rewrites no row, so applying it cannot execute evolving payload/serialization behaviour or invent historic validity. There is deliberately no status, current-pointer or effective-date column. The required-table registry and the release compatibility constant `DB_SCHEMA_REVISION` move to `0037_contract_revisions` with it; no database was migrated by this work. Deployment is not a zero-impact live change: creating the FK takes a table-level lock on `upstream_resource_contracts` that can block contract writers until the migration commits, so it must run with a bounded `lock_timeout` and a rehearsal/retry procedure. Downgrade drops the table and destroys captured revision evidence, so it is gated on a backup (or an empty table) and is never just an application rollback.
- Capture: [`capture_upstream_contract_revision`](../../src/eurogas_nexus/db/repositories/route_cost.py) reads the supplied current contract row, maps it with the strict S1a mapper and persists the canonical snapshot JSON plus its SHA-256 content hash, the unhashed display evidence (contract name and raw operator notes), the capture origin `legacy_capture`, and `recorded_at_utc`/`recorded_by` — the capture time and actor (validated as a concrete UTC offset, not merely a non-`None` `tzinfo`), never an effective date. An invalid legacy mapping and any mapping that records nonempty S1a `mapping_issues` (for example stored notes that are not a JSON object) return a `rejected` result carrying `refusal_code`/`refusal_detail` before anything is inserted or audited and write nothing: a failed or ambiguous mapping is never stored as validated economics, while the domain mapper itself still records the issues.
- Idempotency and numbering: a repeat capture whose mapped content hash equals the contract's latest captured revision returns that revision unchanged (`already_captured`) and retains the original recorder and timestamp without a second audit row. A changed row captures the next `revision_number` under a `SELECT ... FOR UPDATE` read that also refreshes any already-loaded identity-map instance, so PostgreSQL serializes concurrent captures per contract and a stale in-session row another committed transaction has replaced cannot be captured; SQLite fixtures ignore the lock clause (the refresh is covered by a focused SQLite regression) and the opt-in PostgreSQL test covers both.
- Audit: an accepted capture appends exactly one `audit_events` row (`governance.contracts` / `route_cost.contract.capture_revision`, resource `upstream_contract:<contract_id>`, principal = recorder) through the caller's session, so the revision and its attribution commit or roll back together.
- Reads: [`get_upstream_contract_revision` and `list_upstream_contract_revisions`](../../src/eurogas_nexus/db/repositories/route_cost.py) verify the stored schema version, content hash, canonical round trip and matching contract id before returning evidence, and refuse a tampered row with a stable code instead of serving it.
- Honest limits: the legacy row can be updated or overwritten after capture, and a stored revision is evidence of one explicit capture event, not a lifecycle record or a complete history of legacy writes. There is no `DRAFT|FROZEN|SUPERSEDED` status, no `current_revision_id` pointer, no effective window, no freeze/retire/supersede transition, no payment terms and no valuation citation. The hash is an integrity check, never a signature.
- Evidence: [`tests/unit/test_contract_revision_migration.py`](../../tests/unit/test_contract_revision_migration.py) applies the real migration DDL (expand-only table set, exact columns, unique numbering, `ON DELETE RESTRICT`, downgrade) and [`tests/integration/test_contract_revision_capture.py`](../../tests/integration/test_contract_revision_capture.py) covers capture, idempotency with retained recorder, changed-source/new-revision numbering, snapshot preservation across later row edits, invalid and ambiguous-mapping rejection (including malformed stored notes written outside the upsert), stale identity-map refresh, capture-time offset validation, audit-writer failure rollback, rollback atomicity, FK restriction, tamper verification and unknown ids. [`tests/integration/test_contract_revision_capture_postgres.py`](../../tests/integration/test_contract_revision_capture_postgres.py) runs the lock/refresh-sensitive repeat/next-number, stale-identity-map and concurrent-capture cases behind the disposable-PostgreSQL opt-in `EUROGAS_NEXUS_CONTRACT_REVISION_INTEGRATION_TEST=1` in [`scripts/ci/run_postgres_ci.sh`](../../scripts/ci/run_postgres_ci.sh).
- Not implemented (still proposed): guarded revision write/read transitions on the existing routes, revision lifecycle and effective semantics, explicit payment terms and composition/citation (sections 2.4-2.6 and 3.2-3.4).

## 10. S1c implemented — governed contract writes capture both sides of an overwrite (after baseline `9271500`)

The third part of slice S1 — the guarded write transition on the existing route — is implemented. `POST /api/route-cost/upstream-contracts` keeps its request model, response payload, permission and error posture, but it is no longer an unattributed overwrite: the actor is resolved from the authenticated identity before any store access, the economic state being replaced is captured as an immutable revision first, the new state is captured afterwards, and the mutation audit commits or rolls back with the write. No migration, route addition, page, backfill, startup hook, provider call or local database write was added.

- Authority: the handler calls `require_acting_actor(request)` as its first statement (finding C13), so a request with no resolved principal is refused with 401 `authentication_required` before the store is touched, and any body field that looks like an actor (`actor`, `recorded_by`) is ignored: only the authenticated principal is ever recorded. `GOVERNED` on `/api/route-cost/upstream-contracts`, the ANALYST floor and the commercial-data boundary are unchanged, as is the 503 `runtime_db_not_configured` refusal when no runtime store is configured.
- Write path: [`upsert_upstream_contract_governed`](../../src/eurogas_nexus/db/repositories/route_cost.py) validates the contract id, the actor (column bound, never truncated) and the write instant, normalizes the request fields through the same single field list the plain upsert uses, then takes the existing per-contract row read (`SELECT ... FOR UPDATE` plus identity-map refresh) *before* anything else, so the state captured as "previous" is exactly the state this transaction is about to replace. It reuses `capture_upstream_contract_revision` for both captures: no second hash, mapper or numbering implementation exists, and a governed write records its revisions under the same reviewed `legacy_capture` origin — the origin names the mutable source row, not the caller class, so the verified-origin allow-list and read path are unchanged.
- Outcomes and additive metadata: `created` (new identity, captured once — there is no previous state), `economics_updated` (both sides captured, next revision number allocated), `metadata_updated` (only display evidence changed, so the capture is idempotent: no new revision, original recorder and timestamp retained), `unchanged` (economics and display evidence identical: no row write, no revision, no audit row) and `refused` (nothing committed; see below). The response payload keeps every existing field and adds `write_outcome` and `latest_revision` (identity, number, origin, content hash, recorder, capture time). The typed web transport in [`client.ts`](../../clients/web/src/api/client.ts) declares both as optional additions; no UI consumes them yet, and no client-side calculation was added.
- Fail-closed pre-capture: when the stored row does not map to a validated economic snapshot — an unmappable value or the S1a `mapping_issues` ambiguity such as non-object notes — the request is refused with 409 (`error: "conflict"`, `code:` the stable capture refusal, e.g. `contract_revision_mapping_ambiguous`), the session is rolled back and nothing at all is written: no contract overwrite, no revision, no audit row. The malformed stored terms are preserved rather than destroyed. Honest limit: there is **no repair path yet** — a refused contract can only be remediated by a separate, still-proposed write/remediation step; it is not silently repairable through this route.
- Audit: a newly captured revision appends its existing `route_cost.contract.capture_revision` row. Each accepted write that changed something additionally appends exactly one `route_cost.contract.upsert` row naming the principal, the request correlation id, the changed field *names* (never values) and the newest revision identity, with a before/after revision summary. A metadata-only change is therefore auditable even though its capture is idempotent; a true replay appends no second mutation audit. All rows are written through the caller's session, so an audit-writer failure rolls the whole write back (row, revision and audits together).
- Concurrency: per-contract updates are serialized by the row lock, so concurrent governed overwrites cannot allocate the same revision number. Two concurrent creates of the same new identity cannot both insert either: the insert is conflict-tolerant (`INSERT ... ON CONFLICT (contract_id) DO NOTHING`, the pattern `db/repositories/public_ingestion_upsert.py` already uses), so the loser's statement inserts nothing, the session stays usable — unlike after a failed ORM flush, which forces a whole-transaction rollback — and the same call re-reads the winner's committed row under the lock and continues as an overwrite; no `IntegrityError` reaches the caller. A dialect without a reviewed conflict-tolerant insert refuses with a stable code rather than guessing.
- Honest limits (still open): this is **capture-time evidence, not history**. A stored revision records the row as the capture read it; there is no complete history before the first captured write, no `DRAFT|FROZEN|SUPERSEDED` lifecycle, no effective windows, no `current_revision_id` pointer, no freeze/retire/supersede and no payment terms. There is **no revision-level optimistic edit conflict** (no `expected_edit_version` and no draft/frozen state); the route's *bounded* stale-edit precondition was added later and is recorded in section 13 — a same-row last-writer-wins overwrite is now refused only when the writer's opaque row token no longer matches, not because a revision lifecycle detected anything. Read transitions (a route path that serves revisions) are not implemented, so revisions are reachable through the repository read helpers only. The plain [`upsert_upstream_contract`](../../src/eurogas_nexus/db/repositories/route_cost.py) remains an ungoverned repository function used for fixtures and seeding; it is not a route and must not become an API write path.
- Deployment: no migration is required for S1c — it uses the S1b table — and nothing runs on startup or backfills. The PostgreSQL-authoritative cases run in the existing disposable CI job.
- Evidence: [`tests/security/test_contract_write_attribution.py`](../../tests/security/test_contract_write_attribution.py) covers the identity-less refusal before store access (with a configured store), the ignored body actor, the VIEWER refusal and the ADMIN-without-commercial-role refusal. [`tests/integration/test_route_cost_contract_write_revisions.py`](../../tests/integration/test_route_cost_contract_write_revisions.py) runs the real route against SQLite for creation (one revision, one capture audit, one mutation audit), identical replay (nothing written, attribution preserved), economic change (previous snapshot untouched, next revision, both audits, correlation id), metadata-only change (audited without a new revision), malformed stored terms (409, row preserved, no revision, no audit), audit-writer failure rollback for both update and creation, and the create-race recovery (a commit appearing mid-flight continues as an overwrite instead of failing). [`tests/integration/test_contract_revision_capture_postgres.py`](../../tests/integration/test_contract_revision_capture_postgres.py) adds the opt-in PostgreSQL cases for concurrent governed overwrites (unique numbering under the row lock) and concurrent governed creates (convergence without a leaked `IntegrityError`). Focused runs pass 13 new tests locally (SQLite); the PostgreSQL cases are skipped without the disposable-database opt-in and require same-SHA CI evidence.

## 11. S1d implemented — bounded, contract-scoped revision reads (after baseline `9160188`)

The read half of the S1 transition is implemented on the existing route-cost contract family. Two GET routes expose the captured revisions the governed write already stores; there is no new page, no new permission model, no migration, no backfill, no startup hook, no client arithmetic and no write of any kind on the read path.

- Routes: `GET /api/route-cost/upstream-contracts/{contract_id}/revisions` lists one contract's captured revisions oldest revision number first, and `GET /api/route-cost/upstream-contracts/{contract_id}/revisions/{contract_revision_id}` reads one of them. Both delegate to the existing verified repository helpers ([`list_upstream_contract_revisions`, `count_upstream_contract_revisions` and `get_upstream_contract_revision`](../../src/eurogas_nexus/db/repositories/route_cost.py)); no second mapper, verifier, hasher or serializer exists.
- Authority: the new paths declare the existing `GOVERNED` (ANALYST) floor inside the commercial-data boundary, exactly like `GET/POST /api/route-cost/upstream-contracts`. Captured revisions are the same contract economics the sibling route protects, so the reads neither widen commercial-data access to a lower role nor invent a persona/work-mode authority. A VIEWER keeps the role refusal, an ADMIN without a commercial role keeps the `commercial_access_not_granted` refusal, and the release-profile credential gate applies before any row is read.
- Bounded, ordered history: `limit` (default 50, hard maximum 200) and `offset` are pushed into the SQL query, so a contract with a long capture record materializes at most one bounded page of snapshot evidence. Ordering is `revision_number` ascending with `contract_revision_id` as the deterministic tie-break; the page reports `revision_count`, `returned_count`, `has_more`, `limit` and `offset`, and the repository read can still run unbounded for fixtures and seeding callers that do not pass a limit.
- Missing versus empty: an unknown contract is 404 `upstream_contract_not_found`. An existing contract with no captures is an empty 200 page with `revision_count` 0 and an explicit warning, so "nothing captured yet" is never confused with "no such contract". A revision id that belongs to another contract answers the same 404 `contract_revision_not_found` as an unknown id, so the surface never confirms that evidence exists under a contract the caller did not name; the refusal message names neither contract nor revision.
- Verification and sanitized refusals: every returned row is verified by the existing S1b read before it is served (reviewed capture origin, stored hash, strict canonical decode, matching contract id and schema version). A missing revision is 404; any other repository refusal (for example a tampered `snapshot_json` whose hash no longer matches) is a structured 409 `conflict` carrying the stable repository code and one fixed message. Stored row content, driver text, SQL and stack traces are never echoed.
- Evidence preserved, nothing invented: each payload keeps the revision identity, `schema_version`, `capture_origin`, `content_hash`, capture instant, original `recorded_by`, the unhashed display evidence (contract name and raw operator notes) and the canonical snapshot document with exact decimal strings and `payment_terms: null`. Both reads carry warnings that a capture is capture-time evidence rather than a complete history of past contract writes, and that the captured economics contain no payment terms, effective dates or valuation.
- Read-only: the read path calls no capture function. A source row changed after its last capture does not gain a revision or an audit row by being read, and reading through another principal's identity never changes `recorded_by` or the capture instant.
- Honest limits (unchanged by S1d): still no `DRAFT|FROZEN|SUPERSEDED` lifecycle, no effective windows, no `current_revision_id` pointer, no freeze/retire/supersede, no optimistic edit conflict, no explicit payment terms and no valuation citation or composition. A served revision is stored evidence of one capture event, and the hash remains an integrity check rather than a signature.
- Deployment: no migration is required — S1d reads the S1b table — and nothing runs on startup or backfills.
- Evidence: [`tests/security/test_contract_revision_read_authority.py`](../../tests/security/test_contract_revision_read_authority.py) pins the GOVERNED commercial declaration, the VIEWER role refusal, the ADMIN-without-commercial-role refusal, the uncredentialed release refusal and the compatibility-principal read. [`tests/integration/test_route_cost_contract_revision_reads.py`](../../tests/integration/test_route_cost_contract_revision_reads.py) runs the real routes against SQLite for verified history evidence (metadata, exact decimals and warnings), the 404-versus-empty distinction, cross-contract scoping, a tampered stored snapshot (stable 409 code with no leaked driver text), bounded paging with an unchanged revision/audit count, and original-actor preservation across a second principal. Reading captures nothing in any of these cases; the PostgreSQL-authoritative locking/verification cases remain covered by the existing disposable CI job.

## 12. Live-observed client record-mapping repair (baseline `9e0b26e`)

A read-only authenticated observation in the Portfolio Resources Library: loading the persisted
`preview-portfolio-contract-ttf-pool-2025` row into the terms editor displayed
`Operator draft counterparty` and `EFET physical supply`. Cause: the client record mapper
[`contractDraftFromRecord`](../../clients/web/src/app/contractImport.ts) merged the record onto
`cloneDefaultContractDraft()`, so every term the stored columns and `notes` do not carry fell back
to the new-draft template. That row records none of counterparty, agreement form, governing law,
source document/reference, index basis, title transfer, beach delivery point, physical exit point,
terminal access, capacity expiry or document status, so template text was presented as if it were
recorded terms.

Repair — client mapper and its saved-record call site only; no route, schema, permission,
backend arithmetic, page or translation change:

- `contractDraftFromRecord` now takes an explicit base. `"draft"` (the file-import path, unchanged)
  keeps the working draft's value for a term the record does not state; `"stored"` (the editor's
  saved-record load) clears every absent text field to blank, so the panel's existing `n/a`,
  `manual entry` and `no source reference` fallbacks show "unavailable" instead of an invented
  fact. Recorded values — stored columns and structured `notes` fields — are preserved.
- Numeric and list semantics are unchanged: an explicit `null` capacity stays `null` rather than
  becoming zero, the other numeric fields keep their existing fallback, `cloneDefaultContractDraft()`
  keeps the new-draft defaults, and no backend or optimiser arithmetic was touched. List reads now
  return fresh arrays, so a hydrated draft never aliases the base draft or the record it was mapped
  from.
- Consequences stated plainly: a stored row that does not record a validation-required term (this
  row records no counterparty) now shows it blank, and the existing save rule refuses to persist
  the draft until it is entered; an absent `document_status` displays the panel's existing
  `MANUAL_DRAFT` draft label, which is a display fallback, not a recorded status.

Honest limit recorded at baseline `9e0b26e`, repaired at baseline `35091c9` (bounded editor-integrity
task): the editor's save used to replace the entire `notes` value with its `web_contract_capture`
JSON ([`contractPayload.ts`](../../clients/web/src/app/contractPayload.ts)), overwriting note keys it
did not know — for example this row's `preview_portfolio_contract:not_customer_data` marker. The
save now starts from the row's own JSON object instead. A stored load carries it onto the draft as
`preserved_notes` (a structural copy, never a recursive merge, so no stored key can reach a
prototype and no draft aliases the record it was read from), and `buildContractPayload` copies that
object and overlays only the fields the editor owns, so unknown provenance/terms and nested values
survive a load/edit/save round trip. A stored `source` is preserved verbatim rather than rewritten
to `web_contract_capture`; only a draft with no stored object — a new draft, a file-import overlay,
or a row whose notes carry no JSON object — gets the explicit editor envelope. A stored value that
is not a JSON object (free text, malformed JSON, an array or a scalar) is kept as raw operator notes
under the write path's existing `operator_notes` key, which is where the API puts the same text, so
nothing is silently lost. A new draft and a file import clear the base instead of carrying a
previously loaded row's notes. No edit marker was added: the captured revision already records the
write's `recorded_by`/`capture_origin`, and the editor's own metadata (document name, status, source
reference) travels in the fields it owns. Backend payload shape, numeric semantics and the governed
upsert are unchanged.

Mapping-repair evidence: [`clients/web/tests/contractImport.test.ts`](../../clients/web/tests/contractImport.test.ts)
maps the live row's stored shape and pins absent-text blanking, preserved recorded values,
invalid/non-object notes treated as absent, list isolation, explicit `null` remaining `null`, the
unchanged file-import overlay and the unchanged new-draft template; a source check pins both
`useContractEditor.ts` call sites. Focused run: 9 tests passed and `tsc --noEmit` passed; the full
local web suite ran 758 passed with the four pre-existing sandbox-blocked `capturedBoardComparator`
CLI spawn tests failing on `EPERM` only. No migration, client dependency or API surface changed.

Round-trip evidence: [`clients/web/tests/contractNotesRoundtrip.test.ts`](../../clients/web/tests/contractNotesRoundtrip.test.ts)
pins unknown nested fields through load/edit/save, owned edits overriding stored values, preserved
`null`/`false`/`zero` values, a stored `source` never rewritten, contract switching and
new-draft/import resets, the `operator_notes` policy for non-object and malformed notes, and
structural copying without record aliasing or prototype pollution. Focused run: 10 new tests passed,
the five related web test files passed (37 tests), and `tsc --noEmit` passed; the full local web
suite ran 768 passed with only the four pre-existing sandbox-blocked `capturedBoardComparator` CLI
spawn tests failing. No migration, client dependency or API surface changed.

## 13. S1e implemented — bounded stale-edit precondition on the governed write (after baseline `6b5258d`)

The parent architect decision for this slice: keep the existing endpoint, database schema and
governed transaction; add an opaque edit token to the saved-contract reads and the write
response; the token covers **all** mutable persisted fields (identity, economics, display
metadata, raw operator notes, updated instant), not the economic revision alone; compare it
under the existing row lock *before* capture, audit or mutation; refuse rather than overwrite.
Implemented as recorded below.

- Token definition: [`contract_edit_token.py`](../../src/eurogas_nexus/domain/route_cost/contract_edit_token.py)
  hashes (SHA-256) a canonical JSON document carrying the schema discriminator
  `upstream-contract-edit-token/v1` plus every persisted column of
  `upstream_resource_contracts`, in the table's own order. A focused test asserts the covered
  field tuple equals the model's column set, so a column added later cannot silently escape the
  precondition. Decimal-free values are canonicalized without guessing: booleans, non-finite
  floats, non-text list entries and other types are refused; stored instants normalize to
  offset-less UTC text, so PostgreSQL's aware read and the SQLite fixture's naive read of the
  same instant produce the same token.
- Read/write surface: `GET /api/route-cost/upstream-contracts` returns each row's `edit_token`
  and the governed write response carries it alongside `write_outcome`/`latest_revision`. The
  repository read's `include_edit_token` flag keeps the other payload consumers (portfolio and
  scenario projections, resource-pool composition, agent context) at their previous shape.
- Precondition outcomes (all checked on the locked, refreshed row):
  `expected_edit_token` omitted/`null` means **create-only** and an existing identity is
  refused; a supplied token with no stored row is refused without inserting; a supplied token
  that no longer matches the row (stale read, another writer, or a metadata/notes-only edit)
  is refused; a malformed token is refused before any store access. A concurrent create loser
  (`INSERT ... ON CONFLICT DO NOTHING` inserted nothing) is refused rather than taking over
  the winner's row. A matching token proceeds through the unchanged S1c capture/audit
  transaction.
- Refusals are sanitized: HTTP 409 with `error: "conflict"` and the stable codes
  `contract_edit_conflict` / `contract_edit_token_malformed`, one fixed message each. No
  stored value, current commercial figure, stale payload or offered overwrite is returned, and
  no bypass exists. The existing capture-refusal codes (`contract_revision_mapping_ambiguous`
  and friends) are unchanged.
- Authority, acting principal, authorization and the audit transaction are unchanged; the
  precondition is one more refusal *inside* the same governed transaction, not a second write
  path. `require_acting_actor` still runs first.
- Compatibility path, stated honestly: the plain repository
  [`upsert_upstream_contract`](../../src/eurogas_nexus/db/repositories/route_cost.py) remains an
  explicit internal function for fixtures and seeding and enforces no token; only the public
  route is the governed write, and no API surface exposes the plain function.
- Honest limits: the token is an integrity/identity check on the mutable row within this
  deployment's storage. It is **not** cryptographic authenticity (anyone who can read the row
  can recompute it), **not** a monotonic lifecycle counter (it carries no ordering and is not
  the captured revision number), and not a substitute for the proposed
  `DRAFT|FROZEN|SUPERSEDED` lifecycle, effective windows, payment terms or valuation
  citation. It guards one mutable legacy row, nothing else.
- Client: the typed Web transport declares `edit_token` on the saved contract and
  `expected_edit_token` on the write payload. The stored draft carries the token *with its
  originating contract identity*; a new draft, a reset, a file import or a changed contract
  id clears it (create-only). A successful save folds only the refreshed lease and preserved
  notes from the server response - never the editor fields - so edits made while the request
  was in flight survive; the draft is cleared dirty only when it was not touched since
  submission. A conflict keeps the draft and shows an explicit EN/ZH reload-and-reconcile
  notice; there is no automatic retry, no overwrite and no success message on failure.
  The save notice itself is draft-scoped, not merely identity-scoped: a draft transition
  (stored load, reset, import or a typed contract id) releases a save still in flight from
  publishing it, and a newer save takes the claim, so a late answer cannot show a conflict,
  success or refresh-failure notice against a different draft. A committed write whose notice
  was taken away still returns the saved contract to the submitting editor - whose own
  draft-session guard decides whether it lands - and still refreshes the same-identity
  contract library; identity invalidation remains the separate guard that drops the response
  entirely. This notice claim guards nothing but the notice: it is not the identity
  generation, and stale workspace or library reads are handled by their own lanes.
- Evidence: [`tests/unit/test_contract_edit_token.py`](../../tests/unit/test_contract_edit_token.py)
  (token coverage, per-field invalidation, instant normalization, malformed/unsupported
  values); [`tests/integration/test_route_cost_contract_write_revisions.py`](../../tests/integration/test_route_cost_contract_write_revisions.py)
  (stable token across read/write/fresh-session, economics-only and metadata-only
  invalidation, stale update leaves row/revisions/audit unchanged, create-only refusal,
  nonexistent-row refusal, malformed-token refusal, create-race loser refusal, unknown-notes
  preservation); [`tests/integration/test_contract_revision_capture_postgres.py`](../../tests/integration/test_contract_revision_capture_postgres.py)
  (opt-in disposable-PostgreSQL concurrent same-token updates, fresh-token reconciliation and
  concurrent create refusal); [`clients/web/tests/contractEditPrecondition.test.ts`](../../clients/web/tests/contractEditPrecondition.test.ts)
  (client lease lifecycle, ID-change safety, in-flight edit preservation, conflict
  classification and preservation, stale/failed save never folding or clearing dirty), and
  [`clients/web/tests/contractSaveFlow.test.ts`](../../clients/web/tests/contractSaveFlow.test.ts)
  (real-store async flow: committed write vs failed follow-up read, draft-transition notice
  ownership, same-id reload, overlapping saves and identity invalidation).
- Deployment: no migration (the schema is unchanged), no startup hook, no backfill, no new
  dependency and no runtime database write in this slice. The PostgreSQL-authoritative cases
  run only in the existing disposable-database opt-in job, never against a workstation store.

## 14. Bounded stale-read ordering repair (client read lanes, baseline `83bcc59`)

Parent review of S1e's client slice found that the committed save's library refresh was not
sequenced against other reads: `saveDraftContract` re-read `upstreamContracts` and
`resourcePoolOptions` after the write and published both unconditionally, while the workspace
batch, its retry pass and the context-change re-reads wrote the same fields from their own
answers. A read dispatched before the write could resolve after the save's refresh and replace
the library rows (carrying pre-write edit tokens) and the pooled resource view with its pre-write
reading. This slice fixes that ordering; it adds no capability.

- Contract library lane: `upstreamContracts` now has its own claim sequence in
  [`stores/api.ts`](../../clients/web/src/stores/api.ts), like a projection lane. The workspace
  batch and its bounded retry claim it at dispatch; a committed write bumps the sequence before
  its refresh, so every read dispatched before the write loses its claim even when this save's
  refresh never lands. Only the newest claim writes rows and the endpoint record; a superseded
  answer writes neither.
- Failed reads: a failed library read no longer clears the rows (the batch previously published
  `[]` for a failed slice). The last good rows stay and the failure is recorded in
  `endpointErrors.upstreamContracts` (retryable through the existing bounded control); the save
  refresh reports "… was saved, but refreshing the contract library failed: …" in its own lane.
- Pooled resource view: the save's refresh no longer calls the pool-options route. It re-reads
  the canonical portfolio projection through the existing `reReadPortfolioSnapshot` lane read -
  the same read the batch and a context change use - so the pool block arrives with its slice
  freshness, entitlement and source metadata. A committed write bumps the portfolio lane's
  sequence, so a batch dispatched before the write retains the lane instead of publishing its
  pre-write payload, and a context change still clears the lane and drops any older-context
  answer.
- Unchanged: the committed save result (with its refreshed edit token) is still returned to the
  submitting editor - with no write retry and no draft clearing - even when the refresh read
  fails or is superseded; the S1e notice claim is unchanged; identity invalidation still drops
  the library, the pool view and the returned record.
- No API, schema, permission, migration, dependency or runtime database write; the claimed reads
  are client-side ordering only.
- Evidence:
  [`contractLibraryReadOrder.test.ts`](../../clients/web/tests/contractLibraryReadOrder.test.ts)
  drives the real store with only the HTTP boundary mocked and its answers deferred: a pre-write
  batch resolving after the save cannot republish; a batch dispatched after the refresh
  supersedes it; a newer save's refresh supersedes a delayed earlier one; a failed latest read
  keeps the last good rows and records the failure while a late older answer cannot resurrect
  stale rows; identity invalidation drops the pool view as well as the library; a context switch
  drops the refresh's older-context pool view while the context re-read answers.
- Honest limits: the shared `loading` flag is still not action-scoped (recorded in the execution
  state), and the save's success notice is still published before its refresh answers - the
  notice is draft-scoped, not refresh-scoped.

## Open decisions (parent/reviewer)

Capture/replay clarification: an unchanged, previously uncaptured legacy row
still gains its first capture and capture audit. The `unchanged` outcome means
no source-row mutation, not necessarily zero evidence inserts. Already-captured
identical replays add neither a revision nor a mutation audit.

Review constraints: the semantic kernel's `Money`/FX magnitudes use floats; reuse identifiers and vocabulary, not those numeric representations for exact cash arithmetic. Preserve Decimal/string transport. Mutable metadata and document references must be snapshotted when cited as valuation evidence. The proposed lifecycle vocabulary must distinguish retirement from supersession before implementation.

1. Anchor vocabulary, calendar, business-day convention and day-count set — require commercial/legal review; none is asserted here.
2. Revision numbering per contract versus per right (capacity/TSO/slot).
3. Whether valuation citations need a persisted run record or the existing analysis-snapshot/decision-case lineage suffices.
4. Whether `ContractRevision`/`PaymentTerms` become ontology concepts or slots on the existing binding.
5. Migration path for `notes`-embedded economic fields without breaking current read payloads.
