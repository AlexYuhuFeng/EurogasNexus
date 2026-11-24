# API Contract Evolution Policy

Chinese companion: [API_CONTRACT_EVOLUTION_POLICY-CN.md](API_CONTRACT_EVOLUTION_POLICY-CN.md)

## Purpose

Additive 2026-11-24 (LNG cargo in transit, Commercial Intelligence V3 LNG-1): four paths, four
operations. `GET /api/lng/cargoes/plans` (READ, PORTFOLIO_READ, book scope) lists the firm's
cargoes in transit with `slot_status`, `headline` of the last change, `contract_warning` and the
next suggestion. `GET /api/lng/cargoes/{cargo_id}/plan` (READ) answers `cargo`, `inputs` (each
with its source: ETA, slot, boil-off from the contract terms, the approved assumption or the
desk standard, gas in kind, hedges), `plan` (berth, `slot_status` on_time|waiting|missed|no_slot,
`boil_off_mwh`, `gas_in_kind_mwh`, `delivered_mwh`, send-out by gas day, `months[]` per hub and
delivery month with physical, hedged, net, cover ratio and last trading day, demurrage and
`suggestions[]` roll|sell|buy_back|short_notice|find_slot|demurrage|deadline), `contract`,
`last_change` (against the previous `cargo:{id}` market event) and `advisory`; a market cargo
with no book is 404 `cargo_not_found`. `POST /api/lng/cargoes/{cargo_id}/plan/what-if` (READ)
takes `eta_utc`, `berth_delay_hours`, `laytime_hours`, `demurrage_per_day` and returns the
`change` between the stored plan and the altered one; nothing is stored. `PUT
/api/lng/cargoes/{cargo_id}/hedges` (GOVERNED, PORTFOLIO_WRITE) replaces the hedge legs that
cover the cargo (`hub`, `month` YYYY-MM, signed `mwh`, optional `reference`; unknown hub 422
`hub_unknown`), retires the old set, audits it and publishes `cargo.changed` through the market
event outbox. Decision support only: nothing is traded or nominated. Census: 282 paths / 315
operations (+4 / +4 on 278 / 311).

Additive 2026-11-20 (forward balance, CP-25): one path, one operation.
`GET /api/fundamentals/forward-balance` (READ) answers `headline` (tighter/looser/about normal
by GWh/d over D+1..D+14, `main_driver`, `contributions_gwh_d`), `daily[]` and `monthly[]`
(demand, Norway, LNG, storage, gap, each with its normal or error, the inventory and fill path
against the 5-year band), `lines[]` (source, as-of, class: observed, scheduled, forecast,
assumption, manual or simulated), `demand_model`, `backtest`, `storage.target`, `overridden`,
`what_if`, `forward_curve` (for reference only) and `weather_reference` (Eurostat HDD). Query:
`hub` (`nwe`; another hub is 422), `period`, `temperature_shift_c`, `norway_gwh_d`,
`lng_gwh_d`, `outage_line`/`outage_gwh_d`/`outage_from`/`outage_to`. Census: 278 paths /
311 operations (+1 / +1 on 277 / 310).

Additive 2026-11-20 (contract kinds and price formulas, docs/product/CONTRACT_TYPES.md): one
path, one operation. `GET /api/contracts/{contract_id}/price?month=YYYY-MM` (READ, book scope;
404 `contract_not_found` outside it) returns the contract's `price_terms` (`price-terms/v1`:
fixed, index ± premium with its averaging rule, or a weighted formula with cap/floor), a `note`
when the price can only be read as recorded, and `result` (`value` in the contract's own unit,
`input_class`, `words`, `inputs` each with class, source, window and observations, `missing`
indices named, `notes` for cap/floor). `POST /api/route-cost/upstream-contracts` gains optional
`contract_kind`, `kind_terms`, `unmodelled_terms`, `master_contract_id`; its base columns are
optional for a typed kind (derived from the terms) and required for a supply agreement; reads
add `contract_kind`, `contract_kind_reviewed`, `kind_terms`, `unmodelled_terms`,
`master_contract_id`, `headline` (additive). Census: 273 paths / 305 operations (+1 / +1 on
272 / 304).

Additive 2026-11-19 (tracked strategies and the intraday feed path): five paths, six
operations. `GET /api/research/strategy-tracks` (the caller's own tracks) and `POST` (`name`,
`mode` daily|intraday, `spec` a StrategySpec, `rule` an intraday rule: `kind`
zscore_window|vwap_reversion|breakout, window, entry/exit z, `size_mw`, liquidity gates
`min_top_size_mwh`, `max_quote_age_seconds`, `max_no_trade_minutes`, `slippage_per_mwh`,
`require_positive_edge`, `max_hold_minutes`, `advice_ttl_seconds`, `debounce_seconds`; unknown
fields refused) return a track (`snapshot` with signal, advice with `computed_at`,
`quote_age_seconds`, `expires_at`, `cutoff_at`, paper position, realised/unrealised P&L, max
drawdown, `assumptions`); `GET /api/research/strategy-tracks/{track_id}` adds `intents` (order
intent records: legs with instrument and side, size, limit, reason, checks, `sent: false`),
`blotter` (paper fills and refusals), `signals` (signals, gates, `missed`, `superseded`) and
`equity`; `POST .../{track_id}/stop`. `POST /api/market/ticks` (`source_system`, `quotes`
with bid/ask, sizes, last, session open/high/low, VWAP, volume, trade count, settlement, prior
settlement, open interest and the exchange time; `trades` with trade id, price, size, trade
type screen|block|otc_cleared|auction, aggressor, broker; `replay` for simulated sessions)
returns counts and the evaluation of the tracks listening. `GET /api/market/prompt` (`hub`)
returns the live WD/DA screen, the WD − DA spread and today's booked prompt trades against
VWAP, settlement and the mid at trade time. `market_quotes` gains nullable session fields in
`GET /api/market/quotes` (additive). The daily rule backtest (`/api/research/spread-analysis`
and `/spreads/evaluate`) adds `execution`, `assumptions`, `periods`, per-point `signal`,
`signal_level`, `drawdown`, `roll`, per-trade `pnl_per_mwh` and `holding_days`, metrics
`pnl_per_mwh`, `worst_trade`, `best_trade`, `average_holding_days`, `roll_days_excluded`,
`too_few_trades`, and `pnl_currency`; `cost_per_mwh` defaults to the held bid/offer (else
zero) instead of 0.02 and execution to the next close (behaviour change, documented in
`docs/product/STRATEGY_TRACKING.md`). Census: 272 paths / 304 operations (+5 / +6 on 267 / 298).
Removal 2026-11-19 (commercial design basis 2, I.3 and decision L4): the deferred capabilities
are no longer served by default: the dataset builder (`/api/research/features|targets|capabilities|datasets…`)
and the agents workspace (`/api/capabilities…`, `/api/agent/…`), 21 paths / 22 operations, listed
in `security/public_surface.py` `DEFERRED_PUBLIC_PATHS`. Their backends and tests are kept; an
operator serves them again with `EUROGAS_NEXUS_DEFERRED_CAPABILITIES=on`. The strategy registry
and the shadow runtime stay served while the Spreads backtest and shadow tracking are rebuilt.
Census: 266 paths / 297 operations (−21 / −22 on 287 / 319).

Additive 2026-11-18 (scheduled reports): one path, two operations. `GET /api/reports/schedules`
(READ) answers `{schedules[], last_slots}`; `PUT /api/reports/schedules` (ADMIN; body
`{schedules[]}`: kind daily|weekly, at_utc, weekday, language, roles, email) replaces the list,
each schedule validated (422 `bad_kind`, `bad_time`, `bad_weekday`, `bad_roles`, `bad_plan`) and
the change audited as `report.schedules`. A scheduled report runs as the service principal, is
for distribution, and is listed only for its roles (and administrators). No field changes
meaning. Census: 285 paths / 317 operations (+1 / +2 on 284 / 315).
Additive 2026-11-18 (commercial design basis 2, CP-17: pipeline landings): one path, one
operation. `GET /api/fundamentals/flows` (READ; `season` comma-separated codes) returns
Norwegian pipeline gas landed in the EU and the UK terminals as totals, then each landing
(Dornum, Emden, Zeebrugge, Dunkerque, Nybro, Easington, St Fergus): the 7-day mean of the
daily energy landed (GWh/d) and the day's value, against the same gas day last year and the
N-year average and band (N = complete prior gas years held, stated), 30 days for a sparkline
and the full gas-year series for the codes in `season`. Shown only when every source is
entitled; part-simulated landings are not added and the read says so. `meta.attribution`
cites ENTSOG TP. Census: 285 paths / 316 operations (+1 / +1 on 284 / 315).

Additive 2026-11-18 (LNG cargo economics, CP-12): three paths, three operations.
`GET /api/lng/freight-routes` (READ) lists the latest version of each route (`route_id`,
`version`, ports, `routing` direct|suez|panama|cape, `distance_nm`, `canal`, `source`, who and
when). `PUT /api/lng/freight-routes/{route_id}` (GOVERNED, PORTFOLIO_WRITE) adds a version.
`POST /api/lng/cargo-economics` (READ) takes `arrival_month`, `product`, up to ten `cargoes`
(FOB with `route_id` or DES with `des_price`; any omitted figure comes from the approved
assumption set, else is missing), optional `terminal_ids` and per-terminal `terminal_inputs`,
and answers per cargo the cost legs, `cost_usd_mmbtu` and `lifting_cost_usd_mmbtu`, terminals
best first (`netback_per_mwh`, `margin_per_mwh`, `margin_usd_mmbtu`, `margin_total`,
`lifting_margin_per_mwh`, slip range, `regas_basis`, `grade`, `assumptions`, legs) or `blocked`
with its reason, plus one comparison `table`. Census: 283 paths / 314 operations.
Additive 2026-11-18 (commercial design basis 2, CP-17: LNG fundamentals): one path, one
operation. `GET /api/fundamentals/lng` (READ; `season` comma-separated codes) returns the EU
total and each GIE ALSI country: send-out today and as a 7-day mean (GWh/d), against the same
gas day last year and the N-year average and band of the 7-day mean (N = complete prior gas
years held, stated), inventory and its share of the declared maximum (DTMI), 30 days for a
sparkline and the full gas-year series for the codes in `season`; `missing` names countries
not held. `meta.attribution` names GIE when provider rows are used. Census: 281 paths / 312
operations (+1 / +1 on 280 / 311).

Additive 2026-11-19 (reviewed public transmission tariffs): three paths, four operations.
`GET /api/route-cost/tariff-entries` (READ) answers `missing[]` (the legs the register cannot
price this gas year, those blocking drawn crossings and enterable first: point, operator,
direction, crossings blocked, `can_be_entered`, `why_not`), `entries[]` (operator, point,
direction, product, firmness, value, unit, currency, validity, the operator's status, source
URL, publication date and location, state `CANDIDATE`/`REVIEWED`/`RETIRED`/`WITHDRAWN`, who
and when), `counts` and `choices` (operators and points from the reference network). `POST
/api/route-cost/tariff-entries` (OPERATOR; 422 with a stable `code` such as
`unit_not_understood`, `currency_mismatch`, `operator_not_at_point`; 409 `published_row_held`
or `entry_exists`). `POST /api/route-cost/tariff-entries/{entry_id}/review` (OPERATOR; 403
`four_eyes` for the recorder). `POST /api/route-cost/tariff-entries/{entry_id}/withdraw`
(OPERATOR; body `{reason}`). Route legs gain `source_kind` (published, reviewed public tariff,
awaiting review, simulated). Census: 276 paths / 309 operations (+3 / +4 on 273 / 305).

Additive 2026-11-18 (LNG terminal tariff register, CP-11): four paths, four operations.
`GET /api/lng/terminal-tariffs` (READ) answers `operators[]` (reuse terms as checked, the
firm's `permission_state` `needs_firm_terms` / `permitted`, reference, who and when),
`tariffs[]` (figure, basis, unit, validity, exclusions, source URL and SHA-256, review state)
and `counts`. `GET /api/lng/terminal-tariffs/price?terminal_id&arrival_month&cargo_mwh[&product]`
(READ) answers `{basis: firm_terms|reviewed_public|candidate_public|missing, charge, currency,
indicative, reason, tariff_ids, excludes}`. `POST /api/lng/terminal-tariffs/{id}/review`
(OPERATOR; 403 `four_eyes` for the recorder). `PUT /api/lng/terminal-tariffs/operators/{op}`
(ADMIN; body `{permitted, reference}`). `GET /api/setup` `terminal_tariffs` gains `reviewed`,
`candidate` and `operators_needing_terms`; `from_operator` now counts register terminals.
Census: 280 paths / 311 operations (+4 / +4 on 276 / 307).

Additive 2026-11-18 (CP-24 role-aware discovery): one path, one operation. `GET
/api/discoveries?function=&lang=&limit=` returns the caller's findings (opportunities they
may read, credit breach or projected breach under a stated price move with its tenor and the
move that reaches the line, mandate breaches) ranked and phrased for one of the caller's own
job functions (403 `function_not_held` otherwise), each with value, input class, evidence,
link and `phrasing` ("template"). Census: 286 paths / 318 operations (+1 / +1 on 285 / 317).

Additive 2026-11-18 (commercial design basis 2, CP-16/CP-23 backend: Spreads, "describe a
strategy"): two paths, two operations, GOVERNED under `/api/research/`. `POST
/api/research/spreads/interpret` (`text` up to 4000 characters, `language`, `model`) returns a
StrategySpec (`version`, `kind` curve|history, `legs` hub/tenor/weight, `unit`, `fx`
forward|spot, `cost` route_tariff from/to hub, `rule`, `lookback_days`, `volume_mwh_per_day`),
`issues` as questions with `choices`, `basis` parser|model|none, `ai` off|used|failed and
`read_as_text` (pasted code is never run). `POST /api/research/spreads/evaluate` (`spec`,
`as_of`) returns the issues or the result: a curve by delivery month (each leg native and
converted with its FX record, gross, route cost with legs, gas years and classes, net, the
weakest input class) or a history through the spread lab with the route cost both ways as
lines. Census: 276 paths / 307 operations. `GET /api/research/spreads/board` (`hubs` comma list, `as_of`; added
2026-11-19) returns the board Research → Spreads opens on: locational rows against TTF (front
month and day-ahead: legs native and in EUR/MWh, gross, the cheapest route's cost and net in the
direction gas would move or the missing legs named, the one-year percentile and the last 30
closes), time spreads per hub (DA − MA, M+1 − M+2, Win − Sum with the storage carry where the
assumption set holds it, Cal − Cal) and cross-commodity rows (Henry Hub against TTF delivered
through the cargo chain on the desk's standard cargo; the clean spark or why it is not held),
each with the spec that opens it.

Additive 2026-11-18 (commercial design basis 2, CP-02: instrument catalogue): one path, one
operation. `GET /api/market/instruments` (READ, like every `/api/market/` read) returns the
caller's entitled daily price series as hub → product kind (spot, rolling, month, quarter,
season, year, other) → tenor, each instrument with a stable id (`TTF:M+1`, `NBP:Jan-27`), the
hub's native unit and currency, the stored unit, a source class (`sourced`, `indicative`,
`simulated`), its best source and the others, observations held, `thin` under 30 days, the
delivery window of an absolute tenor and the last as-of. `/api/research/spread-series` is
unchanged and stays until its last client is gone. Census: 273 paths / 304 operations.
Additive 2026-11-18 (commercial design basis 2, CP-04: storage fundamentals): one path, one
operation. `GET /api/fundamentals/storage` (READ; `region` `eu`|`nwe`, `season` and `focus`
comma-separated codes) returns the region and each of its countries against their own
history: fill, stock, working capacity, day/week change, the same gas day last year, the
N-year average and band (N = complete prior gas years held, stated; the band from the last
five), injection, withdrawal, the 7-day net rate, the EU target where it applies, 30 days for
a sparkline, the full gas-year series for the codes in `season`; `missing` names countries
not held with the reason; `reconciliation` compares the EU total with its countries.
`meta.attribution` names GIE when provider rows are used. Census: 273 paths / 304 operations
(+1 / +1 on 272 / 303).

Additive 2026-11-18 (commercial design basis 2, CP-08: opportunities): seven paths, nine
operations. `GET /api/opportunities` (two ranked lanes, the watching and cannot-evaluate
groups, counts, the readiness checklist; cursor pagination per bucket, `409 cursor_expired`
after a newer evaluation), `GET /api/opportunities/{opportunity_id}` (claim, legs that sum to
the headline, assumptions, falsifiers, sensitivity, checks, data-quality class, snapshot
record, versions), `PUT /api/opportunities/{opportunity_id}/state` (the caller's own `watch`,
`unwatch`, `dismiss` with a reason, `restore`), `POST /api/opportunities/{opportunity_id}/case`
(a decision case through the existing flow, evidence `opportunity:<id>@v<n>` with the
snapshot id; `409 already_converted`), `GET/POST /api/opportunities/evaluations` (last runs;
run one now), `GET/PUT /api/opportunities/settings` (thresholds, decision L5 defaults) and
`GET /api/opportunities/statistics` (dismissal reasons and case precision per type). Figures
are `{value, unit, currency}` with decimals as text. Census: 269 paths / 299 operations.

Additive 2026-11-17 (commercial design basis 2, CP-07: assumption sets, firm marks, valuation
snapshots): six paths, eight operations. `GET/POST /api/assumption-sets` (list with the key
catalogue; create a set for the organisation or one book), `GET /api/assumption-sets/{set_id}`
(versions with values, who set and who approved), `POST /api/assumption-sets/{set_id}/versions`
(a draft holding the full list of typed values: key, value, unit, currency, range, note),
`POST /api/assumption-sets/{set_id}/versions/{version}/approve` (REVIEWER held itself, never the
author; the earlier approved version is retired), `GET/PUT /api/market/firm-marks` (the firm's
own marks per hub and delivery period in the native unit; every row carries `input_class`
`firm_mark`) and `GET /api/market/valuation-snapshots/{snapshot_id}` (every input one
evaluation read, with class, source, reference and as-of; unentitled values withheld). Reads
need portfolio read and sit inside the commercial boundary; writes are audited without values.
Census: 262 paths / 290 operations.

Additive 2026-11-19 (My gas day): `GET /api/desk/today` appends `rows[5]` (`gas_day`: per hub
for today and tomorrow, IN and OUT lines, net to clear in the hub's unit, the balancing band,
cut-offs with their basis, the cost of leaving it open at the assumption set's cash-out
premium or discount, prompt trades done today, delegated parts) and `rows[6]` (`checklist`:
per source the nomination status as recorded, agent, expected against nominated with the
tolerance, LNG terminal steps, each open step's deadline and urgency); earlier rows keep their
positions. `POST /api/desk/gas-day/status` (WRITE, `gas_day.record`) records a step's status
by hand for a line of the caller's own gas day (labelled `origin: manual`, audited; 404 for a
line outside his scope, 422 for an unknown step, status or day). Census: 274 paths /
306 operations (+1 / +1 on 273 / 305).

Added 2026-11-15: `GET /api/desk/today` returns the Today screen's four rows (key figures,
what changed, the book against the market, fundamentals) computed once on the server from
the reads the desk brief uses, with the caller's licences and books applied. It is a READ
under the new commercial `/api/desk/` prefix (platform administration alone does not
grant it), writes nothing and calls no model. Every figure carries unit, as-of time and
freshness state; risk figures carry a method note. The web client has a typed
`api.deskToday()`; no SDK method yet. Census: 244 paths / 264 operations.

Additive 2026-11-17 (comparable prices, design basis 2 CP-01): two paths, two operations,
both READ under `/api/market/`. `GET /api/market/fx-forward` (`base`, `quote`,
`product` or `value_date`, `as_of`) returns a rate with `method` ("derived: covered interest
parity", "licensed" or the ECB spot), `label`, `input_class`, `value_date`, the spot rate and
its date, the benchmark fixings with day counts, and `tolerance`; 422 `beyond_horizon` beyond
24 months without licensed forwards, 422 `fx_not_convertible` naming the missing rate.
`POST /api/market/normalise` (`to_unit`, `values[]` and/or one `series`) returns each value in
the target unit with `native`, `simulated`, `normalisation` (factors, heating value, FX) and
`tolerance`, or `refused` with the reason. `POST /api/research/spread-analysis` gains an optional `unit` and converts legs
quoted in different units or currencies (the "different units" refusal is gone; a leg whose FX
is not held is refused with the missing rate named), and its response gains `normalisation`.
`/api/research/spread-series` is unchanged. No field changes meaning. Census: 258 paths /
284 operations.
Additive 2026-11-18 (first-run setup): one path, two operations. `GET /api/setup` (ADMIN)
answers the welcome flow's pages (`catalogue.steps[].items[]`: source, how the product connects
to it today, credential provider, key registration URL, licence family, import tools), the
installation's `state` (`not_started` / `in_progress` / `completed` / `dismissed`, step,
`configured_by`), `show_on_sign_in`, `key_storage_ready`, `ai_external_enabled` and
`terminal_tariffs` (LNG terminal tariffs held and their source). `PUT /api/setup` (ADMIN) records
`{status, step}`, audited `setup.state`. No key or approval passes through it. Census: 257 paths
/ 284 operations.

Additive 2026-11-17 (local accounts and SSO pre-provisioning): four paths, six operations.
`POST /api/auth/login` (PUBLIC: user name or e-mail and password; 401 `invalid_credentials`
for every refusal; a temporary password answers `password_change_required` with a single-use
`change_token` instead of a session), `POST /api/auth/password-change` (PUBLIC: the change
token and the new password; opens the session), `POST /api/me/password` (READ: own password,
current one required; other sessions end), `POST /api/access/users` (ADMIN: `kind` `local`
returns `one_time_password` once, `kind` `sso` creates an `INVITED` principal),
`POST /api/access/users/{principal_id}/reset-password` (ADMIN) and `DELETE
/api/access/users/{principal_id}` (ADMIN; 409 `user_has_history` for anyone who signed in or
acted). `GET /api/auth/status` gains `local_login`; `GET /api/access/users` rows gain
`job_functions`, `office`, `account_kind`, `account_state` and `local_password` (safe facts,
never a hash), and its `meta` gains `account_options`; `PATCH /api/access/users/{id}` answers
the same row shape plus the earlier fields and refuses (409 `last_administrator`) to disable,
lock or demote the last active administrator. No field changes meaning. Census: 256 paths /
282 operations.

Additive 2026-11-17 (public-source approval revocation): no new path, one operation.
`DELETE /api/sources/{source_id}/approve` (ADMIN, same route permission as the approval), body
`{reason, confirm}` (`confirm` must be true, else 422 `confirmation_required`), withdraws an
approval: the source's `approval.state` returns to `not_approved`, the ingestion gate refuses
its next read with `source_not_approved`, nothing stored is deleted, and the audit event
`source.approval` (action `revoke_public_source_approval`) records who, when and why.
Idempotent. Census: 251 paths / 273 operations.

Additive 2026-11-17 (public-source approval): one path, one operation under the existing
`/api/sources/` operator prefix: `POST /api/sources/{source_id}/approve` (ADMIN), body
`{reason, accept_terms}`. An administrator approves ENTSOG or GIE for the firm; the call
records who, when, why and which terms summary was accepted, writes the audit event
`source.approval` and runs the bounded live validation the ingestion gate requires.
`GET /api/sources` rows gain an optional `approval` object (class, state, reason, terms,
approver) and freshness-contract rows of a held-back source gain `blocked_reason` and
`blocked_action`. No field changes meaning. Census: 251 paths / 272 operations.

Additive 2026-11-17 (report library): one path, three operations. `DELETE` and `PATCH`
`/api/reports/market/{report_id}` (delete a stored report; rename it) and
`POST /api/reports/market/bulk-delete` (GOVERNED; only the principal who generated a report or
an administrator, checked per report and audited as `report.manage`). Report summaries gain
`question`, `generated_by` and `edited_by`; report metadata gains `answer`. No field changes
meaning. Census: 252 paths / 276 operations.

Additive 2026-11-16 (answer bar): one path, one operation. `POST /api/analysis/ask` (READ,
like `POST /api/analysis/explain` and `POST /api/analysis/brief`) answers a question typed
into the search bar from the caller's Today facts, each with its source and as-of; book and
limit facts only for a caller with `portfolio.read`; a model answer only after the
ai_authority re-check and the `ai_style` answer checks, audited as `ai.ask`. `GET
/api/analysis/ontology` gains an additive `units` object (the units authority's factors).
Census: 250 paths / 271 operations.

Additive 2026-11-16 (market reports): five paths, six operations under the existing
commercial `/api/reports/` prefix: `GET /api/reports/catalogue` (READ), `POST
/api/reports/plan` (GOVERNED: may call the model), `POST /api/reports/market` (GOVERNED:
stores a record, may call the model), `GET /api/reports/market` and `GET
/api/reports/market/{report_id}` (READ, JSON envelope) and `GET
/api/reports/market/{report_id}/html` (READ, `text/html`, one self-contained file). Reading a
stored report re-checks the reader's licences and books. SDK: `eurogas_nexus_sdk.reports`.
Census: 249 paths / 270 operations.

Additive 2026-11-15 (NUM-05): risk responses gain an optional `method` (credit exposure and
mandate usage rows, P&L snapshots, the live summary) or `methods` (position ladder) object.
No field changes meaning and no number changes.

Added 2026-11-06: `POST /api/portfolio/desk-replay` reconciles one book, hub and gas day from
caller-supplied, authorised evidence and compares responses to a revised outage (#48-#50).
It is read-only compute (no persistence), sits under the commercial `/api/portfolio/` prefix,
returns an input fingerprint and the frozen inputs for replay, and has a Python SDK method
(`portfolio.replay_desk_evidence`) and a Decision Center panel. Responses are assessed, never
executed. Census: 243 paths / 263 operations.

Added 2026-11-05: `POST /api/market/nwe-balance` adds caller-declared weather scenarios
alongside the existing GET. It has the governed permission floor, no persistence,
an input hash and a Python SDK method. See the
[functional engine plan](../engineering/FUNCTIONAL_ENGINE_IMPROVEMENTS.md).
Census after the merge: 231 paths / 249 operations; earlier dated census entries remain historical.

The functional branch exposes 240 paths and 260 operations, including the governed task and model operations.

The public `/api` surface is a shared product contract consumed by five
surfaces: Web, Python SDK, CLI, Windows/Linux desktop shells, and the
bilingual operator documentation. Every consumer is a thin client of the same
contract, so the contract changes only through a deliberate, tested process.

This document is the single policy for evolving that contract. It closes
roadmap problem D (no evolution strategy for the stable unversioned `/api` and
five hand-maintained surfaces).

## Principles

1. **Stable unversioned `/api`.** The public surface keeps the unversioned
   `/api` prefix. Operator-only and development-only routes keep their
   profile-gated `/api/internal` and `/api/dev` prefixes. No `/v1` or
   `/api/v1` aliases are ever served.
2. **Additive-only by default.** New endpoints and new optional response
   fields are the normal evolution path. Existing paths, parameters, and
   field meanings do not change silently.
3. **Breaking changes are a major event.** Removing, renaming, or re-typing a
   path, parameter, or response field requires a written migration plan
   (deprecate → dual-run → remove across at least one release) and an
   reviewed public ExecPlan. Follow `docs/engineering/RFC_PROCESS.md` when the
   change introduces a new normative contract. There is no in-place breaking
   change.
4. **Deprecation is explicit.** A deprecated path or field must carry
   `deprecated=True` in its OpenAPI operation, a `meta.warnings` entry in its
   runtime envelope, and a removal date in this document's deprecation table.
   Deprecated surfaces remain functional until removal.
5. **Backend is the only owner of normalization.** Derived fields (FX
   conversion, tenor, hub, spreads) are computed by the backend; clients must
   consume them instead of re-implementing domain logic.

## Compatibility Gates

These tests fail CI loudly on contract drift:

| Gate | File | What it pins |
|---|---|---|
| Surface stability | `tests/contract/test_api_surface_stability.py` | the exact set of public paths; no `/v1` aliases; declared prefixes only |
| Documented counts | `tests/contract/test_architecture_alignment.py` | alembic head, table count, documented route count |
| SDK parity | `tests/contract/test_sdk_backend_parity.py` | SDK DTOs versus backend payload contracts |
| Realtime contracts | `tests/contract/test_realtime_contracts.py` | SSE/streaming semantics, no Kafka/Redis tokens |
| Validation consistency | `tests/contract/test_validation_consistency.py` | the canonical validation commands in documentation |

## Change Process

1. Record a public ExecPlan using `docs/engineering/EXECPLAN_TEMPLATE.md`,
   listing API impact and rollback; update its index entry.
2. For a new path: add it to `PINNED_PUBLIC_PATHS` in
   `tests/contract/test_api_surface_stability.py`, update the documented
   route count (`RELEASE_READINESS.md` and the
   `test_architecture_alignment.py` assertion) in the same change.
3. For a deprecated path: mark it `deprecated` in the router, add the
   envelope warning, and record it in the deprecation table below.
4. For a refused field: keep it declared in the model, refuse a non-empty value
   with a stable `422` code that names every offending field, record it in the
   refused-field table above, and remove it from every client request builder and
   from the client's request DTO in the same change.
5. Add API, SDK, and contract tests before the implementation is considered
   complete.
6. Run the full validation command set from `CONTRIBUTING.md`.

## Declared Additive Paths

| Path | Declared in | Contract |
|---|---|---|
| `POST /api/optimization/portfolio-network` | Accepted release contract | DB-only `RUNTIME_DECISION`; accepts decision metadata only, never client network/tariff/capacity/price facts |
| `POST /api/optimization/storage-dispatch` | Accepted release contract | assessment-only storage dispatch; RUNTIME_DECISION composes PostgreSQL masters/observations |
| `POST /api/optimization/nomination-window` | Accepted release contract | assessment-only nomination windows; RUNTIME_DECISION loads DB window masters; no submission action |
| `GET /api/optimization/nomination-windows` | Desk clock read (Architecture V2 day view) | READ-floor read of the declared `nomination_window_masters` for one gas day, with the declared clock times and the UTC instants they resolve to on that gas day. It exposes a declaration, not an assessment: no market material, no schedule, no submission. A runtime DB that is not configured answers an empty list with `meta.missing_inputs`, and a configured DB that declares no active master answers a measured zero carrying `NOMINATION_WINDOWS_MISSING`, so "no window closes today" cannot be confused with "the windows were not read" |
| `GET/POST /api/strategies` | CR-03 | versioned strategy research identities; writes are policy-gated and research-only |
| `GET/POST /api/strategies/{strategy_id}/versions` | CR-03 | immutable semantic strategy versions; POST creates a new DRAFT only |
| `PATCH /api/strategies/{strategy_id}/metadata` | CR-05 | update editable strategy metadata; identity/history immutable |
| `PUT /api/strategy-versions/{strategy_version_id}/draft` | CR-05 | replace a DRAFT definition; FROZEN versions are immutable |
| `GET /api/strategy-versions/{strategy_version_id}` | CR-03 | read one immutable version and its `definition_json`/`content_hash` |
| `POST /api/strategy-versions/{strategy_version_id}/freeze` | CR-03 | DRAFT -> FROZEN only; frozen versions are immutable |
| `POST /api/strategy-versions/{strategy_version_id}/fork` | CR-03 | FROZEN -> new DRAFT with `parent_version_id`; never mutates the source |
| `GET/POST /api/strategy-runs` | CR-03 | reproducible run registry; only `EVALUATION` is executable in CR-03 |
| `GET /api/strategy-runs/{run_id}` | CR-03 | read one run with full manifest/provenance |
| `POST /api/strategy-runs` (`run_type=BACKTEST`) | CR-04 | as-of historical evaluation; requires period, frozen version, explicit assumptions |
| `GET /api/strategy-runs/{run_id}/events` | CR-04 | normalized persisted decision events |
| `GET /api/strategy-runs/{run_id}/series` | CR-04 | persisted gross/net cumulative PnL and exposure series |
| `GET /api/strategy-runs/{run_id}/attribution` | CR-04 | persisted market-bucket/cost attribution |
| `GET/POST /api/backtest-experiments` | CR-04 | lightweight SINGLE_RUN experiment grouping |
| `GET /api/backtest-experiments/{experiment_id}` | CR-04 | read one experiment and its run ids |
| `GET/POST /api/shadow-monitors` | CR-06 | scheduled non-executing shadow research monitors |
| `GET/POST /api/shadow-monitors/{id}/pause|resume|retire` | CR-06 | monitor lifecycle changes; history and open alerts preserved |
| `GET /api/shadow-monitors/{id}/evaluations` | CR-06 | immutable evaluation history |
| `GET /api/shadow-evaluations/{id}` | CR-06 | evaluation evidence/result/risk checks |
| `GET /api/shadow-monitors/{id}/drift` | CR-06 | interpretable drift snapshots against explicit baseline |
| `GET /api/shadow-alerts`, `POST /api/shadow-alerts/{id}/acknowledge` | CR-06 | deduplicated alert lifecycle |
| `GET /api/shadow-runtime/status` | CR-06 | scheduler heartbeat/health |
| `POST /api/dev/auth/login` | UX-01 authentication-first entry | development-profile-only credential login mounted with `include_dev`; absent from internal/release; validates operator-configured dev credentials server-side and issues the same backend session as OIDC; never creates or elevates a principal |
| `GET /api/data-products` | Architecture V2 Wave 4 (Unified Data Platform) | READ-floor declaration of the Data Product catalogue: product ids, business names, availability state, time basis, declared source/entitlement families and serving surfaces, plus a per-principal entitlement verdict and a freshness/provenance summary. No API key, secret value, scheduler internal or retry trace is returned; a product the caller is not entitled to is reported `restricted` with no provenance block rather than omitted or shown as zero |
| `GET/POST /api/analysis-snapshots` | Architecture V2 Wave 4 (Unified Data Platform) | `POST` (GOVERNED, ANALYST floor) records an Analysis Snapshot descriptor from the current Active Context; `GET` lists recent descriptors. `GET` keeps the READ floor because a descriptor is lineage/provenance metadata with no commercial values; every value it references stays behind its own commercial endpoint |
| `GET /api/analysis-snapshots/{snapshot_id}` | Architecture V2 Wave 4 (Unified Data Platform) | read one Analysis Snapshot by its reproducibility reference; 404 when the reference is unknown |
| `GET/POST /api/decision-cases` | Architecture V2 Wave 6 (Decision Case) | `POST` (GOVERNED, ANALYST floor) opens a case in the current Active Context; `GET` lists recent cases as compact summaries. A Decision Case is evidence and rationale, never execution approval: no order entry, routing, nomination or settlement semantics exist on this surface |
| `GET /api/decision-cases/{case_id}` | Architecture V2 Wave 6 | read one case with its assumptions, alternatives, evidence, AI findings and decision records |
| `POST /api/decision-cases/{case_id}/evidence` | Architecture V2 Wave 6 | attach one evidence reference (GOVERNED); the first evidence moves the case from DRAFT to OPEN. References are deduplicated and carry the snapshot id that makes the decision reproducible |
| `POST /api/decision-cases/{case_id}/decisions` | Architecture V2 Wave 6 | reviewer-gated (REVIEW) recording of the human decision. The actor is the authenticated identity, never a body field. A case without evidence is refused with 409 `case_not_decidable` and its blocker codes |
| `POST /api/decision-cases/{case_id}/reopen` | Architecture V2 Wave 6 | reviewer-gated (REVIEW) reopen; every record is preserved, nothing is deleted |
| `GET /api/projections/market-context` | Architecture V2 Wave 5 (application projections) | READ-floor coherent read model over market observations, normalized quotes, intraday opportunities, spreads and monitoring alerts on one explicit time basis and as-of instant, with a per-slice freshness summary. Commercial-boundary paths: a platform-administration identity without a commercial role is refused |
| `GET /api/projections/portfolio-snapshot` | Architecture V2 Wave 5 | READ-floor coherent portfolio read model (summary, screen orders, PnL snapshots, resource context) with per-slice freshness |
| `GET /api/projections/review-context` | Architecture V2 Wave 5 | READ-floor coherent review read model (evidence, decisions, warnings) for the review workflow |
| `GET /api/projections/scenario-context` | Architecture V2 Wave 5 | GOVERNED-floor (ANALYST) scenario and route-economics read model. The projection keeps the floor of the endpoint it composes, so it cannot widen access; it exists to remove client-side joins, not to relax authorisation |
| `GET /api/jobs` | Architecture V2 Wave 8 (unified jobs) | READ-floor list of tracked long-running operations (ingestion, dataset build, optimisation, backtest, report, agent run, snapshot) newest first, filterable by status, kind and principal. Job telemetry only: no secret, no stack trace, no licensed payload |
| `GET /api/jobs/{job_id}` | Architecture V2 Wave 8 | read one job with its progress, output references, correlation id and, on failure, the stable error code from the product taxonomy; 404 when the job is not tracked |
| `POST /api/jobs/{job_id}/cancel` | Architecture V2 Wave 8 | GOVERNED-floor (ANALYST) cancellation of a cancellable, non-terminal job. A finished job answers 409 `job_already_finished` and a protected one 409 `job_not_cancellable`, so the surface never claims to have stopped work it did not stop |
| `POST /api/research/cash-valuation` | Shared cash valuation capability (2026-09-30) | Sandbox-only (GOVERNED, ANALYST floor inside the commercial boundary) adaptation of the one shared cash-flow engine: caller-supplied canonical `concept:value` references (never resolved or entitled — `meta.references_verified: false`), exact decimal strings for every amount/FX rate/discount factor (JSON numbers refused), ISO dates, and Decimals serialized as exact strings. Refusals are typed (`422 cash_valuation_input_invalid` for wire-syntax violations, `422 cash_valuation_refused` with the engine's stable codes). No persistence, provider, audit record, trade, nomination or settlement; `meta.customer_approval` is always `false`. See [CASH_VALUATION_CAPABILITY.md](CASH_VALUATION_CAPABILITY.md) |
| `GET /api/route-cost/upstream-contracts/{contract_id}/revisions` | Contract revision integration (2026-10-01) | GOVERNED-floor (ANALYST) bounded history of one contract's captured immutable economic revisions, inside the commercial boundary, oldest revision number first (`limit` ≤ 200 with `offset`). Every returned row is verified (reviewed capture origin, stored hash, canonical decode, contract id and schema version) before it is served; an unknown contract is 404 `upstream_contract_not_found` while an existing contract with nothing captured is an empty page with `revision_count` 0 and an explicit warning. Reading captures nothing and re-attributes nothing. Honest evidence only: a capture is not a complete history, and the stored economics carry `payment_terms: null` — no payment date, discount factor or valuation is derived or implied |
| `GET /api/route-cost/upstream-contracts/{contract_id}/revisions/{contract_revision_id}` | Contract revision integration (2026-10-01) | GOVERNED-floor (ANALYST) read of one verified captured revision, explicitly scoped to `contract_id`: a revision id from another contract answers the same 404 `contract_revision_not_found` as an unknown id. An integrity-verification failure is a structured 409 carrying the repository's stable code and a fixed message only (no stored row content, driver text or SQL). The payload preserves capture origin, schema version, content hash, capture instant, original recorder and raw operator notes |
| `GET /api/market/products` | Trader desk conventions (2026-10-30) | READ-floor pure calendar resolution of European gas product codes (`WD`, `DA`, `WE`, `BOM`, `M+n`, `Q+n`, `S+n`, `GY+n`, `Cal+n` and absolute `Nov-26`, `Q1-27`, `Sum-27`, `Win-27`, `GY-27`, `Cal-27`) against `trade_date` (default today UTC) into first/last gas day, UTC delivery interval and DST-true delivery hours on the `EU-CAM-UTC-2025` calendar. Without `code` it returns the standard desk strip. Unknown or fully delivered codes answer 422 `unknown_product_code`. No DB read; exchange holidays are not applied |
| `GET /api/market/price-conversion` | Trader desk conventions (2026-10-30) | READ-floor conversion of one price between EUR/MWh, GBP/MWh, USD/MWh, GBp/th, USD/MMBtu, EUR/GJ and EUR/kWh on International Table BTU factors. FX comes from a named benchmark fix: `fx_source` `ECB` (default, public), `WMR` (WM/Reuters 4pm London, LSEG) or `BFIX` (Bloomberg), optional `fx_fixing` id, on `fx_date` or as the per-pair arithmetic mean over `fx_average_from`..`fx_average_to` (LNG pricing-period practice), latest fix otherwise; USD-quoted pairs are crossed to EUR base. Licensed WMR/BFIX rows are operator-imported only (`scripts/ops/import_fx_fixings.py`) and row-entitlement filtered, so an unentitled principal gets no licensed rate. Explicit `gbp_per_eur`/`usd_per_eur` override per currency. The fix, value dates and count used are echoed; a missing rate yields `null` per target (or 422 `fx_rate_unavailable` for an explicit `to_unit`); unknown source/fixing is 422 `unknown_fx_fixing`. No rate is ever assumed. `GET /api/market/fx` is now row-entitlement filtered for the same reason |
| `GET /api/market/interest-rates` | Contract financing benchmarks (2026-10-30) | READ-floor, entitlement-filtered overnight benchmark fixings (SONIA from the Bank of England, €STR from the ECB, SOFR from the NY Fed) newest first per benchmark (`benchmark`, `limit` ≤ 400), plus the benchmark catalogue (currency, day count, administrator, required attribution). Rows come only from `scripts/ops/ingest_interest_rates.py`; nothing is interpolated. 422 `unknown_benchmark` |
| `GET /api/market/financing-rate` | Contract financing benchmarks (2026-10-30) | READ-floor resolution of a contract financing rate = benchmark fixing with the latest value date on or before `as_of` + `spread_bps`, returned on the benchmark's own day count and restated on ACT/365F (the basis the early-cash term accrues on), with fixing date, staleness and source. A fixing older than `max_staleness_days` (default 7) is refused with 422 `financing_rate_unavailable` instead of using a stale rate |
| `GET /api/storage/target-trajectory` | Trader desk conventions (2026-10-30) | READ-floor, entitlement-filtered filling trajectory of one AGSI code (default `EU`) against a configurable storage target (`target_pct` default 90, `deviation_pp` default 0, window 1 Oct – 1 Dec): fill, gap, required net injection per day to window opening and deadline, recent net-injection pace and projected deadline fill with status `target_met`/`on_track`/`behind`/`unreachable`/`withdrawal_season`. No rows for the code answer 200 with `data: null` and a `storage_series_unavailable` warning (a data state, like other reads); rows that cannot support a trajectory answer 422 `storage_series_unavailable`. Backward-looking pace only; not a forecast or regulatory advice |
| `GET /api/desk/today` | Today read (UX-05, 2026-11-15) | READ-floor, commercial `/api/desk/` prefix. Four rows: `key_figures` (front-month close and day change per hub, net position today and front month, tightest limit headroom), `changes` (open alerts with counts equal to the alert centre, outages from the ticker's and map's service with unlocated assets counted), `book` (per hub position, mark and day P&L change), `fundamentals` (NW Europe storage fill and balance). Every figure: `unit`, `as_of`, `state` (current/late/stale/never/manual), `simulated`; `stale_figures` names each late or stale one. An empty section carries `empty` {code, reason, action}. Licensed prices by data scope, legs by book scope, limits rows only to callers who see every book behind them; the balance only when every source behind it is licensed. No write, no model call |
| `GET /api/weather/forecasts` | Declared additive ECMWF research read (2026-10-28) | Authenticated, entitlement-filtered point-in-time ECMWF grid forecast readings. The caller supplies non-empty `series_ids`, `entity_ids`, `prediction_origin`, `valid_from` and `valid_to` as aware ISO datetimes, plus optional `limit` (1–256, default 100); `valid_to` must follow `valid_from`. Every row exposes `issued_at_utc`, `valid_at_utc`, `available_at_utc`, degC temperature, requested/grid coordinates and GRIB/record SHA-256 values; the API performs no interval aggregation or station inference. Requires a live ECMWF provider certification and ECMWF source entitlement: a missing, expired or uncertified record answers 503 `forecast_source_unavailable`; storage failures answer 503 without inventing values. `meta.research_only` is true and `HUMAN_REVIEW_REQUIRED` is warned |
| `POST /api/weather/degree-days` | Declared additive ECMWF research calculation (2026-10-28) | Authenticated, entitlement-filtered degree-day calculation from persisted ECMWF forecasts. The caller must declare 1–64 unique point bindings (`point_id`, `series_id`, `entity_id`, `location_id`, `region`, exact decimal `weight`), each weight in `[0, 1]` with the set summing exactly to `1`; 1–7 unique gas days; an aware `prediction_origin`; heating and cooling bases; an approved `gas_day_calendar`; `max_hold_minutes` (1–10080); and `min_covered_fraction` (`0`–`1`). The bridge uses `LEFT_HOLD_INSTANT` with the declared hold as its maximum gap, reports the selected forecast vintage, feature-policy hash and coverage diagnostics, and reports nullable daily values with `MISSING_COVERAGE_NULL` rather than zero-filling; `NOT_READY` means no bridge intervals were available. Same certification and entitlement gates; no persistence, forecast invention, trade, nomination or settlement |

## Additive Field Declarations

Field-level additions to existing paths. They introduce no new path, relax no
floor and change no status code; a caller that does not send the optional field
keeps its previous behaviour.

| Path | Field | Contract |
|---|---|---|
| `POST /api/route-cost/recommend` | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4: the reproducibility reference a produced recommendation cites. Verified against persisted Analysis Snapshots before the run — `422 analysis_snapshot_not_found` when the reference is unknown, `503 runtime_db_not_configured` when no runtime database can verify it |
| `POST /api/route-cost/resource-pool/optimize` | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4 scope extended to this run path in the Wave 5 follow-up: same verification and the same refusal codes as the recommendation path. The field is absent from `data` when the caller cites no snapshot, so such a caller's payload is unchanged |
| `POST /api/strategy-runs` (`run_type=BACKTEST`) | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4 scope extended to the strategy backtest run: verified against persisted Analysis Snapshots before the run (no run row and no job are created when it is refused), echoed on the response, and absent when the caller cites nothing |
| `POST /api/analysis/query` | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4 scope extended to the analysis (AI evidence) path: verified before the input snapshot is loaded and before any provider call, so an unverifiable citation can never be paid for with an external request. Same refusal codes as the other paths; the field is absent from `data` when the caller cites nothing, and the citation is part of the persisted analysis record |
| `POST /api/reports/portfolio` | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4 scope extended to the portfolio report: verified before the run, echoed on the report, and recorded on the tracked `REPORT` job as the snapshot the report was computed against (an empty reference when the caller cited nothing). The stored report record keeps its sections and source references; it has no column for a cited reference, which is recorded here rather than implied |
| `GET /api/optimization/nomination-windows` | `next_gas_day`, `next_opens_at_utc`, `next_closes_at_utc` (per window row, optional in the sense that a client may ignore them) | The day view follow-up, and the same family's own field: window masters are daily rules, so once the requested gas day's window has closed the actionable instant is the *following* day's occurrence of the same clock. Both occurrences are resolved on the gas-day calendar by the route rather than by a client adding a day to a clock, and a JSON client that ignores the three fields sees exactly the previous payload |
| `GET /api/decision-cases/{case_id}` | `pack` (object, additive) | The decision pack: the same case composed for the human who signs it — context, evidence with each cited snapshot's resolvability **measured** (`true`/`false`/`null`, the last meaning the reference cites none), assumptions, alternatives, AI findings, warnings, the recorded decision, the case's audit trail (its acts are recorded under `decision_case:<case_id>`), the pack's own blockers beside the case's, `signable`, the platform's statement that it holds no signature, and a canonical `content_hash` with its basis. It rides on this read rather than a new path because it *is* this resource, not a second answer about it; a client that ignores it sees exactly the previous payload. Reading a case already needs the runtime database, so nothing new is refused |
| `GET /api/route-cost/upstream-contracts` | `edit_token` (per contract row, additive) | The bounded stale-edit precondition (2026-10-02): an opaque token over the whole persisted contract row — identity, economics, display metadata, raw operator notes and the updated instant — not the captured revision number and not a signature. A client that ignores it sees exactly the previous payload; a client that edits a row sends it back as `expected_edit_token`. The other consumers of the same repository read (projections, resource-pool composition, agent context) are left at their previous shape |
| `POST /api/route-cost/upstream-contracts` | `expected_edit_token` (request, optional) and `edit_token` (response) | The same precondition. Omitted or null means create-only; a supplied token that no longer matches the locked row, or that names no stored row, is refused `409 contract_edit_conflict`; a token that is not this API's `sha256:` token shape is refused `409 contract_edit_token_malformed`. Both refusals are sanitized, change nothing, and the response keeps every existing field plus `edit_token`/`write_outcome`/`latest_revision` |
| `POST /api/route-cost/upstream-contracts` | `payment_terms` (request, optional) | S2b declared payment terms: a strict canonical `contract-payment-terms/v1` document (validated by the shared domain decoder, not Pydantic, and stored as its own canonical JSON) or an explicit `null`. **Omitted preserves** the stored declaration — presence is read from `model_fields_set`, so a client that does not know the field (every existing client) never erases it; explicit `null` clears it. The nested contents are never echoed: a refused declaration answers `422` with the decoder's own stable, sanitized code in `detail.error` and reason, and nothing is written. A declared change is captured as an explicit v2 revision |
| `GET /api/route-cost/upstream-contracts` | `payment_terms` (per contract row, additive) | The additive public read of the same declaration: the strictly decoded canonical document, or `null` for "not stated". A stored declaration that fails canonical verification refuses the read with `409 contract_payment_terms_corrupt` and a fixed message rather than serving corruption as absent. No date is resolved and no valuation runs |
| `GET /api/portfolio/credit-exposure`, `GET /api/portfolio/mandate-usage` | `method` (per row, JSON only) | NUM-05 method note from `domain/risk/method_notes.py`: `key`, `summary`, `includes`, `excludes`, `params`, `inputs_as_of`, `i18n` keys, `review_status`. CSV/XLSX/PDF downloads keep their columns. No number changes |
| `GET /api/portfolio/position-ladder` | `methods` (object keyed by figure: `mark_to_market`, `var_95_1d`, `tenor_exposure`, `scenario` when shocks are given) | Same note shape; the VaR note states its observation count and the closes' date range |
| `GET /api/portfolio/pnl-snapshots`, `GET /api/portfolio/live-summary` | `method` (per snapshot; on the summary) | Imported P&L is not recomputed; the note says so and names the valuation time |
| `GET /api/route-cost/upstream-contracts/{contract_id}/revisions` and `.../revisions/{contract_revision_id}` | `snapshot.payment_terms` (additive; `schema_version` may be `upstream-contract-revision/v2`) | The captured declaration is served read-only from the verified immutable revision for revisions captured while terms were declared; v1 revisions keep `payment_terms: null` and their pinned bytes/hash. The evidence warnings state that a capture neither asserts when terms applied nor resolves a payment date |

## Refused Request Fields

A declared field the pipeline never reads is a claim the platform cannot honour: a caller that fills
it in receives an unmodified result while believing their selection was applied. Such a field is
**refused with a stable error code instead of ignored**, is listed here, and stays declared (removing
it would turn an explicit refusal into a silent drop for a caller that still sends it). The refusal is
raised before the run is loaded, tracked or paid for, and an empty value is never an offence. Every
refusal code below is catalogued in the product error taxonomy, so a client classifies it (family,
severity, recoverability) rather than reading a raw status code.

| Path | Field | Contract |
|---|---|---|
| `POST /api/analysis/query` | `selected_terms`, `selected_assets`, `selected_contracts`, `include_sections` | `422 analysis_selection_not_supported`, naming every non-empty field in `detail.fields`. The deterministic builders read the snapshot, the task and the question, so a term, asset, contract or section selection describes work that does not happen. Evidence references belong in `question`, which is the prompt the platform records and the provider receives |
| `POST /api/reports/portfolio` | `portfolio_id`, `selected_resources`, `selected_contracts`, `selected_strategies` | same code and the same `detail.fields` contract: a report is computed from the whole entitled snapshot, so a portfolio/resource/contract/strategy selection would be a scope the caller believed was applied |
| `POST /api/agent/research` | `strategy_ir` | `422 strategy_ir_not_accepted`: the orchestrator never read it, so a caller could believe its own specification had been run while the pipeline validated a candidate of its own. The strategy registry is the path that owns a specification |
| `POST /api/agent/research` | `profile` (validated, not refused) | `422 agent_profile_unknown` when the profile is not one the platform declares; a declared profile that never reached all of its stages is reported with `PROFILE_STAGES_NOT_REACHED:<stage,…>` rather than refused, because stopping short is often the honest outcome |

## Deprecation Table

| Surface | Deprecated since | Removal planned | Status |
|---|---|---|---|
| `/api/workflows/*` (10 legacy shells) | 0.5.x (S4.3) | after Web/SDK/CLI migrate to the domain-specific `/api` endpoints | removed in 0.5.x after Web/SDK/CLI migration; legacy paths now return 404 |
| `actor` (request field) on `POST /api/review/decisions` | 0.5.x (W0-03 C13) | when no caller still sends it | accepted but never used: the platform records the authenticated identity as the actor of the decision and of its audit events. A value that disagrees with the identity is reported as an `ACTOR_CLAIM_IGNORED:<claim>` envelope warning, so a caller learns its claim was not recorded. The field became optional in the same change, so omitting it is the supported form |
| `authentication` value `not_installed` on `GET /api/health` / `/api/health/live` | 2026-09-19 (owner decision D1) | when no consumer switches on it | **Replaced, not removed**: every route profile installs authentication now, so no shipped profile produces the value. It stays declared in the response type for a profile that installs nothing, and the payload reports `enforced` by default or `anonymous_allowed` when the deployment itself opted into trusting its network (`EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS`). A consumer that only handled `enforced`/`not_installed` treats `anonymous_allowed` as the old value, which is exactly what it is |

## Deliberate Narrowings

Behaviour changes that refuse more than they used to, recorded here because they are visible to a
caller rather than additive.

| Surface | Change | Why |
|---|---|---|
| Every `/api` path except the credential-exempt ones | **A caller that presents no credential is refused.** Before D1 the `development` and `internal` profiles installed no authentication and served such a caller as the compatibility principal (data scopes `("*",)`, role `OPERATOR`). They now answer 401 `public_api_token_missing` when a deployment token is configured, or 503 `public_api_token_not_configured` when none is, and the identity dependency adds its own 401 `authentication_required` refusal as a backstop. The exempt paths are `/api/auth/*`, `/api/dev/auth/*`, `/api/health` (so `live` and `ready`), `/api/dev/health` and `/api/internal/health` | Owner decision D1: identification is the default and trusting the network is a deployment's own, reported statement. The SDK, CLI, MCP and Web clients are unaffected - they already present the deployment token or a session |
| `/api/internal/*` (12 paths) | **Declared permissions where there were none.** The route-permission gate was not installed in the `internal` profile, so these paths never resolved a permission; installing the gate exposed that a mounted path with no registry entry answers 500 `permission_not_declared` | The registry is enforcement, not documentation. Each entry mirrors the floor the route already enforced in its handler (`validate_internal_operator_headers`), so nothing that could reach them before is refused now |
| `POST /api/route-cost/upstream-contracts` | **A write with no stored-contract edit token is create-only.** Before this change a POST whose `contract_id` already existed overwrote that row (captured and audited, but silently last-writer-wins). An existing identity is now refused `409 contract_edit_conflict` unless the request carries the current token from `GET /api/route-cost/upstream-contracts`; a token-bearing request for a nonexistent identity writes nothing; a concurrent create loser is refused the same way instead of taking over the winner. Permission, acting principal, capture/audit transaction and the error envelope are unchanged; the plain repository upsert stays an internal compatibility path, not an API write path | The route is a multi-writer operator surface over one mutable row; without a read precondition a draft loaded before another operator's save silently replaced their terms, and the captured revision could only prove afterwards what had been replaced. The token is an integrity/identity check on the row (not cryptographic authenticity and not a monotonic lifecycle counter), and there is no overwrite bypass. See [CONTRACT_PAYMENT_INTEGRATION_PLAN.md](../engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md) section 13 |
| `POST /api/route-cost/upstream-contracts` and `GET /api/route-cost/upstream-contracts` | **The edit token schema is `upstream-contract-edit-token/v2`.** S2b added the declared payment-terms carrier column to the covered field set, so a token loaded before the upgrade can never compare equal after it: a client holding an open draft receives `409 contract_edit_conflict` and must reload the contract before saving. There is deliberately no v1 comparison fallback | The token covers the whole persisted row, and the carrier holds operator declarations that a stale draft could otherwise erase. Storing the terms on the row without covering them in the precondition would let a draft loaded before a terms-only edit overwrite it silently. **Deployment:** no client code change is required to keep reading, but any open editor session must be reloaded after the rollout |
| `POST /api/route-cost/resource-pool/optimize` | **The request must carry an explicit finite `annual_financing_rate_pct`.** The field has no server-side default any more: omitting it, or sending `null`, a boolean, a string (including a blank string), `NaN` or ±infinity, is refused `422` by request validation instead of being filled with the previous implicit `6.0`. An explicitly supplied `0` is accepted and is a recorded zero (a zero early-cash term). No other field, sign convention or arithmetic rule changed | The optimiser credits `base_cost × rate / 100 × max(upstream_lag − screen_lag, 0) / 365` to unit margin, so a server-filled rate priced a margin from an assumption the caller never declared. The Web client already refused an unknown rate and sent the resolved value, so it is unaffected; direct API/SDK callers must now declare the rate they want. Boundary change recorded in the business acceptance reconciliation note of 2026-10-06; it establishes no dated cash-need profile, day-count convention, discount factor or NPV |
| `POST /api/route-cost/resource-pool/optimize` | **Payment/sale lags are explicit declarations.** `PortfolioResource.upstream_payment_lag_days` is required (the previous server-side default `20` is removed) and `PortfolioSaleOption.screen_sale_cash_lag_days` must be declared as whole non-negative days or an explicit `null` (the previous `1` default is removed). Supplied values must be strict integers: booleans (which Python counts as integers), floats, strings and negatives are refused `422`, and an explicit `0` is a recorded zero. The optional per-resource `screen_sale_cash_lag_days` override keeps the same whole-day rule. When a pair's effective lag is unknown (no override and an explicit `null` option declaration) the pair is refused and reported (`SALE_CASH_LAG_MISSING` / `SALE_CASH_LAG_UNKNOWN`) instead of being credited as if paid on the delivery day. The composed `GET /api/route-cost/resource-pool/options` read stops substituting the removed one-day default: an undeclared eligible-contract lag is composed as `null`. No other field or arithmetic rule changed | The lags feed the same early-cash term as the rate (`base_cost × rate / 100 × max(upstream_lag − screen_lag, 0) / 365`), so server-filled values priced margin from lag terms the caller never declared, and assuming a zero-day sale lag would produce the largest possible credit. Recorded in the business acceptance reconciliation note of 2026-10-06; no dated cash schedule, day-count convention, discount factor or NPV is introduced |
| `PUT /api/portfolio/credit-lines/{id}`, `/trader-mandates/{id}`, `/hedge-approvals/{id}`, `PUT /api/opportunities/settings`, assumption-set approval | **Segregation of duties (2026-11-24, Commercial Intelligence V3 F1).** REVIEWER is still required; an identity that also holds a front-office role (ANALYST) is now refused `403 segregation_of_duties`. A mandate whose `trader` is any of the caller's names (principal id, name or display name, compared case-insensitively) is refused `403 own_mandate`; before, only the principal id was compared | Persona review P-01/P-02: a trader who was also a reviewer could set the limits their own deals are measured against. A combined demo account does risk work by signing in as a risk identity |
| `PUT /api/portfolio/credit-lines/{id}` | **A field left out keeps its stored value (2026-11-24, F1).** Before, a body without `contract_ids` cleared the links and with them any breach measured on those contracts. Unlinking is now an explicit `[]`. Every reference write's audit event lists each changed field as before -> after, with `before_summary` and `after_summary` filled; the response adds `changed` | Persona review P-01. Callers that always send the full line see no difference |
| `PUT /api/portfolio/credit-lines/{id}`, new `GET` on the same path | **Unlinking every contract is confirmed (2026-11-24, F1).** An empty `contract_ids` on a line that has linked contracts answers `409 unlink_not_confirmed` unless the body also sends `unlink_contracts: true`. The new `GET` returns every stored field (REVIEW, risk function only) so a form sends what it read. A critical limit alert nobody acknowledged no longer resolves itself when its condition clears: it stays open with a `Condition cleared at …` warning and closes on the scan after acknowledgement | Hands-on review QA-R-01: the UI form sent empty links, cleared a 111 % breach and closed its critical alert unseen |
| `POST /api/market/ticks` | **Licensed labels need their own grant, and implausible ticks are refused (2026-11-24, F1).** `EEX`, `ICE_OCM` and `Trayport` are accepted only from a key whose effective data scopes name that family (a `*` key gets `403 source_not_granted`; issue the feed adapter a key scoped to it). A batch with a price outside the band for the hub's quotation and product, a forward product below zero, an exchange time more than 120 s after receipt or a mid more than 3x (or under a third of) the previous one for the instrument is refused `422 ticks_invalid` with the reason, and nothing of it is stored. Simulated sources are unaffected by the grant | Persona review P-03: a fat finger or a pence-for-pounds slip reached strategies and the prompt panel, and any operator key could present prices as a licensed venue's |
| `POST /api/desk/gas-day/status` | **Answers instead of failing (2026-11-24, F1).** The write category had no minimum role, so every call returned 500; it now needs `gas_day.record`, held by the new SCHEDULER role and by ANALYST, and answers 403, 404 `line_not_in_scope`, 422 `unknown_step` or 200 | Persona review P-04 |
| `POST /api/access/api-keys` | **Narrowed (2026-11-24, F1).** An administrator may issue a key only for a SERVICE principal or for themself; a request for another USER answers 403 `personal_key_self_service` and is audited as denied, because a key acts as its owner. Existing keys are untouched. New `GET`/`POST /api/me/api-keys` and `POST /api/me/api-keys/{key_id}/revoke` let a person manage their own keys from an interactive sign-in (90-day default expiry, 365 at most, scopes limited to the owner's) | Hands-on review QA-R-02 |
| `GET /api/portfolio/daily-balance` | **One definition with Today's "My gas day" (2026-11-24, QA-T-07).** The rows are built from `application/gas_day` (the caller's mandate scope, the same lines). `supply` is now the physical lines net (contracts nominated where held, else their quantity, capped by an outage at the source; LNG send-out; storage and imports less offtake, injection and exports), no longer contract quantity x measured delivery; `delivery_ratio` is still the measured ratio but is no longer applied (`delivery_ratio_applied: false`). `state` uses the gas day's band (the approved `balancing.flat_band_pct`, else 2 %) unless `flat_band_mwh` is given. Without `short_premium_per_mwh`/`long_discount_per_mwh` the cost uses the approved cash-out set for the hub's books instead of being null; given, they are labelled `entered`. Added, per day: `physical_in_mwh`, `physical_out_mwh`, `net`, `band`, `cash_out` (rate, set, version, basis), `lines`, `simulated`; top level: `delivery_ratio_applied`, `definition`, `scope`, `as_of_utc` | Two balances for one hub and day (+20,153 MWh on Today, +27,438 MWh on Delivery; cost at 1.20 vs a client default of 0.30 GBP/MWh) |
| `GET /api/desk/today` (`gas_day`, `checklist` rows) | **An outage and the cargo plan change gas-day lines (2026-11-24, QA-T-09, QA-L-01).** A supply line whose source has a REMIT outage that day is capped at the daily contract quantity less the share out over the share of the day, with `adjustments` naming the message (`source`, `id`, `version`); checklist nomination rows add `outages`. A regas slot holding a firm cargo takes the cargo plan's send-out by gas day (`basis` `cargo_plan`, `source_ref` `cargo:<id>`), 0 on the days a missed slot covers; a slot without a cargo keeps `basis` `slot`, now documented as an assumption. A bilateral (ETRM) deal booked today is its own prompt line, `ref` ending `:bilateral`. An LNG send-out still to send is due at the nomination cut-off, passed or not (it was the next open cut-off) | The balance ignored a registered outage and spread send-out over a slot window the cargo had missed |
| `GET /api/lng/cargoes/{id}/plan` and the board | **No gas in kind and nothing delivered without a berth (2026-11-24, QA-L-06).** With no berth (`missed`, `no_slot`) `gas_in_kind_mwh` and `delivered_mwh` are 0; before, gas in kind was still deducted and `delivered_mwh` held the energy at the ETA. Added `energy_at_eta_mwh` (loaded less boil-off to the ETA) on every plan. A `last_change` that misses the slot now shows the delivery lost, not gained | The figures did not add up (1,000,000 against 1,009,840 MWh) |

## Non-Goals

- URL versioning (`/v1`, `/v2`): rejected; the unversioned contract evolves
  additively.
- Generated client stubs: SDK DTOs remain hand-written and are guarded by
  parity tests.


## Strategy ownership and sharing — 2026-10-22

The public path registry now contains 187 paths (previously 182). Added:

- `/api/me/groups` (GET): the authenticated user's active sharing groups.
- `/api/access/groups` (GET/POST): ADMIN group catalogue and creation.
- `/api/access/groups/{group_id}` (PATCH): ADMIN group status/name changes.
- `/api/access/groups/{group_id}/members/{principal_id}` (PUT/DELETE): ADMIN membership changes.
- `/api/strategies/{strategy_id}/sharing` (PATCH): owner-selected PRIVATE, PUBLIC or GROUPS audience.

Strategy responses add `owner_principal_id`, `visibility`, `shared_group_ids` and
`can_manage`. New strategies are PRIVATE and bind ownership to the authenticated
active directory principal, never a request's attribution text. PUBLIC grants
read access within this deployment, still subject to roles and source licences;
it grants no edit or cross-region transfer permission. GROUPS requires explicit
active groups the owner belongs to. Shared readers cannot mutate strategy state.

This deliberately narrows existing access: hidden strategies and their child
resources return 404; lists filter before limiting. Jobs are restricted to their
server-recorded owner; a foreign `principal` query returns an empty list. Review
and portfolio projections withhold inaccessible strategy-linked records. Existing
ownerless strategies remain PRIVATE and quarantined pending verified ownership
assignment; migration 0040 does not infer owners from free-text attribution and
refuses downgrade to code that would expose these records.

Empty identity-key scopes now mean public-baseline access, not inheritance of
commercial grants. Explicit key scopes are intersected with current principal
grants. Operators must replace old implicit-scope keys with approved explicit
scopes; see [API keys](../operations/API_KEYS.md).

Job ownership follow-up: migration 0041 adds nullable `owner_principal_id` to job
records. HTTP producers bind this from the active named identity; display
`principal` remains attribution and an optional narrowing filter. Name-only legacy
jobs have no read/cancel grant until independently verified ownership is assigned.
A principal-name/ID collision cannot grant access.

## 2026-10-27 additive capacity billing contract

`POST /api/research/capacity-billing` adds a sandbox-only, authenticated research
calculation with strict decimal-string amounts and explicit aware billing times.
The shared domain engine owns arithmetic; typed SDK and Web consumers must not
recompute it. It establishes neither booked rights nor physical readiness.
Existing routes and authorization remain unchanged. See
[capacity billing capability](CAPACITY_BILLING_CAPABILITY.md) and
[delivery reconstruction plan](../engineering/DELIVERY_RECOVERY_EXECPLAN.md).
Public census: 196 paths / 210 operations.

`POST /api/research/lng-economics-only` is likewise additive and sandbox-only.
It requires explicit ordered energy stages, charged cost bases and dated cash
inputs. Readiness remains NOT_ASSESSED; API and SDK delegate to the shared domain
composition. See [LNG capability](LNG_ECONOMICS_ONLY_CAPABILITY.md).

## 2026-10-28 additive route-date and provenance carriers

Route recommendation accepts an explicit `tariff_applicability_date` and optional
candidate date/source references; results preserve date and source provenance.
Caller references are labelled unverified and confer no access. Resource-pool
runtime composition accepts `gas_day`; sandbox composition refuses that field.
PortfolioSnapshot uses its existing normalized trading-context gas day for tariff
selection. Unknown cost is never substituted with zero; missing price/cost basis
or conflicting dates blocks allocation. Existing paths/counts remain unchanged.
See [consumer contract](ROUTE_TARIFF_DATE_CONSUMERS.md).

## 2026-10-28 additive ECMWF forecast and degree-day paths

The stable public surface now includes `GET /api/weather/forecasts` and
`POST /api/weather/degree-days`. They are additive research paths: the legacy
shells `GET /api/weather/stations`, `GET /api/weather/observations` and
`GET /api/weather/hdd-cdd` remain mounted with their existing empty-envelope
behaviour, and no existing path, parameter or response meaning changes. This
declaration records a contract; it is not an acceptance, production-readiness or
operational-forecast claim.

**Point-in-time inputs.** `GET /api/weather/forecasts` selects readings by the
caller's explicit `prediction_origin`, `valid_from` and `valid_to`, and each
returned row preserves `issued_at_utc`, `valid_at_utc` and `available_at_utc`;
the API performs no interval aggregation. `POST /api/weather/degree-days`
requires explicit `prediction_origin`, `gas_days` and `max_hold_minutes`; it
reports `selected_forecast_vintage`, `feature_policy_hash`, the resolved gas
days and the query limit, and reads persisted forecasts across the declared
window extended by the hold. Neither path defaults a missing origin, window or
vintage.

**Weights.** Degree-day weights are caller declarations, not server inferences.
Each binding names one persisted `point_id`/`series_id`/`entity_id`/`location_id`
and one `region`; point and location ids must be unique; all bindings must share
the request region (which may be supplied once); each weight is an exact decimal
in `[0, 1]` and the bindings must sum exactly to `1`. The response warns
`CALLER_DEFINED_REGION_WEIGHTS`.

**Coverage.** `min_covered_fraction` is an explicit request field, not a default.
The computation uses the declared `LEFT_HOLD_INSTANT` temporal method with
`max_hold_minutes` as its maximum gap, caps the query at 256 forecast rows and
the bindings at 64 points. Insufficient daily coverage produces null daily
metrics with an explicit missing reason. When no bridge intervals are available,
it returns `NOT_READY` with diagnostics and `FORECAST_INPUT_NOT_READY`. The
`MISSING_COVERAGE_NULL` warning declares the missing-value policy. Missing coverage is never replaced by zero, and a
calibration or station value is never substituted for an absent grid point.

**Research restrictions.** Both paths return `meta.research_only: true` and the
`RESEARCH_ONLY`/`HUMAN_REVIEW_REQUIRED` warnings; the degree-day envelope also
sets `meta.human_review_required: true`. Both carry ECMWF Open Data attribution
(CC BY 4.0). They perform reads and a calculation only: no persistence, no
forecast invention, no provider call at request time, and no trade, order,
nomination or settlement semantics. Existing legacy weather endpoints are not
deprecated by this addition.

**Authentication and source certification.** Both paths sit behind the
deployment's public API authentication, named identity, declared route-permission
and commercial-access gates. They additionally require derived-data access to
`ECMWF_OPEN_DATA` (`weather_forecasts` / `weather_degree_days`), and returned
rows are filtered by entity/source entitlement. Before reading, each path checks
the latest `ProviderCertificationRecord` for `ECMWF_OPEN_DATA`; no record, an
expired record, or a gate that does not allow live use answers
`503 forecast_source_unavailable`. A storage failure or malformed stored data
answers `503` with a sanitized code rather than an empty or invented value.
Bridge or domain violations of the declared bindings, weights, calendar or
coverage policy are refused as `422 invalid_degree_day_inputs`; request-schema
violations use the platform's standard `422` validation response. Neither form
computes a value.


## 2026-10-29 native physical-rate representation (RFC0005)

`GET /api/physical/flows` and `GET /api/physical/capacity` add an explicit
`quantity_basis=native` representation. Default `quantity_basis=volume` keeps the
existing numeric, non-null volume DTOs and returns all admitted rows; the new
`limit` applies only to native mode. Legacy ENTSOG volumes from unverified
normalization are withheld with a warning rather than rewritten, zero-filled or
offered as physical truth. A valid native energy rate has no volume and is served
only in native mode. An empty volume result does not mean zero physical flow.
Other sources retain their finite volume contract.

Native mode accepts `limit`1..2000 (default200) and an optional exact `point_id`
(up to128characters). A query exceeding the native bound answers400
`native_query_overflow`, without silently truncating the result. Authentication,
route permission, commercial access and source entitlement remain authoritative;
row filtering precedes projection and metadata. Invalid stored native content
answers503 `native_rate_invalid` with a fixed message, not raw values or SQL.
The source-format/normalizer namespace is separate from provider revision history.

Native rows carry the existing point/source/period identities plus
`quantity_basis`, `normalizer_version`, `operator_key` (nullable),
`native_rate_json`, `raw_archive_id`, `payload_sha256` and `received_at_utc`.
`flow_status` and `period_type` preserve captured provider labels when available;
they do not infer finality or physical authority. The
native payload preserves original `value_text`/`unit_text`, exact decimal strings
for native and canonical rates, declared dimension and hourly/daily rate basis.
Energy exposes `energy_kwh_per_day` and null volume; volume exposes
`volume_mcm_per_day` and null energy. The backend revalidates the payload from its
source strings. No assumed calorific conversion exists. Timestamps remain
explicit instants; missing provenance is not replaced with a clock default.

The same two paths accept optional `from_utc`/`to_utc` aware ISO-8601 query
instants for a native period window. Both must be supplied or neither; naive
instants are refused, each is normalized to UTC, and `to_utc` must be later than
`from_utc`. A window is accepted only with `quantity_basis=native`; in volume mode
it answers 422 `native_window_invalid` with a fixed message that echoes no input.
The window is a half-open period **overlap**, not containment: a row is selected
when `period_start_utc < to_utc` and `period_end_utc > from_utc`. A longer
technical-capacity observation that covers a requested daily-flow window therefore
remains visible instead of being dropped. The overlap predicates run before native
ordering and the `limit + 1` probe, so overflow still answers 400
`native_query_overflow` and a narrower window can make the same native query fit.
Clients comparing flows with capacity should send the same explicit query window to
both paths. The window selects captured observations only; it is not a complete
history or a provider revision ledger, makes no calorific-value (CV) conversion,
and defaults no clock time when either instant is omitted.

The SDK adds separate typed native methods in `native_physical`; existing
`physical` methods remain volume-only. Clients must not pair different operators,
points, directions, dimensions or incompatible periods, nor interpret absent
quantities as zero. Native rows do not prove booked capacity or execution rights.
See [RFC0005](../engineering/RFC-0005-ENTSOG-NATIVE-RATES.md). No path or operation
was added: the exact census stays191paths/205operations.

## 2026-10-30 additive spread lab contract

`GET /api/research/spread-series` lists the daily close series the caller is entitled
to (hub, tenor, source, unit, first/last date, day count). `POST
/api/research/spread-analysis` builds a weighted spread of one to four of those series,
reports its statistics (z-score, percentile, AR(1) half-life) and backtests one
declarative rule (z-score mean reversion or fixed bands) with positions decided at
close t and P&L earned from t to t+1. Both sit under the existing `/api/research/`
GOVERNED prefix and filter rows by data entitlement; neither creates an order. A
mixed-unit spread, an unknown series or an invalid rule is a 422
`spread_analysis_invalid`. Public census: 198 paths / 212 operations.

## 2026-10-30 additive preferences contract

`GET`/`PUT /api/me/preferences` read and merge the caller's own presentation choices
(language, theme, market view, quote layout) and return them with the
organisation defaults and the effective values. `GET /api/settings/organisation` reads
the organisation defaults; `PUT` sets them and requires identity administration
(audited). Values outside the closed vocabulary are a 422. Preferences grant nothing.
Public census: 200 paths / 216 operations.

## 2026-10-30 additive position ladder

`GET /api/portfolio/position-ladder?months=N` (1-36) returns physical (stored upstream
contracts) and financial (filled screen trades) positions by hub and delivery month with
net and hedge ratio, a mark-to-market against the latest entitled daily close per hub, and
an indicative one-day 95 % historical-simulation VaR of the open position. It reads under
the existing `/api/portfolio/` READ family and commercial boundary; price history is
entitlement-filtered. Public census: 201 paths / 217 operations.

## 2026-10-30 additive gas-for-power

`GET /api/market/gas-for-power?zone=DE_LU&days=14` returns, per delivery day for one
bidding zone, the average day-ahead power price, residual load, implied gas burn and its
basis, the reference gas hub close, front carbon (EUA; UKA plus Carbon Price Support for
GB) and API2 coal, and the clean spark spread, clean dark spread and fuel-switch gas price.
Inputs come only from entitled, non-simulated rows; a missing input leaves the dependent
figure null. Read under the `/api/market/` READ family and commercial boundary. Public
census: 202 paths / 218 operations.

## 2026-10-30 additive market-data licence register

`GET /api/access/market-data-licences` lists the firm's market-data licences (vendor,
source family, enterprise/site/named-user, display or non-display use, validity, offices,
seats, contract reference) with each licence's current holders. `PUT
/api/access/market-data-licences/{licence_id}` records or amends one (identity
administration, audited). `PATCH /api/access/users/{principal_id}` now refuses with 409
`data_scope_not_licensed` a newly added licensed data scope that no active licence covers
for the person's office or that has no free named-user seat; public families and the
`*` wildcard are unaffected. `GET /api/access/data-scopes` derives its families from the
source registry. Public census: 204 paths / 220 operations.

## 2026-10-30 additive north-west Europe balance

`GET /api/market/nwe-balance?days=14` (1-31) returns the north-west Europe call on
Norwegian pipeline gas, LNG send-out and storage in GWh per gas day: the last 28 measured
days (ENTSOG Norwegian entry points, GIE ALSI, GIE AGSI for GB, NL, BE, DE, FR, DK, LU)
and a forecast whose method is stated per component and day, with Norwegian supply reduced
by live REMIT outages and storage rolled into an inventory and fill trajectory. Read under
the `/api/market/` READ family. Public census: 205 paths / 221 operations.

## 2026-10-30 additive trading books and roll-ups

`GET /api/portfolio/books` lists trading books (legal entity, region, business, base
currency, commodities) with their hierarchy and how many contracts and screen trades each
holds. `PUT /api/portfolio/books/{book_id}` defines a book and assigns contracts and trades
to it (OPERATOR, audited). `GET /api/portfolio/position-ladder` gains `group_by`
(hub, firm, legal_entity, region, business, book) returning a `rollup`, and
`reporting_currency`; mark-to-market and VaR now convert each hub's currency through ECB
reference rates (previously GBP and EUR amounts were added unconverted). Without
`reporting_currency` the positions' own currency is used when they share one, else EUR.
Public census: 207 paths / 223 operations.
The contract edit token now covers `book_id` and its schema is
`upstream-contract-edit-token/v3`: open contract drafts must be reloaded after the upgrade.

## 2026-10-31 additive integration: CSV exports and signed hand-offs

`format=csv` on `GET /api/portfolio/position-ladder`, `GET /api/market/gas-for-power` and
`GET /api/market/nwe-balance` returns the same rows as a CSV attachment (UTF-8 with BOM,
`X-Eurogas-Report-Rows`); the JSON default is unchanged.
`GET /api/decision-cases/{case_id}/handoff` returns, for a DECIDED case only (409
`case_not_decided` otherwise; 503 when `EUROGAS_NEXUS_HANDOFF_SIGNING_KEY` is unset), a
`eurogas-nexus-handoff/v1` document with the decision records, the decision pack hash, an
idempotency key stable per decision, and an HMAC-SHA256 signature over its canonical JSON.
It is decision support for ERP/ETRM middleware, never an order. Public census: 208 paths /
224 operations.


## 2026-10-31 additive field and deliberate narrowing: deployment profile and isolation

`GET /api/runtime/release` gains `deployment` (`region`, `map_default_provider`), an
additive object the web client uses to pick the default basemap; older clients ignore it.
With `EUROGAS_NEXUS_PORTFOLIO_ISOLATION=true`, contract, trade, book, ladder and P&L reads
return only rows in the caller's `BOOKS:` scopes, and changes outside them answer 403
`book_outside_scope` or `contract_outside_book_scope`. This narrowing applies only when an
operator turns isolation on; with it off every response is unchanged. No path is added:
208 paths / 224 operations.

## 2026-10-31 additive read: live map situation

`GET /api/portfolio/map-situation` (READ, commercial data) returns `outages`, `flows`,
`contracts`, `cargoes` and `regas_slots`, each with the `location` its source supplied
(`match`: `eic`, `name` or `feed`), plus `unlocated` counts for items with no location.
Book-held items follow portfolio isolation; market items the caller's data scopes. Migration
`0053_lng_cargo_regas` adds `lng_cargoes` and `regas_slots`, loaded by
`scripts/ops/import_lng_positions.py`. Public census: 209 paths / 225 operations.

## 2026-10-31 additive: risk limits, delivery performance, LNG cargo bids, contract intake

Nine paths, all additive; migration `0054_risk_controls` adds `credit_lines`,
`trader_mandates`, `contract_daily_deliveries` and `lng_terminal_terms`.

| Path | Method | Permission | Purpose |
|---|---|---|---|
| `/api/portfolio/credit-exposure` | GET | READ | Exposure per counterparty against its line |
| `/api/portfolio/credit-lines/{counterparty_id}` | PUT | REVIEW, and the caller must hold REVIEWER itself | Approved credit line (audited) |
| `/api/portfolio/credit-lines/{counterparty_id}` | GET | REVIEW, and the caller must hold REVIEWER itself | One stored credit line, every field, for the edit form |
| `/api/portfolio/mandate-usage` | GET | READ | Each trader's positions against their mandate |
| `/api/portfolio/trader-mandates/{mandate_id}` | PUT | REVIEW, REVIEWER held, never one's own (403 `own_mandate`) | Trader mandate (audited) |
| `/api/portfolio/lng-terminal-terms` | GET | READ | The firm's landing costs per terminal |
| `/api/portfolio/lng-terminal-terms/{terminal_id}` | PUT | GOVERNED | Terminal landing costs (audited) |
| `/api/portfolio/lng-cargo-bid` | POST | READ (computes, stores nothing) | Max DES bid per terminal |
| `/api/contracts/delivery-performance` | GET | READ | Allocations against nominations and DCQ |
| `/api/contracts/intake` | POST | GOVERNED | Contract PDF to a review draft (stores nothing; audits the SHA-256) |

The reads accept `format=csv|xlsx|pdf` where they return tables, as do
`/api/portfolio/position-ladder`, `/api/portfolio/pnl-snapshots`,
`/api/market/gas-for-power` and `/api/market/nwe-balance` (previously `json|csv`).
Public census: 218 paths / 234 operations.

## 2026-10-31 additive: contract lifecycle and the sell-down plan

Migration `0055_desk_operations` adds `retired_at_utc`, `retired_by` and `retire_reason` to
`upstream_resource_contracts`, and `min_hedge_ratio_pct`, `max_hedge_ratio_pct` and
`instruments` to `trader_mandates`.

| Path | Method | Permission | Purpose |
|---|---|---|---|
| `/api/route-cost/upstream-contracts/{contract_id}/retire` | POST | GOVERNED | Retire with a reason under the edit token (409 `contract_edit_conflict`, `contract_already_retired`); audited |
| `/api/route-cost/upstream-contracts/{contract_id}/reinstate` | POST | GOVERNED | Bring a retired contract back (409 `contract_not_retired`); audited |
| `/api/portfolio/sell-down-plan` | POST | READ (computes, stores nothing) | Day-ahead versus within-day volume from measured delivery volatility |

`GET /api/route-cost/upstream-contracts` gains `include_retired` (default false) and each
contract gains `retired_at_utc`, `retired_by`, `retire_reason`. Retired contracts leave the
position ladder, risk reads, analysis context and the map. `GET /api/portfolio/mandate-usage`
rows gain `hedge_policy`, `hedge_ratio_range`, `hedge_room_mwh` and `instruments`; the
mandate write accepts the hedge band and instruments (422 `unknown_instrument`,
`hedge_band_inverted`). Public census: 221 paths / 237 operations.

## 2026-10-31 additive: problem reports, notifications, tariff publications

Migration `0055_desk_operations` also adds `support_reports`, `notification_channels`,
`notification_outbox`, `notification_deliveries` and `tso_tariff_publications`, and
`capacity_basis` / `variable_regas_per_mwh` to `lng_terminal_terms`.

| Path | Method | Permission | Purpose |
|---|---|---|---|
| `/api/support/reports` | POST | READ (any signed-in user) | Report a problem to the IT desk with diagnostics |
| `/api/support/reports` | GET | READ | Operators see all reports, others their own (`scope`) |
| `/api/support/reports/{report_id}` | PATCH | OPERATOR | Acknowledge, assign, resolve (resolution required); audited |
| `/api/settings/notification-channels` | GET | ADMIN | Email channels with their last delivery |
| `/api/settings/notification-channels/{channel_id}` | PUT | ADMIN | Email channel (422 `recipients_invalid`); audited |
| `/api/settings/notification-channels/{channel_id}/test` | POST | ADMIN | Send a test now |
| `/api/route-cost/tariff-publications` | GET | READ | TSO tariff publications with NC TAR deadline state |
| `/api/route-cost/tariff-publications/{publication_id}` | PUT | GOVERNED | Register, update, mark final or reviewed; audited |

Public census: 228 paths / 245 operations.

### Deal hedge approvals and the daily gas balance (2026-11-01)

Migration `0056_hedge_approvals` adds `hedge_approvals` (one row per contract: approved
minimum and maximum hedge ratio, approval reference, validity, notes). Risk approves a band
per deal, separately from the trader who books the contract; the mandate's band still
applies to the book.

| Path | Method | Authority | Purpose |
|---|---|---|---|
| `/api/portfolio/hedge-approvals` | GET | READ | Each approval with the cover its linked trades give per month, and breaches |
| `/api/portfolio/hedge-approvals/{contract_id}` | PUT | REVIEWER (risk function) | Approve or change a deal's band (422 `hedge_band_missing`, `hedge_band_inverted`); audited |
| `/api/portfolio/daily-balance` | GET | READ | Per gas day at a hub: supply, exchange and bilateral trades, residual, cash-out cost |

The contract write also refuses an unknown sale mode (422 `contract_sale_mode_unknown`).

Public census: 231 paths / 248 operations.

### Contract price currency (2026-11-05)

Migration `0057_contract_price_currency` adds `upstream_resource_contracts.contract_price_currency`
(`GBP`, `EUR` or `USD`; existing rows read `GBP`, which is what every price recorded so far
was). Additive and backward compatible:

- `POST /api/route-cost/upstream-contracts` accepts an optional `contract_price_currency`.
  Omitted keeps the stored currency (GBP for a new contract), so an older client never
  changes it; any other value is a 422 from request validation.
- Contract reads carry `contract_price_currency`. `contract_price_gbp_mwh` keeps its name
  and now means the price per MWh **in that currency**; the name predates the field.
- The edit token covers the new column, so an edit made against an older read is a 409.
- Revisions: a GBP contract is still captured as `upstream-contract-revision/v1` (or v2
  with declared payment terms), byte for byte as before, so existing hashes hold. A EUR or
  USD contract is captured as `upstream-contract-revision/v3`, which adds
  `contract_price_currency` to the canonical document and may carry payment terms.
- Positions mark a contract against its hub in the hub's quote currency, translating a
  price in another currency at the latest ECB reference rate (with a warning naming it).
  The GBP route-cost engines translate with the as-of FX rule; a contract without a rate
  is left out with blocker `CONTRACT_PRICE_FX_MISSING:<id>:<currency>`
  (`runtime_decision_input_blocked` on the portfolio-network optimisation).

Public census unchanged: 231 paths / 248 operations.
