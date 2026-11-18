# Architecture V2 execution state

Read this before planning (AGENTS.md rule 2). Newest entry first. When this file passes about
500 lines, move the older entries to `history/` and link them below, so the current state
stays quick to read.

Earlier entries: [history/ARCHITECTURE_V2_EXECUTION_LOG_TO_2026-10-30.md](history/ARCHITECTURE_V2_EXECUTION_LOG_TO_2026-10-30.md).

## 2026-11-18 — market reports round 5 (part 2): progress, conversion, question joins (branch `reports-round5b`, not pushed)

- Generation progress uses the shared `WorkProgress` (motion stops under reduced motion).
- Optional reporting currency and energy unit: the closes table keeps the native price and adds
  a converted one through `market_normalisation` (spot ECB, rate and factor in Methodology).
- `reports/joins.py`: storage by country against NW Europe (`desk_today._storage` now returns
  `by_country`), LNG by country, the spread between two hubs (conversion stated), what changed
  since a date; border flows are named as not held. Each join fact declares its `relation`.
- The text-and-side-panel row may break across pages; a text-and-figure row still moves whole.
- No new path or operation.
## 2026-11-18 — CP-11 regulated LNG terminal tariff register (branch `cp-11-terminal-tariffs`, not pushed)

- Terms check first (docs/legal/DATA_SOURCE_TERMS.md): the Fluxys LNG and Elengy legal notices
  forbid reuse without prior written consent; DET states no reuse terms. Every operator starts
  "needs the firm's terms"; the refresh (`scripts/ops/refresh_lng_terminal_tariffs.py`) reads
  no document until an administrator records the operator's permission with a reference. No
  operator document is captured or committed; tests use synthetic figures.
- Migration `0069_lng_terminal_tariff` (versioned `lng_terminal_tariff`,
  `lng_terminal_operator_terms`); `domain/route_cost/terminal_tariff_register.py` (firm terms →
  reviewed → candidate indicative → missing with reason); `application/lng_terminal_tariff_register.py`
  (dedupe by document digest, one attention item per changed document, four-eyes review, audit).
- `/api/lng/terminal-tariffs` (+ `/price`, `/{id}/review`, `/operators/{operator}`); Admin →
  Connectors → Access shows operator terms and the figures to review; the setup guide's LNG step
  counts held, reviewed and candidate terminals. Surface 280 / 311 (+4 / +4).
- K.0 gate 4 (captured Fluxys and Elengy documents reproduce the registered values) cannot pass
  until the firm holds those operators' permission; regulator publications (CREG, CRE) are an
  unchecked alternative.

## 2026-11-18 — CP-16 Research → Spreads and CP-23 "Describe a strategy" (branch `cp-16`, not pushed)

- One StrategySpec (curve | history, legs, unit, forward/spot FX, route tariff, rule) edited
  two ways: the "Describe it" box (`POST /api/research/spreads/interpret`: built-in EN/ZH reader,
  or the model when allowed, translating only; code is read, never run) and the "Understood
  as" chips (picker legs, swap, unit, FX, transport). `POST /api/research/spreads/evaluate`
  computes every figure: curve by delivery month at forward FX net of the proven route's
  published tariffs (gas year, class, missing named, never zero), or a history through the
  spread lab with the route cost both ways as lines. Gaps come back as questions with choices.
- Research → Spreads task (`task=spreads`); chart standard line (net) + grey gross, front-month
  waterfall, tariff table, per-row FX and input classes, weakest class as the result; simulated
  banner. Ctrl K: a spread study opens Spreads with the description.
- Demo acceptance: "forward spread net of transport tariff between TTF and NBP" → NBP − TTF in
  EUR/MWh, BBL route 1.880 EUR/MWh (simulated demo tariffs). Surface 276 / 307.

## 2026-11-18 — CP-02 instrument catalogue and picker (branch `cp-02`, not pushed)

- `GET /api/market/instruments` (READ; `application/instrument_catalogue.py`): the caller's
  entitled daily series as hub → product kind (spot, rolling, month, quarter, season, year) →
  tenor, stable ids (`TTF:M+1`), native unit, source class (sourced / indicative / simulated),
  best source, observations (`thin` under 30), last as-of. The flat spread-series list stays.
- `components/ui/InstrumentPicker.tsx` + `app/model/instrumentPicker.ts`: two levels (hub,
  then kind tabs and tenors), desk shorthand EN/ZH (`ttf jan27`, `nbp m+1`, `the q1-27`,
  `ztp da`, `英国 次月`), presets, recent picks, ≤ 12 options per level, combobox/listbox
  keyboard, bottom sheet ≤ 480 px, tokens only, `sim` mark. Hub-only scope adopted for the
  Prices forward-curve hub. Story page `clients/web/instrument-picker-story.html` (dev only).
- Surface 273 / 304 (272 / 303 before).
## 2026-11-18 — CP-04 storage history and the fundamentals read (branch `cp-04-wip`, not pushed)

- `GET /api/fundamentals/storage` (`application/fundamentals_storage.py`,
  `domain/fundamentals/storage_history.py`): the EU total (GIE's own aggregate) or NW Europe,
  then each country: fill, stock, capacity, day/week change, same gas day last year, N-yr
  average and band (N = complete prior gas years held; band = last five; gaps never filled),
  7-day net rate, EU target, sparkline, full gas-year series on request; missing countries
  named; provider and simulated rows never mixed; EU total reconciled with its countries.
  Surface 273 / 304 (+1 / +1).
- Backfill: `scripts/ops/backfill_gie_history.py` (one gas year per call of the gated
  ingestion script, `--gie-from/--gie-to/--gie-skip-total`; resumable from store coverage;
  2 s pace; `--incremental` for a scheduler). Scratch public store: EU total and 18 countries
  hold 2021-10-01 to 2026-11-16 (5 complete gas years each); 3 countries x 3 dates equal
  AGSI's published fill and stock. GIE terms recorded in `docs/legal/DATA_SOURCE_TERMS.md`.
- Client: "Storage by country" replaces Today's NW Europe storage block (region figures,
  the CP-03 season chart with band and last-year ghost, sortable country table with
  sparklines, a row opens its chart). Demo desk: seven years of simulated storage per country.
- Left: ALSI terminal-level series (the transport reads countries only); not scheduled yet
  (the incremental command exists; adding it to the scheduler is a data-operations change).

## 2026-11-17 — CP-01 normalisation and forward FX (branch `cp-01-02`, not pushed)

- `domain/market/fx_forward.py`: forward FX by covered interest parity from the held ECB
  reference rates and SONIA/€STR/SOFR (GBP ACT/365F, EUR/USD ACT/360), value date = a month's
  15th or the period's middle gas day, spot for prompt products, simple interest to one year and
  annual compounding beyond, refused beyond 24 months, licensed outright forwards
  (`rate_type=forward_outright`) override; tolerance 0.1/0.3/1 %; every result names method,
  inputs and dates; simulated inputs make the rate simulated.
- `application/market_normalisation.py`: one service for values and series (units authority,
  heating value stated or assumed, spot or forward FX per delivery period); refuses with the
  missing rate named. `GET /api/market/fx-forward`, `POST /api/market/normalise` (READ).
  Spread analysis converts mixed-unit legs (NBP p/th vs TTF EUR/MWh). The answer bar sends
  `78 p/th in eur/mwh jan27` to the server; spot stays instant.
- Demo seed holds daily simulated FX and benchmark fixings; a real fixing replaces the demo one.
- Surface 258 / 284 (256 / 282 before). Golden cases in `tests/unit/test_fx_forward.py`.
## 2026-11-18 — CP-07 assumption sets, firm marks, valuation snapshot; CP-08 opportunity core (branch `cp-07-08`, not pushed)

- CP-07: `domain/valuation/` (input classes, weakest-input grade, delivery periods, typed
  assumption catalogue, firm marks that are always class `firm_mark`, the recorded and
  replayable valuation snapshot); `application/valuation_snapshot.py` (one reader for every
  evaluator; spot ECB FX behind the `FxSource` adapter until forward FX lands, labelled
  "FX: spot"); migration `0066_commercial_assumptions`; `/api/assumption-sets`,
  `/api/market/firm-marks`, `/api/market/valuation-snapshots/{id}`; audit without values.
- CP-08: `domain/opportunities/` (object, controls, lifecycle, ranking, claims, evaluator
  contract and harness, reference evaluator type G hedge gap); `application/opportunities/`
  (service, listing, actions, settings, schedule seams); migration `0067_opportunities`;
  `/api/opportunities` (7 paths); evaluator failure raises one admin alert through the
  monitoring scan; demo seed gains Haldor's 60-80 % band and one linked hedge.
- Surface 269 / 299 (+13 paths / +17 operations on 256 / 282). The intraday engine
  (`market_intelligence/opportunity_engine.py`) is unchanged; it becomes the type-L intraday
  evaluator in CP-09 (its three states map to `actionable`/`watch`/`blocked`).
- Not built here: evaluators L, C, S, E, T, R, D, A; scheduled and outbox triggers (seams
  only); the workbench `POST /api/opportunities/evaluate` and the `evaluation` table (CP-15).
## 2026-11-18 — market reports round 5 (part 1): market facts only, no refusals, the report's language, AI in the interface language (branch `reports-round5`, not pushed)

- No meta-commentary: the source was the directive's ANSWER rule ("each section opens with how
  it bears on the question"); directive v4 forbids it (NO META-COMMENTARY), `editor.META`
  refuses it (EN/ZH) and `editor.EFFECT` widens the cause check; rule templates rewritten.
- Refusals moved before Generate: `GET /api/reports/catalogue` carries `availability` (role,
  per-section data held, period limits, AI) from the reports' own builders; a report for
  distribution drops book sections instead of refusing; the form validates and explains
  failures with Retry / Generate without AI.
- Report language (English / 中文) end to end (`reports/lang.py`).
- AI replies in the interface language on every surface: `ai_style.language_rule` and the
  language check in `text_verdict`; Chinese rule fallbacks for Why, the brief and Ask.
## 2026-11-18 — first-run setup guide (branch `accounts-first-run`, not pushed)

- `application/first_run_setup.py`: one mapping of every registered source to a page (open
  data, prices, LNG and shipping, weather, FX and rates; book, AI and people as capability
  items), how each connects today (approval, key, licensed import, none yet, register, ...)
  from the manifests, approval classes and the import tools that exist; a test fails for a
  manifest with no page or an entry without EN/ZH words. LNG terminal tariffs: held / not held
  and from which source (`lng_terminal_terms`).
- `GET`/`PUT /api/setup` (ADMIN), state in `installation_setup` (migration
  `0068_installation_setup`), audited. Keys through the credential routes, approvals through
  the approval route. Surface 257 / 284.
- Web: the welcome dialog for the first administrator (skippable, resumable from Admin →
  Access → Setup), demo marks it configured, UAT seed dismisses it, headless CLI
  `python -m eurogas_nexus.cli.setup`.

## 2026-11-17 — CP-03 chart standard (branch `cp-03-04`, not pushed)

- `components/ui/charts`: history bands from the prior years held (none / grey lines / 5-yr
  min-max band and mean, label never claims more years than drawn; a day any year lacks is a
  gap), ghost series, end labels (≤ 4 lines, never colliding; a line ending early labelled
  beside its last point), rules labelled in the same gutter, gas-year season axis (29 Feb has
  no slot), readout with band and stated comparison, touch-and-drag, screen-reader summary,
  `AlignedPanels`, `SmallMultiples` (shared scale default, list when narrow), `Waterfall`
  (reconciles its totals), `PercentileStrip`, stack form/limit rules. Reports gain the `band`
  and `term_structure` forms; existing exhibits byte-identical.
- Applied: Prices forward curve → term structure with prior-close and week-ago ghosts;
  Delivery → aligned signed shortfall panel; balance stack → area beyond 14 days; board
  sparkline names its last change. Left: NBP–TTF bar spread and Prices furniture (removal
  package; the two-panel spread primitive is ready for CP-20), supply-call sparkline
  comparison (Today recomposition, CP-19), storage season chart (CP-04 replaces it).
- No new path or operation.

## 2026-11-17 — user accounts: local accounts, SSO pre-provisioning, demo test accounts (branch `accounts-first-run`, not pushed)

- Admin → Users can add people: an SSO invite (`INVITED` until the first company sign-in links
  it by verified e-mail or pinned subject) or a local account (`EUROGAS_NEXUS_LOCAL_ACCOUNTS`:
  `auto` = on only without SSO). One-time temporary password shown once, forced change at first
  sign-in, salted scrypt with recorded parameters, uniform refusal, per-account back-off and
  per-address throttle, sessions end on change/reset/disable, last active administrator
  protected, delete only without history. DataGrid + Dialog UI, EN/ZH. Headless first admin:
  `python -m eurogas_nexus.cli.accounts`. Migration `0065_local_accounts`.
- Demo: `EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS` (test_trader … test_admin, weak shared password),
  through the same code path; refused by any non-demo server (start-up, preflight, sign-in).
- Surface: four paths, six operations (256 / 282 on 252 / 276). Security notes: `docs/security/LOCAL_ACCOUNTS.md`.
- Not yet built: the first-run setup flow (part C).

## 2026-11-17 — market reports round 4: asked reports answer the question; report library (branch `reports-round4`, not pushed)

- `reports/answer.py`: question facts for an asked report (outages tied to Norwegian supply,
  landings over the outages' days against the week before, scheduled Norwegian outages),
  engine-declared `related` facts, "what the data cannot tell", the rule answer and the
  relevance order. Rendered as question title, Answer, Evidence, What the data cannot tell.
- Directive v3 adds ANSWER; the checker verifies the answer (rule fallback), refuses a cause
  (only `causes`, none today), allows a time word between related facts, and refuses book words
  in a shareable report. Five recorded asked cases.
- Outage events grouped (`remit_umm.outage_events`) in report reads; a situation report finds
  its outage by any member message id.
- Report library: delete, rename and bulk delete (author or administrator, audited
  `report.manage`); surface 252 paths / 276 operations (+1 / +3 on 251 / 273).
- Viewer: Generate straight from a question (scope optional, collapsed), staged progress with
  Cancel, list with period, by and edited-by, Manage dialog.

## 2026-11-16 — market reports round 3: page economy, exhibits, brand mark (branch `reports-editorial`, not pushed)

- Template `market-report/3`: text beside half-width exhibits, only exhibits kept from splitting,
  lead exhibit sized to fill page one, back matter as run-in paragraphs in three columns, printed
  annex on request (`annex` plan option; default weekly and monthly). Daily prints in 5 pages,
  weekly 7, monthly 9, situation 4, asked 2–3 (Chromium 140).
- Charts: calendar date ticks that never overlap, end labels sized to their text and never
  colliding, accent tonal ramp for categorical stacks, one decimal count per axis.
- Brand mark in the masthead (`brand.mark_svg("colour", ...)`: the report paper is always white).
- Editor: directive v2 adds LINKING (connectives between unrelated indicators refused), runs at
  temperature 0 (recorded); a refused finding is replaced in place. Capacity offline weighs 10x
  its share of Norwegian landings, so material outages lead the rule plan.
- Chinese edition prints its furniture in Chinese.

## 2026-11-16 — market reports round 2: publication standard and AI editor (branch `reports-editorial`, not pushed)

- Template `market-report/2`: fact sheet with comparisons and materiality (`reports/facts.py`,
  `derive.py`), page one (masthead, headline, standfirst, 3–5 findings, At a glance, lead
  exhibit), numbered exhibits with furniture, A4 paged layout with running header/footer,
  data annex and CSV data block, no interface in the document. Standard:
  `docs/product/REPORT_EDITORIAL_STANDARD.md`.
- AI editor (`reports/editor.py`) under `docs/product/REPORT_EDITORIAL_DIRECTIVE.md` v1: fact
  sheet payload (`REPORT_EDITOR_FIELDS`), structured plan, element-level checks and fallback,
  recorded evaluation set (`tests/evals/editor_cases.json`), provider run
  `scripts/ai/run_editor_eval.py`.
- Outage read gains an opt-in `ended_since` for period reports; the live view is unchanged.

## 2026-11-16 — brand mark (branch `brand-mark`, not pushed)

- New mark: a regular hexagon broken by one wave, hand-written SVG on a 32-unit grid
  (`docs/product/BRAND_MARK.md`). `BrandMark` primitive (mark, mark + EN, mark + name; mono,
  colour, reverse, auto) replaces the hub-and-spokes glyph on sign-in, adds the mark to the
  top bar's top-left (name at wide widths), and is the favicon, splash, desktop icons and
  installer art. Brand tokens: `--ds-brand-blue`, `--ds-brand-blue-light` (the two accents);
  `--ds-brand-teal` retired.
- Server side: `eurogas_nexus.application.brand` gives reports the mark as inline SVG; the
  report templates are not changed here (see BRAND_MARK.md, "Report header").

## 2026-11-16 — market reports (branch `market-reports`, not pushed)

- `application/reports/`: a section catalogue (prices, alerts, Norwegian landings, LNG, storage,
  gas-fired power, outages, the NW Europe balance with forecast and Sankey, and Our book:
  position, P&L, limits, contracts) read through the existing entitled services; rule
  commentary; server-side SVG charts with a data table under each; one self-contained HTML file
  with print CSS (PDF = browser print). Kinds daily (morning/eod), weekly, monthly, situation
  (alert or outage), ask (question to a validated, editable plan; model proposal with keyword
  fallback). Model only rewords market sections under `note_verdict`.
- Shareable reports never read book sections; a licensed source keeps a report internal unless
  `market_data_licences.redistribution_allowed`. Records in `market_reports` (migration
  `0064_market_reports`); readers re-checked for sources and books. `/api/reports/*`: 5 paths,
  6 operations (249 / 270). Research → Reports task (no new page id), Report beside Why.
- Not built: scheduled delivery (Part 5), server-side PDF. See `docs/user/REPORTS.md`.

## 2026-11-15 — UX-02/03/05, FRESH-02 and the page frame (client only, uncommitted)

- Primitives Field, Select, Tabs, Segmented, Toolbar, Popover, Dialog, Sheet and DataGrid
  (`clients/web/src/components/ui/`); React Aria measured and not added (see
  `docs/product/DESIGN_TOKENS.md`). Why, desk brief, report-a-problem, shortcuts and the
  phone inspector moved onto them.
- DataGrid carries Position, Limits, the hub board, the NW Europe balance and the capacity
  profile book. Market overview is replaced by Today from `GET /api/desk/today`; late and
  stale figures are named in a popover, the demo desk says "Demo data" once.
- One 40 px page header row. Geometry within budget; CSS lint baseline 292 → 290.

## 2026-11-05 — functional engine improvement branch, F01

- Owner requested isolated functional implementations for later review/merge. Branch
  `feature/functional-engine-improvements` starts from main a40dafc3, independently
  of the documentation PR. No main changes or deployment.
- F01 adds explicit HDD supply-call scenarios at POST `/api/market/nwe-balance`,
  governed permission, SDK, replayable inputs/hash and identical-baseline comparison.
  The original GET and all solver implementations remain unchanged.
- Scenario evidence is caller-declared; no automatic live ECMWF composition or model
  promotion. Production integration and F02–F09 acceptance remain in the
  [functional plan](FUNCTIONAL_ENGINE_IMPROVEMENTS.md).
- Focused API/SDK tests pass. Reviewed and merged to main on 2026-11-05 after the pre-push gate.

## 2026-10-30 — spread lab, training datasets, settings tiers, global topology, storage

- ce2a9e6 Spread lab (Strategy Lab → Spread, default task): weighted spreads of daily
  series, statistics, declared-rule backtest without look-ahead. Fixed the SVG chart point
  offset and dark-mode contrast in strategy-lab.css. CI green.
- 429bf16 Training datasets: declarative lag/difference/rolling/linear-combination
  features, each resolved as of its own cutoff; walk-forward folds with embargo; ML
  readiness assessment; IT admin vs business lead rights. CI green.
- 174b31e Settings tiers (profile / organisation defaults / personal preferences, server
  side), account menu, keyboard-shortcut dialog, locale registry. CI red: revision ID longer
  than alembic_version VARCHAR(32).
- 857a069 Fix: revision IDs shortened, guard test added, 0048 source/time indexes, spread
  lab query bounded, desktop CSP hardened, documentation language policy and guard.
- Docs: GLOBAL_DEPLOYMENT.md (UK-hosted primary for UK/CA/SG, separate China installation,
  one-way signed exports); ADR Decisions 21–24 (Tauri kept and hardened, topology, settings
  tiers, time-series storage); this file rotated.
- Open: power data and gas-for-power drivers; physical + financial position view and
  role dashboards; EEX data fallback; LLM layer; PORTFOLIO scope before office-level book
  separation; access-request approval by business owners.

## 2026-10-30 — commercial-readiness pass: rates, licences, live-price bridge, ladder, CI

Owner-requested pass (see `docs/product/TRADER_ACCEPTANCE_REVIEW.md`). Added SONIA/€STR/SOFR
fixings (migration 0045, BoE/ECB/NY Fed ingest, `/api/market/interest-rates`,
`/api/market/financing-rate`, surface 196/210) for benchmark + spread financing rates.
Licence audit: no blocking dependency. Live prices: no free commercial feed exists, so an
operator import of the desk's own Trayport/ICE/EEX export was added; simulated prices are
flagged. Ladder view and Trayport-familiar conventions added. CI was red since d97fd56; the
redesign's browser-acceptance failures (contrast, hidden evidence, 404 console errors) are
fixed and the sweep passes locally with 0 failures. New AGENTS.md rules 15-18: pre-push
guard, green CI before new work, trader-first UX, commercial-use terms.

## 2026-10-30 — trader acceptance review, import blocker fixed, desk conventions

Supplier-acceptance review from the gas-trader seat: see
`docs/product/TRADER_ACCEPTANCE_REVIEW.md` (conditional acceptance). Blocker: d97fd56
imported the never-committed `ingestion/ecmwf_archive_evidence.py`, so the ECMWF
repository, ingest CLI and archive tests failed to import on a clean checkout. Restored it
as the single pure S1 policy/method/evidence-hash and limitation source, now also used by
the S1 reconstruction; 54 real-PG archive/repository tests pass, including replay. Added
pure desk-convention modules `domain/market/{products,units,storage_targets}.py` and
three READ-floor routes (`/api/market/products`, `/api/market/price-conversion`,
`/api/storage/target-trajectory`), SDK functions, and a Trader desk panel on the existing
Market → Curves task (no new page). Surface pinned at 194 paths / 208 operations. No
execution, nomination or settlement semantics; FX and calorific values are never
assumed.

## 2026-10-30 — final expanded scientific gate232 accepted

CI mapper-registration6345 terminal exit0. Root re-ran final scientific composition
in approvedLinux/NumPy:193 unit/bridge cases plus39 realPG cases passed, zero skips.
Actual updated inlineJUnit gate accepted232 tests and all15 exact module identities.
Root76 scientific/releaseG1/ontology contracts passed;364Markdown local links pass.
No gates relaxed. Register archivePG in fullPGCI, archive/label/mapperunit paths in
scientific selection and exact-module gate. The39PG cases include S3 boundedlocks,
corefit, operator and frozenprediction; no realprovideraccuracy claim.

Native81050 terminal changedNOFILES because brief lacked exact ignored paths and
Harness enumeration was unavailable. Root read finalreport, supplied exact root
and every knownfile, and launched bounded correctionv2 at98158. No ACLrepair or
external network policy bypass authorized; self-authored collector assertion only.
Rootretry of actual conditional archivecapture still refused rate_limited; retained
separate retry-0255 report, no repeatedhammering or actualcapture claim. S481939
still live. Full goal active; latestpushed d97fd56; CIregistration accepted separately.
## 2026-10-30 — bounded archive S3 accepted and pushed d97fd56

Lock worker46931 terminal exit0. Root actualPG30 passed including held-lock timeout
and concurrent replay success,65 existing repository/reader/archive/evidence units
passed, focusedRuff and diffchecks passed. New archive locks use sorted transaction
keys, nonblocking pg_try_advisory_xact_lock and shared monotonic5s acquisitionbudget,
with typed retryable busy refusal; no caller settings/commit/rollback/defaultpath
change. S3 canonical evidence hash/policy/method/limitations and originalrow binding
are verified. First actualreceipt/provenance retained and no oldrowbackfill.
Commitd97fd56 (5files) pushed authorized main; hostedCIpending. Provider S2 authentic
conditional capture remains unproven; these transport/decoderfixtures are synthetic.

Root now authorizes bounded S4 explicit research read/projection only, task81939:
complete typed archive DTO, immutable actualreceipt plus separate reconstructed
clock, trustedserver analysiscap, historicalorigin/evidencebinding validation and
bounded noautoflush actualPGreads. Existing live/API/bridge default receipt semantics
unchanged, no model/runtime/operator/prediction/API opt-in. Register readtests only
after finalreview. Nativecollector81050 and mapper-CI6345 are live and ownseparate
files; oldnative38478/archive54802/labelmapper20659 are terminal. Revalidate handles,
never duplicate. Full scope remains active.
## 2026-10-30 — actual REST label mapper verified and pushed a8f359f

Mapper worker20659 terminal exit0. Root first test run52pass1fail found a test-only
strict-zip length mismatch; corrected labels[:-1] vs labels[1:] without weakening
monotonicity assertion. Final mapper/new+existing tests53 passed; Ruff passed.
Root actual read-only PostgreSQL probe mapped all17 persisted authentic National
Gas REST revisions over5 gas days with explicit research basis,0 diagnostics,
identical revision IDs/ranks/values/actualreceipts to default, no writes and no
model. Evidence target-label-mapper-actual-readonly.json retained. This is actual
stored-source consumption at mapper only, not historical-publication or accuracy
proof. Runtime/operator/predictor nondefault use remains separately gated.

Commit a8f359f includes mapper, newtests/docs and root RFC advancement addendum;
pushed authorized main. Hosted CI pending. Archive lock46931 and native transport
collector81050 remain live; no overlap or restart. Full goal active. Root must
register new mapper unit in scientific gate after archive finalvalidation, then
advance bounded read/fit runtime stages without changing default receipt semantics.
## 2026-10-30 — hosted ontology gate omission corrected 3b02537

Authoritative job snapshot for CI40993736249/ddd22a4 shows validate/Tests failed.
Root fetched exact job123861929027 log: only reported failure is
contract/test_domain_enum_ontology_gate.py requiring review for the new
DemandTargetLabelBasis. Science leaf, PostgreSQL, browser EN/ZH, both SDK wheels,
all three native builds, web build and dependency/license audit jobs succeeded;
this does NOT make the whole failed run successful.

Root architecture ruling: target-label evidence clock is research-methodology
vocabulary, orthogonal to existing allowlisted weather ValidationBasis, not a new
gas-market quality/unit/semantic. Add only this exact enum to reviewed entries
with RFC0008 rationale; retain AST scan and stale-entry checks. Root2 focused
ontology contracts and Ruff passed. Commit3b02537 pushed; new CI must verify it.
No unrelated enum exemption, schema or production behavior change.

Three implementation tasks20659/81050/46931 remain live at last handle poll.
Wait terminal before edits/testing their final source. Full goal active. Previous
continuation verified live waits; this turn fixes actual hosted gate failure.
## 2026-10-30 — archive integrity mechanics verified, bounded lock followup

Workers54802 and38478 completed exit0; do not restart them. Root actual PostgreSQL
archive integrity29 tests passed (including two-session replay and stored-binding
mutation refusals), archive units6 passed and Ruff passed. Canonical policy/method/
evidence hashes and required limitation labels are now recomputed; stored row
binding is checked against original v3 provenance with query-specific receipts
preserved. Root withholds final acceptance because blocking pg_advisory_xact_lock
has no intrinsic wait bound outside tests. New bounded DeepSeek task46931 owns
repository/archive PG tests/doc only, replaces it with a shared total bounded
try-lock budget and typed retryable busy refusal, preserving sorted xact locks.

Root executed native collector: INCOMPLETE,0wheels0APKs11gaps. Its self-authored
non-public DNS assertion rejects the approved machine198.18/15 DNS transport, even
for fixed TLS-verified PyPI/Alpine hosts. Root authorizes correcting THIS prototype
assertion (not any external policy) with strict fixed HTTPS origins/paths, TLS,
redirect/size/hash controls and DNS provenance. New native followup81050 also must
preserve official APK/index signature verification instead of rebuilding unsigned
indexes and using allow-untrusted. No build or production dependency/image change.

Mapper-only stage2 worker20659 remains live; RFC0008 now has explicit root staged
advancement addendum after ddd22a4 pure acceptance. Runtime/operator opt-in stays
unauthorized until separate review/serverclockcap. Main CI40993736249 last observed
in_progress. Earlier complete PG116/numericalgate201 predate final corrections and
must be re-run. Full delivery goal active; previous turn verified live waits.
## 2026-10-30 — reviewed pure label integrity slice pushed ddd22a4

Corrective worker58574 completed exit0. Root reviewed monotonic per-day effective
clock/derived-rank validation, exact complete latest analysis finaltruth, model
fact/count/revision/identity/cutoff binding, fold consistency and standalone
nondefault prediction DTO refusal. Both existing predictors and runtime still
refuse nondefault use; mapper/runtime/operator wire opt-in remains deferred.
Root actual Linux/NumPy58 focused label/core/prediction tests passed after final
worker output, Ruff passed, default pre-change selection/baseline/candidate hashes
and exact ten-fold metrics still match. Operator PG fixture correction keeps pure
field out of strict wire only after proving ACTUAL_RECEIPT; nondefault omission
refused. Earlier real PG116 and combined gate201 predate final integrity changes
and must not be attributed to final revision without revalidation.

Commitddd22a4 (four files) pushed authorized origin/main. Hosted CI pending; source
has no archive or CI-registration changes in this commit. Archive integrity54802
and native experiment38478 still live; their files remain uncommitted and must not
be folded into this slice. Full goal remains active; no provider accuracy, runtime
packaging or customer-delivery completion inferred.
## 2026-10-30 — root adversarial label reproduction and live corrections

Root independently executed a synthetic NumPy constructor/selector probe before
label correction landed: empty finaltruth and one-fact fitted-model metadata were
accepted, and inverted rank/label clocks selected earlier-clock rank2. This
reproduces B1/B2/B3 mechanics; retained review-findings-root-probe.json under
label-default-golden. Existing predictor still refuses nondefault; no emitted
prediction/accuracy/provider-data claim. Corrective task58574 remains live.

Archive corrective task54802 began editing during a root adversarial probe: forged
policy was already typed refused, but normal insert hit a transient undefined new
lock helper in the incomplete live edit. This is NOT final acceptance or a stable
regression result. Wait for actual worker terminal and then run full correction
suite. Preserve probe record; do not restart or patch live worker files. Native
experiment38478 also remains live. Independent reviewer27523 completed exit0.
Station primary PDF collector received403 for both exact official URLs; no mapping
is approved from search excerpts. No repeated provider probing while unchanged.
Prior continuation verified live worker waits and collected primary access evidence.
Full goal stays active; no new customer readiness claim.
## 2026-10-30 — independent integrity findings hold acceptance

Full registered PGCI session72987 completed116 passed, with all migrations0044,
schema and authenticated/unauthenticated API smoke. Correction worker19883 is
terminal exit0; final fixture diff preserves production strict schema and adds
nondefault omission refusal. This mechanics proof does not close review findings.

Independent read-only DeepSeek review now identifies S3 missing canonical evidence
hash/policy/limitations recomputation, unchecked stored per-row archive binding,
and an unexecuted concurrency race concern. Label S1 lacks derived-rank/clock
monotonicity enforcement, exact complete latest finaltruth checks and exact model
fact/count/revision bindings; standalone prediction DTO should refuse nondefault
until full carrier exists. Root inspected cited source and accepts these as
strengthening work before acceptance; the reviewer could not execute tests due
Harness shell ACL. Do not describe concerns as reproduced runtime failures.

Root launched bounded DeepSeek corrective tasks: archive integrity session54802
(object/binding replay validation, canonical evidence hashes and bounded two-session
PG concurrency reproduction; transaction-scoped sorted locks permitted if needed),
label integrity session58574 (pure-only causal/order/completeness validation and
DTO refusal; preserve exact default golden). No overlapping code ownership. Native
source experiment38478 remains separate. Independent reviewer27523 only owns its
review document; revalidate terminal handle before relying on completion. All new
code remains uncommitted pending these corrections and root revalidation; latest
pushed main a98ace6 remains green. Full goal active, no customer completion claim.
## 2026-10-30 — actual combined numerical gate now passes

Root reviewed completed CI-registration worker19754: additive exact-module entries
only, existing required modules/security/pins and zero-skip semantics retained.
Final numerical-CI/release G1 contracts74 passed; focused Ruff passed. Root tested
the in-progress fixture correction (only pure ACTUAL_RECEIPT may be omitted from
strict operator JSON; nondefault refusal regression added): four real PostgreSQL
scientific modules now28 passed, no skips, on Linux/NumPy. Prior25pass2fail evidence
is retained rather than overwritten. Correction worker19883 still finalizing;
revalidate terminal state and final diff before accepting.

Root ran the actual updated workflow inline JUnit gate against173 unit/bridge
cases and28 actualPG cases:201 tests, zero failures/errors/skips, all14 exact module
identities observed. Evidence: .local-runtime/archive-label-gate-review-20261030.
This is local verified numerical mechanics, not hosted CI or provider accuracy.
Full registered PGCI (migrations/schema/auth smoke/all modules) now running at
session72987 in owned nexus_archive_label_full_ci_20261030; do not restart/claim
result before actual terminal output. Independent review27523 and native source
experiment38478 last confirmed live. Full delivery and source/native closure remain
open. Previous turn progress/verified wait, no completion claim.
## 2026-10-30 — full scientific PG cross-contract failure isolated

Root expanded scientific PostgreSQL run (four modules, real Linux NumPy) produced
25 passed2 failed, no skips; do not claim zero-skip gate acceptance yet. Both
failures are existing operator fixture serialization: dataclasses.asdict now emits
the new pure-only model_policy.target_label_basis; the unchanged strict operator
wire schema correctly refuses this unknown field with exit2. Root authorizes a
bounded DeepSeek correction ONLY to the operator PG fixture: require ACTUAL_RECEIPT
before omitting pure-only field, refuse silently dropping nondefault basis, and
preserve strict production parser/schema. Session19883 now owns that test file.
Actual failed JUnit and redacted log are retained. Re-run all four PG modules after
terminal correction, not merely the two assertions. No runtime label opt-in.

CI contract9 passed against new registration while worker19754 still finalizes;
not final acceptance. Independent review27523 and CI registration19754 confirmed
live. New NumPy source-build experiment worker38478 is live, restricted to ignored
prototype output and a new experiment note; production dependencies/images/gates
remain unchanged. It must collect pinned input evidence before any bounded build.
Previous continuation was concrete progress:173 numerical tests and measured default
golden proof. Full delivery goal remains active.
## 2026-10-30 — expanded numerical regression verified

Previous continuation made concrete progress (actual PG19, numerical56 and exact
pre-change default golden comparison). Root now ran the complete existing eight
scientific unit/bridge modules plus both new archive/label modules in the approved
Linux Python/NumPy environment:173 passed, zero skipped, JUnit retained at
.local-runtime/delivery-20261030-label-default-golden/combined-unit.xml. Focused
Ruff and git diff --check pass after two import-order repairs. No customer image
or provider-history/model-accuracy claim follows from synthetic mechanics tests.

DeepSeek independent review session27523 and bounded CI-registration implementation
session19754 were both re-polled and confirmed live. The latter owns only the
existing science workflow, PGCI script, numerical CI contract test and its new
registration note; it must preserve all zero-skip and exact-module gates. Wait for
terminal workers, review findings, validate registered PG and JUnit gates, then
commit/push accepted slices. Do not duplicate live workers. Full goal is active.
## 2026-10-30 — root revalidation of terminal archive and label workers

Actual launcher handles92448/85834 are missing, process inventory has no matching
live Harness processes and both completion records report exit0. Do not duplicate
these implementation workers. Root ran actual Linux/NumPy unit checks:56 passed,
including label-basis, archive persistence, core fitter and frozen prediction.
Root separately recaptured the default golden to after.json (before.json retained):
all three model/selection hashes, ten folds and exact metric strings match.
Windows-only first pass8 passed12 skipped is not numerical acceptance evidence.
Root actual PostgreSQL archive S3 module19 passed using owned disposable schemas
in nexus_archive_s3_review_20261030. These are synthetic transport/decoder mechanics,
not actual provider archive capture. Two Ruff import-order errors were repaired;
implementation is not yet accepted or committed pending adversarial review.

All latest pushed CI runs a98ace6, dab616c, ca8fbaa and a1f281d completed success.
Root independently inspected native wheel ZIP/RECORD/ELF payloads, API base identity
and exact NumPy sdist; facts and remaining closure are added to the native review.
No production dependency/image/license policy changed. Scientific runtime customer
packaging remains open. New bounded read-only DeepSeek independent review of
archive/label code is launched at session27523; revalidate actual handle before
acting, do not infer liveness from log files. Full goal remains active.
## 2026-10-30 — bounded orthogonal label-clock architecture

Root accepts RFC0008 staged research architecture and authorizes pure stage1 only.
Actual receipts stay immutable and always bound by analysis-as-of. Reconstructed
provider applicability is a separate opt-in label clock and historical-publication
assumption, never actual-receipt/genuine OOS proof. Root corrected the draft's
late-receipt test to distinguish receipt AFTER analysis (exclude everywhere) from
receipt AFTER historical fold but BEFORE analysis (eligible only under explicit
reconstruction if its source clock was already applicable). Existing predictor
must refuse nondefault use until full evidence propagation is reviewed.
No runtime opt-in, source activation, API or quality promotion is authorized yet.

Root captured pre-change default synthetic core golden at dab616c:
selection7d2cbc5ee765b775b2f07c51cedc8bc3433c90fd60968112c8be17d523ef1647,
baselinea10059c3b9d4b816fb1df7342bc120a37e25b185976677cc72e1096d9d09e545,
candidate9cfaa82b64efaa5543b36414f152313d733914c25404135c7975cca749c59c58.
Ten folds and exact metrics are retained in ignored
delivery-20261030-label-default-golden/before.json. Future defaults must match.

Live DeepSeek tasks: archiveS3 persistence session92448 and NumPy native-source
closure review98153. Prior S2/prediction/RFC8 workers are terminal. a1f281d whole
CI succeeded, confirming the strengthened G1 leaf integration; ca8fbaa/dab616c
CI pending. S2 actual end-to-end still unproven. Full goal remains active.
## 2026-10-30 — persisted forecast to frozen demand prediction accepted

Reviewed DeepSeek read-only prediction runtime takes an already fitted frozen
DemandModelResult, reads actual eligible persisted ECMWF rows, projects through
the existing bridge/degree-day solver and calls the actual pure selected-model
predictor. It never refits or reads target demand. Missing coverage produces no
prediction; selected baseline is labelled baseline reference without claiming
weather consumption. Native MSCM, model/selection/feature hashes, actual forecast
IDs/vintage, explicit unreviewed weighting reference and no-promotion labels remain
attached. Genuine receipt basis only; no archive fallback, API or scenario policy.

Root final verification:153 selected numerical units plus8 actual PostgreSQL
fit/prediction tests passed; the actual updated inline JUnit gate accepted161
tests, zero failures/errors/skips, including exact prediction module identities.
Full registered PGCI96 passed with schema/API smoke.74 numerical-CI/release-G1
contract tests passed, focused Ruff passed,358 Markdown files have valid local
links. Prediction PG case uses real ORM/SQL/bridge/fitter/predictor on synthetic
21-day history; no provider-history accuracy is claimed. Register new unit and
PG modules in both full PGCI and science zero-skip gate. No customer scientific
runtime dependency closure or full delivery acceptance inferred.

Archive S2 actual transport/decoder path remains unproven after ConnectTimeout;
root added a typed safe transport refusal and verified its mechanics. RFC8 draft
is not yet accepted: its late-receipt test wording needs correction to distinguish
analysis-cutoff admission from reconstructed historical fold eligibility. Continue
S3 append/verify, S4 archive reads, orthogonal label-clock design, regional mapping,
real data/model business consumption and outstanding full acceptance scope.
## 2026-10-30 — bounded archive S2 capture implementation accepted

Reviewed DeepSeek fixed-origin server capture uses HEAD metadata for the exact
AWS index/GRIB keys, conditional If-Match index/range GETs, bounded retries and
streams, strict validators/ranges, exact bytes/hashes, actual receipt clocks,
safe Date metadata, lazy native decoder and S1 validation. Existing live retrieve
default remains unchanged. No DB, source activation, archive eligibility or API.
Root repaired a Range-request test typo, added stable transport-error refusal,
and moved GET receipt clocks after complete bounded body reads with a delayed
stream regression. S2 focused36 passed; S1 focused16 previously passed. Existing
ECMWF client/decoder plus prediction units63 passed in approved Linux environment;
focused Ruff passed. Actual S2 official capture attempt refused on ConnectTimeout,
so authentic S2 end-to-end is still unproven; no raw capture/model claim.

Both implementation workers95817 and10762 are terminal. RFC8 draft9793 is also
terminal and awaits root architecture review. Do not restart them. Broader release
suite48981 completed484 passed7 skipped; those environment skips are not numerical
evidence. Full new PostgreSQL registered script91406 completed96 passed with all
migrations/schema/API smoke in owned nexus_prediction_full_ci_20261030, including
new actual frozen-prediction composition test. Prediction and its CI registration
are reviewed separately in the next commit. Full delivery remains active.
## 2026-10-30 — G1 numerical leaf integration correction

Run40975872180 science job succeeded, but overall CI failed at validate/Tests:
test_required_jobs_are_exactly_the_unconditional_main_push_leaf_jobs correctly
caught that the new numerical leaf was absent from stable G1 required_jobs.
Root adds the exact science leaf to policy and the reusable-leaf contract, so
missing/skipped/failed science jobs now block release. This strengthens the gate;
no skipped/failing check is ignored. Focused G1 tests65 passed and Ruff passed.
Broader tests/release run is still live at session48981; do not restart it or
claim its result. New revision CI must verify the policy integration.

New prediction runtime mechanics verified by root while DeepSeek still finalizes:
9 Linux/NumPy units passed, and1 actual PostgreSQL integration flow passed in
owned nexus_prediction_runtime_ci_20261030. It fits committed synthetic21-day
history, predicts from future committed forecast rows using the actual core,
excludes late receipt/issue rows, preserves pending caller row and transaction.
Not yet accepted/registered/committed; wait for worker terminal and final review.

Causality review worker84538 completed. Root separately executed40 syntheticdays:
historical receipts ->10 folds/weather selected; receipts captured now with past
cutoff -> refused no training rows; today's cutoff -> candidate fitted but zero
folds/INSUFFICIENT_DATA/calendar baseline. Accepted finding: historical weather
archive alone cannot fix target-label availability. No receipt rewriting or
reconstructed-target policy is authorized by the existing ranking option.
See RETROSPECTIVE_DEMAND_LABEL_CAUSALITY_REVIEW.md root addendum.
## 2026-10-30 — hosted numerical proof and S3 null-version correction

Hosted science job123803628020 in run40975872180 at3ee4a79 completed success:
exact wheel install, full registered PostgreSQL script, actual numerical units
and actual PostgreSQL fit modules, zero-skip/module-identity gate, and artifact
upload all succeeded. Whole CI still running at observation; no overall green
claim. ae8eabe and80b91ac whole CI both succeeded.

Root found a metadata-label edge case during S2 review: literal S3 versionId
"null" is overwriteable, not immutable version pinning. Verified AWS primary
reference: https://docs.aws.amazon.com/AmazonS3/latest/userguide/AddingObjectstoVersionSuspendedBuckets.html.
S1 now retains the exact string while recording the unpinned limitation for
both None and literal"null". Sixteen focused S1 tests and Ruff passed. No data
eligibility change; no production or archive capture success inferred.

Regional primary-source review now records the actual13 throughput weights
(sum1.000) explicitly for GasYear2024/25 on2020CWVbasis, not current2026/27.
Xoserve2025review effective dates prove that blindly reusing historical station
weights today is unsound. See REGIONAL_WEATHER_WEIGHT_PRIMARY_REVIEW.md; no
weights/stations activated in code. Exact historical publication knowledge and
temperature/HDD approximation remain unresolved.

Live workers: archiveS2 session95817, prediction runtime10762, and new bounded
causality review84538 (dsh-retrospective-label-causality-review). The latter must
verify whether actual-receipt labels captured now prevent historical fold
training; provider applicability ranking never authorizes receipt rewriting.
S2 in-progress tests currently have failures; do not accept or commit that work
until the worker terminates and root review repairs/verifies it. No restart of
live processes. Full delivery goal stays active.
## 2026-10-30 — isolated numerical CI gate accepted for execution

Reviewed DeepSeek reusable weather-model workflow is called by ordinary/manual
CI with read-only permissions and same dispatched SHA. It installs only the
exact hash-pinned CP311 manylinux NumPy 2.3.5 wheel into its internal environment.
The full PostgreSQL script precedes explicit focused unit/actual PG fit suites.
JUnit gate rejects any skips/failures/errors/zero cases/missing required module;
module evidence comes from exact normalized classname/file identities, never
from testcase names. Root corrected one final test-message spelling assertion.
Nine contract tests passed, including executing the actual inline parser against
valid and tampered evidence; focused Ruff passed. Actual local 144-unit/7-PG
JUnit passed the revised gate with 151 tests and zero skipped/failed/errored.
New isolated Linux target install verified the exact lock with hashes, binaries
only, no dependencies and ignore-installed. No customer runtime/redistribution
approval is inferred; native obligations remain open in NumPy review addendum.

Root also ran the full registered PostgreSQL script in newly owned database
nexus_science_full_ci_20261030: all migrations through0044, required-table check,
credentialed and uncredentialed API smoke, and95 tests passed. This includes
real fits on synthetic fixtures; not provider-history accuracy evidence.
Actual conditional archive index failure was diagnosed as AmazonS3 XML Code
SlowDown (HEAD200, conditionalGET503, no Retry-After); do not hammer or remove
conditional validation. Prior80b91ac remote CI succeeded; ae8eabe pending.

Two bounded DeepSeek workers are active: dsh-archive-s2-capture session95817,
and dsh-demand-prediction-runtime session10762. Respect live handles; no restart
on observation timeout. S2 owns only raw capture/client extension/application
wrapper/new unit module. Prediction owns only new runtime/unit/PG/doc files.
Root will register prediction PG tests only after review. No desktop GUI use.
Full regional history, source coverage, prediction business use, delivered
scientific dependencies/native closure and remaining acceptance gates stay open.
## 2026-10-30 — RFC0007 S1 pure archive evidence validation

Reviewed DeepSeek S1 helper validates typed fixed-bucket HEAD/HTTP metadata,
exact index/range bytes and hashes, decoder/request identity, conservative max
object LastModified, opaque ETags, explicit null versions and public-read
continuity assumption. Replay comparison is explicitly query/decoder specific.
No SQL, network, native decoder loading, source activation, model eligibility
or canonical receipt rewriting is introduced. Root focused tests: 15 passed;
Ruff passed. Duplicate JSON members are refused by the reused strict parser.
Actual end-to-end S1 capture remains unproven: official historical conditional
index GET returned HTTP 503. Earlier historical decode evidence is separate.

Scientific CI review is ongoing in DeepSeek task dsh-weather-ci-review-fix
(session 83435, launcher metadata under ignored dsh-tasks directory). Do not
restart while live. Root ran the exact selected unit set: 144 passed, plus both
real PostgreSQL modules: 7 passed; their actual JUnit reported 151 tests with
zero failures/errors/skips. The current inline gate accepted these reports;
review still requires testcase-name spoof protection and contract correction.
Exact science lock installed successfully into a new isolated Linux target with
--require-hashes --only-binary=:all: --no-deps --ignore-installed. The application
runtime dependency/redistribution gap remains open. NumPy internal-only review
addendum is local and must accompany any science workflow commit.
## 2026-10-30 — explicit REST target ordering reaches runtime/operator

Reviewed DeepSeek implementation forwards optional target_revision_order_policy
through the read-only runtime and strict operator request. Default remains
DERIVED_RECEIPT_ORDER; REST applicability opt-in is rejected for CSV or unknown
policy before repository reads. Request hashes include the nondefault policy;
root compared both default CSV and REST hashes against the committed legacy
implementation and confirmed exact equality. Operator evidence distinguishes
actual receipt availability from source applicability ranking. No rows, source
permissions, public SDK command, schema or customer dependency changed.

Root Linux Python 3.11.12 / approved isolated NumPy 2.3.5 verification: 53 tests
passed across runtime, operator and archive evidence modules, zero skipped;
focused Ruff passed. Actual read-only two-database probe retained source counts
3 ECMWF / 17 National Gas rows. For the requested date window, four target
revisions were admitted without receipt-tie ambiguity, two weather observations
were read, zero feature days or training pairs qualified. Result correctly
INSUFFICIENT_REAL_HISTORY with no model. This is integration/refusal evidence,
not a real-data fitted model, national weighting or forecast accuracy claim.

Latest remote CI at 635b6cc and 8301b27 both succeeded. Scientific CI and archive
S1 helper remain under review, uncommitted. Archive conditional index GET returned
HTTP 503 repeatedly at the official historical AWS URL; no successful S1 actual
capture is claimed. Continue science gate review, bounded archive capture and
regional history/model business consumption. Full delivery goal remains active.

## 2026-11-15 — AI-04 evaluation set, Today SDK, NBP native display, QA-03 audit

Branch `backend-m2` (worktree, not pushed). AI-04: recorded evaluation set (89 cases,
four uses) run in CI through the product's checks; the checker gained advice,
simulated-as-market, per-figure direction and hub, source-name, acronym and Chinese-unit
checks; answer paths and the alert enrichment are now checked (they were shown
unchecked); provider payloads minimised to an allowlist (ids and earlier model text no
longer sent); note budget raised (a 300-token budget made every reasoning-model note
empty). Live DeepSeek run on demo/public evidence: 90.9 % of outputs pass. Python SDK
`desk.fetch_desk_today_result`. Today and the brief show NBP in GBp/th through the unit
authority; storage and every book figure unchanged; readers convert p/th rows instead of
dropping them. Capacity: legacy ENTSOG volume-only rows stay withheld, now with a warning
in native mode and without hiding native rows. National Gas demand readers are under the
identity withholding rule. QA-03 report in `docs/api/API_CONSISTENCY_AUDIT.md`.
