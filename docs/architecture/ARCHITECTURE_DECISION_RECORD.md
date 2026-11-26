# Architecture Decision Record

## ADR Index And Process

This file is the single ADR index and record for Eurogas Nexus. Do not create a
separate architecture-decision authority. Accepted architecture changes must be
recorded here in the same change that introduces them.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this section are to be
interpreted as described in RFC 2119 and RFC 8174.

### Index

| ADR | Title | Status |
| --- | --- | --- |
| ADR-0001 | Product is backend-first and multi-surface | Accepted |
| ADR-0002 | PostgreSQL is runtime truth | Accepted |
| ADR-0003 | Live PostgreSQL validation is in the current release | Accepted |
| ADR-0004 | Stable API prefix is `/api` | Accepted |
| ADR-0005 | Stack boundaries are explicit | Accepted |
| ADR-0006 | Domain work is slice-based | Accepted |
| ADR-0007 | Connectors fetch, they do not analyze | Accepted |
| ADR-0008 | SDK and CLI are API consumers | Accepted |
| ADR-0009 | Output metadata is mandatory for decision support | Accepted |
| ADR-0010 | Offline work is the default for local agents | Accepted |
| ADR-0011 | Historical projects are evidence, not source | Accepted |
| ADR-0012 | Product boundary is decision support only | Accepted |
| ADR-0013 | Documentation index, archive/RFC gates, and shared UI primitives are the baseline | Accepted |
| ADR-0014 | Public RFC/ExecPlan governance replaces private milestone archives | Accepted |
| ADR-0015 | Professional workstation UI convergence contract | Accepted |
| ADR-0016 | Architecture V2 programme authority and product-experience interaction authority | Accepted (supersedes part of ADR-0015) |
| ADR-0017 | Reviewed Cargo licence choices (Decision 16) | Accepted |
| ADR-0018 | ECMWF weather to regional gas demand (Decision 17) | Accepted |
| ADR-0019 | Multi-surface development and delivery pipelines (Decision 18) | Accepted |
| ADR-0020 | ENTSOG native rates (Decision 19) | Accepted |
| ADR-0021 | EEX receipt-bound price evidence (Decision 20) | Accepted |
| ADR-0022 | Desktop shell stays Tauri 2, hardened (Decision 21) | Accepted |
| ADR-0023 | Global topology: UK-hosted primary plus a China installation (Decision 22) | Accepted |
| ADR-0024 | Settings tiers: profile, organisation defaults, personal preferences (Decision 23) | Accepted |
| ADR-0025 | Time-series storage stays in PostgreSQL; index first, partition on measured need (Decision 24) | Accepted |

The numbered sections below are the historical record for these ADRs. ADR-0003
corresponds to Decision 2A below; subsequent decisions shift by one in the
section numbering.

### Process

1. A proposal MUST state the decision, the alternatives considered, the
   affected owners, and the non-goals.
2. Accepted ADRs MUST be appended to this file and to the index. Existing ADR
   text MUST NOT be edited to mean something different; supersede it with a new
   ADR that links the old one.
3. An accepted ADR SHOULD have at least one contract or focused test that makes
   the decision observable where practical.

## Purpose

This record removes ambiguity for implementation agents and keeps the worktree
aligned with the current gas decision-support goal.

## Decision 1: Product Is Backend-First And Multi-Surface

Decision:

Eurogas Nexus includes a Python backend/API service, PostgreSQL runtime
store, Python SDK, CLI, React/Vite Web workspace, and Tauri desktop shell. It
is backend-first because all runtime truth and integration boundaries remain
behind `/api`, not because clients are absent.

Implication:

- Backend/API remains the authoritative runtime boundary.
- The Python SDK is a required product surface and targets `/api`.
- CLI, Web, and Windows clients consume `/api` contracts.
- Web is the primary trader workspace.
- Windows/Tauri packages the same Web workspace.
- Client work may continue under `clients/`, but clients must not connect
  directly to PostgreSQL or read backend local files.

## Decision 2: PostgreSQL Is Runtime Truth

Decision:

PostgreSQL is the runtime source of truth. Local files are not runtime truth in
trial or release modes.

Implication:

- Runtime reads/writes go through repositories.
- Alembic owns migrations.
- Local files are templates, archives, reports, fixtures, or explicit
  development fallback only.
- Preview/test data must be inserted into PostgreSQL with explicit source
  provenance. Price previews use simulated source systems such as `EEX_Sim`,
  `ICE_OCM_Sim`, and `ICIS_Sim` in `market_observations`.

## Decision 2A: Live PostgreSQL Validation Is In The Current Release

Decision:

the product supports explicit live local PostgreSQL validation when the operator
configures a safe DB URL.

Implication:

- App import, route registration, and default tests remain DB-free.
- Read-only validation against a live database is allowed through documented
  operator commands.
- Migration execution is explicit and must not run during import, startup, or
  default tests.
- Secrets and full DB URLs must never appear in output.

## Decision 3: Stable API Prefix Is `/api`

Decision:

New stable client-facing routes use `/api`.

Implication:

- SDK, CLI, Web, and Windows target `/api`.
- `/api/health` is the canonical public health endpoint.
- Internal routes use `/api/internal`.
- Development routes use `/api/dev`.

## Decision 4: Stack Boundaries Are Explicit

Decision:

Use Python/FastAPI/SQLAlchemy/Alembic for backend runtime, React/Vite/TypeScript
for Web, and Tauri/Rust only for the desktop shell.

Implication:

- Backend import paths must not depend on Node, React, Vite, Tauri, Rust,
  browser APIs, or desktop runtime APIs.
- Client code must not import backend internals.
- Electron is not approved for the current release.
- Historical Rust/React/Tauri demos are product evidence, not source code to
  copy into this repository.

## Decision 5: Domain Work Is Slice-Based

Decision:

New product capability should be added as narrow slices with clear data,
contract, API, client, test, and documentation impact.

Implication:

- Each slice needs a contract doc or documented update.
- Each slice must state DB impact, API impact, data policy, tests, validation
  commands, and rollback notes when relevant.
- UI improvements should expose real backend capability or explicit missing
  inputs, not fabricated client-side data.

## Decision 6: Connectors Fetch, They Do Not Analyze

Decision:

Connectors are transport adapters only.

Implication:

- Connector output goes to ingestion/normalization.
- Analytics belong in domain/application layers after canonical data is stored.
- Live connectors require explicit entitlement and credential approval.
- Tests and imports must not make live external provider or LLM calls.

## Decision 7: SDK And CLI Are API Consumers

Decision:

SDK and CLI must call the backend API. They must not import domain,
application, runtime store, or DB internals.

Implication:

- SDK tests assert paths and response models.
- CLI tests mock SDK/API clients, not domain functions.
- SDK implementation follows `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`.
- CLI implementation follows `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`.
- SDK/CLI expansion should not be bundled into unrelated Web or Windows work.

## Decision 8: Output Metadata Is Mandatory For Decision Support

Decision:

Decision-support outputs must carry enough context for human review.

Implication:

Research and intelligence result models include:

- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- `research_only`;
- `human_review_required`.

## Decision 9: Offline Work Is The Default For Local Agents

Decision:

Future local implementation sessions are assumed offline unless the user says
otherwise.

Implication:

- Plans must state `Internet required: no` for local work.
- Tasks needing current external docs must state `Internet required: yes` and an
  offline fallback.
- Offline fallback means mocks, interfaces, tests, and gap reports.

## Decision 10: Historical Projects Are Evidence, Not Source

Decision:

Historical Desktop projects and demos inform product intent and failure
patterns. They are not source code for the current repo.

Implication:

- Extract workflow and architecture lessons.
- Do not copy old code, assets, data, `.env`, credentials, generated reports,
  or vendor artifacts.

## Decision 11: Product Boundary Is Decision Support Only

Decision:

Eurogas Nexus supports gas-trader intelligence and review. It does not execute
or officially recommend trades.

Implication:

the product must not implement:

- order entry;
- order routing;
- order amendment or cancellation;
- trade capture;
- nomination submission;
- official approvals;
- settlement/accounting;
- legal advice;
- official trading recommendations;
- auto-trading;
- ETRM replacement behavior.

## Decision 12: Documentation And UI Baseline Is Maintained Through One Index And One Primitive Boundary

Decision:

`docs/README.md` is the authoritative documentation index; RFC, archive, and
Markdown-link gates govern documentation changes; shared Web UI primitives live
under `clients/web/src/components/ui`.

Implication:

- Root README remains a landing page, not an operations manual.
- Current, runbook, design-reference, historical, and archived documents are
  labelled in the documentation index.
- Obsolete documents move through the archive policy instead of being deleted or
  mixed with current material.
- Shared UI primitives (`WorkspaceTabs`, `PanelHeader`, `StatusBadge`,
  `MetricStrip`) are owned under `components/ui`; workspace components own domain
  rendering and may consume primitives but must not fork their markup or
  keyboard behavior.

## Current Recommended Next Step

Follow `docs/release/RELEASE_READINESS.md`. It is the active ordered
implementation queue; do not use archived milestone plans as a new work
list.

## Decision 13: Public RFC And ExecPlan Governance Does Not Restore Private Records

Decision:

The repository provides a lightweight public RFC/ExecPlan workflow under
`docs/engineering/`. It does not restore deleted internal plans or publish a
private milestone archive. The public workflow is the current implementation
path for reusable proposals and bounded plans.

Implication:

- `docs/engineering/RFC_PROCESS.md` defines proposal and acceptance workflow.
- `docs/engineering/RFC_INDEX.md` and `EXECPLAN_INDEX.md` contain only reusable
  public records.
- README files remain descriptive navigation; normative requirements use RFC
  2119 and RFC 8174 language in policies, contracts, RFCs, or ADRs.
- The accepted ADR history above remains unchanged; future changes append or
  supersede rather than silently rewriting an accepted decision.

## Decision 14: Professional Workstation UI Convergence Contract

Decision:

[RFC-0001](../engineering/RFC-0001-UI-CONVERGENCE.md) is accepted on
2026-09-08 as the binding contract for shared Web/desktop visual and
interaction convergence. The Professional UI Constitution is the sole visual
and interaction authority; `MOTION_SYSTEM.md` is subordinate. `UI_CONTENT_STANDARDS.md`
continues to govern content, domain, time basis, rights, provenance,
entitlement, no-execution, and client-boundary rules. Architecture and API
contracts prevail for domain behavior, schemas, endpoint semantics, and
server/client boundaries. The paired EN/CN guides, `WORKSPACE_LAYOUT_STANDARD.md`,
and `ACTION_GEOGRAPHY.md` are nonnormative or subordinate implementation
companions as defined by RFC-0001.

Implication:

- Contract adoption is distinct from implementation acceptance. Screenshots,
  runtime review, tests, accessibility checks, and visual evidence remain open
  gates and are not claimed by this decision.
- The pre-refactor workflow inventory and coverage remain incomplete; its gate
  stays open.
- This decision changes no domain, API, numerical, rights, calendar, or
  execution rule beyond the authority reconciliation recorded in RFC-0001.

Review record:

- The planner reviewed the drafts, diffs, component census, runtime UI audit,
  and RFC clarifications.
- Planck independently reviewed the contract direction, and the clarifications
  were addressed.
- No human-owner review or implementation acceptance is claimed.

## Decision 15: Architecture V2 Programme Authority And Product-Experience Interaction Authority

Decision:

The Architecture V2 pack under
[`docs/engineering/Architecture-V2/`](../engineering/Architecture-V2/00_README.md)
is accepted as the binding target architecture and product-experience
authority for Eurogas Nexus, under the operating rules of
[`AUTONOMOUS_EXECUTION_POLICY.md`](../engineering/Architecture-V2/AUTONOMOUS_EXECUTION_POLICY.md).

Authority is allocated as follows:

- [Product Experience Architecture](../engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md)
  governs task flows, shell composition, workspace patterns, navigation
  composition, panel taxonomy, the Inspector, action geography, the canonical AI
  actions and the command/keyboard interaction model.
- [`PROFESSIONAL_UI_CONSTITUTION.md`](../clients/PROFESSIONAL_UI_CONSTITUTION.md)
  retains its authority for typography, density, spacing, component styling and
  visual motion, and is subordinate to the product-interaction contracts above
  where the two overlap.
- [`MOTION_SYSTEM.md`](../clients/MOTION_SYSTEM.md) remains the binding
  subordinate motion contract and cannot create a competing interaction model.
- [`UI_CONTENT_STANDARDS.md`](../clients/UI_CONTENT_STANDARDS.md) retains
  authority for content, domain, time basis, rights, provenance, entitlement and
  no-execution rules.
- Domain, API, data, security and release contracts retain their existing
  precedence for domain behaviour, endpoint semantics, schemas and
  server/client boundaries. A UI document cannot override them.
- Functional assignment and work mode SHALL NOT grant backend authority
  ([Constitution](../engineering/Architecture-V2/02_ARCHITECTURE_CONSTITUTION.md)
  rules 16-20, 27). Composition never creates a permission.

Implication:

- [RFC-0001](../engineering/RFC-0001-UI-CONVERGENCE.md) remains accepted. Only
  its authority-matrix row naming the Professional UI Constitution as sole
  *interaction* authority is superseded, and it is superseded by this record
  rather than by editing RFC-0001 or Decision 14. Decision 14's history, its
  implementation acceptance gates and its rights-validation matrix remain in
  force unchanged.
- The normative hierarchy conflict recorded in
  [`AUTHORITY_RECONCILIATION_PROPOSAL.md`](../engineering/Architecture-V2/AUTHORITY_RECONCILIATION_PROPOSAL.md)
  is closed. That proposal's "PROPOSED" status is historical; this decision is
  the accepted resolution.
- Wave 1 delivers the interaction authority as machine-readable contracts under
  `clients/web/src/app/experience/` with focused tests, so the authority is
  executable rather than prose: shell regions, workspace patterns, panel
  taxonomy, action geography, canonical AI actions, the Inspector contract, the
  command palette and the Active Context contract.
- Contract adoption is not implementation acceptance. RFC-0001's screenshots,
  visual review, accessibility, performance, EN/CN, entitlement and UAT gates
  stay open, and the pre-refactor workflow inventory gap is unaffected.
- No domain, API, numerical, rights, calendar, execution, permission or release
  behaviour changes by this decision.

Review record:

- Generated under `AUTONOMOUS_EXECUTION_POLICY.md` section 2, which permits
  automatic supersession of an accepted ADR when it conflicts with Architecture
  V2, provided the superseding decision links the old one and preserves its
  history. No human approval was sought or required for this reconciliation.
- Evidence reviewed: `11_CURRENT_TO_TARGET_GAP_MATRIX.md` rows 24-27 (UI
  Constitution kept but subordinate; navigation and page composition marked
  REFACTOR), the W0-01 client inventory, the W0-02 backend access inventory, and
  the Wave 1 contracts with their focused tests.
- The professional trader/product-owner review of the resulting interaction
  grammar remains an open UAT gate; this record does not claim it.

## Decision 16: Reviewed Cargo License Choices

Accepted2026-10-28 under the autonomous execution policy, following
[RFC-0002](../engineering/RFC-0002-REVIEWED-CARGO-LICENSE-CHOICES.md). The root
architecture/integration review verified the exact r-efi5.3.0/6.0.0 archives
against Cargo.lock and their complete AUTHORS texts. Select MIT for these
exact identities only, with validated archive checksum, exact declared license
expression, retained original text hash and actual Cargo-resolved text hash.

The dependency gate retains its strict default, full-graph coverage and all
unknown/malformed/restricted failure cases. This supplements the dependency
policy's explicit-review provision; it does not reinterpret arbitrary OR/AND/
WITH expressions. Future identity/version/text changes require a new reviewed
record. SBOM and notices must preserve upstream expression, choice and full text.

No separate legal clearance, signed release or customer acceptance is claimed.
Implementation and its negative tests remain necessary before CI may pass.
Rollback removes the reviewed choices and restores the current refusal. No
source license, dependency version, registry, permission or product boundary
changes. Existing decisions remain unchanged.

## Decision 17: ECMWF Weather To Regional Gas Demand

Accepted2026-10-28 under the autonomous execution policy and the owner's explicit
weather-to-supply/demand requirement. [RFC-0003](../engineering/RFC-0003-ECMWF-DEMAND-VERTICAL.md)
governs staged implementation and supersedes conflicting details in the
ECMWF_DEMAND_VERTICAL_DELIVERY_PLAN proposal, particularly future-valid forecast
features and speculative parallel storage. Reuse the existing research temporal/
forecast/artifact foundations. Preserve source/identity controls and product
boundaries. Root reviewed actual official directory/AWS registry responses and
public National Gas target documentation. No implementation, accuracy, source
activation, separate legal review or customer acceptance is claimed by adoption.

## Decision 18: Multi-surface development and delivery pipelines

Accepted 2026-10-28 under the autonomous execution policy and the owner's explicit
Linux/Web/Windows/SDK maintenance requirement. [RFC-0004](../engineering/RFC-0004-MULTI-SURFACE-PIPELINES.md)
requires shared native and installed-SDK workflows and adds their actual hosted
matrix leaf jobs to G1. Existing release, security, signing and external approval
boundaries remain in force. Adoption does not prove hosted execution or GUI UAT.


## Decision19: ENTSOG native rates

Accepted2026-10-29 under the Autonomous Execution Policy.
[RFC-0005](../engineering/RFC-0005-ENTSOG-NATIVE-RATES.md) replaces the assumed-CV
ENTSOG normalization with explicit same-dimension native rates, additive storage,
immutable normalization namespaces and opt-in native physical reads. Existing
volume DTOs remain non-null; unsafe legacy quantities are withheld with warnings,
not rewritten or zero-filled. Agent, SDK and shared client consumers migrate in
stages before the new ingestion path is admitted. Root architecture review does
not claim implementation completion, source activation or customer acceptance.


## Decision20: EEX receipt-bound price evidence

Accepted2026-10-29 under the Autonomous Execution Policy.
[RFC-0006](../engineering/RFC-0006-EEX-RECEIPT-PRICE-EVIDENCE.md) adds explicit
receipt-bound NGP mapping without assigning an unverified publication clock.
The existing strict mapper and source rights/certification gates remain.
Implementation, actual consumer use and delivery acceptance must be verified.


## Decision 21: Desktop shell stays Tauri 2, hardened

Accepted 2026-10-30. The Windows and Linux clients wrap the same React workspace in Tauri 2
(system WebView: WebView2 on Windows, WebKitGTK on Linux).

Alternatives considered: **Electron** gives identical Chromium rendering on every OS and a
larger ecosystem, but ships a 100+ MB runtime per release, uses several times the memory,
carries a Node.js main process with a wide attack surface, and needs its own Chromium
security patch cadence. A **web-only** client (browser PWA) is simplest to deploy, but
desks that lock browsers down or want a separate, always-on window lose the dedicated
window, OS-level single sign-on hand-off and deep links.

Why Tauri fits this product: it is a data and decision workspace, not a native trading
front end, so the WebView is enough. The Rust core holds no business logic (all logic is
behind `/api`), the permission set is `core:default` only, installers are about 10 MB, the
dependency graph passes the commercial licence audit (MIT/Apache-2.0), and the same build
runs on Windows x64 and Linux x64/arm64 in CI.

Hardening that comes with this decision:

- CSP: scripts only from the bundle; images from HTTPS (the customer's own tile service);
  `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`, `form-action 'self'`.
- No updater: updates are managed by the customer's software distribution.
- Windows desks without internet need an installer that carries WebView2 (offline or
  fixed-version mode). The default bootstrapper downloads it at install time.
- Linux rendering (WebKitGTK) differs from Chromium on WebGL maps and fonts. The native
  acceptance jobs build on Linux; GUI acceptance on a Linux desktop remains a release
  gate.

Revisit if a feature needs a Chromium-only API, if WebKitGTK defects block Linux desks,
or if the product adds order-entry latency requirements (out of scope today).

## Decision 22: Global topology is a UK-hosted primary plus a China installation

Accepted 2026-10-30. See [GLOBAL_DEPLOYMENT.md](GLOBAL_DEPLOYMENT.md). The UK, Canada and
Singapore offices share one installation because they share one trading book. Mainland
China runs a separate installation because personal-information, data-security, licensing
and network constraints all differ there. Installations do not share databases. Data moves
one way, primary to China, as signed, approved exports
([REGIONAL_EXCHANGE_PROTOCOL_V1.md](REGIONAL_EXCHANGE_PROTOCOL_V1.md)).

Rejected: one global installation (fails China constraints); one installation per office
(splits the book and duplicates ingestion and licences); active-active federation
(conflict resolution and deletion propagation with no use case). Read replicas and warm
standby are added on the measured triggers listed in that document, not before.

## Decision 23: Settings tiers

Accepted 2026-10-30. Profile (identity admin or SSO), organisation defaults (platform
admin, audited) and personal preferences (the user) are separate tiers with one owner
each; effective = personal, else organisation, else built-in. Personal preferences live
on the server per principal (`principal_preferences`) so they follow a person between
clients and offices. Only settings that change something are offered. No tier grants or
removes access. Tests: `tests/unit/test_settings_preferences.py`,
`tests/api/test_preferences_api.py`.

## Decision 24: Time-series storage stays in PostgreSQL; index first, partition on need

Accepted 2026-10-30. Observation volumes (ENTSOG flows and capacity, AGSI, ALSI, market
quotes) are millions of rows a year, well within PostgreSQL. Migration 0048 adds
source/time indexes next to the existing entity/period ones. Reads that scan history are
bounded (for example the spread lab's 150k-row ceiling).

Rejected for now: TimescaleDB or a separate time-series store (a new datastore and its
licence; AGENTS.md rule 5). Amended 2026-11-26 by Decision 39: the TimescaleDB extension may be
used, optional and off by default, on the same PostgreSQL server. Native declarative partitioning by month is the next step
when any observation table passes about 50 million rows or a time-range read exceeds its
latency budget after indexing. At that point a BRIN index on the time column replaces
the B-tree on the largest partitions. Retention (raw archive and audit pruning) and the
backup/restore drill apply per installation. Test:
`tests/db/test_alembic_revision_ids.py` guards the migration chain on PostgreSQL widths.


## Decision 25: The ontology is the typed reference-data backbone, not a runtime graph

Accepted 2026-10-30.

**Context.** The ontology (`src/eurogas_nexus/domain/ontology/`) grew from two ideas:
Palantir's Ontology (object types, links and actions laid over datasets so every
application shares one model) and Kraken's single domain model. In practice it held
controlled vocabularies, typed concepts, constraints and an OWL export of gas-market roles
(GRM). Meanwhile the facts a desk relies on most (which hubs exist, their currency, quote
unit, calendar and time zone) were repeated in at least seven modules, and there was no way
to add a commodity or region without editing all of them.

**Decision.** The ontology is the **reference-data backbone**, the equivalent of an ETRM's
static data:

1. *Semantic structure lives in code.* `ontology/markets.py` defines commodities (gas, LNG,
   power, emissions, coal), regions (Europe, North America, Asia) and every pricing point
   with its currency, native price and quantity units, delivery calendar, time zone,
   licensed price sources and public reference. Vocabulary enums, concepts, relations,
   actions and constraints stay alongside it.
2. *Everything reads from it.* Hub lists, unit conventions, currency rules and
   recognised codes in portfolio, units, licensed import, route costs and agent tools
   derive from the model. A new market is one entry, plus the ingestion and analytics
   that use it.
3. *Instances live in PostgreSQL.* Observations, contracts, positions and books reference
   markets by code. Effective-dated network reference tables (`reference_market_hubs`,
   facilities, edges) remain the DB master for physical network instances.
4. *Exports are adapters.* OWL/Turtle (`docs/ontology/eurogas-nexus-grm.ttl`) is
   generated for interoperability and documentation; it is never read at runtime. The
   ontology carries its own semantic version.

**Rejected.** A runtime graph or triple store as the system of record (a new datastore
with no measured need, AGENTS.md rule 5; joins across observations and positions are
relational). A pure glossary (a dictionary does not stop seven copies of the hub list
drifting apart). A Palantir-style generic object platform (it would replace the typed
domain code that tests can check, for a configurability the desk does not need).

**Consequences.** Adding AECO, Alberta power or TIER credits for a Canada desk, or EU
power and EUA for a power desk, starts with the market model. Tests:
`tests/unit/test_market_reference.py` (every vocabulary hub is a market, calendars and
units resolve, aliases are unique), `tests/contract/test_ontology_version_alignment.py`.

## Decision 26: Multiple commodities, regions and books in one installation

Accepted 2026-10-30.

**Context.** The firm trades from offices in several countries and may add commodities
beyond European gas: European power and carbon, Canadian AECO gas exported towards Henry
Hub, Alberta power and emission credits. Head office reads performance across all of them;
regional heads and desks read their part.

**Decision.**

1. *Markets* come from the market model (Decision 25): commodity, region, currency, units,
   calendar. A new commodity or region is reference data plus the ingestion and analytics
   that use it.
2. *Positions* are held in **books**; a book belongs to a business in a region of a legal
   entity (`trading_books`; `book_id` on contracts and screen trades). Roll-ups read the
   same positions at firm, legal-entity, region, business or book level.
3. *Money* is reported in one chosen currency. Each market's own currency is converted
   through ECB reference rates; a position without a rate is left unvalued and counted,
   never added unconverted.
4. *Time* stays per market: EU-CAM and NAESB gas days, power hours in the market's zone.
5. *Access* is by role and data scope today. Restricting a desk to its own books needs a
   `PORTFOLIO` scope kind keyed on book or legal entity; until then, separate books that
   must be hidden from another office need separate installations
   ([GLOBAL_DEPLOYMENT.md](GLOBAL_DEPLOYMENT.md)).

**Rejected.** One installation per commodity or per office (splits the firm's book and
duplicates data and licences); currency-blind totals.

Tests: `tests/api/test_portfolio_books_api.py`, `tests/unit/test_market_reference.py`.


## Decision 27: One foundation for currencies, units and time

Accepted 2026-10-31. Offices in several countries and markets in several commodities meet
many currencies (EUR, GBP, USD, CAD, CNY, SGD, ...), quote conventions (pence per therm,
offshore CNH), units (MWh, therm, MMBtu, GJ, m3, t, tCO2) and clocks (EU and NAESB gas
days, power days, office time zones). Each of these now has one definition in the ontology
package, and code converts only through it:

- `domain/ontology/currency.py`: ISO 4217 currencies with minor units; quote units that
  resolve to an ISO currency and a divisor (`GBp` -> GBP/100, `CNH` -> CNY); `Money`
  rounded only for presentation; `FxTable` of dated rates from a named source converting
  directly, inversely or through one pivot. A missing rate is an error, never 1.0.
- `domain/ontology/quantity.py`: units with dimensions (energy, volume, mass, emissions,
  power); conversion only within a dimension, and price units `<currency>/<unit>`.
  Crossing dimensions (volume to energy, coal tonnes to energy) needs a stated factor.
- `domain/ontology/timebase.py`: instants are aware UTC (naive datetimes refused);
  business dates come from the market's calendar; people read instants in their office's
  zone. Offices name their currency and the installation that holds their data.

The position ladder and the gas price converter use the shared FX table. Tests:
`tests/unit/test_foundation_currency_units_time.py`.

## Decision 28: Market events go through a PostgreSQL transactional outbox, not a broker

Accepted 2026-11-24 (branch `innovation/continuous-commercial-intelligence`, programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/03_TARGET_ARCHITECTURE.md)).
Before this decision a market change reached the opportunity engine only as a class-level
flag (`opportunity_pending_inputs`, CP-13): no event identity, no revisions at event level,
no replay and no way to re-evaluate only what a change touches. The platform now records
each change as a canonical market event in the runtime store, in the same transaction as
the data it describes, and delivers it to registered consumers from there:

- `domain/market_events`: the pure event model. Identity is a hash of source, type,
  subject and market time (or an explicit identity such as a REMIT message id); content is
  a hash of the canonical payload and dependency keys, never of publication or ingestion
  time. A changed figure is a new revision that supersedes the last; the same figure again
  is a duplicate; a figure older than the latest revision is out of order. Neither of the
  last two writes anything. Five timestamps are kept: market event, source publication,
  platform ingestion, processing completion and user notification.
- Migration `0077_market_event_outbox`: `market_events` (unique `event_key, revision`) and
  `market_event_deliveries` (one row per consumer and event, with status, attempts,
  backoff, last error and result).
- `application/market_events.py`: `publish` (savepoint, decision, insert, supersede the
  previous revision's undelivered rows, fan out to consumers, `pg_notify` at commit);
  `process` claims due rows by priority with `FOR UPDATE SKIP LOCKED` on PostgreSQL, runs
  each batch in a savepoint, retries with exponential backoff (1 min doubling, cap 1 h) and
  dead-letters after 5 attempts; `replay` re-arms or creates deliveries for the current
  revision of each event; `status`, `staleness` and `timeline` serve operations.
- The first consumer re-evaluates only the evaluators whose stored opportunities depend on
  the event's keys (`opportunity_dependencies`), with trigger `outbox`. Discovery of new
  opportunities stays with the CP-13 debounced full evaluation.

Polling is authoritative; `LISTEN/NOTIFY` only wakes a worker early. Kafka, a separate
broker and new services stay out (AGENTS.md rule 5, Decision 2 and
[STREAMING_KAFKA_CONTRACT.md](STREAMING_KAFKA_CONTRACT.md)) until a measured need such as
cross-installation fan-out or sustained throughput beyond what one PostgreSQL primary
serves. Tests: `tests/domain/test_market_events_model.py`,
`tests/integration/test_market_event_outbox.py`,
`tests/integration/test_market_event_outbox_postgres.py`,
`tests/unit/test_market_event_outbox_migration.py`.

M5 (2026-11-24): producers capture changes from the stored rows rather than hooking each
writer, because writers mix Core upserts and ORM merges. `application/market_event_capture.py`
publishes settlements (`hub:<HUB>:<period>`, identity hub, period, venue and trade day), FX
fixings (`fx:<BASE><QUOTE>`) and REMIT messages (`outage:<message id>`, versions as
revisions) after each scheduler cycle and inside the settlement and FX importers' own
transaction. Held content writes nothing. The consumer widens a EUR fixing to stored cross
pairs. Tests: `tests/integration/test_market_event_capture.py`.

M5b and M6 (2026-11-24): desk edits (contracts, hedge bands, assumption versions) publish
digests captured from the store at save time; a later publication returning to earlier
content is a revision. Monitoring raises one alert per stale source, dead letter and lag
condition and clears it on recovery. Tests: `tests/integration/test_desk_event_capture.py`,
`tests/integration/test_feed_and_outbox_alerts.py`.

## Decision 29: Hedges against an LNG cargo are recorded by the desk, never placed

Accepted 2026-11-24 (branch `innovation/continuous-commercial-intelligence`, programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/12_LNG_CARGO_IN_TRANSIT.md)).
A cargo in transit is planned as one chain from ETA to hedge months, and the plan needs to
know which hedges cover which cargo. Trades by hub and month cannot say that, so the desk
records the legs against the cargo: migration `0078_lng_cargo_hedges` (`lng_cargo_hedges`:
cargo, hub, delivery month, signed MWh, reference, who and when, retired by and when).
Replacing a set retires the old rows rather than deleting them, the change is audited, and
a `cargo.changed` market event carries the plan inputs (ETA, departure, energy, slot,
hedges; not vessel positions) so the plan before any change can be rebuilt and compared.
Exposure is allocated by the terminal's send-out profile by gas day, not by arrival date.
The platform suggests rolls, sales, buy-backs and short-notice cover; it places nothing
(AGENTS.md rule 8). Matching recorded legs to ETRM trades is left for the integration layer.
Tests: `tests/domain/test_lng_in_transit.py`, `tests/api/test_lng_cargo_plan_api.py`,
`tests/sdk/test_lng_cargo_plan_client.py`.

## Decision 30: Scheduling is a role, not a job function

Accepted 2026-11-24 (branch `innovation/continuous-commercial-intelligence`, programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/13_PERSONA_AND_PRACTICE_REVIEW.md),
finding QA-T-06). The person who schedules gas, a VIEWER with the OPERATIONS job function,
could not record that a nomination was sent, because recording needed `portfolio.write`,
which also edits contracts and positions. Job functions compose the screen and never grant
authority (decision D4, machine-checked), so the fix is a role: `SCHEDULER` holds a viewer's
reads plus one permission, `gas_day.record`, which records nomination and terminal-step
status by hand (nothing is nominated or sent; AGENTS.md rule 8). ANALYST also holds it.
SCHEDULER ranks above VIEWER and below REVIEWER, so the route gate admits it exactly where
it admits a viewer; the status route's gate category floor is SCHEDULER and its handler
requires `gas_day.record`. This mirrors an ETRM's scheduling security group. Rejected:
letting OPERATIONS grant the write (breaks D4); giving schedulers ANALYST (strategies,
scenarios and book edits they do not need). Tests: `tests/api/test_gas_day_status_api.py`,
`tests/unit/test_demo_identity_access.py`.


## Decision 31: Licensed data use is counted per request into one aggregated table

Accepted 2026-11-24 (branch `wip/gov`, programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/16_COMPETITIVE_STUDY.md),
lesson P6, slice GOV-1). Exchanges and data vendors ask the firm to declare who used their
data and what left the platform as a file. The entitlement checks
(`security/identity.principal_allows_source_family`,
`domain/dataops/entitlement.principal_allows_source`) already decide every licensed read, so
they note each vendor-licensed family they allow in a per-request meter
(`governance/usage.py`, a context variable, no I/O). One ASGI middleware
(`api/middleware/licensed_use.py`) counts each family once per request, after the response,
off the event loop, into migration `0079_licensed_data_use` (`licensed_data_use`: day,
principal, family, route template, reads, first and last read; primary key on the first four,
an upsert). It is a new table in the existing PostgreSQL database, not a new datastore.
Usage of a read is best-effort, like the read's audit (P5 makes only governed writes fail
closed). File exports (CSV, XLSX, PDF through `api/csv_export.py`) read the same meter and
apply `ExportDecision` per family (`governance/entitlement.file_export_decision`): a current
licence that allows redistribution allows the file, any other registered or known licensed
family restricts it to internal use, and a family with no registered terms is refused
(fail closed). Rejected: one row per request (volume without meaning), a declared family per
route (routes compose several sources), a broker or analytics store (rule 5).
Tests: `tests/unit/test_licensed_use.py`, `tests/api/test_licensed_use_api.py`.

## Decision 32: Changes to limits and reference data are proposed and approved in one table

Accepted 2026-11-24 (branch `wip/p17`, programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/13_PERSONA_AND_PRACTICE_REVIEW.md),
finding P-17 and P-01's second half). A change to a credit line, a trader mandate, a deal hedge
band, the firm's marks, LNG terminal terms or a freight route takes effect only when a
different authorised person approves it (four eyes, as in an ETRM's or a bank's market-risk
controls). The writes and who approves each are one register in code
(`governance/four_eyes.py`): the risk function (REVIEWER and no front-office role) for limits,
bands and marks (for marks, the independent price check), another person with portfolio write
for terminal terms and freight routes, and never the trader for their own mandate. A proposal
is one row in migration `0081_change_requests` (`change_requests`: the action, the record it
targets, the payload, each field before and after, the reason, the proposer and time, and the
decision); approval re-reads the stored figures `FOR UPDATE`, refuses a stale proposal, applies
the payload through the same write path as before (`application/reference_rows.py`,
`application/maker_checker.py`) and stamps a nullable `change_id` on the governed row, so each
figure keeps who proposed and who approved it (`provenance` on the reads). Proposal, approval,
rejection and withdrawal are governed writes (`record_governed_audit`, same transaction). It is
one table and six nullable columns in the existing PostgreSQL database, not a new service or
datastore, and no workflow engine. Which writes need two people is the organisation setting
`four_eyes` (default on for all six; an administrator switches one off, itself an audited
governed write), so a one-person or demo installation still works. Approved assumption sets
keep their own always-on draft and approval (CP-07). Writes answer 202 with the proposal
(recorded in the [API contract evolution policy](API_CONTRACT_EVOLUTION_POLICY.md)).
Rejected: a separate pending copy of each table (six schemas to keep in step); detecting "no
second approver exists" (identities are unknowable under SSO); a bypass endpoint for one-person
installs (an unaudited path round the control); effective-dated scheduling now (deferred).
Tests: `tests/api/test_maker_checker_api.py`, `tests/unit/test_maker_checker.py`,
`tests/integration/test_maker_checker_postgres.py`.

## Decision 33: ERP counterparty and invoice references are kept in one reference table

Accepted 2026-11-24 (branch `wip/data1`, programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/05_IMPLEMENTATION_ROADMAP.md),
slice DATA-1). The ETRM and ERP import contracts (`application/import_contracts.py`,
[ETRM_ERP_IMPORT_CONTRACTS.md](../integration/ETRM_ERP_IMPORT_CONTRACTS.md)) land deals, the
physical schedule, nomination statuses and the cargo schedule in the tables that already hold
them. The ERP's counterparties and invoices had no home, so migration
`0082_data1_integration` adds `erp_references`. It holds one row per (system, kind
`counterparty` or `invoice`, the ERP's own number), with the link to this platform's
counterparty (`counterparty_id`, as the credit lines name it), an invoice's ERP counterparty
and trade reference, the contract's other columns as `fields` (JSON) and their digest
`content_hash`, so a re-import of the same row changes nothing. It is a new table in the
existing PostgreSQL database, not a new datastore, and it is a reference for reconciliation,
not a ledger: nothing posts, pays or settles from it (AGENTS.md rule 8). The contracts refuse
a file that carries bank details or tax or government identifiers, so none is stored. The
same migration adds `market_events.writer_txid`, a nullable column stamped by PostgreSQL, so
that the change feed (`GET /api/market/changes`) serves events in commit-safe order without a
new table. Rejected: a table per ERP object (two now, more later, each with its own
migration), columns on `credit_lines` (an invoice is not a credit line, and an ERP
counterparty need not have one), and a connector per ERP product (vendor-specific code against
the contract-first rule).
Tests: `tests/api/test_data1_import_contracts.py`, `tests/unit/test_market_event_outbox_migration.py`.

## Decision 34: Public tariffs are versioned in a tariff book beside the registers

Accepted 2026-11-24 (branch `wip/tar1`, programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/05_IMPLEMENTATION_ROADMAP.md),
slice TAR-1). Route pricing and valuations keep reading the registers they read
(`tso_tariffs`: ENTSOG reserve prices, administrators' reviewed entries, documents an
administrator loaded; `lng_terminal_tariff`: terminal documents, read only once the firm has
recorded the operator's permission). Those registers hold the figure in force and are
overwritten when a publisher republishes, so the platform could not say what it knew before or
when a tariff went from indicative to final. Migration `0083_tar1_tariff_book` adds two tables
in the existing PostgreSQL database. `tariff_versions` keeps one row per version of one public
tariff: publisher (a registry in code, `domain/tariffs/publishers.py`), point or terminal,
operator, direction, capacity product and duration, firmness, value (or per cargo class), unit,
currency, period, status `INDICATIVE` or `FINAL` with its basis (operator stated, period
started or not, figures disagree, reviewed or awaiting review), publication and retrieval
times, source URL and a content hash. It is append-only except `superseded_at_utc`, stamped on
the version a newer one replaces, so a read as of an instant takes the version current then.
A new version is written only when the content hash differs; an older read never supersedes a
newer one; a change of status is its own named kind (`INDICATIVE->FINAL`), never silent; a row
that leaves a register is recorded as withdrawn. Each version publishes one `tariff.changed`
market event (Decision 28) in the same transaction, carrying the valuation snapshot keys
(`tariff:<point>:<DIR>:<PRODUCT>:<gas year>[:<operator>]`) and any stored opportunity
dependency key with the same prefix, so only the evaluators that read the tariff re-run.
`capacity_notices` keeps upcoming capacity windows: the CAM standard auctions derived from
Regulation (EU) 2017/459 and labelled rule-derived, and LNG slot or secondary-capacity notices
imported from a publisher's own list (one row per notice, a content hash and a revision count;
notices publish no market event, since they change no price an evaluator reads). Both are
tables, not a service or datastore; no source behind a login is read and no value is invented:
a publisher with only a PDF or HTML page is recorded in the registry with its page, cadence and
access `manual` or `parsed`. Rejected: deriving history from the `tariff.changed` revision chain
alone (DATA-1's as-of reads work on revision chains, but listing and filtering thousands of
tariffs by facility, status and period over JSON payloads is the wrong shape); versioning
inside `tso_tariffs` (its primary key and every reader would change); a scraper per TSO site
(terms not reviewed, most sites unreachable from the build environment on 2026-11-24).
Tests: `tests/unit/test_tariff_book.py`, `tests/unit/test_tariff_book_migration.py`,
`tests/domain/test_tariff_book_domain.py`, `tests/api/test_tariffs_api.py`,
`tests/integration/test_tariff_book_postgres.py`.

## Decision 35: News items and source polls are two tables in the runtime store; no news service

Accepted 2026-11-25 (branch `wip/news1`, programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/05_IMPLEMENTATION_ROADMAP.md),
slice NEWS-1). News, policy and geopolitical
events from public sources whose terms permit reuse
([NEWS_SOURCE_REGISTRY.md](../integration/NEWS_SOURCE_REGISTRY.md)) are stored by migration
`0084_news_items` in two tables of the existing PostgreSQL database: `news_items`, one row per
item (source, the source's own reference, URL, publisher, title, what the source's terms let us
keep of its text, language, published, retrieved and first-seen times, content hash, licence
note, deterministic tags as JSON, the held outage it is linked to, revision), keyed by a digest
of source and reference so a re-poll of the same entry changes nothing and an edit is a new
revision; and `news_source_polls`, one row per source with its last poll, status, counts and
the feed's ETag and Last-Modified for conditional requests. Each new or changed item publishes
a `news.published` market event through the existing outbox (Decision 28); an item on a held
outage carries that outage's dependency key, so opportunities re-evaluate through the existing
consumer, and the consumer `news_roles` routes items that touch the book to each role through
M7 routing. The poll runs as an operator script (`scripts/ops/poll_news_sources.py`), not a
service. Migration 0084 follows SCHED-1's `0085_sched1_nomination_matching`, which merged
first. Rejected: a search engine or vector store
for news (a new datastore; the volumes are small and the tags are deterministic), storing
items as market events only (the event carries digests, not text, by Decision 28's design),
and a news-fetching service (a new process to operate for a few items a day).
Tests: `tests/unit/test_news_items_migration.py`, `tests/unit/test_news_ingest.py`,
`tests/integration/test_news_postgres.py`.

## Decision 36: A disruption re-optimisation is a deterministic pure engine with seven expand-only tables

Accepted 2026-11-25 (branch `wip/lng3`, programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/05_IMPLEMENTATION_ROADMAP.md),
slice LNG-3). When an LNG cargo is
late or a pipeline supply is curtailed, the desk's options (wait and absorb, borrow in tank and
return, buy extra send-out and storage, divert to a spare slot, swap terminals with another
cargo, cover a pipeline shortfall from a cargo, and the hedge re-alignment and demurrage each
implies) are generated, valued against the plan before the disruption, checked against hard
constraints (firm delivery obligations, storage rights, diversion rights) and placed on a
Pareto frontier by `domain/lng/disruption.py`: plain Python, no solver, no randomness, no
model call. The option space is small and enumerable (positions x capacity strategies,
combinations across disrupted supplies capped at 256), so enumeration with a day-level
simulation is exact for the options it lists, explainable line by line, and needs no new
dependency; a MILP solver would add a dependency and make each answer harder to explain to
a trader for no gain at this size. Migration `0086_lng_disruption` adds `lng_slot_terms`,
`lng_capacity_offers`, `lng_delivery_obligations`, `lng_voyage_terms`, `pipeline_supplies`,
`lng_disruption_runs` (the recommendation's timeline) and `lng_disruption_decisions` (the
option a person chose) to the existing PostgreSQL database: no new service or datastore. The
engine re-runs from the existing market-event outbox (consumer `lng_disruption`) and notifies
through the LNG-2 role routing. Choosing an option records the choice in an audited governed
write (`lng.disruption_choice`); nothing is booked, borrowed, bought, nominated or traded
(AGENTS.md rule 8). No AI is used, so no GOV-1 register entry is needed. Rejected: a MILP
(PuLP/CBC or OR-Tools; a new dependency, opaque to the desk), columns on `regas_slots`
(slot product terms are the desk's own entry, not the ETRM's import, and would be overwritten
by it), a cache of the frontier instead of a run table (the timeline is part of the
requirement) and storing terminal tariff figures as product data (Fluxys, Elengy and DET terms
forbid reuse; offers are the desk's own quotes or entries and are labelled).
Tests: `tests/domain/test_lng_disruption.py`, `tests/unit/test_lng_disruption_migration.py`,
`tests/api/test_lng_disruption_api.py`, `tests/integration/test_lng_disruption_postgres.py`.

## Decision 37: Disruption options carry their consequences; REMIT outages curtail pipeline supply through one link table

Accepted 2026-11-25 (programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/05_IMPLEMENTATION_ROADMAP.md),
slice LNG-4). The owner's instruction of 2026-11-25: optimisation is not a single answer. A
contract may forbid a move, a location may have no storage and no swap, an option may break a
contract or move cargoes running normally, and the trader decides. So the engine of Decision 36
keeps every option a complete course of action and labels its consequences: an option that
cannot physically happen (no storage right, energy with no send-out right, a slot the book does
not hold) is listed as not possible; an option that breaks a contract (short-delivers a firm
obligation, diverts a cargo with no diversion right) stays listed and can be chosen, valued at
the contract's liquidated damages where the data holds them and otherwise stated with its
shortfall and "penalty not held"; an option that moves supplies running to plan names them and
the MWh. A recommended set (the best option that breaks no contract and moves nothing, the
highest expected P&L that breaks no contract, and the best overall, where they differ, each with
a one-line reason) replaces the single fixed-weight default; the weights stay as named, editable
assumptions that only order the list. Demurrage is read from the cargo's Confirmation Notice,
then its voyage terms, then the master agreement, in the contract's currency, and converted to
EUR with an FX fix the user picks from the `fx_observations` the platform holds (ECB reference
rate by default; WMR and BFIX only for entitled principals; or a rate entered by hand, said so).
A REMIT unavailability message held in `remit_umm_messages` that names an asset a pipeline
supply depends on curtails that supply's available volume for the gas days it covers, pro rata
to the share of the asset's capacity that is unavailable; a new version revises it, a dismissed
or inactive one removes it. The link runs in the existing `lng_disruption` outbox consumer when
it receives `outage.published` (Decision 28), before the books that hold a linked supply are
re-optimised, so the re-run always sees the new curtailment. Two further owner instructions of
the same day widen the valuation. Each option is valued at its full cost: its direct P&L and
its opportunity cost, shown apart and both in the P&L. The opportunity cost is the knock-on on
the book's other cargoes (a cargo the option moves takes the berth on the day it can, so a
cargo due there waits, and it draws the terminals' shared per-day limits first, so a later
cargo finds less left), the demurrage and boil-off of another user's ship due at a berth the
option takes (where the line-up is held), the release value or best other use of a spare slot
it uses, and the value of storage gas in the month it was to be used. A spot slot at another
terminal (a `slot` capacity offer) is an option like a held slot, so a long-term contracted
terminal is never assumed to be the better choice. When an option leaves a delivery obligation
short, substitute supply from across the portfolio covers it as further options: gas the book
holds upstream (a supply contract's swing), hub gas bought at the month price plus the
transport to the delivery point (capacity the firm holds first, else the public tariff, through
`application/contract_costs.transport_leg_cost`), or storage gas, each alone and cheapest first.
Every arithmetic line names the price, rate and tariff sources it applied. Every currency
conversion goes through one function, `application/lng_demurrage._fx_rate`, and every
transport cost through one, `application/lng_substitutes._transport_cost`, so a later
source-precedence resolver can replace their bodies without any caller changing. Migration
`0087_lng4_options_demurrage_outages.py` (revision id `0087_lng4_options_demurrage`, which
fits alembic's 32-character version column) is expand-only: nullable columns on `lng_voyage_terms`
(`demurrage_rate_per_day`, `demurrage_currency`, `demurrage_terms`), `lng_delivery_obligations`
(`penalty_terms`), `pipeline_supplies` (`depends_on`, `outage_mode`), `lng_disruption_runs`
(`recommended_set`), `lng_disruption_decisions` (`recommended_set`, `consequences`, `fx`),
`lng_capacity_offers` (`hub`, for a spot slot) and `lng_slot_terms` (`berth_days`), and two new
tables: `pipeline_outage_links` (one row per supply and message, unique on the pair: what
matched, why, the fraction, the curtailed gas days, and `applied`, `unsized`, `withdrawn` or
`ended`) and `lng_berth_calls` (another user's ship due at a terminal's berth: the gas day, the
berth days, the laytime it has left, its demurrage rate and currency, its boil-off, the
source). A day entered by hand on the supply wins over a linked outage, and
`outage_mode = manual` stops links from curtailing at all (the override, audited
`lng.pipeline_outage_override`). It stays advisory: the curtailment is the platform's reading
of the message, shown with its source, and nothing is nominated. Rejected: a separate outage
consumer (it could run after `lng_disruption` and leave a run on the old curtailment), writing
REMIT curtailment into `pipeline_supplies.curtailed` (it would overwrite the desk's own entries
and lose why), a fuzzy name match (a link must be an EIC, an exact normalised name, or a
reviewed GIE alias), and fetching FX rates at read time (no network read; licensing of WMR and
BFIX stays with the customer's own import), and taking the long-term terminal's tariff as its
cost (the slot it uses and the berth it takes have a value elsewhere). Tests:
`tests/domain/test_lng_disruption.py`, `tests/unit/test_lng_substitutes.py`,
`tests/unit/test_lng_disruption_migration.py`, `tests/unit/test_lng_demurrage.py`,
`tests/unit/test_pipeline_outages.py`, `tests/api/test_lng_disruption_api.py`,
`tests/api/test_data1_import_contracts.py`, `tests/integration/test_lng_disruption_postgres.py`,
`tests/integration/test_demo_planted_cases.py`, `clients/web/tests/disruptionOptionsModel.test.ts`.

Addendum of 2026-11-26 (the owner's decisions on berth priority and on another company's
demurrage). A terminal's berth access rule is a hard constraint of the engine
(`domain/lng/disruption.BerthRule`): a ship within its arrival window berths in turn; a late
ship takes the next free gap without displacing an on-time holder, and its laytime starts at
berthing (or at arrival where the rule says so). A swap of berth turn is an option: with a cargo
of the book (`berth_swap`, its knock-on costed) or with another company's call
(`counterparty_swap`, costed at that company's negotiated quote, `pending` until entered and then
ranked as costed); either needs the terminal's approval where the rule says so, listed on the
option as `approvals` (sentences) and `approval_requests` (the same as data, for the client's
own language). Another company's demurrage and boil-off leave the book's opportunity cost; the
delay is stated in `counterparty_effects` with no value. The previous text above ("the demurrage
and boil-off of another user's ship ... where the line-up is held") is superseded by this.
Migration `0091_lng_berth_rules` (on `0090_job_progress_steps`, expand-only) adds the table
`lng_terminal_berth_rules` (terminal, arrival window in gas days, where a late ship's laytime
starts, whether a swap needs approval, basis `terminal_code`, `example` or `assumption`, citation,
the rule as worded, source) and nullable columns on `lng_berth_calls` (`counterparty`,
`quote_amount`, `quote_currency`, `quote_reference`); the call's own demurrage columns stay but
are no longer read. The reads add `berth_rules` (each terminal's rule as applied) and, per
option, `quotes`, `approvals`, `approval_requests` and `counterparty_effects`, all additive.
Not built: a way to record a terminal's rule, a line-up call or a quote (no route and no import
contract writes `lng_terminal_berth_rules` or `lng_berth_calls`; today only the demo seed and the
tests do, so on a customer store every terminal shows the default rule and no counterparty swap
is offered until one is added); a quote in a currency without an FX fix stays pending. Tests:
`tests/domain/test_lng_disruption.py`, `tests/unit/test_lng_berth_rules_migration.py`,
`tests/api/test_lng_disruption_api.py`, `tests/integration/test_lng_disruption_postgres.py`,
`clients/web/tests/disruptionOptionsModel.test.ts`.

## Decision 38: Capacity the firm holds is one table, priced before public tariffs through one source-precedence resolver

Accepted 2026-11-25 (programme
[Commercial Intelligence V3](../engineering/Commercial-Intelligence-V3/05_IMPLEMENTATION_ROADMAP.md),
slice TAR-2; Decision 37 is reserved for another slice). Migration
`0088_tar2_capacity_bookings` (on `0086_lng_disruption`, expand only) adds one table,
`capacity_bookings`: pipeline entry and exit capacity, LNG slots, regasification, send-out
and storage the firm holds, each with how it was acquired (auction, long term, allocation,
secondary, FCFS, bilateral), its period, quantity, unit and basis (per day or a pool of slots), contracted
price and unit, book and source, and the instants it was recorded and released, imported
through the contract `etrm.capacity_bookings.v1` and read as of any instant. It also adds the
nullable `tariff_versions.tariff_year` (the year as the publisher defines it; older versions
keep NULL and readers derive it from the period, so no row is rewritten). The downgrade drops
only these two.

A capacity cost is priced in layers by `domain/tariffs/precedence.split`: what the bookings
cover at the contracted cost, the rest at the public price of how it would be bought (the
day-ahead or within-day reserve price plus premium, or a terminal's first-come-first-served
rate), final where a final version was held at the instant valued, else indicative and
flagged, and anything else not held, never zero. A tariff whose publisher states no status
takes NC TAR Article 29 at that instant, re-derived on every read. The order of the layers,
and of the sources of FX rates, interest rates, tariffs and commodity prices, comes from one
resolver, `domain/pricing/source_precedence.py`, with a default per kind and an order the firm
may set per kind and per calculation context in the existing organisation setting
`source_precedence` (administrators only, validated, audited in the same transaction); every
result lists every tier in order with the one used marked. The firm's banks are named in the
organisation setting `financial_institutions` and their rates arrive by file or by hand
(`bank.fx_rates.v1`, `bank.interest_rates.v1`) into the existing FX and interest-rate tables
as `BANK:<key>` rows, so no further table is needed; a credential is refused, and a live feed
is recorded only as needing the firm's agreement. Nothing is booked, bid or nominated
(AGENTS.md rule 8).

Rejected: columns on the ETRM's capacity contract tables (an import would overwrite them and
they do not say how capacity was acquired or its price unit), a precedence table (the
organisation setting already has governed, audited writes and one row per firm), a table per
bank feed (the rates are FX and interest observations like any other, with a source), storing
the status derived on the day of reading (wrong for an earlier or later instant), and a live
bank connector (needs the firm's own agreement and credentials, which this product does not
hold). Tests: `tests/domain/test_tar2_tariff_year_and_precedence.py`,
`tests/unit/test_tar2_capacity_costs.py`, `tests/api/test_tar2_api.py`.

Amended 2026-11-26 (owner): one live bank connector is built, for Société Générale
(institution key `SOCGEN`, source `src-bank-socgen`, `ingestion/connectors/socgen.py`); other
banks still arrive by file. It writes through `bank.fx_rates.v1` and `bank.interest_rates.v1`
as `BANK:SOCGEN` rows, so no table, migration, tier or route is added and the order (contracted
bank, published reference, ECB) is unchanged. The agreement requirement stands: it fetches only
with `access: api` and `agreement_recorded` true on `SOCGEN`; the credential is still never in
the setting, it is the firm's own, held in the deployment (environment, key file or the
encrypted credential store, provider `SOCGEN`), and the endpoint, auth scheme and field mapping
are a configuration file the firm sets from its agreement with the bank. Without all of them it
makes no network call and reports not connected. The scheduled source is off by default. The
earlier rejection of a live bank connector now applies to every bank but this one. Tests:
`tests/unit/test_socgen_bank_connector.py`.

## Decision 39: TimescaleDB Community Edition is an optional extension, off by default

Accepted 2026-11-26 on the owner's instruction to bring in the TimescaleDB work
(`wip/timescale-on-innovation`) as an optional extension. It amends Decision 24, which rejected
TimescaleDB "for now". PostgreSQL stays the runtime store and no new datastore or service is
added (AGENTS.md rule 5): TimescaleDB is an extension inside the same server. The setting
`EUROGAS_NEXUS_TIMESCALE` is `off` by default; `auto` converts where the server has TimescaleDB
2.13 or later preloaded with the Community Edition licence loaded; `require` stops a migration
that cannot. Migration `0092_timescale_optional` (on `0091_lng_berth_rules`) calls the
idempotent `eurogas_nexus.db.timescale.apply`, also run by `scripts/ops/timescale.py apply`. It
converts `raw_payload_archives`, `market_quotes` and `market_trades` to hypertables with
compression policies, widening each primary key from `(id)` to `(id, time)`; no writer uses
those keys as an `ON CONFLICT` target. The observation tables, the outbox and the audit log stay
plain (their unique keys have no time column). No continuous aggregate (the daily readers are
point-in-time and revision-aware). On SQLite, on PostgreSQL without the extension and with the
setting `off`, the migration changes nothing; the downgrade is a no-op (turning a hypertable
back into a table is a copy, `docs/deployment/TIMESCALEDB.md`). Readiness reports the
extension's state (`extensions.timescaledb`), never failing on it; the restore drill fails when
a converted source restores without its hypertables.

Measured need: none yet. Doc 19 (CAP-1) found the benefit, compression of old raw archives and
of ticks, not needed in its scenarios A and B and matched by partitions and Parquet, and
recommended DEFER; the extension is therefore built so that an operator who reaches scenario C
(licensed ticks kept beyond days) can turn it on, not turned on anywhere. The decision to turn
it on in a deployment is the operator's, against that deployment's measured size.

Licence: compression is under the Timescale License; the review (internal use and value-added
grants, the database-as-a-service prohibition, the no-schema-access condition for a hosted
offering) is in `docs/legal/DEPENDENCY_LICENSE_REVIEW.md`. The product does not bundle or host
it. Rejected: on by default (`auto`) (a managed service listing `timescaledb` would be converted
without anyone choosing it, and the key change is not reversed by a downgrade); converting the
observation tables (their upserts are keyed on the id alone); continuous aggregates (they leak
a later revision into an earlier read). Tests: `tests/unit/test_timescale_optional.py`,
`tests/integration/test_timescale_optional_postgres.py` (plain PostgreSQL),
`tests/integration/test_timescale_present_postgres.py` (TimescaleDB), `tests/unit/test_reliability_ops.py`.

