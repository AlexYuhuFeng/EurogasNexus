# Competitive research: products, workflows, data and architecture

Prepared 2026-11-24 for Eurogas Nexus (decision support only: no execution, settlement or binding
nominations). Scope: market data and analytics vendors, ETRM/CTRM and scheduling systems, LNG
shipping tools, and Kraken. UI/UX design is covered separately.

Method: public vendor pages, documentation, published talks and reputable press only. No sign-up,
no credentials. Every claim about a product cites a source in section 4 as `[Sn]`. Statements marked
*(inferred)* are my reading, not the vendor's words. "Not stated publicly" means the public material
I found does not say; it does not mean the feature is absent. Eurogas Nexus facts come from the
repository (commit `a3d1d5e` on the development branch, read 2026-11-24); paths are relative to the repo
root, and `src/eurogas_nexus/` is shortened to `src/`.

Coverage limits: public detail on Openlink Endur, Allegro LNG, Enuit and Ignite is thin (vendor pages
are marketing level and detailed material is behind brochures or sign-up), so those rows lean on what
ION publishes about its gas scheduling connector. Enuit and Ignite are left out of the matrix for that
reason.

---

## 1. The ten most valuable lessons

Each lesson names what the market does, the Eurogas Nexus gap, and the file or feature it would change.

### 1. Treat a price correction as a typed, dated fact, and let anyone read prices "as known at T"

- **What the market does.** Platts publishes every correction as a dated subscriber note and
  updates its database [S1][S3]; it distinguishes correcting wrong values, backfilling missing ones
  and deleting ones that should not exist [S2], and separately corrects a rationale's wording without
  changing the price [S1]. A recent Platts correction rewrote six weeks of TTF/NBP differential
  history after a back-end calculation error [S3]. Argus delivers corrections in the next scheduled
  data file and keeps them searchable by date [S7]. ICIS versions every entity (`c:version`) and
  separates created, released and committed times [S8]. Montel pushes corrections one day back for
  OHLC and three days back for spot, and marks trades Active or Removed [S30]. IOSCO principle 2.19
  says a changed price must be communicated to the market as soon as possible [S6]. Platts also
  warns that high, low and close series for one symbol can start on different dates and that some
  vendors extrapolate a close from high and low where Platts published none [S4]: a filled value
  must never pass for a published one.
- **Eurogas gap.** Physical observations already keep versions with as-of reads
  (`docs/operations/DATA_REVISIONS.md`, migrations `0062`/`0063`), and the M4/M5 outbox keeps a
  revision chain per event (`src/db/models/market_events.py`: `revision`, `supersedes_event_id`). But
  for price sources the store refuses any change (`*_revision_requires_history`, per
  `DATA_REVISIONS.md`), and the V3 audit records that prices and FX are overwritten in place
  (`docs/engineering/Commercial-Intelligence-V3/01_CURRENT_STATE_AUDIT.md`). So a licensed PRA
  correction delivered through the customer's feed would either be refused or lose the earlier value,
  and no screen can say "this TTF close was corrected on 4 Sep".
- **Change.** Extend the `observation_revisions` pattern to `market_quotes`, settlements, FX
  (`fx_observations`) and `firm_marks`, with a `change_kind` of `correction | backfill | deletion |
  rationale_only`. Add `as_of` to the price read routes (`src/api/routes/public/market.py`) and the SDK
  (`packages/python-sdk/src/eurogas_nexus_sdk/market.py`). Show a "corrected" marker with the before
  value in the hover provenance. The outbox already re-runs only what uses the figure.

### 2. Give clients a change feed with a cursor, not only full reads

- **What the market does.** Kpler's `trades/updates` returns diffs since a timestamp with an
  `INSERT`/`UPDATE` operation and the changed columns, plus a `lastAvailableDate` header; diffs are
  kept 15 days [S13]. Kpler also serves a trades snapshot as of a given date [S14]. ICIS polling uses
  `committed-since` against its transaction log, returns the next commit time to store, and can
  include deleted items [S8]. Montel pushes over SignalR and tells clients to insert, update or
  remove by trade id and status [S30].
- **Eurogas gap.** The outbox (`src/application/market_events.py`) is internal; I found no public read
  route over it (only `/api/strategy-runs/{run_id}/events`). The SDK reads current state, so an ETRM
  or BI client that wants "what changed since my last sync" must re-read everything.
- **Change.** A read-only `GET /api/changes?since=<cursor>` over `market_events` returning digests
  (key, kind, revision, operation, times), entitlement-filtered with the existing helpers in
  `src/api/dependencies/row_entitlement.py`; never values for desk-private data (decision log: firm
  marks publish digests only). Add `fetch_changes(since)` to the SDK. Keep full history rather than
  Kpler's 15-day window (see section 3).

### 3. Label every estimate as an estimate, with its basis and confidence

- **What the market does.** Kpler offers trades "With Forecast" as a separate option [S12], gives
  each modelled future port call a confidence score and measures accuracy, completeness and stability
  [S16], and uses an explicit status lifecycle (Scheduled, Loading, InTransit, Delivered) [S14]. Its
  public note on misreported LNG activity shows the failure mode: a model probability about a
  company's cargoes was read by a third party as fact, and Kpler stresses its data is subject to
  change [S17]. ICIS LNG Edge combined dual AIS feeds with an analyst team that verifies published
  data [S55].
- **Eurogas gap.** The cargo plan takes the ETA "that the import says" and does not use vessel position
  (`docs/engineering/Commercial-Intelligence-V3/12_LNG_CARGO_IN_TRANSIT.md`, Limits). An import lists
  an ETA that overrides another source (QA-L-04), but the plan carries no basis or confidence, so a
  model ETA from a vessel feed and a confirmed berth time from the terminal look the same.
- **Change.** In `src/application/lng_positions_import.py` and the plan (`src/application/lng_in_transit.py`),
  store `eta_basis` (`contract_window | etrm | terminal_confirmed | vessel_feed_reported |
  vendor_forecast`) and an optional `confidence` from the feed, plus a status lifecycle aligned with
  the vendor's. The cargo board shows the basis in the hover and treats a forecast destination as an
  estimate. This is the same rule as AGENTS.md rule 17 ("no simulated price that can be read as a
  market price") applied to schedules.

### 4. Publish how each figure was made, and govern changes to the method

- **What the market does.** IOSCO asks PRAs to publish with each assessment how it was developed:
  data types used, transaction-based or interpolated, judgement applied and data excluded (2.3), to
  give advance notice and consultation for material methodology changes (1.5), and to review
  methodologies routinely (1.6) [S6]. Platts reviews methodologies at least annually, approves changes
  in a workflow tool that keeps an audit trail, and does not publish an assessment until a senior
  person approves it [S5].
- **Eurogas gap.** The parts exist but are not joined up: the forward curve records how each point
  was obtained (`src/domain/market/forward_curve.py`), `src/application/calculation_manifest.py`
  fingerprints the numerical code, and assumption sets have four-eyes. But a tick batch that fails a
  plausibility band is returned whole (decision log) and I found no record a data steward can read of
  what was excluded and why *(inferred from the decision log and code read; not tested)*; and when the
  numerical bundle fingerprint changes, nothing tells a desk that P&L or curve outputs moved because
  of a method change. LNG terms and freight routes still change with no second approval (P-17).
- **Change.** (a) Expose the curve point provenance and excluded quotes in the curve and prices APIs
  as a short rationale. (b) When `numerical_bundle_fingerprint()` changes on deploy, publish a
  `method.changed` event and a release note entry naming affected calculations, so outcome attribution
  (M9) can separate method from market. (c) Finish the shared maker-checker flow (P-17) for terminal
  terms, freight routes and limit increases.

### 5. Make the audit trail part of the write, and review access on a schedule

- **What the market does.** IOSCO asks for information to be documented when generated, including
  who did what, and kept for at least five years (2.9, 2.10) [S6]. Platts reviews access to key
  applications quarterly and logs methodology approvals for audit [S5]. ION advertises built-in
  validation, approvals and audit trails for its gas scheduling connector [S37].
- **Eurogas gap.** Retention is right (default 1,827 days in `src/application/audit_retention.py`),
  but `src/application/audit_service.py` is explicitly best-effort: "Failures to record are never
  raised." For limits, mandates, hedge records, credit links and assumption approvals that means a
  governed change can succeed with no audit row.
- **Change.** For the governed writes (risk controls, `PUT /api/lng/cargoes/{id}/hedges`, assumption
  approvals, user and key administration), write the audit row in the same transaction, as the outbox
  already does for events, and refuse the write if it cannot be recorded. Keep best-effort only for
  reads. Add a quarterly "who can do what" access report to Admin > Users, built from roles, keys
  and portfolio scopes.

### 6. Turn entitlements into something an administrator can report on

- **What the market does.** Bloomberg's EMRS manages entitlements per user, group, application and
  publishing service, authorises server applications as well as people, and reports usage to
  exchanges and for cost allocation [S26]. Montel allows one valid session per user and client id
  [S30]; Kpler caps records per query and queries per minute [S11]. Licensed data reaches users only
  through these controls.
- **Eurogas gap.** Enforcement is solid and fail-closed (`src/governance/entitlement.py`,
  `src/api/dependencies/row_entitlement.py`, `market_data_licences`, the source-label family grant
  from F1), and the data product catalogue reports a restricted product as restricted rather than empty
  (`src/application/data_products.py`). What is missing is the reporting side: who read or exported
  which licensed family, and whether an export of licensed data was allowed. `ExportDecision` exists
  in `entitlement.py` but I did not find it applied to the XLSX/CSV report exports
  (`src/core/report_files.py`, `src/api/csv_export.py`) *(inferred from a code search)*.
- **Change.** Log entitled reads and exports per source family (counts, not values) and add a
  monthly usage report per licence; apply `ExportDecision` to every report export so a licensed
  series is labelled or withheld in files. This also supports AGENTS.md rule 18 (licensed data only
  through the customer's entitlement).

### 7. Excel is a delivery channel, not an export button

- **What the market does.** Nearly every vendor ships an Excel add-in beside its API: Kpler (16 LNG
  tables) [S11][S12], Vortexa [S19][S20], ICIS [S9], Platts [S32], Trayport lists Excel integration [S24], and Molecule pulls live
  data into Excel and Power BI over its API [S42][S43]. ICIS and Wood Mackenzie also deliver into
  Snowflake [S9][S23].
- **Eurogas gap.** Excel output is a static workbook rendered on request (`src/core/report_files.py`);
  the Python SDK is the only refreshable channel, and SDK docs were the subject of P-22. Analysts and
  risk staff at gas desks live in Excel *(inferred, consistent with the persona review)*.
- **Change, cheapest first.** (a) Stable, key-authenticated CSV/JSON endpoints for prices, curve,
  ladder and cargo plans that Excel's Power Query can refresh (personal API keys already exist since
  F1-9); document them in the four-kind docs. (b) Later, an Office add-in with custom functions
  *(inferred technology choice; a new client and dependency, needs an ADR under AGENTS.md rule 5)*.
  Commit the OpenAPI document first (gap matrix row 8), because every channel builds on it.

### 8. For nominations, the value is in reconciling and explaining mismatches

- **What the market does.** Brady Igloo for GB gas generates day-ahead and within-day nominations,
  reads each nomination's status back from Gemini, lists nominations that need investigation with
  likely causes and suggested actions, and lets the user drill from a nomination to the trades behind
  it, for example a trade done after nominating or a counterparty that has not nominated [S34]. The
  PwC study of 13 European scheduling vendors found automatic IN/OUT EDI matching in all of them
  [S36]. ION's Allegro connector keeps scheduled quantities in sync with pipelines with validation and
  audit [S37].
- **Eurogas gap.** My gas day records nomination step statuses append-only, imported or entered by
  hand (`alembic/versions/0076_gas_day_nominations.py`, `src/application/gas_day.py`,
  `src/application/gas_day_checklist.py`), computes net to clear and the cost of doing nothing, and caps
  supply by REMIT outages (QA-T-09). It does not compare what was nominated with what was traded or
  confirmed, so it cannot say why a line is out.
- **Change.** A read-only "why is this out" step in the checklist: trades booked after the
  nomination time, counterparty-side not confirmed (from an imported confirmation or matching file),
  quantity differences by counterparty, each with the trades behind it. Import scheduling-system
  confirmation files read-only. Sending nominations stays out of scope (AGENTS.md rule 8).

### 9. Let people choose what to be alerted about, and reach them where they work

- **What the market does.** Montel lets users configure alerts on prices, spreads and thresholds,
  delivered in the browser or by email [S31]. Brady PowerDesk raises event-triggered alerts on market
  events [S35]. Kraken's asset platform offers customisable alerts on asset health and available power
  [S52]. Platts Dimensions Pro notifies on news, heards and subscriber notes [S32].
- **Eurogas gap.** `src/application/notifications.py` sends email only (`KINDS = ("email",)`) to
  channels an administrator configures by category and severity. The new opportunity engine raises no
  alert (M7). Monitoring alerts have acknowledgement (M6), but a trader cannot subscribe to "TTF
  Q1-27 below X", "cargo X's ETA moved" or "a correction to a mark I use".
- **Change.** Per-user subscriptions keyed by the outbox event keys (`cargo:<id>`, hub/period,
  `fx:`), evaluated by an outbox consumer; an additional channel kind (a webhook for Teams or Slack is
  the usual first step *(inferred)*); escalation when a critical item is not acknowledged. Route the
  new engine's opportunities through the same path (M7). Keep the one-alert-per-condition rule from
  M6 to avoid noise.

### 10. Borrow Kraken's engineering governance, not its product

- **What Kraken does.** Kraken runs a very large Python monolith (about 28k modules, about 400
  developers in 2023) and enforces layering and independence between client and territory packages
  with Import Linter contracts that block merges; known violations were ignored at adoption and the
  ignored count is a burndown metric [S47]. It ships over 100 versions a day to 25+ client
  environments, every change backwards and forwards compatible, database changes deployed before the
  code that uses them, environments pinnable to a version, flags held in a reviewed config repo or in
  database settings, and old and new implementations run side by side in production to compare
  results before switching [S48]. Migrations run before the rollout, and configuration moved from a
  store without audit logs to Git-versioned config [S49]. Kraken publishes its coding conventions
  [S50].
- **Eurogas gap.** The audit lists two opportunity engines, four LNG economics implementations (P-09),
  three min-cost-flow kernels, five P&L engines and five freshness implementations
  (`01_CURRENT_STATE_AUDIT.md`, `13_PERSONA_AND_PRACTICE_REVIEW.md`). A module ownership matrix exists
  (`docs/architecture/MODULE_OWNERSHIP_MATRIX.md`) but I found no automated import contract.
- **Change.** (a) Add import contracts for `domain` → `application` → `api` layering and for the
  one-kernel rules (LNG economics, flow kernel, freshness), with today's violations listed as ignored
  and counted down. (b) Retire the legacy engine (M7) by a parallel run: compute both, serve the
  legacy result, log differences per opportunity until they are explained, then switch. (c) Keep
  calculation-affecting flags in the reviewed config, never in an instantly changeable table, so the
  audit trail shows when a desk's numbers could have changed *(inferred adaptation)*.

---

## 2. Gap matrix

Legend: cells summarise public material with its source. "Not stated publicly" = not found in what I
read. The Eurogas column is from the repository.

### 2a. Market data and analytics vendors

| Capability | Kpler | Vortexa | S&P Global / Platts | Argus | ICIS | Bloomberg | LSEG Workspace | Montel | Spark | Trayport |
|---|---|---|---|---|---|---|---|---|---|---|
| Corrections / revision history of assessed prices | Data "subject to change" as information improves [S17]; diffs feed (15 days) [S13] | Not stated publicly | Dated correction notes; correction, backfill, deletion distinguished; DB updated [S1][S2][S3] | Corrections in next scheduled file, searchable by date; >6 months may be excluded [S7] | Entity `c:version`; deleted items returnable [S8] | Not stated publicly | Not stated publicly (chapter read covers customs "correctives") [S28] | Corrections pushed 1 day (OHLC) / 3 days (spot) back; trade status Active/Removed [S30] | Not stated publicly | Not stated publicly |
| Point-in-time / as-of reads | Trades snapshot at a date [S14] | Not stated publicly | Archived forecast vintages in SDK; corrected/removed records selectable for point-in-time in one dataset [S33] | Not stated publicly | `created-on`, `released-on`, commit log [S8] | Not stated publicly for gas | `get_history` [S28] | `AsOfDate` on fundamentals and forecasts [S30] | Not stated publicly | Not stated publicly |
| Incremental change feed | `trades/updates` with INSERT/UPDATE [S13] | Not stated publicly | Not stated publicly | Scheduled files [S7] | `committed-since` cursor [S8] | B-PIPE real-time feed [S26] | Streaming access channel [S29] | SignalR subscriptions [S30] | Not stated publicly | Real-time market data [S24] |
| Methodology and per-assessment rationale | Model confidence and accuracy tracking for destinations [S16] | "Hard data, human intelligence and AI" [S19] | Rationales with judgement and exclusions; annual review; approvals audited [S5] | Published methodology documents (index page) [S7] | Published methodologies (compliance pages; not read in detail) | n/a | n/a | n/a | Assessment is the settlement reference for ICE freight futures [S21] | n/a (venue, not assessor) |
| Entitlements and usage reporting | Rate and record limits [S11] | API key [S18] | Credentials per user [S33] | Not stated publicly | Basic auth, daily quota [S8] | EMRS per user/group/app, usage reporting, cost allocation [S26] | Desktop session [S29] | One session per user and client id [S30] | Not stated publicly | Not stated publicly |
| Excel add-in | Yes [S11][S12] | Yes [S19][S20] | Yes [S32] | Not stated publicly | Yes [S9] | Not confirmed (vendor page could not be fetched) | Excel fields listed [S28] | Not mentioned on Markets page [S31] | Not stated publicly | Excel integration listed [S24] |
| Python SDK / API | REST + `kpler.sdk` [S11] | REST + `vortexasdk` [S18] | `spgci` client, pandas [S33] | Not stated publicly | REST/XML, Atom search [S8] | API listed [S26] | Data Library for Python [S29] | Web API [S30] | Not stated publicly | API integration listed [S24] |
| Bulk / cloud delivery | Power BI, Tableau via REST [S11] | HTTP integration [S20] | Channel partners [S32] | Data files [S7] | Snowflake marketplace [S9] | Cloud delivery [S26] | Cloud channel [S29] | Not stated publicly | Not stated publicly | Cloud services listed [S24] |
| Alerting | Not stated publicly | Not mentioned [S19] | Notifications on news, heards, subscriber notes [S32] | Not stated publicly | Course and ETA change updates (2015) [S55] | Not stated publicly | Not stated publicly | Price, spread, threshold alerts by browser/email [S31] | Not stated publicly | Not stated publicly |
| LNG voyage tracking | 16 LNG tables incl. trades, diversions, congestion, outages [S12]; >13,000 AIS receivers [S15] | >710 carriers, >250 terminals, diversions, floating storage [S19] | LNG Global Analytics: cargo trips, diversions, netbacks [S33] | Not stated publicly | LNG Edge fleet view, predicted path, ETAs (2015) [S55] | Not stated publicly for LNG [S27] | Shipping chains; vessel tracking not described [S28] | n/a | Freight rates; GAC port-cost data [S21][S22] | n/a |
| Estimated vs confirmed | Forecast option; confidence score; status enum [S12][S14][S16] | Not stated publicly | Not stated publicly | Not stated publicly | Analyst verification (2015) [S55] | n/a | n/a | Forecasts carry `AsOfDate` [S30] | n/a | n/a |
| Data lineage / provenance | Bills of lading from US CBP named as source [S12] | Not stated publicly | Rationale names data used [S5] | Not stated publicly | Series linked to unit, currency, location, vessel [S8] | Not stated publicly | RIC and chain structure [S28] | Source per series (exchanges, brokers) [S31] | Not stated publicly | Venue-level data [S24] |
| Audit / retention | Not stated publicly | Not stated publicly | ≥5 years assessment records; quarterly access review [S5] | Not stated publicly | Not stated publicly | Not stated publicly | Not stated publicly | Not stated publicly | Not stated publicly | Not stated publicly |

### 2b. ETRM/CTRM, scheduling, LNG shipping and Kraken

| Capability | Brady (Igloo, PowerDesk) | ION Allegro | ION Openlink Endur | ION Aspect | Molecule | Eka | Veson IMOS / Lacima (LNG shipping) | Kraken |
|---|---|---|---|---|---|---|---|---|
| Nominations workflow | Igloo generates DA/WD nominations, sends to Gemini (auto or button), status back, mismatch summary with likely causes, drill to trades [S34] | NatGasHub Connect: >300 North American pipelines, automated nominations, validation, approvals, audit trails [S37] | Not stated publicly at product level [S41] | Not stated publicly [S39] | Not stated publicly | Not stated publicly | n/a | n/a (power and flexibility, not gas nominations) |
| LNG cargo management | n/a | LNG named among scope; detail not public [S38][S40] | "Power, gas and LNG" scope; detail not public [S41] | LNG not mentioned [S39] | Not stated publicly | Not stated publicly | IMOS: LNG fuel and cargo linked, boil-off, heel back-calculation, voyage P&L [S45]; Lacima: lifts/deliveries/vessels optimised, ranked near-optimal schedules [S46] | n/a |
| Market data and curves | n/a | Connect module for price providers and exchanges [S38] | n/a | Integrated real-time prices, reference data [S39] | EOD prices auto-loaded; custom curves via API; snapshots (valuation archives) [S42][S43] | Live market data feeds via APIs [S44] | Forward curves as optimiser input [S46] | n/a |
| Revision history / snapshots | Not stated publicly | Not stated publicly | Not stated publicly | Not stated publicly | Valuation snapshots via API [S42] | Not stated publicly | Not stated publicly | Old and new implementations run in parallel and compared [S48] |
| Entitlements | Not stated publicly | Not stated publicly | Not stated publicly | Multi-tenant SaaS [S39] | SSO (SAML/AD), 2FA, domain limits [S43] | Not stated publicly | Separate licence per module [S45] | Token auth, refresh tokens, rate-limit error code [S51] |
| Excel / API / SDK | PowerDesk interfaces to ETRM and market operators [S35] | Extensible framework; external system connectors [S38] | Not stated publicly | Scripting language; ERP integration [S39] | REST (JSON/CSV) read and write; Excel, Power BI, SQL, Python [S42][S43] | APIs to SAP, Oracle, Refinitiv and others [S44] | Voyage report capture [S45] | GraphQL API, cursor pagination, documented possible errors, deprecation in schema [S51] |
| Alert routing | PowerDesk event-triggered alerts [S35] | "Messaging" and approvals contrasted with spreadsheets [S38] | Not stated publicly | Not stated publicly | Automated limit testing; delivery not stated [S43] | Mobile access to position and P&L [S44] | n/a | Customisable asset alerts [S52]; incident tooling in Slack [S48] |
| Audit | Not stated publicly | Audit trails (connector) [S37] | Not stated publicly | Not stated publicly | SOC 2 Type 2 cited [S42] | Not stated publicly | n/a | Config moved to Git for audit [S49] |
| Release and change governance | n/a | Test automation of end-to-end scenarios [S38] | Not stated publicly | Automatic upgrades (SaaS) [S39] | Not stated publicly | 12–16 week implementation claimed [S44] | n/a | >100 versions/day to >25 environments; compatible migrations; pinning; flags; import contracts [S47][S48][S49] |
| Automation boundary | PowerDesk rules-based and algo trading [S35] | n/a | n/a | n/a | n/a | n/a | Optimiser proposes schedules [S46] | Executes dispatch between a client's trading algorithm and assets; client keeps trading and risk [S53] |

### 2c. Eurogas Nexus today, against the same rows

| Capability | Eurogas Nexus today (repo evidence) | Verdict |
|---|---|---|
| Corrections / revision history of assessed prices | Physical observations versioned with as-of reads (`observation_revisions`, `DATA_REVISIONS.md`); market events carry `revision` and `supersedes_event_id` (`src/db/models/market_events.py`); price sources refuse changes (`*_revision_requires_history`); price and FX tables overwritten in place at baseline (V3 audit) | Gap for prices (lesson 1) |
| Point-in-time / as-of reads | Physical: `versions_as_of`, `resolve_capacity_as_of`; prices: none found | Gap for prices |
| Incremental change feed | Outbox with replay, internal; no public cursor route found | Gap (lesson 2) |
| Methodology and rationale | Curve points record their derivation (`forward_curve.py`); calculation manifest fingerprint; assumption set versions with four-eyes; tariff register hashes documents | Partial (lesson 4) |
| Entitlements and usage | Fail-closed entitlement, row filters, licence table, source label bound to key family, data products report "restricted"; no usage reporting; `ExportDecision` not seen on exports | Strong enforcement, weak reporting (lesson 6) |
| Excel | Static XLSX/PDF/CSV report renditions (`src/core/report_files.py`) | Gap (lesson 7) |
| Python SDK / API | `packages/python-sdk` (market, lng_cargo_plan, portfolio, ...), CLI, signed handoff packages; OpenAPI not committed (V3 audit); `NexusAPIError` with code and correlation id | Good; commit OpenAPI |
| Bulk / cloud delivery | Not present (single-tenant Docker; hosted pilot blocked on access) | Later |
| Alert routing | Email outbox by admin channel, category and severity; monitoring alerts raised once, cleared on recovery; critical limit alerts need acknowledgement | Partial (lesson 9) |
| LNG voyage tracking | Cargo plan: ETA from import, slot, boil-off, gas in kind, send-out by gas day, hub months, hedge cover, roll suggestions, what-if, cargo board (`12_LNG_CARGO_IN_TRANSIT.md`); no own AIS; position not used for ETA | Strong commercial chain; weak voyage evidence (lesson 3) |
| Estimated vs confirmed | Assumptions labelled (boil-off desk standard, cash-out rates, slot spread); ETA basis not labelled | Partial (lesson 3) |
| Nominations workflow | Append-only nomination step statuses, cut-offs, net to clear, cost of doing nothing, SCHEDULER role; nothing sent (by design) | Partial: no mismatch reconciliation (lesson 8) |
| Data lineage / provenance | Hover provenance (source, unit, as-of) on cargo board; `0011_reference_source_lineage`; valuation snapshot inputs; freshness contract | Good |
| Audit / retention | `audit_events`, 5-year default retention, keyset paging; recording is best-effort | Gap for governed writes (lesson 5) |
| Release and change governance | Pre-push gate, CI on `main`, ADRs, Alembic expand-only migrations; module ownership matrix; duplicated kernels | Partial (lesson 10) |
| Automation boundary | Decision support only: proposals and handoff packages (ADR Decision 11, AGENTS.md rule 8) | Deliberate |

---

## 3. Deliberately not worth copying

| What | Who does it | Why not for Eurogas Nexus |
|---|---|---|
| Order entry, auto-trading, sending nominations, dispatching assets | Trayport Joule order screens [S25]; PowerDesk algo trading [S35]; Igloo auto-send to Gemini [S34]; Kraken dispatch layer [S53] | Out of scope by ADR Decision 11 and AGENTS.md rule 8. Copy the reconciliation and explanation around these steps, not the steps. |
| Running a sensor or AIS network | Kpler (>13,000 receivers) [S15]; Wood Mackenzie (8,300 sensors) [S23] | A capital-heavy data business. Consume vessel and flow data through the customer's licence (rule 18) and spend effort on what the desk does with it. |
| Publishing benchmark assessments | Platts, Argus, ICIS [S5][S6][S10] | Becoming a PRA brings IOSCO obligations (complaints, independent review, consultation) [S6]. Borrow the rationale and correction discipline for internal marks; do not publish prices. |
| A proprietary query language or instrument-code system | LSEG RICs and chains, whose recursive expansion took 640–1,570 s in LSEG's own examples [S28] | Plain REST, the SDK and Power Query-friendly endpoints serve a desk-sized product better; the ontology already gives stable identities. |
| One session per user, revoked by the next login | Montel [S30] | Hostile to people who use the web client and the Tauri desktop app at once. Short-lived personal API keys (F1-9) are the better model. |
| HTTP 200 for every response with errors in the body | Kraken GraphQL [S51] | Breaks the existing `NexusAPIError` contract and standard HTTP tooling. Kraken's documented `possibleErrors` per field is worth copying, though. |
| A short retention window on change history | Kpler keeps diffs 15 days [S13] | Fine for a sync feed, wrong for audit; Eurogas keeps the full event log and should continue to. Copy the feed's shape, not its retention. |
| Instantly changeable database flags for calculation behaviour | Kraken (DB-backed settings) [S48] | Kraken's context is retail operations; a trading desk needs to show when its numbers could have changed. Keep calculation flags in reviewed config (lesson 10). |
| Microservices, Kubernetes fleets, message brokers | Kraken runs Celery, RabbitMQ, Kubernetes and ArgoCD across 25+ environments [S48][S49] | AGENTS.md rule 5 and ADR Decision 28 (outbox over a broker). Kraken itself is a monolith [S47]; copy its boundary enforcement and compatibility rules, not its infrastructure scale. |
| Full ETRM scope: settlement, invoicing, voyage P&L, chartering operations | Allegro, Endur, Molecule [S38][S42]; Veson IMOS [S45] | The ETRM stays the system of record (persona review practice 14). Integrate with these systems (snapshot imports, P-16) rather than rebuild them. |
| Ranked optimiser outputs presented as a schedule to execute | Lacima ranks near-optimal schedules [S46] | Useful idea for later (showing near-optimal alternatives with their value gap), but the optimisers are experimental (gap matrix row 6) and outputs must stay proposals. |
| Model probabilities shown without a label | The third-party misreading in Kpler's note [S17] | The failure Eurogas must avoid: every estimate carries its basis (lesson 3). |

---

## 4. Sources

Platts / S&P Global
- [S1] Platts corrects Nov 17 LNG NWE DES assessment rationale: https://www.spglobal.com/energy/en/pricing-benchmarks/our-methodology/subscriber-notes/111822-platts-corrects-nov-17-lng-nwe-des-assessment-rationale
- [S2] Platts cleans erroneous data through correction, backfilling or deletion: https://www.spglobal.com/energy/en/pricing-benchmarks/our-methodology/price-symbols/040618-platts-cleans-erroneous-data-through-correction-backfilling-or-deletion
- [S3] Platts corrects European natural gas differential assessments (Sep 2026): https://www.spglobal.com/energy/en/pricing-benchmarks/our-methodology/subscriber-notes/090426-platts-corrects-european-natural-gas-differential-assessments-following-back-end-calculation-error
- [S4] Variation in Platts high/low/close historical data series: https://www.spglobal.com/energy/en/pricing-benchmarks/our-methodology/subscriber-notes/031020-variation-in-platts-high-low-close-historical-data-series
- [S5] Control procedures for Platts commodities benchmarks (assurance report): https://www.spglobal.com/commodityinsights/process/control-procedures-for-platts-commodities-benchmarks
- [S32] S&P Global Platts launches Platts Dimensions Pro: https://press.spglobal.com/2021-08-09-S-P-Global-Platts-Launches-Platts-Dimensions-Pro
- [S33] spgci Python client: https://github.com/spgi-ci/spgci-python

Regulation
- [S6] IOSCO Principles for Oil Price Reporting Agencies: https://www.iosco.org/library/pubdocs/pdf/IOSCOPD391.pdf

Argus, ICIS
- [S7] Argus data corrections: https://www.argusmedia.com/en/methodology/data-help-and-support/data-corrections
- [S8] ICIS API quick start guide: https://www.icis.com/explore/services/dataexpress/icis-api/api-quick-start-guide
- [S9] ICIS Data as a Service: https://www.icis.com/explore/daas/
- [S10] ICE NBP/TTF Gas Daily Futures (ICIS TIC) FAQ: https://www.ice.com/publicdocs/ICE_NBP_TTF_Gas_Daily_Futures_ICIS_TIC_FAQ.pdf
- [S55] ICIS launches LNG Edge (2015): https://prnewswire.com/news-releases/icis-officially-launches-lng-edge---the-next-generation-in-real-time-online-intelligence-platforms-503254951.html

Kpler, Vortexa, Spark, Wood Mackenzie
- [S11] Kpler API and SDK introduction: https://help.kpler.com/en/articles/6022217-kpler-api-and-sdk-introduction
- [S12] Kpler LNG (Excel add-in tables): https://help.kpler.com/en/articles/7984551-lng
- [S13] Kpler SDK Trades Updates: https://python-sdk.dev.kpler.com/resources/trades_updates.html
- [S14] Kpler SDK Trades Snapshot: https://python-sdk.dev.kpler.com/resources/trades_snapshot.html
- [S15] Kpler maritime data quality: https://www.kpler.com/product/maritime/data-quality
- [S16] Kpler, building LNG destination forecasting models: https://www.kpler.com/fr/blog/building-best-in-class-lng-destination-forecasting-models
- [S17] Kpler response to misreported LNG market activity: https://www.kpler.com/blog/kpler-response-to-misreported-lng-market-activity
- [S18] Vortexa SDK (PyPI): https://pypi.org/project/vortexasdk
- [S19] Vortexa LNG product: https://vortexa.com/product-lng
- [S20] Vortexa Excel integration: https://www.vortexa.com/product/integrations/excel-energy-market-data-integration
- [S21] ICE Spark30S LNG freight future specification: https://www.ice.com/api/productguide/spec/79234891/pdf
- [S22] GAC on board with Spark's LNG freight platform: https://ajot.com/news/gac-onboard-with-sparks-lng-freight-platform
- [S23] Wood Mackenzie Trading Analytics: https://www.woodmac.com/industry/commodity-trading-analytics/

Bloomberg, LSEG, Montel, Trayport
- [S24] CME Group, TMX Trayport vendor page: https://www.cmegroup.com/solutions/market-tech-and-data-services/technology-vendor-services/trayport-limited.html
- [S25] Trayport ships Joule trading screen (Finextra): https://www.finextra.com/pressarticle/42120/trayport-ships-joule-trading-screen
- [S26] Bloomberg enterprise data (B-PIPE, EMRS): https://www.bloomberg.com/professional/?p=5264
- [S27] Gas and LNG markets with Bloomberg (webinar page): https://professional.content.cirrus.bloomberg.com/professional2023/insights/webinar/gas-lng-markets-with-bloomberg
- [S28] LSEG data guide, chapter 9, commodities and energy: https://developers.lseg.com/content/dam/devportal/en_us/product-docs/lseg-data-guide/chapter09
- [S29] LSEG Data Library for Python: https://developers.lseg.com/en/api-catalog/lseg-data-platform/lseg-data-library-for-python
- [S30] Montel Web API user guide: https://support.montel.energy/hubfs/Montel_webapi_userguide.pdf
- [S31] Montel Markets (formerly Montel Online): https://montel.energy/platforms/montel-online

ETRM, scheduling, LNG shipping
- [S34] Brady Igloo, UK gas nominations: https://www.bradytechnologies.com/igloo-etrm/uk-gas-nominations
- [S35] Brady PowerDesk: https://www.bradytechnologies.com/powerdesk-trading/
- [S36] PwC, power scheduling and gas nomination solutions: https://www.pwc.de/en/energy-sector/power-scheduling-and-gas-nomination-solutions-for-european-power.html
- [S37] ION, Allegro and NatGasHub Connect: https://iongroup.com/resource-center/commodities/allegro-natgashub-connect-gas-scheduling-software-for-pipeline-scale-operations/
- [S38] ION Allegro: https://iongroup.com/commodities/allegro/
- [S39] ION Aspect: https://iongroup.com/products/commodities/aspect/
- [S40] ION solutions for natural gas and LNG: https://iongroup.com/resource-center/commodities/ion-for-natural-gas-lng/
- [S41] Openlink for renewable power, gas and LNG: https://iongroup.com/resource-center/commodities/openlink-for-renewable-power-gas-and-lng/
- [S42] Molecule, APIs make your ETRM/CTRM powerful: https://molecule.io/blog/apis-make-your-etrm-ctrm-powerful/
- [S43] Molecule features: https://molecule.io/platform/features.html
- [S44] Risk.net, technology house of the year: Eka: https://www.risk.net/commodities/6732766/technology-house-of-the-year-eka-software-solutions
- [S45] Veson IMOS VIP LNG: https://help.veson.com/imos/vip-lng
- [S46] Lacima LNG shipping optimiser: https://www.lacimagroup.com/lng-shipping-optimiser

Kraken
- [S47] Kraken Technologies: how we organise our very large Python monolith (EuroPython): https://blog.europython.eu/kraken-technologies-how-we-organize-our-very-large-pythonmonolith/
- [S48] Kraken, how we ship (Feb 2025): https://engineering.kraken.tech/news/2025/02/07/how-we-ship.html
- [S49] Kraken, Django, Kubernetes health checks and continuous delivery (Feb 2026): https://engineering.kraken.tech/news/2026/02/11/django-kubernetes-health-checks-continuous-delivery.html
- [S50] Kraken conventions repo: https://engineering.kraken.tech/news/2019/02/28/conventions-repo.html
- [S51] Kraken GraphQL API basics: https://developer.octopus.energy/graphql/guides/basics
- [S52] Kraken generation flexibility / asset optimisation: https://www.kraken.tech/asset-optimization
- [S53] ESS News, Vattenfall brings in Kraken for its German fleet (Nov 2026): https://www.ess-news.com/2026/11/10/vattenfall-brings-in-kraken-to-manage-entire-german-battery-and-renewables-fleet-as-one/
