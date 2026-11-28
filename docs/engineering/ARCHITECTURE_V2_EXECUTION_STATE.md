# Architecture V2 execution state

Read this before planning (AGENTS.md rule 2). Newest entry first. When this file passes about
500 lines, move the older entries to `history/` and link them below, so the current state
stays quick to read.

Earlier entries: [history/ARCHITECTURE_V2_EXECUTION_LOG_TO_2026-10-30.md](history/ARCHITECTURE_V2_EXECUTION_LOG_TO_2026-10-30.md).

## 2026-11-28 — Package I: consented public sources are fetched (branch `sd-consent`, not pushed)

The owner reports written consents from twelve publishers (publicly available data, the firm's
own use, no resale); not seen by the development team.

- Consent records ship as data (`reference_data/publisher_consents.toml`,
  `domain/publications/consents.py`); the legal register states each with the finding it
  supersedes. Registry verdict `consented`: fetched only while the record exists and an
  administrator has not withdrawn it (Admin → Data sources → Watched publications, audited;
  `POST /api/publications/consents/{id}/withdraw|restore`).
- Scope enforced: consented families (`THE`, `NATIONAL_GAS_PRICES`, `MIBGAS`, `EEX_PUBLIC`,
  `ICE_PUBLIC`) are read by every identified user, never by an anonymous caller, and are
  internal use only in every file and report export decision.
- Fetched: THE DataExport (VTP daily average, imbalance prices, from 2021-10-01), National Gas
  API (SAP, SMP buy/sell, five years), MIBGAS yearly CSVs (PVB DA, M+1, Q+1, Y+1, from 2021),
  EEX TTF NGP 60-day file; EEX gas trading and holiday calendars, ICE Endex and IFEU schedules
  (the hand file is the fallback; EEX 24 and 31 December are early closes, 08:00-13:00 CET).
  Polite client: generic User-Agent, robots.txt, conditional requests, 2 s apart, back-off and
  Retry-After. EEX and ICE price tables, PRISMA and the LNG/storage operators: consented, not
  yet implemented.
- Board: published daily prices fill NBP/TTF/THE WD and PVB DA, M1, Q1, Cal, dated, no bid or
  offer; spreads never mix a real and a simulated leg; My gas day uses the published cash-out.
- Data model: migration `0102_publisher_consents` (one table, three states, two columns),
  reversible, `down_revision = "0100_watched_publications"` (0101 is another package's; the
  coordinator re-chains).

## 2026-11-28 — Package G: what is published is fetched, not typed (branch `sd-publications`, not pushed)

`docs/product/SMALL_DESK_PLAN.md` section 11 (owner, 2026-11-28; extends AGENTS.md rule 19).

- One registry of watched publications (`domain/publications/registry.py`): publisher, exact
  location, terms entry (required: no entry, no fetch), verdict (fetched, hand-maintained, link
  only), interval, parser. Terms of 21 publications read and quoted in
  `docs/legal/DATA_SOURCE_TERMS.md` ("Watched publications, checked 2026-11-28").
- One watcher on the existing pieces (`application/publication_watch.py`): news poller's
  fetcher and robots.txt check, raw pages kept once by digest, capacity notices, the tariff
  book's capacity alerts, notifications, the market-event outbox; run by the data scheduler
  every 15 minutes (`EUROGAS_NEXUS_PUBLICATION_WATCH=off` stops it). A document the parser cannot
  read holds the old record as "needs a person to confirm"; unreachable and not permitted are
  stated.
- Fetched: ENTSOG's CAM NC auction calendar (daily; verified live, 34 auctions for 2026/27); its
  auctions replace the rule-derived CAM dates. Exchange calendars (EEX, ICE Endex, ICE Futures
  Europe) stay hand-maintained, because their terms forbid storing them, with a dated check
  reminder and the link; the ICE lists in the file were corrected (Easter Monday, UK bank
  holidays). Everything else is link only.
- Desk → Board gains a Calendar tab; its coming week joins the events list. Admin → Data sources
  gains Watched publications (state of each, confirm a changed document: ADMIN, audited).
- Data model: migration `0100_watched_publications` (one table), reversible; chained after
  `0099_remove_strategy_laboratory`.

## 2026-11-27 — Strategy laboratory removed (branch `sd-rm-strategy`, not pushed)

Owner-approved removal of the strategy laboratory: the strategy registry, evaluation and
tracks, its decision-time "backtest" and the scheduled shadow runtime, including the inline
strategy evaluation in tick ingestion. Profit is fixed at decision time, so the "backtest"
proved no outcome. The spread laboratory, research datasets and leakage tooling, the
opportunity engine, the hand-written solvers, forward curve, position ladder, P&L, limits and
reports stay; the research bench (`/api/research/backtest`, `/api/research/shadow-run`) and the
NWE model shadow evaluation stay.

- Migration `0099_remove_strategy_laboratory` (renumbered from 0098 at the merge with
  `inno-merge-test`) chains after `0098_deal_position_source` (one head; `DB_SCHEMA_REVISION`
  0099) and drops 22 tables (registry, versions, runs, backtests,
  allocation targets, alerts, tracks, eight shadow tables). Declared `irreversible`: the
  downgrade refuses and going back means restoring the backup; `DATABASE_UPGRADE.md` says to
  export stored runs first. Identity groups and members stay as identity infrastructure. The
  full chain was applied on a scratch PostgreSQL 16 database; every dropped table is absent and
  `identity_groups`, `identity_group_members` and `market_trades` remain.
- Shared pieces moved to neutral modules rather than keeping the laboratory alive:
  `core/content_hash.py` (agent records), `domain/market_intelligence/price_series.py` (market
  discovery and research), `application/agents/review_access.py` (review capability),
  `db/models/identity_groups.py` + `db/repositories/identity_access.py` (identity groups),
  `api/routes/public/market_ticks.py` + `clients/web/src/api/promptMarket.ts` (licensed tick
  ingestion and the prompt desk read, without the evaluation hook).
- Removed: four public route modules (strategy lab, registry, tracks, shadow) and the internal
  shadow route, the agent research orchestration and shadow handlers, the strategy
  domain/application/repository/model packages, the SDK's
  strategy/shadow clients, `run_shadow_scheduler.py`/`backtest_benchmark.py`, the release
  metadata constants and manifest fields, the client pages/components/API client/store lanes,
  selection-context and inspector kinds, CSS selectors, permissions/capabilities and the unused
  translation keys. Old links (`?workspace=strategy`, `research:strategies`) still land on
  Research → Spreads; the `strategy` primary id now carries the Research label.
- Docs: the feature specs and user pages were deleted, indexes and current guides updated, SDK
  reference regenerated; historical wave/audit records stay as records. Tests that only covered
  the feature were deleted; mixed tests keep the surviving half (tick ingestion, review
  evidence, agent contracts, tick quotas).
- Validation: `ruff check .` clean; `check_markdown_links.py` resolves all 495 files;
  `generate_env_template.py --check` current; `pytest -q -n auto tests`: 8430 passed,
  268 skipped, 0 failed; Web `tsc --noEmit` clean, `npm test`: 1558 passed, 3 skipped,
  0 failed, `lint:css` clean; on PostgreSQL 16 the full Alembic chain, the gated upgrade
  tests and `validate_runtime_db.py` all report the removal's head with no
  missing required tables.

## 2026-11-27 — Position and P&L during the day from captured deals (branch `sd-ladder`, not pushed)

`docs/product/SMALL_DESK_PLAN.md` section 4 step 3, section 5 ("a new deal changes position and
P&L within one second") and section 9 (position units).

- One position source: `position_inputs.ladder_inputs` now reads the captured deals on every
  call (`application/captured_position.captured_book`), so the ladder, Today, credit exposure,
  mandate usage, the limit alerts, the opportunity stream, the reports and the daily pack all
  include them. The daily pack's context-variable overlay is removed.
- Same deal counted once, at read time: captured deals are paired with the ETRM trades in the
  book by the end-of-day check's own rule (`domain/deals/eod.pair_deals`: a pair recorded at a
  close, else the exchange reference, else hub, side and delivery period); the captured deal
  counts while its day is open, the ETRM trade once it is closed.
- Physical or financial from a rule file (`reference_data/desk/position_kinds.toml`, desk copy
  replaces it) with a per-deal choice by hand (`POST /api/desk/deals/position-kind`, audited);
  the ETRM entry sheet's physical column follows it.
- Exact decimal rows in desk units (th/d at NBP, MW elsewhere, MWh beside) for the captured
  deals in the ladder response (`captured`); the estimate wording on the ladder, Today, limits,
  limit alerts and the packs.
- Live: a `deals` topic on `/api/stream/live`; the deal routes wake the poller at once and make
  the position warm views unservable (`ViewSpec.follows_deals`); the web client re-reads on
  `deals` past the price throttle (`useLiveTopics` `immediateTopics`). Commit to notice measured
  3 to 8 ms with the wake, 1.3 s without (the default poll).
- Exchange holidays from a hand-maintained file (`reference_data/desk/trading_calendars.toml`).
- Data model: migration `0098_deal_position_source` (exchange reference on ETRM trades, the
  `deal_position_kinds` table), reversible.

## 2026-11-27 — Small-desk install and self-support, server part (branch `sd-install`, not pushed)

`docs/product/SMALL_DESK_PLAN.md` section 3 items 2, 3 and 7 (server) and section 7 (server).

- `deploy/small-desk/`: one compose stack (PostgreSQL on the SSD, config check, start-up schema
  check, reference seed, API, scheduler, market-events worker, Caddy gateway serving the web
  client and `/api` on one HTTPS address), release environment, local accounts with
  `EUROGAS_NEXUS_MFA_REQUIRED=all`, book isolation on, separate database roles, restart policies.
  No demo seed, simulated prices, Valkey, standby or SSO.
- `nexus <verb>` (`deploy/small-desk/nexus`, stdlib Python in `nexusctl/`, Python 3.10+): install,
  start, stop, status, backup, restore, update, undo-update, diagnostics. systemd units for boot
  and the nightly backup are the only Linux-specific part. Release folders are built by
  `scripts/release/package_small_desk_bundle.py`.
- `scripts/ops/upgrade_database.py` gained `plan --json` and `downgrade --to` (gated, audited,
  refuses to cross an irreversible or undeclared migration); `python -m
  eurogas_nexus.cli.desk_status` gives `nexus status` the schema, scheduler heartbeat, source
  freshness and backup marker. No data-model change.
- Rehearsed against real containers here (`tests/integration/test_small_desk_rehearsal.py`,
  opt-in with `NEXUS_REHEARSAL_IMAGE`). Runbooks: `docs/operations/SMALL_DESK_*.md`.
- Follow-up: `nexus install` records each step in `state.json` and continues from the step that
  failed when run again (keeping the first attempt's secrets); it refuses a finished installation
  and a database folder it did not create. `nexus uninstall` keeps the database, backups and
  secrets (`--delete-data` with the typed words removes them). The replaced-PC path
  (`--restore-from` + `--recovery-key`) is rehearsed: second factors and stored provider keys
  decrypt on the new PC. The release workflow's `small-desk` job attaches
  `eurogas-nexus-small-desk-<version>.tar.gz` (pinned to the published digest), and the artefact
  contract and the dry run include it.

## 2026-11-26 — Live-stream 429s while browsing fixed at the cause (branch `streamfix`, not pushed)

- Cause (measured on a local demo stack with a Playwright crawl, `scripts/uat/cold_load_requests.mjs`):
  each browser tab held four streams (quotes, opportunities, alerts, live) against the per-person
  cap of 5, re-opened all four on every cold load and the live one on every topic change, so one
  more tab, one more tester on a shared account, or a gateway that delivers the new request
  before the old close is processed hit the cap (two tabs: 429s on 2 of 8 pages, one console
  error per refused stream). A slot was freed only through the server's cancellation; a server
  that reports a disconnect through a failed write would have kept it until garbage collection.
- Client: ONE live connection per tab (`app/data/liveStream.ts`), every topic, reference-counted
  listeners, kept across page changes and workspace loads (10 s linger), backoff on drops, and a
  quiet `paused` state on a refusal ("Live updates paused" once in the top bar; retried after
  1 to 5 min) while pages re-read on a timer (`useLiveTopics` default fallback). The separate
  quotes/opportunities/alerts EventSources and `changeNotices.ts` are gone.
- Server: the live stream also carries the opportunity engine's `opportunity`/`evaluated` events
  (with `opportunities`). `CountedStreamingResponse` closes its stream however the response ends,
  a quiet stream sends a keepalive every 10 s, and the counted stream frees its slot at once on
  end, error or cancellation (`tests/security/test_stream_release.py`, a real server: 20 opened
  and closed in turn with a cap of 2, none refused; a third at once gets the coded 429 with
  `Retry-After`). `EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL` default 8 (tabs per person); the
  demo profile sets 40 (shared tester accounts).
- Quotas: the pool optimiser's automatic run (a heavy POST) went out on every cold load of any
  page (15 of 22); it now runs only on Position, Deals and Review. The replay of a recorded cold
  load mix (`tests/security/test_cold_load_quotas.py`) keeps a fast crawl inside the trial
  quotas. The admin throttle counts per person once signed in (per address before).
- Sources "infrastructure" no longer asks for capacity bookings without commercial reads (403 as
  platform administrator). The report catalogue answers 200 with `availability_state.code`
  (`ready`, `pending` past a 4 s probe budget, `unavailable`) instead of failing.

## 2026-11-26 — P1-D recovery and retention merged (branch `int2`, not pushed)

- `p1-D` merged onto int2 (P1-C + P1-A + secfix). Its migration is now
  `0096_retention_by_class` after `0095_security_hardening` (one head; `DB_SCHEMA_REVISION`
  0096), declared `conditional`: the downgrade refuses while a raw-page receipt has no inline
  page (`tests/integration/test_retention_migration_postgres.py`). Its ADR is Decision 41.
- Audit retention: seven years is the default and the floor (`EUROGAS_NEXUS_AUDIT_RETENTION_DAYS`
  cannot lower it); one prune path, secfix's dual-controlled, audited prune with its chain
  anchor; the retention job keeps the audit trail and trading records (`keep`).
- The retention pass runs inside the scheduler's locked iteration (a standby never prunes)
  and in the explicit system book scope, also when started by `scripts/ops/retention.py`.
- One database-error mapping (`core/db_errors.py`) for the middleware and the handlers:
  `runtime_db_timeout`, `runtime_db_unavailable` (lost store, no writable primary, a standby's
  25006) and `runtime_db_commit_unconfirmed` (no retry hint). A connection lost while the
  audit chain is sealed at commit is no longer swallowed (it became a PendingRollbackError).
- Failover connects per host under the 5 s connect bound, the timeout fix's socket tuning
  after; the start-up probe is one-off with a 10 s socket bound; readiness uses a one-off
  engine (probes no longer count in the pool metrics). Readiness and the new
  `eurogas_db_primary_writable` gauge share one standby check (alert `EurogasDatabaseReadOnly`).
  One table of timeouts in `docs/operations/DB_RUNTIME_HARDENING.md`.
- Compose: failover and start-up wait in every database user's settings; the object-store key
  only in the scheduler and ingestion services (not the API). `deploy/ha`: read-only roots,
  capabilities dropped (a node keeps the five its root start needs), no-new-privileges, the
  replication passfile on a node-only tmpfs, and the app and owner roles documented.
- The drill scripts' one-hour "connect timeout" workaround for the socket defect removed.
- Not verified here: the HA image (pgBackRest from apt) could not be built on this machine
  (no route to the Debian mirrors), so the hardened HA stack was tested only with the real node
  entrypoint on `postgres:16` without pgBackRest; rerun `scripts/ops/ha_drill.py failover`
  where the image builds.

## 2026-11-26 — Security remediation merged onto phase 1 (branch `int2`, not pushed)

- `secfix` merged onto P1-C + P1-A. Streams keep the per-process poller (`api/stream_hub.py`)
  with secfix's rules: header-only token, session and identity re-checks (now also roles: a
  lost commercial role ends the stream), and ONE per-person cap,
  `EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL` (5), counted across processes as expiring slots in
  the shared cache (per process without one); P1-A's `EUROGAS_NEXUS_STREAMS_PER_PRINCIPAL` is
  gone. The poller reads in an explicit `portfolio_scope.system_scope()`; each connection's
  guard applies its user's book scope, licences and commercial boundary
  (`tests/security/test_stream_book_scope.py`, two entities on one poller).
- Secfix's write/heavy quotas count through the shared-cache rate limiter (across processes).
- The scheduler, the upgrade command and the metrics exporter's reads run in the explicit
  system scope (`tests/security/test_background_scope.py`).
- Preflight: P1's serving checks plus secfix's start-up refusals (sign-in method, isolation,
  dual control, deployment token) reported by `config-check` before the API would crash-loop.
- Compose: secfix's hardening and per-service settings, P1's metrics tmpfs, workers and pool
  settings; Valkey hardened (read-only, no capabilities, non-root); the migration no longer
  receives the Valkey URL.
- The gated upgrade runs as the owner role and refuses up front as the application role;
  `alembic/env.py` now migrates the URL it is given (it used to prefer the environment's).
- The 5 s socket defect fixed: the connect bound no longer bounds every statement
  (`db/session.py`); a server-cancelled statement answers 503 `runtime_db_timeout` with
  `Retry-After`, is counted and leaves the connection usable; every engine audited; timeouts
  table in `docs/operations/DB_RUNTIME_HARDENING.md`. Load rerun in
  `docs/operations/API_SERVING_AND_SHARED_CACHE.md` (no 5xx; main reads still CPU-bound cold).
- Open: background jobs inside the API share its 30 s per-statement limit; the demo launcher
  needs a built web client to serve; per-person cold reads (phase 2).

## 2026-11-26 — Security review remediation (branch `secfix`)

- The 2026-11 security review (7 High, 10 Medium, 5 Low) worked through finding by finding:
  [SECURITY_REVIEW_REMEDIATION_2026-11](../security/SECURITY_REVIEW_REMEDIATION_2026-11.md);
  behaviour changes for installations in
  [the release note](../release/notes/SECURITY_HARDENING_2026-11.md).
- Book isolation on by default, enforced once in the ORM layer (`db/book_scope.py`); the
  commercial boundary is default-commercial; `risk.limits.read` and `PERM:` grants; OPERATOR no
  longer reads positions. Compatible with the role-model DRAFT ADR (phase 1 not started).
- Deployment token as a scoped service principal; licensed venue labels only from a connector
  key; hash-chained audit trail with a role split (`deploy/runtime/database_roles.sql`); TOTP;
  dual control with a cooling period and break-glass. Migration `0095_security_hardening`.
- Open: PostgreSQL row-level security, WebAuthn, an approval screen in Admin, KMS/Vault, image
  digests for PostgreSQL and Caddy, a query outside a request still sees every book.

## 2026-11-26 — Demo re-seed clear survives a feed-sized quote table (branch `seedfix`)

- Cause: `_clear` deleted `market_quotes` in one statement. `get_engine` passes its
  `connect_timeout_seconds` (5 s) to pg8000 as `timeout`, which pg8000 applies with
  `settimeout` to the whole socket, so it bounds every statement rather than only the
  connect. The continuous feed leaves the table feed-sized and `market_quotes` has no index
  leading with `source_system` (the lookup index leads with `hub`), so the DELETE is a
  sequential scan: 1,000,000 rows measured 0.73 s (Seq Scan, cost 0..35,756); at 5,000,000
  rows the seed's own engine raised `TimeoutError: timed out` after exactly 5.0 s.
- Fix: `_delete_in_batches` removes at most 5,000 rows per statement, commits per batch
  and logs progress (PostgreSQL by `ctid`, SQLite by primary-key range); `_clear` uses it
  for the quotes, prints/trades, market observations and the flow, storage, LNG, power, FX
  and rate series, still filtering on the simulated source only. The seed holds
  `SEED_CLEAR_LOCK` while clearing; the exchange feed checks it each loop and takes it in
  shared mode around each write, so a feed from a previous start (or a re-seed of a serving
  demo) pauses. The start already ran the seed before the feed. The FATAL exit is kept and
  the seed marker is written only after success, so the next start re-seeds (test).
- Measured on scratch PostgreSQL 16: a re-seed over 1,000,000 simulated quotes clears the
  table in 15.5 s over 201 batches (each statement well inside the 2 s socket timeout the
  test uses); the whole re-seed takes 26 s. With 200,000 quotes: 0.7 s clear, 12 s seed.
- Tests: batching helper (SQLite), the retry after a failed clear, the feed/seed lock, and
  `tests/integration/test_demo_seed_clear_postgres.py` (added to
  `scripts/ci/run_postgres_ci.sh`). Two stale tariff expectations (34; the quantfix merge
  made 34 legs x 3 capacity products) were corrected in the demo seed tests.
## 2026-11-26 — Phase 1, P1-A merged onto P1-C (branch `p1-int`, not pushed)

- Conflicts resolved keeping both sides: both runtime dependencies (`prometheus-client` 0.26.0,
  `valkey` 6.2.0 with `async-timeout` below Python 3.11.3), both hash pins unchanged in both
  locks; `THIRD_PARTY_NOTICES.md` regenerated (34 python-runtime packages); licence review 48.
- **Metrics, one mechanism.** P1-A's hand-written exposition lines are gone; its pool counters
  (`eurogas_db_pool_{checkouts,waits,timeouts,wait_seconds}_total`) and poller counters
  (`eurogas_stream_{polls,poll_seconds,poll_failures,refused}_total`) are `prometheus_client`
  counters in `application/process_metrics.py`, summed over workers. Pool gauges and counters
  read one source, `db.session.pool_state` (`pool_counters` plus occupancy); `observe_pools`
  still never imports the database layer. `eurogas_stream_open` dropped for P1-C's
  `eurogas_stream_connections{topic}`.
- New alert EurogasDbPoolExhausted (timeouts, or over 10 % of checkouts waited; 13 rules,
  promtool tests pass). Preflight warns when several API processes have no shared metrics
  directory. The poller logs a poll that cannot reach the store (JSON, throttled); before,
  the usual outage was answered with warning events and logged nothing.
- Checked: compose.scale.yaml multiplies only the API (scheduler and workers stay single,
  release never upgrades on start); only the API lifespan sets the 30 s statement timeout.
  Real 2-worker uvicorn with scratch PostgreSQL 16 and Valkey 8: one scrape, each family once,
  counters equal to the sum of the two workers' files (checkouts 92 + 98 = 190).
- Fixed tests that failed on one branch alone: four preflight tests (p1-C) and the liveness
  test (p1-A, `health_live` is async).

## 2026-11-26 — Phase 1, P1-A serving: one poller per process, several processes, Valkey (branch `p1-A`, not pushed)

- Decision record accepted and renamed:
  [2026-11-26-multi-process-api-and-shared-cache.md](../architecture/decisions/2026-11-26-multi-process-api-and-shared-cache.md)
  (Decision 40 in the decision log).
- Built: the per-process live-update poller (`api/stream_hub.py`, shared reads in
  `application/live_topics.Reads`, per-connection entitlement kept); no synchronous database call
  on the event loop (identity resolution, contract intake, import validation, entitlement
  audits, lifespan; a contract test guards it); the shared-cache seam with an in-process and a
  Valkey backend (rate limits, sign-in throttle, warm-view write signal, revocation notes on
  open streams); nine reader-independent warm views kept once per scope; pool sizing, request
  threads from the pool, a 30 s API statement timeout, pool and poller metrics; the load test
  `scripts/ops/load_test_desk.py`; `deploy/runtime/compose.scale.yaml` (4 processes + Valkey).
- New runtime dependency: `valkey` 6.2 (MIT), hash-pinned; no other pin moved.
- Measured on a shared 4-core machine: see
  [API_SERVING_AND_SHARED_CACHE.md](../operations/API_SERVING_AND_SHARED_CACHE.md#results-2026-11-26).
- Not done here: `LISTEN/NOTIFY` early wake of the poller (pg8000 delivers notices only on a
  round trip, so it would cost the same as the 1.5 s poll), warm-view values in Valkey (the
  write signal is shared, values stay per process), per-person views kept by scope (seven views
  read per-person state), cross-process stream caps (the cap is per process).

## 2026-11-26 — Quant review fixes (branch `quantfix`)

- Confirmed errors of the quant review fixed, each with a failing test first: VaR on one
  product and one source per hub (no day-ahead filling month-ahead gaps), moves within one
  contract (`domain/market/returns`, shared with the spread lab), 250-change minimum ("not
  enough history" below); index-priced legs carry their flat-price exposure on the index
  (`index_mwh`, `price_exposure_mwh`; `net_mwh` keeps its meaning) through hedge ratio, hedge
  bands, mandates, tenor exposure, shocks and VaR; the forward curve from one snapshot per hub
  (one as-of, settlements then the primary source, staleness per tenor, quoted-quarter shape,
  no flat fill, basis and age per point); spread-lab day-ahead legs are a signal study and held
  rolls pay costs; the strategy-lab run is labelled a signal study of decision-time margin;
  prompt-spread transport at the marginal (daily/monthly) product plus commodity and fuel, the
  yearly route kept as sunk capacity (demo tariffs gain simulated monthly/daily rows);
  network flow tells infeasible from uneconomic; storage dispatch grid scaled and bounded;
  MtM and credit replacement at forward FX per delivery month, discounted to the payment date;
  Today and the ladder read one horizon (`ladder_horizon`) and one net position
  (`net_position_by_hub`).
- Demo (seeded 2026-11-26T09:00Z): ladder MtM 84,903,959 -> 83,842,383 EUR; VaR 8,685,763 ->
  7,725,338 EUR (399 -> 386 scenarios); net 18,356,399 MWh, price exposure 17,908,000 MWh;
  NBP Dec-26 hedge 39.7 % -> 45.5 %; NBP-TTF transport 1.80 -> 2.25 (MA, monthly) / 2.70 (DA,
  daily) EUR/MWh with 1.80 sunk; Rhinmark replacement 19,377,360 -> 19,228,594 EUR.
- Not built (plan work, `ARCHITECTURE_V3_PLAN.md`): storage extrinsic value, swing/ToP,
  options, PFE, P&L attribution, power, the stored EOD ladder/VaR run.

## 2026-11-26 — P1-C: observability, scheduler safety, gated upgrades (branch `p1-C`, not pushed)

Plan v3 section 3.10 (and 3.2 for migrations), phase 1. Built:

- **Metrics.** `GET /metrics` (plain Prometheus text) for a scrape token
  (`EUROGAS_NEXUS_METRICS_SCRAPE_TOKEN`) and/or allowed networks
  (`EUROGAS_NEXUS_METRICS_ALLOWED_NETWORKS`); 404 with neither, served outside the route table,
  404 at both gateways. `prometheus_client` multi-process mode (`PROMETHEUS_MULTIPROC_DIR`,
  tmpfs in the runtime compose): latency histograms and counters by route group, method and
  status class; pool gauges and open streams summed over live workers. Database metrics at
  scrape time with aggregates (the old exporter loaded all of `ingestion_runs` per scrape):
  freshness aged by the clock against each source's stale rule, heartbeat age (+Inf when
  never), jobs, feed lag, outbox lag. `/api/runtime/metrics` keeps its JSON for the UI.
- **Logs and traces.** JSON lines (default in trial/release) with `request_id` and
  `principal_id`, redaction, one access record per request (route template, no address or
  query); Docker rotation in the runtime compose. OpenTelemetry seam, off by default.
- **Alerts.** `deploy/monitoring/prometheus/`: 12 rules, promtool unit tests (stopped
  scheduler fires), example scrape config; responses in `docs/operations/ALERT_RESPONSES.md`.
- **Scheduler.** PostgreSQL advisory lock (standby exits 3 with `--once`, takes over when the
  lock frees, notices a lost lock connection); heartbeat every 30 s while active. The demo's
  "no heartbeat, 0/42 scheduled" was real, not only a display fault: no scheduler process ran on
  the demo (its refresh loop called the ingest scripts directly), and the Runtime page counted
  schedules in source rows that only a scheduler scan creates. The demo now starts the product
  scheduler after its first catch-up (`EUROGAS_NEXUS_DEMO_SCHEDULER`, default on); the Runtime
  row reads the heartbeat (not running / stopped / the scheduler's own count and age).
- **Gated upgrades.** `scripts/ops/upgrade_database.py` (plan, check, upgrade, record-backup,
  on-start): backup marker within 24 h or an audited override; `lock_timeout` 10s and
  `statement_timeout` 1h in `alembic/env.py`; pending revisions with their reversibility;
  `database.upgrade` audit rows. Release compose `migrate` only checks; development and demo
  auto-upgrade through the same command (`EUROGAS_NEXUS_AUTO_MIGRATE`, ignored in trial and
  release). All 94 migrations declare `reversibility` (scripted,
  `scripts/dev/declare_migration_reversibility.py`); contract test for the declaration and for
  non-blocking index builds on large tables after 0094 (seven older blocking builds listed).

Decisions (P1-C):

1. **P1-C-1 `prometheus-client` added** (Apache-2.0 AND BSD-2-Clause, no dependencies; the gate
   passes). Locks updated with `uv pip compile` without `--upgrade`: only this pin moved.
2. **P1-C-2 `/metrics` outside the route table** (an outermost ASGI middleware), so the sign-in,
   permission and CSRF dependencies a scraper cannot satisfy are not bypassed per route, and
   the endpoint is not public API surface. Network binding is by allowed ranges, not a second
   listener (a second port cannot be shared by N workers).
3. **P1-C-3 OpenTelemetry not added to the locks.** Its licences pass the gate, but SDK plus
   OTLP exporter add about a dozen packages to every install for a setting that is off by
   default; the seam activates when a deployment installs them (MONITORING.md, Tracing).
4. **P1-C-4 Advisory lock, not a lease row**: no migration, released by PostgreSQL when the
   holder dies. SQLite (single process) uses a no-op lease.
5. **P1-C-5 Backup marker is an audit event** (`database.backup.recorded`), not a file: it
   lives in the database the upgrade runs against, works for pgBackRest or managed snapshots
   (`record-backup`), and auditors see it.
6. **P1-C-6 Auto-migrate refused in trial and release even when set**: plan 3.10 says never on
   start in production.
7. **P1-C-7 Job and failure alerts read last-hour gauges, not all-time counters**: pruning
   `job_records` would read as a counter reset and fire a false alert.
8. **P1-C-8 `create_index_nonblocking` ends a leftover transaction** in Alembic's autocommit
   block: under pg8000 Alembic's isolation-level read opens one, and `CONCURRENTLY` then fails.

No migration added; `DB_SCHEMA_REVISION` unchanged (0094). Verified on PostgreSQL 16
(scratch container): lock and takeover, upgrade gate, lock-timeout rollback, concurrent
index; end-to-end: 2 uvicorn workers summed in one scrape, a real Prometheus scraping with
the token, EurogasSchedulerHeartbeatMissing firing and clearing when a heartbeat started.

## 2026-11-26 — P1-D recovery and retention (branch `p1-D`, not pushed)

- Decision record accepted: `docs/architecture/decisions/2026-11-26-standby-backup-object-storage-retention.md`
  (was `DRAFT-...`), appended as ADR Decision 40 (Decision 41 after the int2 merge).
- Database tier `deploy/ha`: primary and hot standby, pgBackRest (MIT) to any S3-compatible store,
  one-command failover with fencing, rejoin by delta restore. Test object store SeaweedFS
  (Apache-2.0), test-only; MinIO not used (AGPL). No new Python dependency (S3 signing over httpx).
- Application during failover: `db/resilience.py` (start-up backoff, readiness fails on an
  unreachable or read-only database, 503 instead of 500, `runtime_db_commit_unconfirmed` for a
  commit whose outcome is unknown, failover hosts).
- Retention by class (`application/retention.py`, migration `0095_retention_by_class`,
  `DB_SCHEMA_REVISION` updated); raw pages stored once per digest; the 30/90-day deletion and
  `prune_runtime_data.py` removed; audit prune floor 7 years.
- Drills: `scripts/ops/ha_drill.py pitr|failover`; measured results in
  `docs/operations/BACKUP_RESTORE.md` and `DISASTER_RECOVERY.md`. The 50 GB exit-criterion drill
  needs the pilot servers.
- Merge notes: migration 0095 may collide with other phase-1 packages' migrations (renumber the
  later one); `scripts/ops/run_dataops_scheduler.py` and `deploy/runtime/compose.yaml` are also
  edited by P1-C (small, separate hunks).

## 2026-11-26 — Architecture plan version 3 proposed (branch `archplan`, docs only, not pushed)

- Seven professional reviews (front office, middle and back office, technology, multinational,
  security, operations and governance, quant) are kept as written in
  [docs/assessments/professional-review-2026-11-26/](../assessments/professional-review-2026-11-26/README.md).
- The response is [docs/architecture/ARCHITECTURE_V3_PLAN.md](../architecture/ARCHITECTURE_V3_PLAN.md):
  six root causes, a target per layer, removals, six phases with exit criteria, hardware, twelve
  owner decisions and a traceability table of every blocker and major finding. Ten draft decision
  records are in `docs/architecture/decisions/DRAFT-*.md`; none is accepted.
- Status: **awaiting the owner's decisions** (plan section 8). Until then no work starts from the
  plan, except what is already under way: the risk-formula fixes (branch `quantfix`) and the
  security remediation of H1 to H7 and the mediums (branch `secfix`), which the plan does not
  re-plan.
- Checked in code while writing: two reviews' claims are outdated (TimescaleDB is merged as an
  optional extension, Decision 39; option settlements and Black-76 implied volatility are merged,
  migration 0094); the suggested psycopg 3 driver is LGPL and refused by the dependency gate; two
  LNG cargo-economics engines exist (desk and research copy).

## 2026-11-26 — Half-built branches integrated (branch `halfbuilt`)

- LNG berth priority (`wip/berth-rule-on-innovation`): migration renumbered
  `0092_lng_berth_rules` on `0091_hub_one_identity` (it was 0090 on 0089; the background-jobs and
  hub-identity branches took 0090 and 0091 from the same base); engine and API as the branch left them, plus `approval_requests` on each option (the
  approvals as data). Web finished: the Options section lists the berth rules (folded, terminals
  on one rule on one line), words approvals, quotes and another company's delay from their data
  in EN and ZH, and tones "needs terminal approval" and "quote pending" as watch, not breach. Docs:
  design 17 section 9.8, ADR Decision 37 addendum, decision log, LNG4-11. The demo's Dunkerque
  call names its company. Not built: recording a terminal's rule, a call or a quote (no route or
  import writes them); the rest of the Options panel still shows the engine's English sentences
  (titles, reasons, notes, warnings) in ZH.
- TimescaleDB (`wip/timescale-on-innovation`): migration renumbered `0093_timescale_optional`
  on `0092`; off by default, a no-op on plain PostgreSQL and SQLite. The branch referenced an
  ADR 39 and a deployment guide that did not exist: added ADR Decision 39 (amends Decision 24),
  `docs/deployment/TIMESCALEDB.md` (enable, leave, proof), the TimescaleDB sections of
  `BACKUP_RESTORE.md` and `DISASTER_RECOVERY.md`, the TSL review in
  `docs/legal/DEPENDENCY_LICENSE_REVIEW.md` (self-hosted internal use permitted; not bundled or
  hosted). New `tests/integration/test_timescale_present_postgres.py`
  (`EUROGAS_NEXUS_TEST_TIMESCALE_URL`): conversion, writers on compressed chunks, idempotence,
  no-op downgrade. The restore drill fails when hypertables do not come back. Proven on
  `timescale/timescaledb:latest-pg16` (2.32.1): upgrade, downgrade, re-upgrade, a downgrade
  past 0072, dump and restore. Not turned on anywhere: doc 19 found no measured need yet.
- Portfolio and outlook report (`fix/portfolio-report-on-innovation`): finished. Its P&L and
  forward view never marked simulated marks (rule 17: it matched the ladder warning's old
  wording); tests for book isolation, a caller with no book, simulated marks and the
  counterparty fall-backs; section names and descriptions in EN and ZH (the descriptions were
  only in the main-based copy, `fix/portfolio-report-main`, which otherwise holds the same
  work); the report's PDF note in the reader's language.
- `fix/demo-review` (55 commits) was not superseded: about 30 of its commits had no
  counterpart on the innovation branch. Ported: page error boundary, report waits after a
  timeout, Chinese report masthead, "Data incomplete" reasons, section hints, palette days in the
  reader's language (also in the conversion and forward answers), the dataset, backtest, shadow,
  strategy-track and spread-lab fixes, decision cases out of platform administration, the i18n
  plural gate, the catalogue probe, the seasonal-normal index, pg8000 date decoding, gas option
  settlements (migration `0094_option_settlements`, census 315 / 351 with the topology read), the
  options follow-ups, loading rings, the copilot ring, the glossary test and policy test. Not
  ported, for the owner: `95cdcf5` (demo live public sources without a key and
  `docs/engineering/demo-data-audit.md`, a demo behaviour change), the seed's remaining "Demo"
  display names (`03b9c84`'s renames; the tests on this branch pin them), the parts of
  `f2cc17c`, `34cc0f7`, `e3e9618` and `eba65e6` that the innovation ports redid differently;
  `7cc1816` is superseded by the glossary and map ports.
- `research/agentic-decision-architecture`: its documents were already here except the Codex
  handoff, now added with a status note; the experiment stays on its branch (doc 18).
- Migration tests no longer pin the schema head (merged from `inno-merge-test`); the head is
  checked once against the alembic chain in `tests/api/test_release_metadata_api.py`.
## 2026-11-26 — Backend audit (branch `backend-audit`)

- Findings, causes, other occurrences and the structural plan:
  [BACKEND_AUDIT_2026-11-26](../assessments/BACKEND_AUDIT_2026-11-26.md).
- One error envelope (`api/error_handlers.error_body`; the router's own 404/405 included);
  `api/errors.ApiError(status, code, text, params)`; the envelope adds `params` and
  `fallback_message`; 73 English-only refusals converted; gate
  `tests/contract/test_api_error_codes.py`. Uncatalogued codes keep their name (family from
  the status); `CODE_ALIASES` for the four runtime-database spellings.
- No-store rule: `meta.runtime_store` on every enveloped read without a store (middleware).
- `application/bounded_reads.read_bounded`: calculation inputs refuse past their bound (422
  `read_bound_exceeded`) instead of using part (positions, Today storage, NWE prices, reports,
  outages, news REMIT).
- Ingestion: script failures classified by their report (`classify_script_failure`); EIA
  and IIP report codes; demo catch-up ends the IIP partial-read loop; demo monitoring asks for
  enrichment only with a service identity.
- Provenance: `domain/ontology/provenance.is_simulated` (one rule, ratchet test); outage and
  observation rows carry `simulated`; `capacity_impact_mcm_d` is `None` when unknown.
- Performance: one price book per valuation snapshot (spread board 54 → 3 quote reads); one
  source-state read on reconcile.
- No route, migration, ADR or census change.

## 2026-11-26 — Commercial Intelligence V3, LNG-4: options with consequences, full cost, substitute supply, demurrage, REMIT

- `domain/lng/disruption.py`: every option listed and ranked with its flags
  (`contract_breach` with the contract and its liquidated damages or "penalty not held";
  `disrupts_normal_cargo`; `physically_possible`), a recommended set (clean, best expected,
  overall) with a reason for each; a breach option can be chosen. Full cost: P&L = direct P&L
  - opportunity cost (displaced third-party calls, knock-on on own cargoes, capacity and
  storage forgone), each arithmetic line with its `sources` and `basis`. Spot slots and
  substitute supply (upstream swing, hub gas plus transport, storage, merit order) are options.
- `application/lng_demurrage.py`: demurrage from the Confirmation Notice, voyage terms or master
  agreement in its currency; one FX function `_fx_rate` (ECB default, WMR or BFIX when
  entitled, or a rate entered by hand; no fetch, no hard-coded rate).
  `application/lng_substitutes.py`: substitute sources and one transport function
  `_transport_cost`. `application/pipeline_outages.py`: REMIT messages linked to pipeline
  supply in the `lng_disruption` consumer on `outage.published`, a manual override.
- Migration `0087_lng4_options_demurrage_outages.py` (revision `0087_lng4_options_demurrage`,
  32-character version column; `down_revision` `0086_lng_disruption`), ADR Decision 37: tables
  `pipeline_outage_links` and `lng_berth_calls`, nullable columns on seven tables.
  `DB_SCHEMA_REVISION` and the 13 pinned head literals moved.
- Routes: additive fields and FX query on the three reads and the choose body; new `GET
  /api/lng/pipeline-supplies/{id}/outage-links` and `PUT .../outage-override` (governed,
  audited `lng.pipeline_outage_override`). Census 305 paths / 340 operations. The ETRM cargo
  schedule import takes `laytime_hours`, `demurrage_rate_per_day`, `demurrage_currency`,
  `demurrage_terms`.
- Web: the Options section shows flags, recommended reasons, direct and opportunity cost,
  consequences, a breakdown with each line's sources, an FX picker, demurrage in its
  currency and the REMIT links; EN and ZH. Demo D1: the Huelva swap is a flagged breach option
  and PVB hub gas covering it is a further option.
- Design: [17](Commercial-Intelligence-V3/17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md)
  section 9. Fixed on the way: a disruption with no workable option was announced as
  "Disruption cleared"; it is now "No workable option", and "cleared" follows only the end of an
  open disruption. Not yet: a firm storage contract type (no storage source read), carbon and
  electricity (CE-1). Open for the owner: berth priority, counting third-party demurrage, the
  spare-slot value, the largest-link REMIT rule.

## 2026-11-25 — Commercial Intelligence V3, CODEX-1: the Codex assessments reviewed

- Reviewed `research/agentic-decision-architecture` (five Codex commits on `main@6d21b89`) against
  the innovation branch; verdicts and the list for the owner in
  [18](Commercial-Intelligence-V3/18_CODEX_ASSESSMENT_REVIEW.md). The research branch is unchanged.
- `application/agents/runtime.py`: every result, refusals included, carries capability, version,
  principal, agent run and argument hash; a success carries `output_hash` and is refused when it
  breaks its declared `output_schema`; `TIMEOUT_OVERRUN` when a handler runs past its
  `timeout_policy`; a `HUMAN_CONFIRMATION` capability runs only on a signed-in person's own
  confirmation (not a model, the deployment token or a service account); confirmations and
  writing calls audited (`governance.agent_capability`). `CapabilityResult` quality defaults to
  `NOT_ASSESSED`. `AgentInvocationContext.principal_type` (default `SERVICE`).
- `api/routes/public/agents.py`: no identity is 401, not a wildcard analyst.
- `streaming/contracts.py`: `MarketChangeV1`, the versioned wire form of a DATA-1 change digest
  (key `event_key`; unknown versions and extra fields refused). No broker or dependency. The
  research branch's `IngestionInvalidationV1` is not built (the outbox already records
  `source.ingested`).
- AI gate: AGENT-EVAL-031 to 033; `agent_research` and `mcp_tools` re-recorded (set hash, cases).
- No route, migration, ADR or census change (303 paths / 338 operations).
  Not built, for the owner: a broker, TimescaleDB, pgvector, Iceberg, Temporal, live model
  routing, MCP delegated identity (C8).

## 2026-11-25 — Commercial Intelligence V3, TAR-2: contracted before public, tariff years, one source order

- Point in time: a figure valued as of T uses the tariff version held at T, final if a final
  was held, else indicative and flagged. A row with no stated status (ENTSOG) takes NC TAR
  Art. 29 at T (`domain/tariffs/tariff_year.py`: in force, or the yearly auction that ran at
  it held; else indicative), re-derived on every read; new bases `nc_tar_tariff_in_force`,
  `nc_tar_yearly_auction_held`, `nc_tar_before_yearly_auction`.
- Tariff years: each publisher's convention and cadence in `domain/tariffs/publishers.py`
  (unconfirmed ones say so) and the registry document; `tariff_versions.tariff_year`; both
  versions per year side by side (`application/tariff_book.tariff_years`); a period across two
  years splits per gas day; a newly final version is flagged in `tariff.changed`
  (`new_final`, priority 1) and raises `tariff_final_published`. ENTSOG polled hourly in wider
  windows, 6-hourly otherwise (the hourly ENTSOG job is the floor).
- Capacity the firm holds: migration `0088_tar2_capacity_bookings` (on `0086_lng_disruption`;
  0087 left free), ADR Decision 38 (37 reserved): table `capacity_bookings`, import contract
  `etrm.capacity_bookings.v1`. `domain/tariffs/precedence.split` prices contracted, then
  public (how the rest would be bought: DA/WD reserve plus premium, FCFS at terminals), else
  not held (never zero); `application/capacity_costs.py` for pipeline and terminal; applied in
  route pricing (`RouteLeg.cost_basis`, `layers`), contract costs, the capacity optimiser
  (`held_capacity_mwh`) and LNG-3 (booked send-out and storage as `contracted` offers ranked
  first).
- One resolver, `domain/pricing/source_precedence.py` (FX, interest, capacity cost, tariff,
  commodity price): default orders, the firm's order per kind and `kind@context` in the
  organisation setting `source_precedence` (admin, validated, audited); every result lists all
  tiers in order with the one used marked. `application/source_precedence.resolve_fx_rate(
  session, from_ccy, to_ccy, as_of, context)` and `resolve_interest_rate`.
- Financial-institution connector type: registry entry `src-bank-rates` (no credential), the
  setting `financial_institutions` (credential fields refused; `api` access only with the
  firm's agreement recorded, still unconnected), contracts `bank.fx_rates.v1` and
  `bank.interest_rates.v1` (rows `BANK:<key>`).
- Routes (READ): `GET /api/tariffs/years`, `/api/capacity/bookings`, `/api/capacity/cost`,
  `/api/pricing/fx-rate`, `/api/pricing/source-precedence`. Census 308 paths / 343 operations.
- Web: Sources → Infrastructure: the tariff book shows each row's tariff year and a new mark,
  and a facility's years with both versions; a capacity cost panel (bookings, a cost by layer
  with status, tariff year and publication date, the sources in order, the order in force and
  an FX check), EN and ZH, design tokens.
- Open: booking content history (an update overwrites), a re-sent interest rate overwrites, LNG-3
  takes the first-ranked offer per kind (no spill beyond a booking), no maker-checker on the
  settings, bank rows are not served by the general FX reads for database identities (entitlement
  family unknown).

## 2026-11-25 — Commercial Intelligence V3, LNG-3: a disruption re-optimises the portfolio (branch `wip/lng3`)

- `domain/lng/disruption.py` (pure, deterministic, no solver): a late cargo or a curtailed
  pipeline supply's options (wait, borrow in tank, buy send-out or storage, borrow and buy,
  divert to a spare slot, swap with another cargo; absorb or cover from a cargo), each
  simulated by gas day and valued against the plan across the whole book under ETA and
  price scenarios; hard constraints (firm obligations judged against the plan, storage,
  stranded energy, diversion rights); a Pareto frontier over five objectives with each
  dominated option's reason; a default by a configurable score (`lng.disruption.*`
  assumptions, desk standards otherwise). Capped at 24 options per supply, 256 combinations.
- Migration `0086_lng_disruption` (`down_revision` `0082_data1_integration`), ADR Decision 36:
  seven expand-only tables (slot terms, capacity offers, delivery obligations, voyage terms,
  pipeline supplies, runs, decisions). `DB_SCHEMA_REVISION` and the 10 pinned head literals
  moved.
- `application/lng_disruption.py`: loads the book from the store; outbox consumer
  `lng_disruption` (cargo, capacity, tariff, contract, assumption and outage events; not
  price ticks) keeps a run timeline and tells the trader, scheduler and desk head through the
  LNG-2 routes on a material change, deduplicated, with a 30-minute cooldown.
- Routes: `GET /api/lng/cargoes/{id}/disruption-options`, `.../{option_id}`, `POST
  .../{option_id}/choose` (governed, audited `lng.disruption_choice`; nothing booked) and `GET
  /api/lng/disruption/frontier` (pipeline what-if). Census 296 paths / 331 operations.
- Web: an Options section in the cargo plan sheet (`CargoOptionsPanel.tsx`,
  `app/model/disruptionOptionsModel.ts`, `cargo-options.css` in `@layer ds-components`), EN
  and ZH. Demo planted case D1 on the 24th of each month.
- Design, sources and limits: [17](Commercial-Intelligence-V3/17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md).
  Not yet: USD demurrage conversion, REMIT outage to pipeline-supply linking.

## 2026-11-25 — Commercial Intelligence V3, NEWS-1: news, policy and geopolitical events (branch `wip/news1`)

- Source registry `domain/news/sources.py` with quoted, dated terms
  ([NEWS_SOURCE_REGISTRY.md](../integration/NEWS_SOURCE_REGISTRY.md)): REMIT messages already held
  (no fetch) and the GOV.UK DESNZ Atom feed are read; the Commission (CC BY 4.0), EUR-Lex and ACER
  (titles only) are permitted but wait for a feed address on their own host; wire services, EEX's
  website and LNG operators' sites are recorded as excluded. Feed reader `domain/news/feeds.py`
  (stdlib XML, DOCTYPE and entities refused), deterministic tagging `domain/news/tagging.py`.
- Ingest `application/news_ingest.py` (robots.txt, interval, ETag, dedupe by source reference,
  revisions by content hash; operator script `scripts/ops/poll_news_sources.py`, dry run unless
  `--commit`). Each new or changed item publishes `news.published`; one naming the asset of a held,
  open REMIT outage carries `outage:<message>` as dependency key, so opportunities re-evaluate.
- Relevance `application/news_relevance.py` (contracts by delivery hub, open cargoes by vessel or
  terminal, recent nominations by hub; only books the caller may see) and routing
  `application/news_routing.py` (consumer `news_roles`; categories `news_trader`, `news_lng`,
  `news_scheduler`, book-scoped and self-notifying; dedupe, 30-minute cooldown, one message per
  held outage).
- AI use `news_note` in the GOV-1 register (`application/news_note.py`, check
  `application/news_grounding.py`: every sentence cites evidence ids and is checked against only
  those lines; any failure keeps the rule note); evaluation set `tests/evals/news_note_cases.json`
  (36 cases) in the gate record.
- Reads `GET /api/news`, `GET /api/news/{item_id}`, `POST /api/news/{item_id}/note`; census 295
  paths / 330 operations. Web: `components/NewsPanel.tsx` on Desk → Today (`news-panel.css` in
  `@layer ds-components`, EN and ZH). Migration `0084_news_items` on SCHED-1's `0085_sched1_nomination_matching`, ADR Decision 35.
- Not yet: feed addresses for the Commission, EUR-Lex and ACER (not readable from the build
  environment); the poll on the scheduler (SCHED-1); end-to-end latency measured; national
  regulators' terms.

## 2026-11-25 — Commercial Intelligence V3, SCHED-1: why trades, confirmations and nominations disagree (branch `wip/sched1`)

- New pure module `domain/portfolio/nomination_reconciliation.py` (eleven break kinds, the
  urgency of a cut-off, unit slips) and `application/gas_day_reconciliation.py` (facts from ETRM
  deals in `screen_order_observations` and the append-only `gas_day_nomination_events`, scope
  as the gas-day reads, payload, CSV rows, Today items, alerts).
- One read, `GET /api/desk/gas-day/{gas_day}/reconciliation` (`portfolio.read`; filters;
  `format=csv` with the GOV-1 export decision). Census 296 paths / 331 operations (from 295 /
  330 after TAR-1).
- Migration `0085_sched1_nomination_matching` (nullable columns on `gas_day_nomination_events`:
  counterparty, direction, point, shipper codes, the counterparty's quantity), on
  TAR-1's `0083_tar1_tariff_book`. No table, so no ADR. `etrm.nominations.v1` takes the fields as optional
  columns, the step `trade_confirmation` and the line prefix `counterparty:`.
- Alerts: monitoring category `gas_day_break` (book-scoped, notifies itself in `nomination`,
  Operations then Trader; deduplicated, 30-minute cooldown unless worse, withdrawn when fixed),
  queued by `run_monitoring_worker.py` and `dispatch_notifications.py` after the deadline
  prompts. Today: "What needs me" items of kind `reconciliation`; web Reconciliation row for
  operations (`components/today/ReconciliationRow.tsx`, `app/model/reconciliationModel.ts`).
- Demo: planted case R1 (gas days 11 and 12: Aldermoor nominates 4,800 of 6,000 MWh at NBP,
  the TSO confirms the lesser); the Aldermoor sale and the simulated feed's prompt trades are
  nominated and matched every other day.
- Not yet: shipper-code reference data (codes come from the scheduling file); a TSO
  confirmation feed; confirmations from a trade-confirmation platform (imported as a step).

## 2026-11-24 — Commercial Intelligence V3, MAP-1: the map (branch `wip/map1`)

- `GET /api/portfolio/map-situation` gained `assets` (LNG terminals and storage sites with
  ENTSOG's newest firm technical capacity per direction, the latest closed-day flow, and GIE
  inventory labelled `site` or `country_aggregate`; `application/map_assets.py`), `asset_rule`,
  `flow_days` (stored closed gas days of the entitled flows), and per cargo `eta` (the LNG-2
  basis object) and `position_basis`. Same entitlement as the read's other items. No route,
  table, migration or service; census unchanged (292 paths / 327 operations).
- Web: the network map gained a scene (`app/mapScene.ts` pure model, `app/mapSceneCards.ts`,
  `components/mapScene/useMapScene.ts`, `MapSceneControls.tsx`, `map-scene.css` in
  `@layer ds-components`): 3D columns (`fill-extrusion`) or 2D circles for sites, reported and
  labelled estimated vessel positions (great-circle interpolation to the ETA), animated flows
  with direction only where the operator's side is known, a gas-day scrubber, 2D/3D with an
  eased camera and reduced-motion fallbacks, and a keyboard key. EN and ZH strings. No npm
  package added; basemap unchanged (bundled outline by default, D4).
- Not yet: frame rate measured in a browser; page-to-page transitions.

## 2026-11-24 — Commercial Intelligence V3, TAR-1: public tariffs versioned, capacity windows (branch `wip/tar1`)

- Tariff book (`application/tariff_book.py`, `domain/tariffs/`): every row of the tariff
  registers (`tso_tariffs`, `lng_terminal_tariff`) becomes a version in `tariff_versions`
  (publisher, facility, product, unit, currency, period, INDICATIVE or FINAL with its basis,
  publication and retrieval times, source URL, content hash); a newer version supersedes, the
  history stays readable as of any instant; indicative to final is a named status change.
  Registers and route pricing are unchanged. Migration `0083_tar1_tariff_book` (expand-only,
  down_revision `0082_data1_integration`; `0084` is MAP-1's), ADR Decision 34.
- Freshness: the ENTSOG read versions its rows and publishes `tariff.changed` in its own
  transaction; the scheduler's capture (kind `tariffs`) versions the rest when the registers
  change and hourly; ENTSOG is polled hourly in the NC TAR publication weeks, daily otherwise.
  Monitoring adds `tariff_publisher_stale`, `tariff_publication_missed` (`data_source`) and
  `capacity_window_opening` (new category `capacity`, routed to OPERATIONS, escalation TRADER).
- Publishers: registry in code and `docs/data/TARIFF_PUBLISHER_REGISTRY.md`. ENTSOG (API) and
  the CAM network code's standard auction calendar (rule-derived, checked against FGSZ's
  published 2026/27 calendar) are automated; every TSO, LNG and storage site tried was
  unreachable from the build environment, so each is recorded `manual` (or `parsed` behind the
  firm's permission for Fluxys LNG, Elengy, DET) with nothing fetched.
- Routes `GET /api/tariffs` (filters, `as_of`, `history`), `GET /api/tariffs/publishers`,
  `GET /api/capacity/notices` (295 paths / 330 operations). Ops: `scripts/ops/tariff_book.py`
  (status, sync, import-notices). Web: Sources → Infrastructure → Tariff book (indicative and
  final labelled, version trail, source link, upcoming windows, publishers). Valuation snapshot
  tariff inputs name the version and basis they priced.
- Measured on PostgreSQL 16: read to version and event committed median 12.5 ms, commit to the
  opportunities consumer 5.5 ms (8 runs); a first full capture of a 12,670-row ENTSOG register
  takes 77 s once (run `scripts/ops/tariff_book.py sync --commit` after deploy), 2.3 s after.
  The designed figure is the poll (1 h in publication weeks, 24 h otherwise). Evidence in 09.

## 2026-11-24 — Commercial Intelligence V3, P-17: maker-checker on limits and reference data (branch `wip/p17`)

- A change to a credit line, trader mandate, deal hedge band, firm marks, LNG terminal terms or
  freight route is a proposal (202) until a different authorised person approves it
  (`application/maker_checker.py`; register and approvers in `governance/four_eyes.py`; the
  shared write path in `application/reference_rows.py`). Proposal, approval, rejection and
  withdrawal are governed writes; `lng.freight_route` is now one too.
- Migration `0081_change_requests` (down_revision `0080_lng_eta_basis`; `0082` is reserved for
  DATA-1): table `change_requests` and a nullable `change_id` on the six governed tables, so
  each figure keeps who proposed and who approved it (`provenance` on the reads). ADR
  Decision 32.
- Organisation setting `four_eyes` (default on for all six; an administrator switches a write
  off, audited) keeps one-person and demo installations working.
- Routes `GET /api/portfolio/change-requests` and `POST .../{change_id}/approve|reject|withdraw`
  (288 paths / 323 operations). Web: "Changes awaiting approval" on Book → Exposure (approve,
  reject with a reason, withdraw), "proposed, awaiting approval" on the limits, hedge-band and
  marks screens, and who set and approved each limit and band. Not built: effective-dated
  changes; screens for terminal terms and freight routes (no web editor exists for either).

## 2026-11-24 — Commercial Intelligence V3, DATA-1: as-of reads, change feed, refreshable reads, import contracts (branch `wip/data1`)

- As-of reads (lesson P1, `application/as_of_reads.py`): `GET /api/market/observations` and
  `GET /api/market/fx` take `as_of`; settlements, closes and FX fixings read the revision
  current then from the market event outbox (no new table); ticks count from their receipt.
  New `GET /api/market/prices`: the monthly price strip from the P-08 resolver, live or as of,
  one flat row per hub and month with revision, publication and first-held times.
- Change feed (lesson P2, `application/change_feed.py`): `GET /api/market/changes` serves digests
  of market events after a cursor, entitlement-filtered per caller. Migration
  `0082_data1_integration` (expand-only, on `0080`) adds `market_events.writer_txid`, stamped by
  PostgreSQL; the feed orders by (writer, `seq`) and serves only up to the snapshot horizon, so
  no committed event is skipped. SDK `fetch_market_changes_result` and `sync_market_changes`.
- Refreshable reads (lesson P7, `application/refreshable_reads.py`): `format=csv` on the price
  strip, observations and FX, fixed headers, through the report CSV writer so the GOV-1 export
  decision and metering apply. How-to with an M query: `docs/sdk/POWER_QUERY.md`.
- Import contracts (`application/import_contracts.py`): six versioned CSV contracts for ETRM
  deals, the physical schedule, nomination statuses, the LNG cargo schedule, and ERP
  counterparties and invoices; row-level reasons, idempotent re-import, nothing executed.
  `GET /api/imports/contracts`, `POST /api/imports/{contract_id}/validate` (stores nothing),
  `scripts/ops/import_contract_file.py` (dry run unless `--commit`). New table
  `erp_references` in `0082` (ADR Decision 33). Census 292 paths / 327 operations with P-17.

## 2026-11-24 — Commercial Intelligence V3, LNG-2: a cargo change reaches each role (branch `wip/lng2`)

- `cargo_roles` outbox consumer (`application/lng_cargo_alerts.py`) rebuilds a cargo's plan on
  each `cargo.changed` and derives one message per role (`domain/lng/consequences.py`): trader
  (hedge actions with arithmetic), scheduler (berth, send-out, nomination cut-offs), risk (net
  by month, mandates), desk head (only when material by `lng.material_change_mwh`). Alerts
  `lng_hedge`, `lng_schedule`, `lng_exposure`, `lng_material` notify themselves (digest dedupe,
  30-minute cooldown, withdrawal). New notification categories `cargo`, `desk_head`.
- Migration `0080_lng_eta_basis` (down_revision `0079_licensed_data_use`, the
  governance slice's migration): ETA basis, confidence, source and time (lesson P3).
- No new route; additive fields in the contract policy. Web: board column,
  plan section, Today item. Commit to every role's notification on PostgreSQL through the
  listen worker: median 0.66 s on the worker's first change, 0.11 s after.

## 2026-11-24 — Commercial Intelligence V3, M5b, M6 and LNG-1 (branch `innovation/continuous-commercial-intelligence`)

- M5b: contract, hedge-band and assumption edits publish `contract.changed` and
  `assumption.changed` (digests only, captured at save time); a later publication returning
  to earlier content is a revision.
- M6: stale feeds, dead letters and outbox lag raise monitoring alerts, one per condition,
  cleared on recovery; source freshness ages with the clock.
- LNG-1: a cargo in transit as one plan from ETA to hedge months (`domain/lng/in_transit.py`,
  `application/lng_in_transit.py`), migration `0078_lng_cargo_hedges` (ADR Decision 29),
  `cargo.changed` events, four routes under `/api/lng/cargoes` (census 282 / 315), SDK module
  `lng_cargo_plan`, web client transport. No screen yet.
- Programme documents 11 (commercial quality standard), 12 (cargo in transit) and 13
  (persona and practice review) added.

## 2026-11-24 — Commercial Intelligence V3, M5: price, FX and outage events (branch `innovation/continuous-commercial-intelligence`)

- `application/market_event_capture.py` publishes `price.updated` (settlements mapped to a
  day, month, quarter or season), `fx.updated` and `outage.published` (REMIT versions as
  revisions of one message) from the stored rows: after each DataOps scheduler cycle over a
  4-day window, and in `import_settlements.py` / `import_fx_fixings.py` in the importer's
  transaction. `scripts/ops/market_events.py capture` backfills. No migration, no route.
- The opportunity consumer widens a EUR fixing to stored cross pairs (`fx:GBPUSD` for
  `fx:EURUSD`).
- CP-13 `run_due` deletes pending input classes by condition in the store, so a change noted
  while the evaluation runs stays pending (fixes R4; SQLite and PostgreSQL tests).
- Open: contract and assumption edits as events (M5b); live quotes not captured (R14).

## 2026-11-24 — Commercial Intelligence V3, M4: market event outbox (branch `innovation/continuous-commercial-intelligence`)

- Programme documents in [Commercial-Intelligence-V3/](Commercial-Intelligence-V3/10_PROGRAMME_STATE.md):
  baseline `main@6d21b89`, audit of 12 capabilities, gap matrix, target architecture,
  roadmap M1 to M13, acceptance criteria, risks, decisions, evidence.
- Canonical market events (`domain/market_events`) and a PostgreSQL transactional outbox
  (`application/market_events.py`, migration `0077_market_event_outbox`, ADR Decision 28):
  identity and content hashes, revisions, five timestamps, priority, skip-locked claims,
  backoff and dead letters, replay, staleness, timeline. The opportunity consumer re-runs
  only evaluators whose opportunities depend on the event's keys (trigger `outbox`).
  Producers: ingestion runs and firm marks (digest only). No new route (census unchanged).
- Open: prices, FX, outages and desk edits do not publish yet (M5); no alerting from
  staleness or dead letters yet (M6). Migration 0077 chains from 0076; an unpushed branch
  using 0076 must renumber on merge.

## 2026-11-19 — Today → My gas day, stage 2: the checklist (branch `today-gas-day`, not pushed)

- Today `rows[6]` `checklist` (`application/gas_day_checklist.py`), same view and scope as
  `rows[5]`: per contract and scheduled line the nomination status as recorded (newest
  `gas_day_nomination_events` row, else the delivery record's nominated quantity as "sent",
  else "to send"), the agent the contract names (`upstream_resource_contracts.nomination_agent`),
  expected against nominated beyond the contract's nomination tolerance, LNG terminal steps
  per regas slot (unloading window, send-out nomination, inventory only where recorded) and a
  DES cargo confirmation whose window covers the day. Each open step's deadline from
  `hub_cutoffs`; due within 3 h or overdue goes to "What needs me" first and to the outbox
  once (`queue_deadline_notifications`, monitoring worker and `dispatch_notifications.py`).
- `POST /api/desk/gas-day/status` (WRITE, portfolio.write in the handler): a status entered by
  hand, only for a line of the caller's own gas day; labelled `manual`, audited
  (`gas_day.status.record`). Nothing is nominated. Census 277 / 310.
- Migration `0076_gas_day_nominations`. Review points: a hub reads "balanced" within
  `balancing.flat_band_pct` (new assumption key; default 2 % of the day's larger side, stated);
  Time left turns amber within 2 h and red within 30 min and names its basis on hover.
- Open: no assumption-set editor exists in the web client, so "not estimated" says who enters
  the premium and where, without a link; the demo operations identity is read-only by an
  existing deliberate test (`test_demo_identity_access`), so it sees but cannot record.

## 2026-11-19 — Today → My gas day, stage 1 (branch `today-gas-day`, not pushed)

- Today row 6 `gas_day` (appended to `GET /api/desk/today`, earlier rows keep their positions;
  no new route): per hub, today's and tomorrow's gas day, IN (contracts by delivery point,
  nominated where held else contract quantity; LNG send-out from regas slots; storage
  withdrawal and imports from the schedule; purchases), OUT (sales, offtake, injection,
  exports), net to clear (NBP th/d, continental MWh/d with MW), WD/DA trades booked today,
  cut-offs, and the cost of leaving it open at the approved assumption set's cash-out premium
  or discount (no imbalance price is read: terms not verified, `docs/legal/DATA_SOURCE_TERMS.md`).
- Scope from mandates and books (`application/gas_day.scope_of`), never the persona: a mandated
  trader sees his books less what is delegated away plus what is delegated to him; a caller
  without a mandate sees every book portfolio isolation lets him see.
- One calendar: `domain/market/hub_cutoffs.py` (network-code defaults, labelled assumptions;
  declared `nomination_window_masters` replace them); `strategy_tracking.cutoff_for` reads it.
- Migration `0074_gas_day_schedule` (after `0073_contract_kinds`):
  `gas_day_schedule_lines`, `gas_day_delegations`. `DB_SCHEMA_REVISION` pinned to it.
- Demo: `seed_demo_gas_day` through `ensure_demo_fixtures` (schedule, today's nominations, a
  send-out day, the TTF split, per-book cash-out sets); simulated, said once on the row.
- Web: `components/today/GasDayRow.tsx`, first row for trader and operations
  (`roleComposition.todayRows`); other roles unchanged.

## 2026-11-18 — CP-13 evaluation scheduling (branch `cp-13-eval-scheduling`, not pushed)

- Migration `0071_opportunity_pending_inputs`: one row per input class changed since the last
  scheduled evaluation. `application/opportunities/schedule.py`: `note_input_changed` (in the
  writer's transaction), `note_ingestion_changes` (a successful ingestion that inserted or
  updated rows: price, fx, rates, tariff, outage or capacity source), `run_due` (one full
  evaluation, trigger `schedule`, at most once per 5 minutes on the evaluation instant; it
  clears the classes noted before it started, a change during the run stays pending),
  `StoreTrigger`.
- The data-operations scheduler calls it after each execution, in its own transactions, so an
  evaluation failure never stops ingestion. On-write triggers: firm marks, assumption-set
  approval, credit lines and mandates (limits), hedge approvals, books and upstream contracts
  (book), the firm's terminal terms and a reviewed register figure (tariffs), freight routes.
- A failing evaluator: no opportunity changes, one administrator alert (the monitoring scan).
  The outbox subscription stays an interface until M4. No new path or operation.
## 2026-11-18 — market reports round 6: print layout, storage and spread joins, delete, scheduling (branch `reports-round6`, not pushed)

- Print: a text-and-figure row that would cross a page keeps its text on the page and its
  figure follows the break (`render.PRINT_LAYOUT_JS` on `beforeprint`; the in-app Print applies
  `app/model/reportPrintLayout.ts` to its script-less frame). No blank part-pages.
- Joins: storage by country reads `fundamentals_storage.storage_read` (N-year average, five-year
  range); the hub spread converts contract by contract at delivery-month FX
  (`market_normalisation`, CIP forward else ECB spot), each rate stated.
- Delete from the viewer checked after CP-00 (confirmation, audited `report.manage`); the
  viewer now empties after deleting the shown report.
- Scheduled reports: `reports/schedule.py`, kept in `organisation_settings`
  (`report_schedules`), run by the monitoring worker as the service principal, always for
  distribution; in-app to the distribution roles (`store.reader_may_see`), e-mail through the
  outbox category `report`; audited `report.schedule` / `report.schedules`. Research →
  Reports → Scheduled reports (administrators edit). `GET`/`PUT /api/reports/schedules`:
  Surface 285 / 317 (+1 / +2).


## 2026-11-18 — CP-12 voyage and cargo model (branch `cp-12-cargo-model`, not pushed)

- `domain/lng/voyage.py`, `domain/lng/cargo_economics.py`: the chain of design C.1 in Decimal;
  FOB (a x HH + b or a fixed FOB price) and DES cargoes in one result; full and lifting cost;
  netback and margin per terminal, slip range, no winner inside 0.10/MWh; input classes, the
  weakest grades the result; a missing input blocks with its reason, never zero. Golden: C.3 to
  the cent and a 200-cargo reconciliation property test.
- Migration `0070_freight_route` (versioned, shipped empty: no licensed distance source yet);
  assumption keys `lng.speed`, `lng.ballast_fuel`, `lng.insurance`, `lng.fob_slope`,
  `lng.fob_fee`; `application/lng_cargo_economics.py` reads marks and FX through the valuation
  snapshot, HH forward else the EIA spot as an indicative proxy (EIA stopped publishing futures
  in April 2024), regas through the CP-11 resolution order. `GET/PUT /api/lng/freight-routes`,
  `POST /api/lng/cargo-economics`; typed client methods for CP-18. Surface 283 / 314.
- Not built here: evaluators D and A (they need snapshot reads for cargoes, terminal regas and
  routes, so that a replay reproduces them); the ENTSOG entry tariff conversion at a load
  factor (the entry tariff is the firm's terms or an entered figure); the design's C.3 "lifting
  basis +10.3" contradicts C.4, the engine gives 15.22 EUR/MWh by the stated arithmetic.

## 2026-11-18 — CP-18 Research → Cargo & netback (branch `cp-18`, not pushed)

- Research gains the task Cargo & netback (`task=cargo`, `components/research/CargoStudy.tsx`):
  one FOB or DES cargo against the terminals with firm terms or tariffs; headline (cost at the
  ship's rail, best terminal or "no winner", margin, lifting-cost margin), the terminal table,
  the margin waterfall, Henry Hub against the hub read two ways (delivered and netback, same
  total), the delivered spread by arrival month and the margin's sensitivity (HH, hire, hub,
  FX). Opens on the design's worked example (assumptions, not market values).
- The voyage: `freight_route` ships empty, so `POST /api/lng/cargo-economics` takes a voyage the
  desk enters (`distance_nm` at `speed_kn`, or `laden_days`; class assumption, "entered");
  saved routes are offered when the table has rows. Henry Hub: firm mark or licensed price,
  else the EIA spot as a labelled proxy, else the page asks for a mark.
- Engine additions (CP-12 chain, no new route): per-terminal steps, the C.4 delivered/netback
  views, FX used; `series_months` for the line; sensitivity. Uses the shared `SimulatedScope`.
- Left: a daily HH–TTF history line (needs EIA HH history held); NBP margins stay per MWh in
  GBP (the table compares per MWh), the board's p/th is not repeated here.

## 2026-11-18 — CP-17 Research → Fundamentals (branch `cp-17`, not pushed)

- Research gains the task Fundamentals (`task=fundamentals`, tabs in `view=`): Storage (the
  storage-by-country panel, then every country as small multiples), LNG (new
  `GET /api/fundamentals/lng`: EU total and the 12 GIE ALSI countries, send-out as a 7-day
  mean against the N-yr band, inventory against DTMI), Balance and Gas for power (re-homed).
  Surface 281 / 312 (+1 / +1). GR and FI added to the GIE identity list.
- Scheduler: `src-gie` runs `backfill_gie_history.py --years 5 --refresh --max-windows 40`
  (history kept filled, last week re-read; every window through the gated ingestor). Checked
  with the scheduler's own attempt runner: 36 windows, 2,051 rows unchanged.
- Left: a Flows tab (Norway by landing point against history needs a per-point read and a
  year of ENTSOG history); demo LNG keeps ~400 days, so it says "no complete prior year held".
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
## 2026-11-18 — CP-09 evaluators I and CP-10 evaluators II; snapshot on forward FX (branch `cp-09-10`, not pushed)

- Snapshot FX is the CP-01 forward-FX service (licensed forward sourced, covered interest
  parity derived with its tolerance, spot for prompt periods); the D.5 example reproduces.
- CP-09: L (forward months M+1..M+6 from the book's positions, day-ahead from tomorrow's long
  residual on executable quotes) over the proven graph with exit/pipeline/entry tariffs, the
  firm's load factor and short-term multiplier, FX rows; C (held capacity, charges sunk);
  S (tomorrow's residual against the desk's cash-out discount or premium); E (an outage that
  names a contract's source, cover cost). Checks: capacity, outage on the path, mandate
  (traded hubs, net after the move). Golden: TTF -> THE Jan-27 incl. the 80 % load-factor
  falsifier.
- CP-10: T (held storage from the facility masters; storage not held from the firm's tariff,
  indicative; ratchets not assessed) and R (the pool optimiser with and without re-route
  options; the claim is its delta; single-currency pools only).
- Snapshot collections: positions, contracts, mandates, held_capacity, residuals,
  outage_feed, storage, resource_pool. Demo TTF mandate covers THE, ZTP and PEG.
- Demo run (with ENTSOG tariffs, ECB and fixings ingested): G 37, E 3, C 6 indicative; L 3
  watch (thin margins), 3 blocked (UK mandate); R 1 watch; S blocked (no day-ahead price or
  cash-out assumption on the demo); all simulated-marked. Public-data run: nothing until the
  firm enters marks; then L on real tariffs as indicative, nothing simulated.
- Open on integrate (not from these packages): the config-contract gate
  (`EUROGAS_NEXUS_DEMO_CATCH_UP_STATUS` undeclared) and two demo-seed outage-roll tests.

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
