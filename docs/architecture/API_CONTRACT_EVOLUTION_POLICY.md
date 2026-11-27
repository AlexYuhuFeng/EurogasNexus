# API Contract Evolution Policy

Chinese companion: [API_CONTRACT_EVOLUTION_POLICY-CN.md](API_CONTRACT_EVOLUTION_POLICY-CN.md)

## Purpose

Additive 2026-11-26 (security review 2026-11): twelve paths, twelve operations. ADMIN:
`GET /api/access/privileged-changes`, `POST .../{change_id}/approve|reject|withdraw`,
`POST /api/access/users/{principal_id}/mfa/reset`, `GET /api/audit/verify`,
`POST /api/audit/checkpoint`, `POST /api/audit/prune`. The caller's own: `GET /api/me/mfa`,
`POST /api/me/mfa/enrol`, `POST /api/me/mfa/confirm`; sign-in: `POST /api/auth/mfa/verify`.
Census: 342 paths / 379 operations (+13 / +14 on 329 / 365: deal capture under `/api/desk/deals`; +1 / +1 on 328 / 364: `GET /api/settings/ai`; +12 / +12 before that on 316 / 352). Behaviour changes on existing
paths are listed in docs/release/notes/SECURITY_HARDENING_2026-11.md.

Additive 2026-11-26 (planning inputs): one path, one operation, READ: `GET /api/optimization/planning-inputs`.
Census on the innovation branch: 316 paths / 352 operations (+1 / +1 on 315 / 351).

Additive 2026-11-26 (topology): one path, one operation, READ: `GET /api/reference-network/supply-corridors`
(the reference network's supply corridors; reference data, no book data). Census on the innovation branch:
315 paths / 351 operations (+1 / +1 on 314 / 350).

Additive 2026-11-26 (gas option settlements, ported from the main-based demo review): two paths,
two operations, both READ: `GET /api/market/options/surface` and `GET /api/market/options/metrics`.
Census on the innovation branch: 314 paths / 350 operations (+2 / +2 on 312 / 348).

Additive 2026-11-26 (live data): one path, one operation. `GET /api/stream/live?topics=...`
(server-sent events, the caller's own entitlement) sends `change` notices (`topic`, `changed_at`;
no row, no value) for the subscribed topics: from the market event outbox (`market_events`, read
through the change feed) `prices` (price, FX, rate), `outages`, `tariffs`, `cargoes`, `book`
(contract, mark, limit, assumption, freight), `capacity`, `sources`, `news`; from their own
tables `prices` (screen quotes), `trades`, `alerts`, `nominations`, `tariffs` (publications) and
the map's `outages`, `flows`, `cargoes`, `slots`, `opportunities`. `jobs` events carry the
caller's own jobs (`job_id`, `kind`, `status`, `progress`, `step`), a `heartbeat` comes every 5 s,
and `ready`, `warning` and `revoked` as on the other streams. Resumes from `Last-Event-ID` or
`last_event_id` (`live|<time>|<outbox cursor>`; the time at most 15 min back). Census on the
innovation branch: 312 paths / 348 operations (+1 / +1 on 311 / 347).

Additive 2026-11-26 (each reader's own alert marks, demo-test alert centre): one path, two
operations, both READ. `GET /api/me/alert-state` returns the caller's own read and dismissed
marks on the unresolved alerts they may see; `POST /api/me/alert-state` marks alerts `read`,
`dismiss` or `restore` (1-500 ids) for the caller only and lists unknown or hidden ids under
`not_found`. The shared, audited alert status is untouched, and a mark lapses when the alert
recurs or escalates. Stored in `monitoring_alert_reader_state` (migration
`0089_alert_reader_state`). Census: 311 paths / 347 operations (+1 / +2 on 310 / 345).

Additive 2026-11-26 (options with consequences, demurrage by contract, REMIT outages on
pipeline supply, Commercial Intelligence V3 LNG-4, ADR Decision 37): two paths, two operations;
every other change is additive. `GET /api/lng/cargoes/{cargo_id}/disruption-options`, `GET
.../disruption-options/{option_id}` and `GET /api/lng/disruption/frontier` take the optional
query `reporting_currency` EUR|GBP|USD, `fx_source` ECB|WMR|BFIX|manual (ECB by default),
`fx_fixing`, `fx_rate_date`, `fx_rate` (units of `fx_currency` per 1 EUR, with `manual`) and
`fx_currency` USD|GBP; an FX choice the read cannot work from is 422 `fx_choice_invalid`, a
licensed source (WMR, BFIX) the principal holds no entitled fix of is 403
`fx_source_entitlement_denied`. Each option adds `possible` (it can physically happen; `feasible`
keeps the same meaning), `rank` (1 is first by the desk's ordering weights), `flags`
(`physically_possible`, `contract_breach`, `disrupts_normal_cargo`), `breaches[]` (the obligation, the
contract, the counterparty, the point, the shortfall by gas day, `penalty_eur_mwh` with
`penalty_held` and `penalty_terms`, or "penalty not held", and `exposure_eur`), `disrupts[]` (a
cargo or supply running to plan the option moves, with what moved and why), `recommended_as[]`
and `recommended_why[]`, `covers[]` (substitute supply bought for a short obligation),
`direct_pnl_expected`, `opportunity_cost_expected` (the expected P&L is direct P&L less
opportunity cost), `opportunity[]` (a call delayed, capacity or storage forgone, each with
`value_eur`, `sources[]` and whose cargo it hits) and `reporting` (the figures in the reporting
currency), and each leg adds `demurrage` (the terms and the amount in the contract's currency beside
the EUR figure); option kinds add `substitute` and `spot`; each scenario adds `direct_pnl` and
`opportunity_cost`. The read adds `recommended_set[]` (`option_id`, `key`, `title`, `basis`
clean|best_expected|overall, `reason`), `valuation`, `demurrage` (the rate as the charter party
or Confirmation Notice states it, its currency, source and terms, laytime, `eur_per_day` and the
`fx` conversion with its source, label and rate date), `fx` (the choice, the rate date used and
the sources) and `pipeline_outages[]`. The option detail's `arithmetic` lines add `sources[]`
(the price, rate and tariff applied) and `basis` direct|opportunity. `POST
.../choose` accepts the same FX fields in its body, answers a breach option (it can be chosen;
only an option that cannot physically happen is 409 `option_infeasible`) and adds
`recommended_set`, `consequences` (flags, breaches, cargoes moved, opportunity costs, covers,
rank) and `fx` to the decision. New `GET /api/lng/pipeline-supplies/{supply_id}/outage-links`
(READ, PORTFOLIO_READ, book scope) answers the REMIT messages linked to the supply (message id,
version, status applied|unsized|withdrawn|ended, what matched and why, the fraction unavailable
and the gas days each curtails), `outage_mode` auto|manual, the days entered by hand and the
curtailment the valuation reads with the source of each day; an unknown or out-of-scope supply is
404 `pipeline_supply_not_found`. New `PUT /api/lng/pipeline-supplies/{supply_id}/outage-override`
(GOVERNED, PORTFOLIO_WRITE, audited `lng.pipeline_outage_override`) takes `outage_mode`,
`curtailed` ([gas day, MWh] pairs, at most 400) and `reason`; a day outside the supply's window or
above its daily volume is 422 `curtailment_invalid`, an unknown mode 422 `outage_mode_invalid`.
The notification of a changed recommended set is titled "Recommended options changed". The ETRM
cargo schedule import takes the optional columns `laytime_hours`, `demurrage_rate_per_day`,
`demurrage_currency` and `demurrage_terms`. Nothing is booked, traded, nominated or sent. Census:
305 paths / 340 operations (+2 / +2 on 303 / 338). Design:
`docs/engineering/Commercial-Intelligence-V3/17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md`.

Additive 2026-11-25 (public tariffs and capacity windows, Commercial Intelligence V3 TAR-1, ADR
Decision 34): three paths, three operations, all READ and read-only. New `GET /api/tariffs`
(filters `publisher`, `facility`, `operator`, `direction` ENTRY|EXIT, `product`, `status`
INDICATIVE|FINAL, `on` a gas day, `key`; `as_of` ISO 8601 UTC; `history` true with `key` or
`facility` for every version; `limit` 1 to 2000, `offset`): `rows[]` of tariff versions
(`tariff_key`, `version`, `version_id`, `change_kind` first|revised|status_change|withdrawn,
`status`, `status_basis`, `status_change`, publisher, facility, operator, direction, product,
duration, firmness, `value` or `by_class`, unit, currency, period, `published_at_utc`,
`retrieved_at_utc`, `recorded_at_utc`, `superseded_at_utc`, `source_url`, `content_hash`,
`event_id`, `withdrawn`), `total`, `as_of`, `history`. New `GET /api/tariffs/publishers`: the
publisher registry (page, cadence, format, `manual` or `parsed`, terms) with what is held, when
each was last read, the next poll, `missed_publications` and, for a terminal whose terms need
it, `firm_permission`. New `GET /api/capacity/notices` (`kind`
auction|lng_slot|secondary_capacity, `product`, `facility`, `publisher`, `days` 1 to 400,
`past_days` 0 to 31): capacity auctions derived by rule from the CAM network code (`basis`
`rule_derived`), operators' slot windows and open seasons (`basis` `published`), each with its
opening and closing times, what it offers and its source. Rows are limited to the publisher
families the caller may read; a terminal whose terms need the firm's permission is left out
until it is recorded. 422 `history_needs_scope`, `as_of_invalid`, `as_of_in_future`; without a
runtime store the three answer empty with a warning; 503 `runtime_db_unavailable` when the store
is configured but cannot be read. Additive elsewhere: market event type `tariff.changed` (one
per new version, `source_id` the publisher's family, payload the version's identity, status,
`previous_status`, `status_change`, value, unit, period, `source_url`, `content_hash`), served by
`GET /api/market/changes` under the market rule; monitoring alert types
`tariff_publisher_stale` and `tariff_publication_missed` (category `data_source`) and
`capacity_window_opening` (new category `capacity`, routed to the `nomination` notification
category); valuation snapshot tariff inputs add `detail.tariff_version`,
`detail.tariff_status_basis`, `detail.tariff_source_url`; the public-source ingest report's
ENTSOG tariff detail adds `tariff_versions` and `tariff_events`. Migration `0083_tar1_tariff_book`
(tables `tariff_versions`, `capacity_notices`, expand-only). Census: 295 paths / 330 operations
(+3 / +3). Registry: `docs/data/TARIFF_PUBLISHER_REGISTRY.md`.

Additive 2026-11-25 (gas-day reconciliation, Commercial Intelligence V3 SCHED-1): one path, one
operation. New `GET /api/desk/gas-day/{gas_day}/reconciliation` (READ, `portfolio.read`, else 403
`permission_denied`): per hub (point) and counterparty the traded, confirmed, nominated and
TSO-matched quantities of the gas day, `groups[]` (`hub`, `point`, `counterparty`,
`shipper_codes`, `traded`, `confirmed`, `nominated`, `tso` each `{value, unit, mwh, kwh_h}` or
null, `held`, `state` break|matched, `urgency`, `cutoff`, `minutes_left`, `mwh_at_risk`,
`break_ids`, `book_ids`, `trades[]`, `nominations[]`, `simulated`) and `breaks[]` (`id`, `kind`
one of not_nominated, nomination_without_trade, quantity_mismatch, counterparty_mismatch,
shipper_code_mismatch, wrong_direction, lesser_rule_cut, late, unit_mismatch,
gas_day_misaligned, not_confirmed; `explanation`, `explanation_zh`, `next_step`,
`next_step_zh`, `gap_mwh`, `mwh_at_risk`, `quantity`, `figures`, `urgency`
due_soon|open|passed|closed, `severity`, `cutoff`, `minutes_left`, `cash_out` with `basis`
indicative|missing|not_an_imbalance, `trade_ids`, `line_refs`, `book_ids`), ordered by the time
to the hub's next cut-off then the MWh at risk; also `hubs[]` with their cut-offs, `counts`,
`kinds`, `mwh_at_risk`, `exchange_trades[]` (counted, not reconciled), `empty` and `execution`
(nothing is nominated, confirmed or sent). Filters `hub`, `counterparty` (substring),
`kind`, `book_id`, `breaks_only`; `format` `json` (default) or `csv` (one row per break, fixed
header, the GOV-1 export decision). 404 `book_not_in_scope`; 422 `unknown_kind`,
`gas_day_out_of_range` (more than 31 days from today). Scope as the gas-day reads (mandated
books, else every book the caller may see). `GET /api/desk/today` "What needs me" may hold items
of `kind` `reconciliation` (`break_kind`, `hub`, `gas_day`, `explanation`, `explanation_zh`,
`quantity`, `deadline_utc`, `target`); `GET /api/monitoring/alerts` may hold the category
`gas_day_break` (book-scoped; notified in the existing `nomination` category). The import
contract `etrm.nominations.v1` gains optional columns (`counterparty`, `direction`, `point`,
`shipper_code`, `counterparty_shipper_code`, `counterparty_quantity_mwh`), the step
`trade_confirmation` and the line prefix `counterparty:`; a file without them is read as before
(migration `0085_sched1_nomination_matching`, nullable columns). Census: 296 paths / 331
operations (+1 / +1 on 295 / 330, after TAR-1).

Additive 2026-11-25 (news and events, Commercial Intelligence V3 NEWS-1, ADR Decision 35): three
paths, three operations. New `GET /api/news` (READ; `/api/news/` is inside the commercial-data
boundary): items from the registered public sources (REMIT messages the platform holds, official
feeds whose terms permit reuse), filters `hub`, `country`, `type` (`outage`, `sanction`,
`policy`, `weather`, `strike`, `geopolitical`), `source`, `since`, `mine`, `order` (`relevance`,
the default, puts the items that touch the caller's book first; `time`) and `limit` (1 to 200);
each item has its source, URL, publisher, published and retrieved times, content hash, language,
licence note, tags and `relevance`; `meta.sources` lists the registry with each source's terms
and last poll. New `GET /api/news/{item_id}` (READ): the item with its source registry row,
`linked_exposures` (contracts, cargoes and nominations it touches, only in books the caller may
see and only for a caller who may read the portfolio), `related` items and the rule `note`
(sentences each citing evidence ids, and `citations`). New `POST /api/news/{item_id}/note`
(GOVERNED; body `language` `en` or `zh-CN`): the AI note ("what this means for my book") under
the AI use `news_note` when the organisation, deployment and caller allow it and every sentence
passes the grounding check, labelled `AI-generated` with its prompt version; otherwise the rule
note, with `ai.status` `off`, `refused` (and the failing check) or `unavailable`; each AI request
is audited (`ai.news_note`). 422 `type_unknown`, `source_unknown`, `since_invalid`,
`order_unknown`; 404 `not_found`; 503 `runtime_db_not_configured`. Market event type
`news.published` (source `src-news`). Migration `0084_news_items`. Census: 299 paths / 334
operations (+3 / +3 on 296 / 331). Sources and terms: `docs/integration/NEWS_SOURCE_REGISTRY.md`.

Changed and additive 2026-11-24 (maker-checker on limits and reference data, Commercial
Intelligence V3 P-17, ADR Decision 32). **Status change:** while four eyes is on for the write
(the default), `PUT /api/portfolio/credit-lines/{id}`, `PUT /api/portfolio/trader-mandates/{id}`,
`PUT /api/portfolio/hedge-approvals/{id}`, `PUT /api/portfolio/lng-terminal-terms/{id}`,
`PUT /api/market/firm-marks` and `PUT /api/lng/freight-routes/{route_id}` answer **202** with
`pending_approval: true`, `changed` (the fields that would change) and `change` (the proposal)
instead of 200, and store nothing until a different authorised person approves; an unchanged
save answers 200 with `pending_approval: false`; a second proposal for the same record answers
409 `change_pending`. With four eyes off for a write the answer is 200 as before, plus
`pending_approval: false`. Clients that treat any 2xx as success keep working but must not read a
202 as applied. Each of those bodies accepts an optional `change_reason` (at most 500
characters). New paths: `GET /api/portfolio/change-requests` (READ; `state` pending, decided or
all; `resource`; `limit`) answers `changes[]` (`change_id`, `action`, `kind`, `label`,
`label_zh`, `subject`, `target_key`, `new_record`, `fields[]` with `name`, `before`, `after`,
`reason`, `state`, `proposed_by`, `proposed_by_name`, `proposed_at_utc`, `decided_by`,
`decided_by_name`, `decided_at_utc`, `decision_note`, `own`, `may_approve`, `may_reject`,
`may_withdraw`, `approver`) and `four_eyes[]` (each write, its approver and whether it is
required now); `POST /api/portfolio/change-requests/{change_id}/approve`, `.../reject` (body
`note`, required) and `.../withdraw` (REVIEW; 403 `four_eyes_required`, `own_mandate`,
`segregation_of_duties` or `not_the_proposer`; 409 `change_not_pending` or `change_stale`; 422
`note_required`). Additive `provenance` (`second_approval`, `set_by`, `set_by_name`,
`set_at_utc`, `approved_by`, `approved_by_name`, `approved_at_utc`, `change_id`, `reason`) on
`GET /api/portfolio/credit-lines/{id}`, the rows of credit exposure, mandate usage, hedge
approvals, LNG terminal terms, firm marks and freight routes. `PUT /api/settings/organisation`
accepts `four_eyes` (an object of those six actions to true or false; ADMIN, audited). The audit
actions `change_request.propose`, `.approve`, `.reject`, `.withdraw` and `lng.freight_route` are
governed writes (503 `audit_unavailable` when their audit row cannot be written). Migration
`0081_change_requests`. Census: 288 paths / 323 operations (284 / 319 before).

Additive 2026-11-24 (ETRM and ERP import contracts, Commercial Intelligence V3 DATA-1): two
paths, two operations. New `GET /api/imports/contracts` (READ): the versioned file contracts
(`etrm.deals.v1`, `etrm.physical_positions.v1`, `etrm.nominations.v1`,
`etrm.cargo_schedule.v1`, `erp.counterparties.v1`, `erp.invoices.v1`), each with its columns,
required flags, key and target. New `POST /api/imports/{contract_id}/validate` (GOVERNED,
ANALYST floor; `/api/imports/` is inside the commercial-data boundary): a `text/csv` body of at
most 8 MB, `system` (required) and `on_error` (`reject_file` default, or `skip_rows`); it answers
the report (rows, accepted, `refused[]` with line, reason code, message and key, and what
storing would create, update, leave unchanged or remove) and stores nothing. 404
`contract_unknown`; 422 `column_missing`, `column_forbidden`, `file_empty`, `encoding_invalid`;
413 `file_too_large`. A contract id carries its version; a change that alters the meaning of an
accepted file, or refuses one that was accepted, is a new version. Census: 288 paths / 323
operations (+2 / +2). Contracts: `docs/integration/ETRM_ERP_IMPORT_CONTRACTS.md`.

Additive 2026-11-24 (refreshable reads, Commercial Intelligence V3 DATA-1, lesson P7): no new
path. `GET /api/market/prices`, `GET /api/market/observations` and `GET /api/market/fx` accept
`format` (`json` default, unchanged; `csv`). The CSV is one header line in a fixed order, the same
with or without rows and with or without `as_of` (strip: the `meta.columns` order; observations
and FX: their JSON fields with the version columns `revision`, `revision_basis`,
`published_at_utc`, `known_from_utc`, `revision_event_id`, `as_of_utc` before `metadata_json`,
empty without `as_of`), UTF-8 with a byte-order mark, nested values as JSON text. The file
carries the GOV-1 export decision of the licensed families its rows came from
(`X-Eurogas-Export-Decision`, 403 `export_denied` when terms are unregistered) and is metered as
an export. An unknown `format` is 422. Census unchanged: 286 paths / 321 operations. How-to:
`docs/sdk/POWER_QUERY.md`.

Additive 2026-11-24 (change feed, Commercial Intelligence V3 DATA-1, lesson P2): one path, one
operation. New `GET /api/market/changes` (READ, `/api/market/` floor): the market events recorded
after a cursor, oldest first (`after` = a cursor this feed gave, none for the start, or `latest`;
`kinds` repeated or comma-separated event types; `subject` a subject-key prefix; `limit` 1 to
1000, default 200). Each change is a digest in a stable column order (`meta.columns`): `cursor`,
`event_id`, `event_key`, `event_type`, `operation` (`insert` for revision 1, else `update`),
`revision`, `supersedes_event_id`, `subject_key`, `source_id`, `input_class`, `dependency_keys`,
`content_hash` and the market, published and ingested times; never the event's values, which stay
behind the entitled reads. `meta` carries `next_cursor`, `has_more` and `retention`. A market
event is shown when the caller may read its source family (metered like the market reads); a
desk event (contract, cargo, mark, assumption, limit, freight) only to a caller holding
`portfolio.read` who sees every book. Withheld events still move the cursor and are not counted
to the caller. An unusable cursor is 422 `cursor_invalid`, an unknown event type 422
`kind_unknown`. Order is (writer transaction, `seq`) and only events whose writer transaction has
ended are served, so no committed event is ever skipped (migration 0082 adds the nullable
`market_events.writer_txid`, expand-only). Retention: nothing prunes `market_events`, so a cursor
stays valid; a future retention policy must answer 410 `cursor_expired` for an expired one.
Census: 286 paths / 321 operations (+1 / +1). Design: `application/change_feed.py`.

Additive 2026-11-24 (as-of reads, Commercial Intelligence V3 DATA-1, lesson P1): one path, one
operation. `GET /api/market/observations` and `GET /api/market/fx` accept `as_of` (ISO 8601 UTC):
each figure is answered at the revision current at that instant, a figure first held later is
left out, and the rows add `revision`, `revision_basis` (`market_event` or `stored_row`),
`published_at_utc`, `known_from_utc`, `revision_event_id` and `as_of_utc`. Without `as_of` both
answer exactly as before. An unusable `as_of` is 422 `as_of_invalid`, one later than the server
clock 422 `as_of_in_future`. New `GET /api/market/prices` (READ, `/api/market/` floor) answers
the monthly price strip of one or more hubs (`hub` repeated or comma-separated, `start` YYYY-MM,
`months` 1 to 36, `side`, `include_simulated` default false, `as_of`): one flat row per hub and
month with the P-08 price, its kind, source, age and version (`revision`, `revision_basis`,
`published_at_utc`, `known_from_utc`), and `meta.columns` naming the stable column order; a month
with no price is a row with empty price fields. Unknown hub 422 `hub_unknown`, none 422
`hub_required`, bad month 422 `start_invalid`. Entitlement and licensed-use metering are the
market reads' own. Census: 285 paths / 320 operations (+1 / +1). Design:
`docs/operations/DATA_REVISIONS.md` ("Prices, FX and settlements as of an instant").

Additive 2026-11-24 (a cargo change reaches each role, Commercial Intelligence V3 LNG-2): no new
path. `GET /api/lng/cargoes/plans` and `GET /api/lng/cargoes/{cargo_id}/plan` add `cargo.eta`
(`basis`, `confidence`, `source`, `recorded_at_utc`, `text`); the board lines add `attention[]`
(one per open role message: `alert_id`, `role` trader|scheduler|risk|desk_head, `severity`,
`title`, `title_zh`, `due_utc`, `mine`, `updated_at_utc`) and the plan adds `roles[]` (each
role's message, open or withdrawn in the last day, with `lines`, `lines_zh`, `items`,
`inputs_as_of`, `withdrawn` and `mine`), both filtered by the cargo's book. `GET
/api/desk/today` "What needs me" may hold items of `kind` `cargo` with `role` and `cargo_id`.
`PUT /api/settings/notification-channels/{id}` accepts the categories `cargo` and `desk_head`;
`GET /api/monitoring/alerts` may hold the categories `lng_hedge`, `lng_schedule`,
`lng_exposure` and `lng_material`. The LNG positions import takes two optional columns,
`eta_basis` and `eta_confidence` (migration `0080_lng_eta_basis`). Census unchanged: 282 paths
/ 315 operations. Design: `docs/engineering/Commercial-Intelligence-V3/12_LNG_CARGO_IN_TRANSIT.md`.

Narrowed and additive 2026-11-24 (live pipeline, Commercial Intelligence V3 M7): no new path.
`GET /api/stream/opportunities` now follows the opportunity engine instead of the legacy intraday
scan: event `opportunity` carries `opportunity_id`, `type`, `lane`, `state`, `version`, `status`
(`open` | `withdrawn`), `reason` (the state left for, or `expired` when the validity window
lapsed), `changed_at_utc`, `expires_at_utc`, `deadline_utc`, `evaluation_id`, `book_ids` and
`source_families`, and no figure (the page re-reads `GET /api/opportunities`); event `evaluated`
carries `evaluation_id`, `trigger`, `as_of_utc`. Legacy intraday rows are no longer streamed; they
are still served by `GET /api/market/opportunities`. `PUT /api/settings/notification-channels/{id}`
accepts the categories `opportunity` and `nomination`; a channel subscribed to `alert` keeps
receiving both. Census unchanged: 282 paths / 315 operations. Design and budgets:
`docs/engineering/Commercial-Intelligence-V3/15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md`.

Additive 2026-11-25 (contracted before public, tariff years and source precedence, Commercial
Intelligence V3 TAR-2): five paths, five operations, all READ and storing nothing. `GET
/api/tariffs/years?facility=` (`direction`, `product`, `operator`, `as_of`; 422 without
`facility`) answers `facility_id`, `as_of` and `years[]`, each with `tariff_year` (`label`,
`convention`, `first_gas_day`, `last_gas_day`), `direction`, `product`, `firmness`, `operator`,
`period_from`, `period_to`, the `INDICATIVE` and the `FINAL` version side by side (a version row
as `GET /api/tariffs` returns it, or null), `versions`, `used` (the status a valuation as of
`as_of` uses) and `used_version_id`. `GET /api/capacity/bookings` (`kind`
entry|exit|lng_slot|regas|send_out|storage, `facility`, `as_of`) lists the firm's imported
bookings in the caller's books as held at `as_of` (`booking_id`, `source_system`,
`external_id`, `book_id`, `kind`, `facility_kind`, `facility_id`, `facility_name`, `operator`,
`direction`, `product`, `firmness`, `acquired_via`, `first_gas_day`, `last_gas_day`,
`quantity`, `quantity_unit`, `quantity_basis`, `price`, `price_unit`, `currency`,
`price_recorded`, `counterparty`, `source_reference`, `recorded_at_utc`, `updated_at_utc`,
`released_at_utc`). `GET /api/capacity/cost` (`kind` pipeline|terminal, `facility`; a pipeline
needs `direction`, `first`, `last`, `mwh_per_day`, with `product` (default DAILY), `premium`,
`operator`; a terminal needs `arrival`, `cargo_mwh`, with `product` (default spot); `as_of`)
prices the requirement contracted before public and answers `layers[]` (`layer`
contracted|public|not_held, `reference`, `quantity`, `unit`, `unit_cost`, `cost`, `currency`,
`first_gas_day`, `last_gas_day`, `status`, and for a contracted layer `booking_id`,
`acquired_via`, `contracted_price`, for a public one `status_basis`, `tariff_year`,
`version_id`, `published_at` (null when the publisher states none), `recorded_at`,
`how_bought`, `premium`, `public_price`, `source`), `covered`, `total_quantity`, `total_cost`
(null unless complete: never zero), `unit_cost`, `currency`, `complete`, `indicative`,
`precedence`, `order`, `order_source`, `sources[]` (every tier in order: `tier`, `label`,
`used`, `quantity`, `reason`, `note`) and `issues` (also the envelope's warnings); refused
inputs are 422 `capacity_cost_input_missing`, `period_too_long` (over 400 gas days) or
`period_reversed`. `GET /api/pricing/fx-rate?from=&to=` (`as_of`, `context`, `rate_type`)
resolves one FX rate through the firm's source order and answers `kind`, `context`, `as_of`,
`value` (units of `to` per unit of `from`, or null), `used_tier`, `source`, `order`,
`order_source` (`default`, `setting:<key>` or `calculation`) and `sources[]` (each tier with
`used`, `reason` not_held|stale|not_covering|not_configured|not_entitled|not_tried|used,
`note`, and for the tier used `value`, `source`, `reference`, `as_of`, `unit`, `method`).
`GET /api/pricing/source-precedence` (`context`) answers `kinds[]` (`kind`, `context`, `order`,
`order_source`, `tiers[]`), `institutions[]` (the firm's configured banks, no credential) and
`live_feed_terms`. Additive fields elsewhere: tariff version rows (`GET /api/tariffs`) gain
`tariff_year`, `status_rule`, `new` and `published_at_stated`, and their `status_basis` may be
`nc_tar_tariff_in_force`, `nc_tar_yearly_auction_held` or `nc_tar_before_yearly_auction`
(re-read as of the instant asked; the older `period_started` and `period_not_started` are
re-read by the same rule); `GET /api/tariffs/publishers` rows gain `tariff_year`, `cadence` and
`cadence_confirmed`; a route leg gains `indicative`, `version_id`, `version`, `tariff_year`,
`status_basis`, `published_at`, `recorded_at`, `cost_basis` (public|contracted|contracted+public),
`layers` and `breakdown`; a contract cost answer may have `basis` `contracted` or
`contracted+public` with a `breakdown`; `POST /api/optimization/capacity` accepts optional
`held_capacity_mwh` (default 0) and `held_cost_gbp`, and its result gains `held_capacity_mwh`,
`held_cost_gbp` and `layers`; `PUT /api/settings/organisation` (ADMIN, audited
`settings.organisation.update`) accepts `source_precedence` (`kind` or `kind@context` -> an
ordered list of that kind's tiers) and `financial_institutions` (KEY -> name, contracted,
provides, access file|manual|api, contexts, max_age_days; api needs `agreement_recorded`; a
credential field is 422 `setting_invalid`; a null value removes a key); alerts may carry type
`tariff_final_published`; the `tariff.changed` payload gains `tariff_year`, `published_at_utc`,
`recorded_at_utc` and `new_final`. Nothing is booked, bid, nominated or sent. Census: 308 paths
/ 343 operations (+5 / +5 on 303 / 338).

Additive 2026-11-25 (portfolio disruption re-optimisation, Commercial Intelligence V3 LNG-3):
four paths, four operations. `GET /api/lng/cargoes/{cargo_id}/disruption-options` (READ,
PORTFOLIO_READ, book scope) re-optimises the cargo's book around every disrupted supply (a cargo
due after its slot starts, a pipeline supply with curtailed days) and answers `cargo` (with the
slot's day-by-day `entitlement`), `status` disrupted|affected|as_planned, `disrupted[]`,
`scenarios[]` (base, ETA earlier and later by the confidence's spread, prices up and down),
`objectives[]` (`pnl_expected` max, `pnl_worst` max, `cost` min, `flexibility_mwh` max,
`disrupted_mwh` min), `options[]` that move this cargo (each with `option_id`, `key`, `kind`
wait|borrow|buy|borrow_buy|divert|swap|absorb|cover|combined, `title`, `feasible` and `reasons`,
`on_frontier`, `dominated_by` and `dominated_why`, `objectives`, `score`, `scenarios[]`,
`hedge_legs[]`, `legs[]`, `obligations[]`, `affects_other_supplies`), `frontier` (option ids),
`recommended`, `digest`, `preference` (weights, rule and their sources), `costs`, `inputs`,
`warnings`, `timeline` (the consumer's runs) and `decision` (the last recorded choice, or
null). `GET /api/lng/cargoes/{cargo_id}/disruption-options/{option_id}` (READ) answers one
option with `components`, `arithmetic` lines, `scenario_detail` and `mandates` (usage before
and with the option); an id the current run no longer holds is 404 `option_not_found`. `GET
/api/lng/disruption/frontier?book_id=` (READ) answers the whole book's options, `supplies` and
`obligations`; `curtail_supply`, `curtail_from`, `curtail_to` and `curtail_mwh_per_day` take a
pipeline supply as curtailed for the read (all four or none, else 422
`curtailment_incomplete`; at most 93 gas days). `POST
/api/lng/cargoes/{cargo_id}/disruption-options/{option_id}/choose` (GOVERNED, PORTFOLIO_WRITE,
audited `lng.disruption_choice`) records the chosen option with an optional `note` and answers
the decision with `booked: false`; an infeasible option is 409 `option_infeasible`. Nothing is
booked, borrowed, bought, traded or nominated. Census: 296 paths / 331 operations (+4 / +4 on
292 / 327).

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

Additive 2026-11-24 (QA-T-03, QA-T-04): each row of `GET /api/market/quotes` and of the
market-context quotes slice adds `close_price`, `close_day`, `close_kind`, `close_source_system`
and `close_simulated` (the previous close of the same hub and tenor from the desk's daily
closes, a month-ahead close only for the same delivery month, else the feed's prior settlement
with no day) and `as_of_utc`, `age_seconds`, `stale_after_seconds` (the source's declared
cadence) and `freshness_state`. No existing field changes.

Additive 2026-11-24 (QA-R-07, QA-R-03): each row of `GET /api/portfolio/credit-exposure` and
`GET /api/portfolio/mandate-usage` adds `marks_as_of` (the day of the daily close its marks come
from: the least current of its hubs' newest closes; `null` on a mandate, which is measured in
MWh), `state` (`current`, `late` one business day behind, `stale` more, `never`; a mandate is
`current`) and `freshness_state` (the same verdict in the quotes' words: FRESH, LATE, STALE,
MISSING). Each row of `GET /api/portfolio/position-ladder` adds `marks_as_of` and `state` (the
hub's newest close), and the payload adds `marks_as_of` and `marks_state` (the least current hub
held). The monitoring scan adds one `limits` alert, `alert_type` `marks_stale` (fingerprint
`marks_stale:credit`, severity warning, book-scoped), while the marks behind any credit line are
late or stale. `GET /api/access/users` rows and the `user` of `POST /api/access/users` and
`PATCH /api/access/users/{id}` add `segregation_warning` (`null`, or `code`
`segregation_of_duties`, `roles`, `message` when the grant holds ANALYST with REVIEWER); the
grant is not refused. No existing field changes.

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
| `GET /api/lng/cargoes/plans`, `GET /api/lng/cargoes/{cargo_id}/plan` | `cargo.vessel_imo`, `cargo.loaded_mwh`, `cargo.departed_at_utc`, `cargo.imported_at_utc`, `cargo.hub`, `cargo.slot` (`slot_id`, `terminal`, window, `send_out_mwh_per_day`), `cargo.changed` (`at_utc`, `kinds`, `by`, `eta_before_utc`); on the plan also `hedges[]` (`hub`, `month`, `mwh`, `reference`, `created_by`, `created_at_utc`), `slot_options[]` (`slot_id`, `terminal`, window, `send_out_gwh_d`, `held_by`, `free`) and `contract.mspa` (`laytime_hours`, `demurrage_usd_per_day` from the master agreement); on each board line also `next_action`, `next_expiry` (a suggestion each, or null) and `months[]` (the plan's hub months) | Additive 2026-11-24 for the cargo board and plan screen (QA-L-05). Nothing existing changes: no path, no status code, no figure. `changed.by` is the person who recorded the hedge set for a hedge change, else `import <source_system>` (the `cargo.changed` event names no person); `kinds` is `["recorded"]` for the first recorded state. `next_action` is the non-deadline suggestion due first. `slot_options` lists the book's own or unbooked slots whose window has not closed; `free` is false when another cargo holds the slot. A client that ignores the fields sees the previous payload |
| `GET /api/portfolio/position-ladder` | `rows[].cargoes` (JSON only), `legs.cargoes` (2026-11-24, QA-L-03) | Per row, the firm's cargoes in it by `cargo_id` with their `physical_mwh` (plan send-out) and `financial_mwh` (recorded hedges); `[]` for a row with none. `legs.cargoes` counts the cargoes on the ladder. CSV/XLSX/PDF downloads keep their columns |
| `GET /api/route-cost/upstream-contracts/{contract_id}/revisions` and `.../revisions/{contract_revision_id}` | `snapshot.payment_terms` (additive; `schema_version` may be `upstream-contract-revision/v2`) | The captured declaration is served read-only from the verified immutable revision for revisions captured while terms were declared; v1 revisions keep `payment_terms: null` and their pinned bytes/hash. The evidence warnings state that a capture neither asserts when terms applied nor resolves a payment date |
| `PUT /api/settings/notification-channels/{channel_id}`, `GET /api/settings/notification-channels` | `categories` values `opportunity` and `nomination` (2026-11-24, M7) | Opportunity alerts (new engine, routed to the trader) and gas-day nomination deadlines and delivery alerts (routed to operations) now have their own category, so a scheduler can subscribe to nominations without every market alert. A channel whose categories include `alert` still receives both (an umbrella), so an existing subscription loses nothing; an empty list still means every category |
| `PUT /api/settings/notification-channels/{channel_id}`, `GET /api/settings/notification-channels` | `categories` values `cargo` and `desk_head` (2026-11-24, LNG-2) | `cargo`: a cargo change's hedge proposal for the LNG trader; `desk_head`: a cargo change material by `lng.material_change_mwh`. A channel subscribed to `alert` does not receive either; the scheduler's and risk's cargo messages use `nomination` and `limits` |
| `GET /api/lng/cargoes/plans`, `GET /api/lng/cargoes/{cargo_id}/plan` | `cargo.eta` (additive, 2026-11-24, LNG-2) | What the ETA rests on: `basis` (master_notice, ais_declared, feed_estimate, schedule, manual or `null`), `confidence` (high, medium, low or `null`), `source` (the source system that set it), `recorded_at_utc`, and `text` in English words |
| `GET /api/lng/cargoes/plans` | `[].attention` (additive, 2026-11-24, LNG-2) | The open role messages about the cargo the caller may see (the cargo's book), `[]` for none; `mine` is true when the role matches one of the caller's job functions |
| `GET /api/lng/cargoes/{cargo_id}/plan` | `roles` (additive, 2026-11-24, LNG-2) | Each role's message about the cargo's last change, open or withdrawn within the last day; nothing in it is executed |
| `GET /api/desk/today` | `needs_me` items of `kind` `cargo`, with `role` and `cargo_id` (additive, 2026-11-24, LNG-2) | The open cargo messages for the caller's own roles (job functions), critical first; `target` opens Desk → Cargoes at the cargo; `why` names the alert |
| `GET /api/monitoring/alerts` | `category` values `lng_hedge`, `lng_schedule`, `lng_exposure`, `lng_material`; `entity_type` `lng_cargo` (2026-11-24, LNG-2) | One alert per cargo and role, book-scoped like limits; resolved with `evidence_snapshot.withdrawn` when a later change makes it moot |
| `GET /api/monitoring/alerts` | `category` value `capacity`; `alert_type` values `tariff_publisher_stale`, `tariff_publication_missed`, `capacity_window_opening`; `entity_type` values `tariff_publisher`, `capacity_notice` (2026-11-25, TAR-1) | A publisher read later than its cadence, an operator without next-period reserve prices 30 days before the July yearly auction, and a capacity auction or slot window opening within three days (monthly auctions are not alerted); nothing is booked or bid |
| `GET /api/desk/today` | `needs_me` items of `kind` `reconciliation`, with `break_kind`, `explanation`, `explanation_zh`, `quantity` and `deadline_utc` (additive, 2026-11-25, SCHED-1) | A scheduling break due within 3 hours of its cut-off, or with no renomination left, in the caller's gas-day scope; `target` names the Today Reconciliation row and the gas day |
| `GET /api/monitoring/alerts` | `category` value `gas_day_break`, `entity_type` `gas_day_break` (2026-11-25, SCHED-1) | One alert per break near its cut-off, book-scoped; notified in `nomination`; resolved with `evidence_snapshot.withdrawn` when the break is fixed or the gas day ends |
| `GET /api/market/quotes` | per row `resolved_price` (`hub`, `period_start`, `period_end`, `side`, `value`, `unit`, `value_mwh`, `unit_mwh`, `kind`, `source_system`, `as_of_utc`, `state`, `freshness_state`, `simulated`, `basis`, `reference`) (additive, 2026-11-24, P-08, QA-T-02, QA-L-22) | The one price every screen shows for the row's hub and delivery window at the read instant, from `domain/market/price_resolution` (freshest in-date tick or settlement, else the firm's mark, else the freshest held, stated stale; entitled sources only). The row's own quote fields are unchanged; `null` where nothing is held for that window |
| `GET /api/desk/today` | `resolved_price` on the `key_figures` `price.<hub>` items, on `market.hubs[].front_month` and on the `book` row's `mark` (additive, 2026-11-24, P-08) | The same object as on the Prices board for the front month; `null` where no price is held. `close_day` stays the last month-ahead close |
| `POST /api/analysis/brief` | `resolved_prices` (top-level list, additive, 2026-11-24, P-08) | One `resolved_price` object per hub line in the prices section; the sections' shape is unchanged |
| `GET /api/portfolio/position-ladder` | `rows[].resolved_price` (JSON only, additive, 2026-11-24, P-08) | The price behind the row's `mark`; `null` where no price is held. `mark_method` may also read `firm_mark` (below) |
| `GET /api/research/spreads/board` | `locational[].tenors[].legs[].resolved_price` for month-ahead legs on a live read (no `as_of`) (additive, 2026-11-24, P-08) | The price every other screen shows for that leg's hub and month; the spread itself still compares closes with closes |
| Valuation snapshot price inputs (opportunity evaluations, LNG cargo economics) | `detail.price_kind`, `detail.state`, `detail.resolution` (additive, 2026-11-24, P-08) | The resolver's kind, freshness state and basis for the price the evaluation used |
| `GET /api/opportunities/{opportunity_id}` (`object.assumptions[]`, and the version payloads and case evidence that freeze it) | `book_id`, `set_id`, `set_name`, `set_version` (additive, 2026-11-24, P-11) | The approved set the value was read from: `book_id` names the book whose own set holds it, `null` for the firm-wide set; `origin` stays `firm_set`. A book-scoped value's `input_key` is `assumption:<key>@book:<book_id>`, and its dependency key stays `assumption:<key>` |
| `GET /api/settings/organisation`, `PUT /api/settings/organisation` | `ai_features` (object: registered AI use to boolean; additive, 2026-11-24, GOV-1) | A switch per AI use (`domain/ai/register.py`). A use left out is on. A `PUT` merges the switches it sends over the stored ones. The response shape is otherwise unchanged |
| `POST /api/monitoring/alerts/{alert_id}/analysis` | `provider_status` value `switched_off` with warning `ai_use_switched_off:alert_analysis` (additive value, 2026-11-24, GOV-1) | The organisation switched alert analysis off: no provider call, `answer` is `null`, `analysis_id` is `null`, the alert's own text stands |
| `POST /api/analysis/query`, `POST /api/reports/portfolio` | provider status `AI_USE_SWITCHED_OFF` (additive value, 2026-11-24, GOV-1) | The organisation switched the analysis use off: no provider call, the deterministic answer stands |
| Audit rows of AI requests (`ai.explain` for explain, brief and market report; `ai.ask`, `ai.spreads`, `ai.report_plan`, `ai.alert_analysis`; `llm.invoke` for analysis query and portfolio report; `monitoring.enrichment.provider_call`) | `after_summary.ai` (`use`, `prompt_version`, `prompt_fingerprint`, `model_id`, `model_evaluated`, `calls`, `hashes[]` with `input_sha256`, `output_sha256`, `status`) (additive, 2026-11-24, GOV-1) | Set when a model was called. Hashes only, never the text. `GET /api/audit/events` shows it where it shows `after_summary` |
| `GET /api/access/market-data-licences` | `usage_30d` per licence (`principals`, `reads`, `exports`, `last_read_utc`) (additive, 2026-11-24, GOV-1, P6) | Recorded use of the licence's source family over the last 30 days: distinct people, request count, file exports and the last read. Zeros where nothing was recorded |
| Every report file (`format=csv`, `xlsx`, `pdf` on the routes that offer it) | response headers `X-Eurogas-Export-Decision` (`allowed` or `restricted`), `X-Eurogas-Licensed-Sources`, `X-Eurogas-Export-Restrictions`; XLSX and PDF description rows `Licensed data` and `Use` (additive, 2026-11-24, GOV-1, P6) | The export decision for the licensed families the file's rows were read from. Columns and rows are unchanged |
| `GET /api/portfolio/map-situation` | `assets[]` (`asset_id`, `kind` `lng_terminal` or `storage`, `name`, `country`, `eic`, `location`, `capacity[]`, `flow[]`, `stock`), `asset_rule`, `flow_days[]` (`gas_day`, `flows[]`), `cargoes[].eta` and `cargoes[].position_basis` (additive, 2026-11-24, MAP-1) | The map's terminals and storage sites with ENTSOG's newest firm technical capacity per direction (energy, gas day, source, receipt time), the point's newest closed-day flow, and GIE inventory with `basis` `site` or `country_aggregate`; `flow_days` holds the stored closed gas days of the entitled flows for the map's day scrubber; `eta` says what a cargo's ETA rests on (the LNG-2 object; a confirmed contract cargo reads `contract_window`), and `position_basis` is `reported` when the feed reported the position, else `null`. Every list follows the same rule as the existing items: book items by portfolio isolation, market rows by the caller's data scopes. No path, status code or existing field changes; public census unchanged |
| `GET /api/portfolio/position-ladder` (and the rollup) | `rows[].index_mwh`, `rows[].physical_price_mwh`, `rows[].price_exposure_mwh`, `totals.index_mwh`, `totals.price_exposure_mwh`, rollup `price_exposure_mwh`, `close_series` (per hub: `tenor`, `source_system`, `closes`, `first`, `last`); `curve[].basis`, `curve[].as_of`, `curve[].age_days`, `curve[].method` value `not_available` (with `price` null) (additive, 2026-11-26, quant review) | An index-priced contract's flat-price exposure on its index; `net_mwh` keeps its meaning (net volume). `hedge_ratio`, `tenor_exposure`, `gross_tenor_mwh`, the shock scenario and VaR now read price exposure (see Deliberate Narrowings) |
| `GET /api/portfolio/hedge-approvals` and the hedge-gap snapshot rows | `months[].price_exposure_mwh` (additive, 2026-11-26); `hedge_pct`/`room_mwh` `null` for an index-priced contract; breach `APPROVAL_INDEXED_HEDGE_OPEN` | An index-priced contract has no flat-price exposure to hedge; a linked trade is an open position |
| `POST /api/research/spreads/history` (spread lab) | `metrics.pnl_basis` (`traded_closes` or `not_computed_day_ahead_leg`) (additive, 2026-11-26) | With a day-ahead leg the money figures (`total_pnl`, `pnl_per_mwh`, `hit_rate`, `max_drawdown`, `best_trade`, `worst_trade`, `sharpe_annualised`, points' `pnl`/`cumulative_pnl`/`drawdown`, trades' `pnl`/`pnl_per_mwh`) are `null`: a signal study |
| Strategy-lab runs (`POST /api/strategy-runs` `BACKTEST`, the stored result snapshot) | `evaluation_kind` `signal_study`, `pnl_basis` `decision_time_margin`, run warning `SIGNAL_STUDY_DECISION_TIME_MARGIN` (additive, 2026-11-26) | The paper P&L is the margin at the decision's own reference price, not a realised P&L |
| `GET /api/research/spreads/board` locational rows, `GET /api/desk/today` spreads | `route.marginal` / `route_cost.marginal` (`product`, `capacity`, `commodity`, `fuel_pct`, `fuel`, `flow_not_held`, `total`, `holder`, `sunk_capacity`), `route_cost.product` (additive, 2026-11-26) | `route.product` now names the marginal product (`DAILY` for day-ahead, `MONTHLY` for a month) instead of `ANNUAL`; `cost` is the marginal cost; yearly capacity is `sunk_capacity` |
| Network flow result (`optimization.network_flow`) | `infeasible_demand_mwh`, `uneconomic_demand_mwh`, status value `uneconomic`, warnings `REQUIRED_DEMAND_NOT_DELIVERABLE` / `REQUIRED_DEMAND_UNECONOMIC` (additive, 2026-11-26) | A deliverable but loss-making requirement is uneconomic, not infeasible |

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
| Strategy laboratory: `/api/strategies*`, `/api/strategy-versions/*`, `/api/strategy-runs*`, `/api/backtest-experiments*`, `/api/strategy-lab/*`, `/api/shadow-monitors*`, `/api/shadow-evaluations/*`, `/api/shadow-alerts*`, `/api/shadow-runtime/status`, `/api/research/strategy-tracks*`, `/api/internal/shadow-scheduler/tick`; the deferred governed research agent `/api/agent/research`, `/api/agent/runs*`, `/api/agent/profiles`, `/api/agent/plans/validate`, `/api/agent/strategy-ir/validate`; the `strategy.*`, `backtest.*` and `shadow.*` capabilities; the release-metadata keys `backtest_engine_version`, `legacy_backtest_engine_version`, `strategy_schema_version`, `strategy_run_schema_version` | 2026-11-27 (owner approval, `ARCHITECTURE_V3_PLAN.md` section 5) | removed with the feature | **Removed**: the paths answer 404 and migration `0098_remove_strategy_laboratory` drops their tables (irreversible). The entries above that declare these paths, and the strategy sharing section below, are kept as history. `selected_strategies` on `POST /api/reports/portfolio` stays declared and refused, so a caller that still names a strategy is told so rather than answered with the whole snapshot |

## Deliberate Narrowings

Behaviour changes that refuse more than they used to, recorded here because they are visible to a
caller rather than additive.

| Surface | Change | Why |
|---|---|---|
| Every `/api` path except the credential-exempt ones | **A caller that presents no credential is refused.** Before D1 the `development` and `internal` profiles installed no authentication and served such a caller as the compatibility principal (data scopes `("*",)`, role `OPERATOR`). They now answer 401 `public_api_token_missing` when a deployment token is configured, or 503 `public_api_token_not_configured` when none is, and the identity dependency adds its own 401 `authentication_required` refusal as a backstop. The exempt paths are `/api/auth/*`, `/api/dev/auth/*`, `/api/health` (so `live` and `ready`), `/api/dev/health` and `/api/internal/health` | Owner decision D1: identification is the default and trusting the network is a deployment's own, reported statement. The SDK, CLI, MCP and Web clients are unaffected - they already present the deployment token or a session |
| `POST /api/market/ticks` | **`replay` is no longer accepted, and the answer carries only `quotes` and `trades`** (2026-11-27). The request model forbids unknown fields, so a feed adapter that still sends `replay` is answered 422; the `evaluation` and `subscribers` members of the answer are gone | `replay` only chose the instant tracked strategies were evaluated at, and the inline evaluation left with the strategy laboratory (it coupled research code to the tick write path). The demo exchange simulator no longer sends it |
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
| `GET /api/portfolio/position-ladder` and every read built on its legs (Today's `book` and `key_figures` rows, the desk brief, mandate usage, the valuation snapshot's positions, the book report) | **The firm's cargoes are on the ladder (2026-11-24, QA-L-03, QA-R-26).** A cargo of the firm (book set, not ballast) adds its plan's send-out by gas day at the terminal's hub as physical legs, and the hedges the desk recorded on it (`PUT /api/lng/cargoes/{id}/hedges`, not retired) as financial legs over their delivery month; both are volume only (not valued, counted in `unpriced_rows`) and named in a warning. Nothing is counted twice: a cargo that a DES cargo contract on the ladder names adds no send-out, and a hedge whose `reference` is a trade on the ladder is not added. The FOB warning ("not on a European hub") is no longer given for a cargo whose plan is on the ladder. `legs.physical`/`legs.financial` count the cargo legs (one per gas day, one per hedge). The gas day (`My gas day`, `GET /api/portfolio/daily-balance`), the opportunity residuals, credit exposure and the hedge-approval contract list are unchanged: the gas day already takes the send-out from the slot line, and a recorded hedge is not a booked trade or a contract | The desk head's P&L and hedge ratio missed more than 4 TWh of cargo exposure and hedges |
| `GET /api/lng/cargoes/{id}/plan`, `POST .../plan/what-if`, the board's `next` | **A roll is due before the earlier of its two months stops trading (2026-11-24, QA-L-02).** `due_utc` of a `roll` suggestion is the close of whichever of `from_month` and `to_month` stops trading first; before, it was always the close of `from_month`, so a backward roll (the cargo now arrives a month earlier) was due after the target month had stopped trading. A roll into a month that has stopped trading is still not suggested (`short_notice` instead) | A roll from Jan-27 to Dec-26 was due 31 Dec while Dec-26 stops trading on 27 Nov |
| `GET /api/lng/cargoes/{id}/plan` and the board | **No gas in kind and nothing delivered without a berth (2026-11-24, QA-L-06).** With no berth (`missed`, `no_slot`) `gas_in_kind_mwh` and `delivered_mwh` are 0; before, gas in kind was still deducted and `delivered_mwh` held the energy at the ETA. Added `energy_at_eta_mwh` (loaded less boil-off to the ETA) on every plan. A `last_change` that misses the slot now shows the delivery lost, not gained | The figures did not add up (1,000,000 against 1,009,840 MWh) |
| `PUT /api/market/firm-marks` | **Refused with the tick bands (2026-11-24, QA-R-05).** A mark is checked against the per-unit plausibility band `POST /api/market/ticks` uses (`domain/market/feed.py`): in EUR/MWh up to 500 and, for a month or longer, not below 0 (a one-day period may go to -50); in GBp/th up to 1,500 (-150 for a day). Other units in EUR or GBP are converted to those first; USD and CAD units keep the old -500..5,000 bounds. Outside answers `422 value_implausible` with the cell's `index` and the band in `message`, and nothing of the grid is stored. Before, 4,200 and -50 EUR/MWh on a forward month were stored | Hands-on review QA-R-05: an implausible firm mark reached valuations as the firm's own figure |
| `GET /api/projections/market-context` (slice `freshness.state`, `data_sources` rows), `GET /api/projections/portfolio-snapshot` (`data_sources` rows) | **One freshness rule (2026-11-24, QA-R-07).** Where the rows name a source the connector manifests declare, the state is the freshness contract's (the source's `FreshnessPolicy` and calendar, the rule `GET /api/desk/today` `stale_figures` uses): within the normal age `FRESH`, then `LATE` up to the stale threshold, then `STALE`, none `MISSING`. Before, anything older than the declared expectation was `STALE` (an EEX tick 10 minutes old; it is now `LATE`, stale after 3 days). The `SOURCE_STALE` warning follows `STALE` only. A slice whose rows name no declared source keeps the expectation-only judgement. `expected_within_minutes` and the block's keys are unchanged | The Data feeds popover said "Stale" for every feed while Today said every figure was current |
| `GET /api/desk/today` (`rows[0].tightest_limit` for a credit line) | **The credit line's own marks (2026-11-24, QA-R-07).** `as_of` and `state` are the row's `marks_as_of` and `state` (its hubs' least current close); before, the newest close of any hub, so a line marked at an old hub could read current | One judgement for the Limits page, Today and the `marks_stale` alert |
| `GET /api/stream/opportunities` | **Serves the opportunity engine, not the legacy intraday scan (2026-11-24, M7).** Before, the stream sent `IntradayOpportunityRecord` rows with their figures. It now sends `opportunity` events with `status` `open` or `withdrawn` (a withdrawal is pushed when an opportunity leaves the listed states or its validity window ends) and `evaluated` events when an evaluation finishes; an event carries no figure. Each event is filtered by the opportunity's own read rule (every source family granted; every book visible unless the lane is `market`). Gas-day deadline notifications move from category `alert` to `nomination`, data-source alerts from `alert` to `source`; each body ends with the alert's owner and escalation | One opportunity model on every surface: the page, the alerts and the stream now agree, and the legacy scan's duplicate alerts are gone (07 R11). Legacy rows stay readable at `GET /api/market/opportunities` |
| `GET /api/desk/today` (`price.<hub>`, `market.hubs[].front_month`, `book` `mark`), `POST /api/analysis/brief` (prices section) | **One price per hub and month (2026-11-24, P-08, QA-T-02, QA-L-22).** The month-ahead figure is the resolver's price: a live tick in date by its source's freshness policy beats yesterday's close; `as_of`, `state`, `simulated` and `source` are that price's. The day change is measured against the previous close of the same delivery month (none across a month roll), and Today's book day P&L follows the change shown. The brief's line date is the price's as-of day. Day-ahead figures are unchanged | Up to three prices for one month at one instant |
| `GET /api/portfolio/position-ladder` and every read built on `ladder_inputs` | **Marks from the resolver (2026-11-24, P-08).** A month's mark is the freshest in-date tick or settlement, else the firm's current mark (`mark_method` `firm_mark`, new value), else the curve or close fill as before; `flat_months` is recounted after it | The ladder marked the demo curve while the board showed a fresher quote |
| `GET /api/lng/cargoes/{cargo_id}/plan` (`inputs[]`, the `ETA` row) | **The ETA's source says what it rests on (2026-11-24, LNG-2).** `source` was the fixed text "cargo record eta_utc"; it is now "ETA from <source system> (<basis in words>, <confidence>)", with "basis not stated" and "confidence not stated" when the import did not say. A client that matched the old text must read `cargo.eta` instead | Lesson P3: an estimate says it is one; the trader weighs a delay by who reported it |
| Valuation snapshot prices (opportunity scan, LNG cargo economics) | **A stale quote no longer beats an in-date settlement (2026-11-24, P-08).** The price input is the resolver's; a quote is preferred only while it is in date. Prices are read from the last 400 days before the snapshot instant | A quote of any age was taken before settlements |
| `GET /api/opportunities`, `GET /api/opportunities/{opportunity_id}` (type `sell_down`; `locational` day-ahead candidates) | **Each book's own set and the gas day's residual (2026-11-24, P-11).** The firm-wide evaluation reads a book's own approved assumption set before the firm-wide set (sell-down cash-out discount and premium; locational load factor, fuel and shrinkage, short-term multiplier); a book's cash-out rate in another currency than the hub's is not used. The residual is the book's daily balance for tomorrow from the gas day's own lines (`GET /api/portfolio/daily-balance`, `My gas day`), within the book's band, no longer scaled by the measured delivery ratio (the snapshot's residual inputs say `definition: gas_day`, `delivery_ratio_applied: false`). Sell-down records that read "Cannot evaluate" are now valued where a book owns the rate, their figures change, and the volume leg and first falsifier are reworded (evaluator version 2). Advisory only | Persona review P-11; one balance with QA-T-07 |
| Governed writes: `PUT /api/portfolio/credit-lines/{counterparty_id}`, `PUT /api/portfolio/trader-mandates/{mandate_id}`, `PUT /api/portfolio/hedge-approvals/{contract_id}`, `PUT /api/portfolio/lng-terminal-terms/{terminal_id}`, `PUT /api/opportunities/settings`, `POST /api/assumption-sets`, `POST /api/assumption-sets/{set_id}/versions`, `POST /api/assumption-sets/{set_id}/versions/{version}/approve`, `PUT /api/market/firm-marks`, the user, group, licence and key writes under `/api/access/*` and `/api/me/api-keys`, `PUT /api/credentials/{provider_id}`, `DELETE /api/credentials/{provider_id}`, `PUT /api/lng/cargoes/{cargo_id}/hedges`, and the internal identity writes | **Audit is part of the write (2026-11-24, GOV-1, P5).** When the change's audit row cannot be written, the write answers `503` with `detail.code` and `error` `audit_unavailable` (family DEPENDENCY, recoverability `retry`) and `detail.action` naming the audit action, and nothing of the change is stored. Before, the change could succeed with no audit row. Reads are unaffected. The user and licence update audit rows now also carry `before_summary` and `after_summary` | A governed change must be attributable (lesson 5 in the competitive study) |
| `PUT /api/settings/organisation` | **A governed write, and `ai_features` is checked (2026-11-24, GOV-1).** The audit row is written in the same transaction; when it cannot be written the change is not stored and the call answers 503 `audit_unavailable` (before, the audit failure was swallowed). The row now carries `before_summary` and `after_summary`. An `ai_features` key that is not a registered AI use, or a value that is not a boolean, answers 422 `setting_invalid` | AI switches are a control; a change to one without its audit row is not allowed (P5) |
| Every AI surface (`POST /api/analysis/explain`, `/brief`, `/ask`, `/query`, `POST /api/reports/market`, `/plan`, `/portfolio`, `POST /api/research/spreads/interpret`, `POST /api/monitoring/alerts/{alert_id}/analysis`, alert enrichment) | **A use the organisation switched off makes no provider call (2026-11-24, GOV-1).** The reader gets the rule text with basis `rule`, as when no provider is configured. When the settings store is configured but cannot be read, AI is off | A per-use kill switch (NIST AI RMF Manage 2.4) |
| Capability calls made for a model: `POST /api/agent/research` runs and the MCP capability tools | **Refused outside the model tool allowlist (2026-11-24, GOV-1).** A capability the AI use does not list, that none of the caller's roles allows a model to call, or that is never called by a model (`dataset.export`, `review.record_analytical_decision`, `shadow.start`, `shadow.pause`, `shadow.resume`, `strategy.freeze_version`) is blocked with `PERMISSION_DENIED` and detail `ai_tool_not_allowed: ...`. The refusal is audited (`ai.tool.refused`). The same capability called directly by a person is unchanged | Bounded agency (OWASP LLM Top 10, excessive agency) |
| `POST /api/capabilities/{capability_id}/invoke` and the MCP capability tools (`CapabilityResult`) | **Refusals traced, results checked, confirmation by a person only (2026-11-25, CODEX-1).** `execution_metadata` now names the capability, version, principal, agent run and argument hash on a `BLOCKED` result too, and carries `output_hash` on a success. A success whose data breaks the capability's declared `output_schema` is answered `BLOCKED` `INTERNAL_ERROR`. A call that ran past its declared `timeout_policy` carries a `TIMEOUT_OVERRUN` warning. `quality_state` is `NOT_ASSESSED` unless the handler checked its evidence (it was `VERIFIED` by default). `human_confirmation` counts only from a signed-in person: from the deployment token, a service account or a model acting for an AI use it is answered `HUMAN_CONFIRMATION_REQUIRED` with the reason, and confirmations and writing calls are audited (`governance.agent_capability`). A request with no identity is 401, as the app-wide dependency already answered; the route no longer falls back to a wildcard analyst. No field is removed or renamed | Human oversight comes from a human; honest provenance (NIST AI 600-1); fail closed |
| Every report file (`format=csv`, `xlsx`, `pdf`) | **A file of licensed data without registered export terms is refused (2026-11-24, GOV-1, P6).** When the rows were read from a vendor-licensed family that is neither in the governance register nor covered by a current licence in the licence register, the file answers 403 `export_denied` with `licensed_families`. The JSON read of the same rows is unchanged | Fail-closed export policy (`ExportDecision`): a file leaves the platform |
| `GET /api/portfolio/position-ladder`, credit exposure, the portfolio report, Today's book | **Marks, VaR and MtM inputs (2026-11-26, quant review).** VaR needs 250 one-day changes (it was 20) and says "not enough history" below; it reads one product and one source per hub and no move across a contract roll. The curve is one snapshot per hub with staleness limits; an unquoted month is not available (no flat fill with the latest close, which could be a day-ahead price), so more leg-months can be unvalued. MtM is a present value at the forward FX per delivery month, discounted to the payment date. Credit replacement value likewise | The same figures were computed on spliced products, roll jumps, stale and mixed quotes, spot FX and no discounting |
| `POST /api/optimization/storage-dispatch` | **Bounded grid (2026-11-26).** `inventory_step_mwh` defaults to the working range over 200 levels (was 1 MWh); more than 1,000 levels, 400 periods (also a request `max_length`) or 6,000,000 transitions is refused 422 | A 1 TWh facility at 1 MWh was 10^6 levels; the period list was unbounded |

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
| `/api/support/reports` | POST | READ (any signed-in user) | Report a problem to the IT desk with diagnostics, or send a suggestion (category `suggestion`, stored as P4) |
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
