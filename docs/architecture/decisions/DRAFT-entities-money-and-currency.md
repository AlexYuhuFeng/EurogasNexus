# DRAFT ADR: Legal entities as reference data; money as exact decimals with an explicit currency

**Status:** DRAFT, awaiting owner review (2026-11-26). Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) section 3.1. On acceptance it is appended to
[ARCHITECTURE_DECISION_RECORD.md](../ARCHITECTURE_DECISION_RECORD.md). It amends Decision 26
(a book's legal entity becomes a reference, not text) and extends Decision 27 (currency and
units) to storage.

**Context.** About 206 `Float` columns hold prices, quantities, credit limits, profit and loss and
invoice amounts, against about 16 exact-decimal ones (`db/models`). Product control cannot
reconcile floating-point figures to the cent. `domain/market_intelligence/normalized_view.py`
pins `TARGET_CURRENCY = "GBP"`, and columns such as `realized_pnl_gbp`, `unrealized_pnl_gbp` and
`contract_price_gbp_mwh` write a currency into the schema (six model files, mostly the strategy
laboratory, shadow and back-test tables, which the plan removes). A continental desk reports in
euros. A book's legal entity is a free-text `String(64)` (`db/models/books.py`): there is no
entity with a functional currency, LEI, ACER code, regulators, jurisdiction, data-residency
zone or holiday calendar, so nothing consolidates by entity, routes by regulator or applies the
right calendar (middle office, multinational, front office, quant reviews).

**Decision.**

1. **Legal entities** are effective-dated reference data: name, LEI, ACER code, functional
   currency, jurisdiction, regulators, data-residency zone, holiday calendar. Desks belong to an
   entity; books belong to a desk; traders link to identities. Counterparties gain parents,
   guarantors, master agreements and netting sets. The firm's own reference data (ETRM or ERP)
   is the master where it exists; entities are created in Nexus only where none exists.
2. **Holiday calendars** per exchange and market (EEX, ICE Endex, UK, CH, ES, IT, US) are
   reference data; freshness, expiry, rolls and the close read them.
3. **Money, prices and contractual quantities are stored exactly**: `Numeric(28, 10)` for amounts
   and prices, `Numeric(20, 6)` for energy quantities, each with an ISO 4217 currency and a unit
   column beside it (Decision 27's quote units, such as `GBp/th`, are kept as units). Python code
   handles them as `Decimal` at the storage and API boundary.
4. **Floating point stays where it is right**: physical measurements (flows, stocks, send-out),
   weather and statistical outputs, and inside numerical models (NumPy). A model's stored result
   of record is rounded to its declared precision and stored as a decimal.
5. **No column or field name carries a currency.** Figures are reported in three currencies,
   each named: the instrument's own (native), the entity's functional currency, and the reader's
   chosen reporting currency, converted through the dated FX table (Decision 27) and labelled
   with the rate and its date. The API returns `amount` with `currency`, never `amount_gbp`.

**Alternatives.** (a) Integers in minor units: exact, but prices need more precision than a
currency's minor unit (p/th to four decimals) and quantities are not money. (b) Keep floats and
round on display: does not reconcile when sums are compared with the ETRM. (c) Decimal
everywhere including measurements and models: slower numerics for no control benefit. (d) A
separate reference-data service: a new service with no need; reference data stays in the one
database.

**Consequences.** Every money-bearing table family changes once. JSON responses carry decimals
as strings or numbers with stated precision (the API contract states which). Reports and the
ladder gain an explicit reporting-currency choice. Entity scope becomes available to the access
model, which the role-model decision uses.

**Migration (expand and contract, no big bang).** Order: the strategy, shadow and back-test
tables are removed rather than migrated (plan section 5). Then per family (risk, credit and
limits; profit and loss and invoices; trades and curves; contracts and capacity): (1) add the
decimal and currency columns, (2) dual-write for one release, (3) a reconciliation test proves
old and new agree within the float's precision, (4) readers move, (5) old columns dropped in a
later release with a reversibility statement. `legal_entities` arrives first; `books.legal_entity`
text is matched to entity keys by a reviewed mapping, kept as a read-only column for one release.

**Tests that make it observable.** A schema test that refuses a new `Float` column in the money
families and any column name ending in a currency code; a reconciliation test per family; a
consolidation test that rolls two entities' books up in each functional currency with the rates
named.
