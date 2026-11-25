# 15 Live pipeline and latency budget

How fresh each kind of data has to be for the desk, what moves it through the platform today,
and where "live" is the wrong goal. Written with M7 (2026-11-24). Measurements are in
[09](09_VALIDATION_EVIDENCE.md); decisions in [08](08_DECISION_LOG.md); acceptance in
[06](06_ACCEPTANCE_CRITERIA.md) (M7-1 to M7-9).

The owner's picture: each role gets a prompt when something it is responsible for changes. A
trader balancing the day's gas position, a scheduler before a nomination cut-off, risk on a
breach, the LNG desk on an ETA or slot change. An opportunity is shown while it is valid and is
withdrawn, visibly, when it is not. A crisis reaches whoever is in charge at once. A strategy
could later act on the same signals, but a person approves and nothing is executed.

## 1. What is live today (honest assessment)

**Before M7.** The outbox and targeted re-evaluation existed (M4, M5), but nothing ran them
between scheduler ticks. A price committed by an importer waited for the next 60 s ingestion
tick, which drained at most ten batches (1,000 events) and then ran the full sweep only after a
5-minute debounce. Alerts came from the legacy intraday engine, so the new engine's
opportunities raised no alert and the legacy one raised its own (R11). `/api/stream/opportunities`
streamed legacy rows. The Opportunities page read once and never refreshed by itself.

**After M7 (this branch).**

- The listen worker (`market-events-worker`, deployed with the scheduler's profile) wakes on
  the `market_events` notification at commit, drains the outbox without an event cap (a 45 s
  time budget per pass hands the rest to the next pass), and then runs the debounced full sweep.
  The scheduler keeps both as its fallback. A full sweep runs at most once a minute and holds a
  PostgreSQL advisory lock, so a targeted run and a sweep never merge at once.
- A listed new-engine opportunity (actionable or indicative, surfaced, within its validity
  window) becomes a monitoring alert within one monitoring pass (10 s), is notified once, and is
  resolved when it is withdrawn. The legacy engine no longer alerts.
- `/api/stream/opportunities` pushes `opportunity` events (`open` or `withdrawn`, with the
  reason) and `evaluated` events. The page re-reads on a notice, shows how old its data is,
  and falls back to a one-minute poll if the stream drops.
- Measured end to end on PostgreSQL with the demo desk (section 8 and [09](09_VALIDATION_EVIDENCE.md)).

**Still not live.**

- No licensed real-time feed is connected in any deployment. EEX, ICE OCM and Trayport are
  declared sources with 1-minute freshness policies, but they need the firm's licence and an
  adapter that posts to `POST /api/market/ticks`. The demo uses simulated ticks.
- Ticks reach the quote stream and intraday strategy tracks, not the opportunity engine: quotes
  are not captured as market events (R14). An opportunity that reads a quote waits for the next
  full sweep.
- Firm data (ETRM trades, deliveries, cargo positions) arrives by file import. Nothing watches
  for a file; the cadence is whoever or whatever runs the import.
- News is not ingested at all.
- The legacy intraday engine still serves `GET /api/market/opportunities` and the market
  screens (section 9).

## 2. Latency budget per data class

"Budget" is from the moment the platform receives the data to the moment the screen or alert
shows the change (ingest, evaluate, show). The source's own publication delay comes on top and
is outside our control; it is stated so the total is honest.

| Data class | Source cadence | Target budget (ingest to screen or alert) | What drives it today | Gap | How the UI shows its age |
| --- | --- | --- | --- | --- | --- |
| Exchange ticks and quotes (EEX, ICE OCM, Trayport; demo feed) | Sub-second to seconds while the market is open | Quote board 3 s. Opportunity re-evaluation 60 s, on a conflated price | `POST /api/market/ticks` stores quotes; `/api/stream/quotes` polls every 1.5 s; strategy tracks evaluate on the tick | No licensed feed connected; quotes are not market events, so opportunities see them only at the next sweep (R14) | Exchange time on each quote; the source's freshness state (current within 1 minute, stale after 30) |
| Settlements and closes | Once a day after the close (EEX, ICE Endex), with corrections | 2 minutes | Importer or scheduler capture publishes `price.updated` in the same transaction; the listen worker re-runs only the evaluators that read the key | The importer's own schedule dominates; there is no file watcher | `marks_as_of` and `current`/`late`/`stale` per row on risk screens; the page's "as of" |
| FX | Daily reference fixing (ECB around 16:00 CET; WMR and BFIX files) | 5 minutes | ECB on the daily schedule; `fx.updated` events, widened to the cross pairs | None that matters for decision support | The fixing's value date in the evidence of each converted figure |
| Outages and REMIT UMMs | Event-driven; REMIT requires publication within an hour of the event | 1 minute from receipt to the event-exposure alert; poll every 15 minutes or faster | ENTSOG UMM every 60 minutes, REMIT platform daily, GIE IIP; `outage.published` events re-run event exposure; outage alerts every 10 s | The poll interval, not the pipeline, sets the delay (up to an hour); no push subscription from any platform | Published and received times on the outage; the alert's time |
| TSO flows and nominations | ENTSOG hourly with a lag; National Gas within-day; the firm's nominations at D-1 and hourly renominations with a lead time | Flows 15 minutes after publication; deadline prompts at least 30 minutes before each cut-off | ENTSOG hourly, National Gas daily; nomination status recorded by the scheduler; deadline notifications from the gas-day checklist | No TSO nomination or confirmation feed (status is recorded by hand) | Gas day and publication time on flows; countdown to the cut-off on the checklist |
| Tariffs and auctions (TAR-1) | NC TAR: yearly reserve prices final 30 days before the July yearly auction, indicative earlier; ENTSOG republishes operators' data; CAM NC auctions on a published calendar (yearly, quarterly, monthly), day-ahead and within-day rolling; LNG and storage tariffs per operator, mostly PDF | A change on ENTSOG in the tariff book and on the event bus within 1 hour of its publication in the NC TAR publication weeks (1 May to 15 July, 1 to 10 October, 15 December to 10 January) and within 24 hours otherwise; an operator's register edit within the next capture (a minute); a capacity window alerted 3 days before it opens | ENTSOG polled hourly or daily by the scheduler; the read writes each changed tariff as a new version (`tariff_versions`) with its `tariff.changed` event in the same transaction (median 12.5 ms, section 8); the scheduler's capture records operator edits; `tariff_publisher_stale` when a publisher is read later than its cadence; CAM NC standard auctions derived by rule; operators' slot windows imported from a file | Only ENTSOG is machine-readable; every other TSO, LNG terminal and storage operator is manual from its PDF or page (registry); no PRISMA auction offers or results (they need a platform account, none is used); the hourly poll, not the pipeline, sets the delay | Version, `INDICATIVE` or `FINAL`, publication and retrieval times and source on each row (Sources, Tariff book); valuations name the version they priced |
| Scheduling breaks: trades against confirmations, nominations and the TSO's match (SCHED-1) | Per scheduling-file import (nominations, renominations, the TSO's confirmations) and per ETRM deal import | Break alert within 3 hours of the cut-off, at least 30 minutes before it; withdrawn on the next pass after the fix | The monitoring worker (every 10 s by default) and the dispatch script call `queue_break_alerts`; one pass 0.03 s on PostgreSQL (section 8); Today's Reconciliation row reads on open | No TSO confirmation feed (the TSO's answer is imported); shipper codes come from the file, not reference data | Countdown to the hub's next cut-off per break; the read's `as_of_utc` |

| Storage and LNG send-out | Daily (GIE AGSI and ALSI publish gas day D on D+1, with revisions) | 1 hour after publication | GIE on its daily schedule | None that matters | Gas day of the figure and receipt state |
| AIS positions and ETAs | Positions every few minutes at sea; ETAs change on the scale of hours | ETA or slot change to an LNG prompt within 15 minutes | Kpler declared with a 60-minute policy; cargo positions by file import; the cargo plan reads the latest ETA; since LNG-2 each role is told within about a second of the import's commit (median 0.66 s on the worker's first change, 0.11 s after, section 8) | No AIS feed connected; the budget is met from the commit of an import, not from the vessel's report | The ETA's source, basis and confidence, and the source of each other plan input, on the plan and in each role's message |
| LNG disruption options (LNG-3) | Whenever a cargo ETA, a slot, a capacity offer, a tariff, a contract, an assumption or an outage changes | Re-optimised options and a notice to the trader, scheduler and desk head within 15 minutes of the input's commit (the cargo budget); the options read in under 2 s | The outbox consumer `lng_disruption` re-runs the book on the listen worker; measured in process on the owner's scenario: commit to run row and notices median 0.05 s on PostgreSQL (0.03 s SQLite), max 0.26 s; the options read 0.05 s; the engine alone 12 ms (section 8) | A price tick does not start a run (prices are valued at each read); the cargo import's own schedule dominates | The timeline of runs (time, what changed, whether the roles were told) and each input's source on the Options panel |
| Weather runs and forecasts | ECMWF open data at 00, 06, 12 and 18 UTC, released some hours after the run | 30 minutes after release | `ingest_ecmwf_forecasts.py` on a 12-hour freshness policy | None that matters | Model run time ("ECMWF 00z") on the forecast |
| News (NEWS-1) | Continuous; official feeds publish a few items a day; REMIT within an hour of the event | REMIT items on the next poll after the message is held; a feed headline within its poll interval (60 minutes for GOV.UK DESNZ; REMIT items every 5 minutes) plus one outbox pass to the role's alert | `scripts/ops/poll_news_sources.py` on the operator's schedule (REMIT items from held messages, feeds with ETag and robots.txt); `news.published` events through the outbox to `news_roles` | Feed addresses for the Commission, EUR-Lex and ACER not yet recorded; the poll is not yet on the scheduler (SCHED-1); not measured end to end | Each item shows its publisher, published and retrieved times and source link |
| Firm's own deals, positions and cargo imports | Per file drop from the ETRM or LNG desk (often end of day, sometimes hourly) | Position screens 1 minute after the import; opportunities 2 minutes | Import scripts; `contract.changed`, `cargo.changed` and `book` pending inputs; positions recompute on read | No drop-folder watcher; an import runs when someone runs it | "Positions as of" the last import |
| Change feed to an external client (DATA-1, `GET /api/market/changes`) | As each market or desk event commits | Served on the client's next poll after the commit; held back at most by the longest write transaction that began before the event committed (a long import holds the feed for its length) | The feed reads `market_events` up to `pg_snapshot_xmin`; the client sets its own poll interval (the SDK's `sync_market_changes` pages until `has_more` is false) | No push to external clients (they poll); a writer left open holds every later event back | Each change's `ingested_at_utc`, `published_at_utc` and `market_time_utc` |
| Backtests and retraining | On demand; scheduled tracks once a day on the new close | Minutes to hours; never on the live path | Strategy runs on demand; tracks by the scheduler; model fits by script | None (deliberate) | Run time and data cut-off on each result |

## 3. How data moves through the engines

There are three shapes of arrival. Each lands in its own table with provenance, then one step
turns a changed row into a market event with a canonical key: `hub:TTF:2026-11-25`, `fx:EURGBP`,
`outage:<id>`, `contract:<id>`, `cargo:<id>`. Evaluators store the keys they read
(`opportunity_dependencies`), so the outbox can re-run only the evaluators a change touches.

1. **Files** (CSV and XLSX of mixed layouts: ETRM trades, settlements, WMR and BFIX fixings,
   Kpler positions, cargo imports). The importer validates, normalises units and identifiers
   (hub aliases, periods, currencies), stores, and publishes the events in the same
   transaction (settlements and FX since M5; contracts, hedge bands and assumptions since M5b).
   A rejected file publishes nothing. To run closer to real time, the scheduler should look for
   new files on its own tick (a mode of the existing scheduler, not a new service), so the
   delay is the file's arrival, not an operator.
2. **Polled APIs** (ENTSOG, GIE, ECB, ECMWF, National Gas, Elexon, ENTSO-E). The scheduler runs
   each source on its declared schedule and freshness policy, then captures changed rows over a
   4-day window (R12) and drains. The right cadence is publication-aware: poll just after the
   publisher's known release time, and more often only where the publisher updates more often
   (UMMs every 15 minutes or faster; storage once, after the daily release).
3. **Pushed feeds** (ticks from a licensed adapter). These go to the quote store and the quote
   stream, not through the outbox. For opportunities, a quote should be conflated per
   instrument (the latest price every few seconds, and only when it moved by more than a tick
   size) before it becomes a `price.updated` event, so the engine evaluates prices, not ticks.

Downstream of the event, every class runs the same path: outbox delivery, targeted
re-evaluation, the opportunity store (persistence, a 20 % material-change threshold, the
validity window), the stream, monitoring and notifications. Classes differ only in how fast
data arrives and how often it is worth evaluating.

## 4. A streaming layer, or the outbox and LISTEN/NOTIFY

Measured, not assumed ([09](09_VALIDATION_EVIDENCE.md)). On PostgreSQL with the demo desk, the
listen worker has claimed and started an event about 0.2 s after its commit; the end-to-end
path to the stream is dominated by the evaluation (5 to 6 s for the evaluators one TTF price
feeds) and the stream's 1.5 s poll, not by the transport. One process published about 230
events a second (each checked against the revisions held) and delivered 1,300 to 1,900 a second
to a consumer that does no work (section 8). That is far more than this desk produces: a few
thousand settlements and fixings a day, tens of UMMs, and file imports. A burst of a full day's
settlements is delivered in seconds; what takes time is evaluating them, and the targeted path
evaluates each affected evaluator once per batch, not once per event.

**Judgement: keep the outbox and LISTEN/NOTIFY.** A streaming platform (Kafka, Redis streams,
a managed equivalent) would add a service to run, secure and back up, and a second place where
state lives, without moving the number that matters. The costs that do matter are evaluation
time and source cadence, and both are addressed in the pipeline itself (targeted re-evaluation,
conflation, publication-aware polling).

Revisit, with an ADR, only when one of these is measured:

- outbox lag (oldest pending delivery) above the budget of its class for a sustained period
  at normal load;
- tick-level inputs that must be evaluated individually rather than conflated;
- consumers outside this monolith that need the event history replayed independently;
- event volume a hundred times today's, sustained.

`market_events.py status` and the M6 lag alert already report the first of these.

## 5. Role-specific routing

Every monitoring alert carries a category; M7 maps each category to a notification category,
an owner role and an escalation role (`application/alert_routing.py`). The notification body
ends with "For: <owner>. If not acted on: <escalation>." A channel (an email list today) picks
the categories and the lowest severity it receives; a channel subscribed to `alert` keeps
receiving opportunities, nominations and source alerts as before.

| Alert | Notification category | Owner | Escalation | Prompt in the owner's words |
| --- | --- | --- | --- | --- |
| New-engine opportunity open | `opportunity` | Trader | Management | "Opportunity open: Kestrel supply; valid until 17:00; for review, nothing is traded" |
| Credit line, mandate, stale marks | `limits` | Risk manager | Management | A breach or a mark too old to value the book |
| Nomination deadline, delivery shortfall | `nomination` | Operations (scheduler) | Trader | "Renomination for the TTF line closes in 30 minutes" |
| Outage at a supply point | `alert` | Trader | Risk manager | The supply lost and what covering it costs |
| Price move | `alert` | Trader | Management | |
| Fundamentals (storage, demand) | `alert` | Analyst | Trader | |
| Strategy | `alert` | Quant researcher | Trader | |
| Data source failed or stale | `source` | Data operator | Platform administrator | |
| Tariff publisher not read on schedule; operator without next-period prices after the NC TAR deadline (TAR-1) | `source` | Data operator | Platform administrator | "ENTSOG transparency platform: tariffs not read on schedule" |
| Capacity auction or LNG slot window opening within 3 days (TAR-1) | `nomination` | Operations (scheduler) | Trader | "Opens Mon 01 Mar 15:00 UTC: Quarterly capacity auction (CAM NC)"; monthly auctions are not alerted |
| LNG cargo change: hedges (LNG-2) | `cargo` | Trader | Management | "Hedges no longer match Aurora (SAB-0420): buy 383,333 MWh TTF 2026-11 at short notice; sell 379,373 MWh TTF 2026-12" |
| LNG cargo change: berth, send-out, nominations | `nomination` | Operations (scheduler) | Trader | "Renominate 10 gas day(s) for Aurora (SAB-0420)", each day with the cut-off it hits |
| Scheduling break near its cut-off (SCHED-1) | `nomination` | Operations (scheduler) | Trader | "NBP Aldermoor Energy plc: lesser rule cut, 1,200 MWh at risk", with the arithmetic, the next step, the cut-off and the indicative cash-out; "Withdrawn: …" when fixed |
| LNG cargo change: exposure and mandates | `limits` | Risk manager | Management | "Mandate breach from Aurora (SAB-0420)": net by month, the mandate before and after |
| LNG cargo change: material | `desk_head` | Management | Management | "Material cargo change: Aurora (SAB-0420)" with the reasons and the threshold |
| News on a contract's hub (NEWS-1) | `alert` | Trader | Management | "Department for Energy Security and Net Zero: Update on Langeled flows to Easington", why it touches the book and the source |
| News on a cargo's vessel or terminal (NEWS-1) | `cargo` | Trader (LNG desk) | Management | The item, the cargo it names and the source |
| News on a hub the firm nominates at (NEWS-1) | `nomination` | Operations (scheduler) | Trader | The item and the hub's nominations it touches |
| LNG disruption: new default or frontier (LNG-3) | `cargo` | Trader | Management | "Disruption options changed: ZEE-1", then "Recommended: ZEE-1: … borrow in tank and buy extra send-out. Expected P&L -182,000 EUR (worst -395,000)", the frontier and what changed; nothing is booked |
| LNG disruption: schedule consequences (LNG-3) | `nomination` | Operations (scheduler) | Trader | The same notice: the default's berth and send-out change the nominations |
| LNG disruption: material (LNG-3) | `desk_head` | Management | Management | The same notice; told on a new default, a new frontier or a P&L move of 50,000 EUR or more |

The four LNG rows are one consumer's messages, one per role, about the same `cargo.changed`
revision (12, "Who hears about a change"). They do not go through the one-per-alert mirror
below: each notifies itself, keyed on its message's digest, with a 30-minute cooldown per role
(broken by a rise in severity or a new item) and a withdrawal notice when a later change makes
it moot. A channel subscribed to `alert` receives the scheduler's message (through
`nomination`) and none of the other three; a desk subscribes each role's category.

Dedupe, materiality and cooldown are unchanged. An alert's fingerprint gives it a stable id;
the notification outbox holds one row per alert id (`alert:<id>`), now inserted under a
savepoint so two workers cannot write it twice, and sent under `FOR UPDATE SKIP LOCKED` so two
dispatchers cannot send it twice. The opportunity engine cuts a new version only on a 20 %
move or a state change. A failed delivery is retried at most three times, five minutes apart.

**What this routing does not do yet.**

- Routing is by category to a channel, not to a named person on duty. The owner is a role in
  the message. "Whoever is in charge" means the channel the desk points at its duty roster;
  there is no rota in the platform.
- Escalation is stated, not timed. A critical limit alert already waits for acknowledgement
  (F1-10); the next step is a second notification to the escalation channel when an owner has
  not acknowledged within a set time. That is the crisis path the owner asked for, and it
  needs an acknowledgement deadline per category (not built).
- One notification per alert id: an alert that resolves and opens again under the same
  fingerprint is not notified a second time, and a new version of an open opportunity is not
  notified. The stream and the page show both.

## 6. The opportunity lifecycle on the stream

An opportunity is **open** while it is listed (actionable or indicative, surfaced) and inside
its validity window (`expires_at_utc`; `deadline_utc` when it has one). The stream sends:

- `opportunity` with `status: "open"` when it becomes listed, and again on each material new
  version;
- `opportunity` with `status: "withdrawn"` and a `reason` (`watch`, `blocked`, `expired`,
  `converted`) when it leaves the listed states, and with reason `expired` the moment its
  validity window ends, even if the engine has not run since (the stream checks the window on
  every poll);
- `evaluated` when an evaluation finishes, so the page's "as of" moves even when nothing
  changed.

Events carry identifiers, state, version, times, books and source families, and no figure: the
page re-reads `GET /api/opportunities`, which applies the caller's entitlements to the values.
Each event is filtered by the same rule as the opportunity itself (every source family granted;
every book visible unless the lane is `market`). The monitoring alert follows the same
lifecycle: opened when listed, resolved when withdrawn or past its validity.

## 7. Automation one step away

The signals are shaped so a strategy could later act on them: every change names the
opportunity, its version and the evaluation that produced it, and a withdrawal is an explicit
event, so a proposal built on version 3 can be voided when version 3 is withdrawn. What stays:
a person approves through a decision case, and nothing is executed or sent to a venue. No
order path exists, and none is added.

## 8. Measured before and after

Price event committed to the opportunity change visible, PostgreSQL 16, demo desk, one host.
Method and raw samples in [09](09_VALIDATION_EVIDENCE.md)
(`scripts/ops/measure_live_latency.py`).

| Path | Commit to evaluation committed | Commit to change on the stream | Samples |
| --- | --- | --- | --- |
| Before M7: the 60 s scheduler tick drains the outbox (10-batch cap); the stream carries the legacy engine | median 29.5 s (16.6 to 57.1 s); evaluation itself 5.8 to 7.8 s | Never: the page showed it only when reloaded | 6 |
| After M7: listen worker woken at commit; `/api/stream/opportunities` | median 5.7 s (5.3 to 12.3 s) | **median 6.6 s (6.0 to 12.7 s)** | 12 |

Where the 6.6 s goes: about 0.2 s from commit to the worker's claim, 5.2 to 6.5 s evaluating
the four evaluators that read a TTF next-day price (event exposure, locational, market scan,
sell-down), then up to 1.5 s until the stream's next poll. The slowest sample (12.7 s) waited
for the one-minute full sweep, which held the evaluation lock. The input was a firm mark saved
through the same calls as `PUT /api/market/firm-marks`; a settlement or fixing takes the same
path from its event on. The transport is not the cost: the next step is making the evaluation
cheaper (the price queries it repeats), not a faster bus.

The measurement found a defect, fixed in M7: a mark set back to an earlier value
(44, 40, 44) was refused by the outbox as a replay, because its event had no publication
time, so the third save waited for the full sweep (about 20 s) instead of the targeted run.

### A scheduling break to the scheduler (SCHED-1)

| Path | Budget | Measured | How |
| --- | --- | --- | --- |
| Nomination or TSO answer imported to the break alert in the outbox | Within 3 hours of the cut-off and at least 30 minutes before it; withdrawn on the next pass after the fix | One pass (`queue_break_alerts`, today and tomorrow, firm-wide) 0.03 s on PostgreSQL 16 (median of 6 runs, 0.026 to 0.036 s, the demo desk); the delay is the monitoring worker's cadence (`--interval-seconds`, default 10 s) or the dispatch script's schedule | `tests/integration/test_gas_day_reconciliation_postgres.py` |

The alert is raised by polling, not by an outbox event: an imported status publishes no
market event, and a break becomes urgent because time passes (a cut-off nears), not because
anything is written. The import itself, which runs when the scheduling file arrives, remains
the larger delay; there is no TSO confirmation feed (Edig@s messages are imported).

### A cargo change to each role (LNG-2)

ETA import committed to every role's notification in the outbox, PostgreSQL 16, one host, the
listen worker as its own process (`--poll-seconds 0.05`), 8 runs of
`tests/integration/test_lng_cargo_change_postgres.py`:

| Change | Median | Min | Max |
| --- | --- | --- | --- |
| The first change after the worker starts (it loads the cargo modules) | 0.66 s | 0.61 s | 0.75 s |
| The next change in the same worker (the ETA corrected back: every message withdrawn) | 0.11 s | 0.09 s | 0.16 s |
| Outbox to the channel sender (dispatch) | +0.02 s | | |

The consumer's own work is the plan rebuilt twice and each mandate on the book re-checked
over the ladder; the ladder read is most of it (about 0.1 to 0.15 s on the test desk). The
budget for an ETA or slot change is 15 minutes; the import, which runs when the file arrives,
is now the whole of the delay.

### A tariff change (TAR-1)

A register row written to its new version and `tariff.changed` event committed together, and
from that commit to the `opportunities` consumer having processed the delivery, PostgreSQL 16,
one host, 8 runs of `tests/integration/test_tariff_book_postgres.py` (the consumer drained in
process; no opportunity depended on the test point, so no evaluator ran):

| Step | Median | Min | Max |
| --- | --- | --- | --- |
| Read written to version and event committed (an `INDICATIVE->FINAL` change) | 12.5 ms | 11 ms | 14 ms |
| The first write in a fresh process (imports and connection) | 166 ms | 160 ms | 205 ms |
| Commit to the opportunities consumer having processed it | 5.5 ms | 5 ms | 7 ms |

An earlier set of 8 runs on the same host, before a restart, gave 18 ms, 244 ms and 10.5 ms.
The designed figure is the poll: hourly in the NC TAR publication weeks and daily otherwise,
plus ENTSOG's read time (about 2 s per point). A full capture over ENTSOG's 12,670 register
rows took 77 s the first time (every row becomes version 1 with its event, a one-off backfill
best run once after deploy with `scripts/ops/tariff_book.py sync --commit`) and 2.3 s when
nothing had changed; the scheduler's capture therefore reads the register's signature each
minute and makes a full pass only when it moved or once an hour. An opportunity that read the
tariff is re-evaluated by its stored dependency keys; that evaluation's cost is the one in the
table above, not the tariff path.

### A disruption re-optimised (LNG-3)

The owner's scenario (17, section 4) seeded as rows, the cargo's ETA moved twelve times
between 28, 29 and 30 January, `capture_desk` committed, then the `lng_disruption` consumer
run in process (`market_events.process`) to the run row and its notices committed. One host,
the development container:

| Store | Commit to run row and notices, median | Max | Options read (`disruption_options`) | Engine alone |
| --- | --- | --- | --- | --- |
| PostgreSQL 16 | 0.052 s | 0.260 s (first run: imports) | 0.050 s | 12 ms |
| SQLite | 0.028 s | 0.153 s | 0.025 s | 12 ms |

The engine is about 2 ms per option: 112 options (three cargoes late, eight spare slots)
take 0.22 s, and the cap of 256 combinations about 0.5 s. The budget is the cargo budget,
15 minutes from the input's commit; as for LNG-2, the import's own schedule is the delay,
not the re-optimisation.

## 9. Retiring the legacy intraday engine (M7 d): blocked

Alerts and the opportunity stream no longer read the legacy engine. It cannot be removed yet,
because these still depend on `IntradayOpportunityRecord` and
`scan_and_persist_intraday_opportunities`:

- `GET /api/market/opportunities` (a public, documented route);
- the market-context projection and the review context;
- `pipeline_health` and runtime-data retention;
- `scripts/ops/import_market_quotes.py` and the simulated-price ingestion, which run the scan
  after storing quotes;
- the web market and day-board screens that read the route above.

Retirement needs the intraday quote spreads it computes to become a new-engine evaluator fed by
conflated quote events (R14), the route to be deprecated in the contract policy with a removal
date, and those screens to read `GET /api/opportunities`. Recorded as R19 in
[07](07_RISK_AND_DEPENDENCY_REGISTER.md).

## 10. Where "live everywhere" is not the goal

- **Daily data stays daily.** Settlements, storage, FX fixings, tariffs and weather runs change
  once a day or less. Polling them every few seconds adds load on the publisher and on us, and
  a "live" badge on a daily figure misleads more than an honest "as of" does.
- **Evaluation needs calm inputs.** The engine keeps an opportunity only after it persists and
  cuts a new version only on a material move. Evaluating every tick would flap opportunities in
  and out and raise alerts nobody can act on.
- **Attention is the scarce resource.** A prompt that arrives every minute is ignored. The
  budget is set by when a person can act: before a cut-off, within a trading window, while a
  cargo can still be rerouted.
- **Licences and cost.** Real-time exchange data is licensed per user and per use. Seconds-level
  prices are worth paying for on the quote board and for prompt spreads, not on every screen.
- **Backtests and model fits** belong off the live path, on a fixed data cut-off, so their
  results can be reproduced.

The goal is that each class is as fresh as its decisions need and that every screen says how
old its data is.
