# 19 Data capacity and infrastructure (CAP-1)

How much data the platform holds and takes in today, how much it will hold after a 5-year
history back-fill and 10 years of operation, what infrastructure that needs and when, and how
it compares with what trading firms and energy majors publish about their own systems.
Written 2026-11-25 for the owner's question (relayed): "What's my data size? What's my data
rate? What kind of infrastructure will I need? ... We're not gonna waste money on hardware,
but we're definitely not gonna constrain us with it."

**This report recommends; it adopts nothing.** No service, datastore or dependency is added.
AGENTS.md rule 5 (no new service or datastore without a reviewed ADR and a measured need) and
ADR Decisions 2, 24 and 28 stand. Section 3.4 lists the ADRs the owner may want to take later,
each with the measurement that should trigger it. The only code in CAP-1 is a read-only
measurement script (section 5). Decisions are in [08](08_DECISION_LOG.md); programme state in
[10](10_PROGRAMME_STATE.md).

Every figure is marked **measured** (on this repository's code and a PostgreSQL 16 store),
**published** (with its source), or **estimate** (an assumption, stated so it can be changed).

## Summary for the owner

**Size.** Under the main scenario (today's sources plus the planned ones: hourly flows from
every ENTSOG point, more TSOs, all European power zones, weather forecasts, LNG carrier
positions, power and carbon curves), 15 years of data (5 years of history plus 10 years of
operation) comes to about **1.5 TB** stored as the platform stores rows today, or about
**0.33 TB** once older data is compressed. With a standby copy and backups the whole
footprint is about 5.3 TB, or about 1.2 TB compressed. Today's sources alone stay under
50 GB for 15 years.

**One thing to fix first.** The platform keeps a full raw copy of every ENTSOG page it reads,
every hour, including the six days of data it re-reads each time. Today that is about 107 MB
a day, ten times everything else together. With the planned hourly ENTSOG data it would be
about 3.2 GB a day and 12.8 TB after 15 years. Keeping each distinct page once, and moving
old raw pages to cheap file storage, takes that to well under 0.4 TB. This is a code and
policy change, not hardware.

**Rate.** This is a slow-data business. The main scenario averages about 5 new rows a second
and peaks near 1,000 rows (about 1 MB) a second for a minute at the gas-day rollover or when
day-ahead power prices publish. A burst of outage messages is a few rows a second; what takes
time there is re-valuing the book, not storing the messages. One PostgreSQL server measured
here writes about 14,000 rows a second, so the main scenario has more than 10 times headroom.
Only exchange tick data (the aggressive scenario: every quote on ICE and EEX screens) changes
the picture, at about 3,000 to 5,000 rows a second in bursts and 3 TB a year.

**What to run now.** What the platform already uses: one PostgreSQL primary with a hot
standby, off-site backups, and the existing outbox for events. No Kafka, no TimescaleDB, no
new database. A dedicated server of the Hetzner AX102 class (128 GB memory, NVMe disks) lists
at 259 EUR a month; two of them (primary and standby) plus object storage for backups is
about 550 to 700 EUR a month (estimate) and has 10 times headroom on size and rate for the
main scenario.

**What to add, and when.**

1. When the planned sources arrive: split the biggest tables by month inside PostgreSQL
   (already planned in ADR 24, when a table passes about 50 million rows; the planned ENTSOG,
   power and vessel tables would pass it as soon as five years of their history is loaded,
   or within about 14 to 21 months of new data if no history is loaded).
2. Then: move months older than two or three years out of the database into compressed
   Parquet files on object storage, read with DuckDB for research and backtests. Measured
   here, that format is 8 to 45 times smaller than the database rows.
3. When analysts' queries slow the desk's screens: add a read replica (one more server).
4. Only if the firm licenses and keeps tick data: a column store (ClickHouse, open source)
   for ticks, beside PostgreSQL, not instead of it.
5. Kafka only if one of the triggers already written in doc 15 is measured (sustained outbox
   lag, ticks that must be evaluated one by one, outside consumers that need replay, or 100
   times today's event volume). None is close.

**Cost.** Today and mid-term about 550 to 700 EUR a month self-hosted, or roughly 2 to 4 times
that on a managed database service (estimate). Adding a read replica and a tick store is
about another 250 to 600 EUR a month each. Licensed market data costs far more than any of
this hardware.

**How we compare.** High-frequency firms (Citadel Securities, Hudson River Trading, Jane
Street) solve a different problem: microsecond market making on exchange tick data. They
store petabytes (Jane Street sized one warehouse at 10 PB; HRT stores "hundreds of
petabytes") and run hundreds of thousands to over a million CPU cores. Copying them would be
waste. Energy majors' trading arms (Shell, BP, Equinor and its trading company Danske
Commodities, Trafigura) are closer to our job and publish their tools, not their volumes:
Azure or AWS data lakes with Databricks or Snowflake, Kafka in some teams, and PostgreSQL,
TimescaleDB, ClickHouse or kdb+ for time series. What to borrow: compressed columnar files
for history, one governed catalogue of data, and a stream bus only when many systems must
share one feed.

## 1 What we ingest today

### 1.1 Method

- **Inventory from the code.** Every connector manifest
  (`src/eurogas_nexus/domain/connectors/builtin/`, read through
  `domain/dataops/registry.py:source_definitions()`), the ingestion modules under
  `src/eurogas_nexus/ingestion/`, `reference_data/` and `streaming/`, and the runtime tables
  they write (164 tables at schema head `0086_lng_disruption`).
- **Row sizes measured** on a scratch PostgreSQL 16 database migrated to head and loaded with
  the demo desk (`scripts/demo/seed_demo_desk.py`: 400 gas days of simulated flows, storage,
  LNG, power fundamentals and month-ahead history), then `scripts/ops/market_events.py
  capture` and `drain` over that history (22,698 events). Bytes per row are
  `pg_total_relation_size` (heap, indexes and TOAST) divided by rows, so **indexes are
  included in every bytes-per-row figure below**.
- **Ticks measured** through the product's own `application.market_ticks.ingest_ticks`
  with the demo exchange feed's generator (`scripts/demo/exchange_feed.py`): 44,637 quotes
  and 7,423 trade prints.
- **Raw archive measured** through the product's own `archive_raw_payload` with 19 pages of
  1,000 records shaped on the fields the ENTSOG API manual documents for an operationalData
  record ([ENTSOG TP API manual v3.0](https://transparency.entsog.eu/api/archiveDirectories/8/api-manual/ENTSOG_TP_API_UserManual_v3.0.pdf)).
  The pages are synthetic; a real page was not fetched because this environment's network
  proxy refused `transparency.entsog.eu` (counted as tried).
- **Live counts** from the first live bring-up of the public sources
  ([LIVE_BRINGUP_2026-11-12.md](../../data/LIVE_BRINGUP_2026-11-12.md)): rows received,
  inserted and revised per scheduler attempt against the real ENTSOG, GIE, ENTSO-E, Elexon,
  National Gas, ECB, BoE, NY Fed and EIA platforms.
- The demo data is simulated and more repetitive than real data, so measured compression
  ratios (section 2.3) flatter; the model uses lower published ratios.

### 1.2 Measured bytes per row

| Table | What it holds | Rows measured | Bytes per row (heap + indexes + TOAST) | Basis |
| --- | --- | --- | --- | --- |
| `flow_observations` | ENTSOG, National Gas, demo flows | 25,802 | 831 | measured |
| `market_observations` | settlements, curves, assessments | 35,050 | 471 | measured |
| `storage_observations` | GIE AGSI+, National Gas storage | 15,730 | 376 | measured |
| `power_observations` | ENTSO-E, Elexon | 14,880 | 373 | measured |
| `lng_observations` | GIE ALSI, National Gas LNG | 13,175 | 356 | measured |
| `market_quotes` | ticks: two-sided quotes with session statistics | 44,877 | 888 | measured |
| `market_trades` | ticks: trade prints | 7,423 | 523 | measured |
| `market_events` | outbox events | 22,698 | 676 | measured |
| `market_event_deliveries` | one row per consumer and event | 22,714 | 141 | measured |
| `raw_payload_archives` (ENTSOG page) | exact page text and its parsed JSON, both kept | 19 pages, 19,000 records | 235 per record (922 bytes of JSON per record before TOAST compression) | measured, synthetic pages |
| `opportunity_versions` | an opportunity's figures at a version | 74 | 1,653 (tuple) | measured |
| `audit_events` | governed actions | 17 (in the shared test store) | 580 (tuple) | measured |
| `capacity_observations` | ENTSOG capacity ranges | 0 in demo | 831 (same columns as flows) | estimate |
| `forecast_observations` | ECMWF point forecasts with provenance | 0 in demo | 600 | estimate |
| `news_items` | item, summary, entities | 0 in demo | 3,000 | estimate |
| `remit_umm_messages` | REMIT UMMs with versions | 2 in demo (304-byte tuple) | 1,500 with real remarks text | estimate |

The observation rows are wide for what they carry (a number, a period, a point) because each
holds its provenance: source reference, receipt time, freshness, native unit and value, a
normaliser version and a JSON metadata object (233 bytes of JSON on an average quote row).
That provenance is the platform's point and stays; it is also why columnar compression pays
so well on history (section 2.3).

### 1.3 Source inventory

Granularity and cadence are from the connector manifests and ingestion code; counts "today"
are the live bring-up's; real-world counts are published where a source is given, otherwise
estimates.

| Source (code) | Granularity | Cadence in code | Entities today | Real-world entities | Rows a day today | Bytes a row | MB a day |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ENTSOG flows (`src-entsog`, `ingestion/entsog_*`) | gas day (`periodType=day`); the API also serves `hour` (manual v3.0) | hourly (`interval_seconds=3600`), 7-gas-day rolling look-back (`PRODUCTION_SOURCE_OPERATIONS.md`) | about 790 rows a closed gas day at about 530 points; 805 series | 789 connection points and 1,283 operator point directions read live (`entsog_transport.py`); 25 operationalData indicators (manual v3.0) | 830 (790 plus about 40 revisions) | 831 | 0.69 |
| ENTSOG capacity (same connector) | validity ranges | hourly with flows | 3,925 series, 12,647 rows | as left | about 470 (297 inserted and 175 revised on 14 Nov) | 831 | 0.39 |
| ENTSOG reference (points, operator directions) | current network | at most daily (`--entsog-reference-max-age-hours 24`) | 789 + 1,283 | as left | upserts, no growth | 840 | 0 |
| ENTSOG raw page archive (`raw_payload_archives`) | every page of every query | every run | about 19,000 records a run (38,006 over two attempts in the soak) | as left | **456,000 records** (24 runs) | 235 a record | **107** |
| ENTSOG tariffs (TAR-1, `tariff_versions`) | tariff period | hourly signature check, full pass on change | 12,670 register rows | every EU TSO through ENTSOG | about 35 versions (estimate) | 1,000 (estimate) | 0.04 |
| ENTSOG transmission UMMs (`src-entsog-umm`) and REMIT UMMs via GIE IIP (`src-remit-umm`, `gie_iip.py`) | event | hourly and every 30 minutes | 1,588 messages held after the first read | ACER registers 21,169 market participants ([ACER REMIT Quarterly Q1 2026](https://www.acer.europa.eu/sites/default/files/REMIT/REMIT%20Reports%20and%20Recommendations/REMIT%20Quarterly/ACER-REMIT-Quarterly-Q1-2026.pdf)); gas UMM count not published | about 100 (estimate) | 1,500 (estimate) | 0.15 |
| GIE AGSI+ and ALSI (`src-gie`) | gas day, revised for about two weeks | daily | 11 series (Europe and NWE countries) | facility-level series across the EU, about 500 (estimate) | about 15 | 376 | 0.01 |
| ENTSO-E (`src-entsoe`, `entsoe_transparency.py`) | 15 minutes since the day-ahead market moved to a 15-minute unit on 1 Oct 2025 ([EPEX SPOT](https://www.epexspot.com/en/news/market-coupling-steering-committee-confirms-go-live-15-minute-mtu-sdac-trading-day-30)) | hourly | 4 zones (BE, DE-LU, FR, NL), 24 series | about 40 bidding zones (estimate) | about 1,545 (13,908 rows over 9 days) | 373 | 0.58 |
| Elexon (`src-elexon`) | half hour | every 30 minutes | 4 series | GB | about 200 | 373 | 0.07 |
| National Gas supply and demand (`src-national-gas-*`) | gas day and within-day | every 3 and 6 hours | 1 storage, 1 LNG, 96 demand series | GB NTS | about 120 | 600 (estimate) | 0.07 |
| ECB FX, €STR, SONIA, SOFR, EIA Henry Hub | daily fixing | daily | 6 pairs, 3 rates, 1 price | as left | about 12 | 300 (estimate) | 0.004 |
| Settlements and curves (EEX NGP public download, ICE Endex, licensed EOD files; `market_observations`) | trading day | after the close, by importer | demo: 5 hubs | 8 hubs times about 65 tenors (WD, DA, WE, BOM, 36 months, 12 quarters, 6 seasons, 6 years) = 520 (estimate) | 520 | 471 | 0.24 |
| Exchange ticks (EEX, ICE OCM, Trayport adapters; `market_quotes`, `market_trades`) | sub-second | push to `POST /api/market/ticks` | **none licensed**; demo feed 4 instruments, 0.8 to 4 events a second, pruned after 48 h | section 2.1, scenario C | 0 counted | 888 and 523 | 0 |
| LNG cargo positions (Kpler file import, `lng_positions.py`, `lng_cargoes`) | per import | file drop | the book's cargoes | 804 active LNG vessels (published, section 2.1) | about 50 updates (estimate) | 1,000 (estimate, with track JSON) | 0.05 |
| ECMWF open data (`src-ecmwf-open-data`) | 0.25° grid, 4 runs a day | not scheduled (series bindings first) | 0 rows | section 2.1 | 0 | 600 (estimate) | 0 |
| News (NEWS-1, `news_items`) | item | poll script | a few a day | official feeds | about 20 (estimate) | 3,000 (estimate) | 0.06 |
| Firm data: ETRM trades, deliveries, nominations, confirmations (DATA-1, SCHED-1 imports) | deal and gas day | file import | demo book | the firm's own | about 1,000 (estimate) | 400 (estimate) | 0.4 |
| Market events and deliveries (outbox) | change | at commit | 22,698 from 400 demo days | section 2 | about 2,000 (estimate) | 958 (one event, two deliveries) | 1.9 |
| Opportunity evaluations and versions | sweep and change | full sweep at most once a minute, targeted on events | 37 opportunities | as left | about 1,640 (upper bound: a sweep every minute) | 1,507 (estimate) | 2.5 |
| Audit events | governed action | on write | as left | as left | about 2,000 (estimate) | 1,000 | 2.0 |
| Ingestion runs and issues, observation revisions, monitoring and notifications | run, revision, alert | per attempt | 71 scheduler iterations in 77 minutes (soak) | as left | about 700 | 1,357 | 0.95 |
| **Total today** | | | | | **about 11,300 rows and 456,000 raw records** | | **about 117 (10 canonical, 107 raw)** |

### 1.4 Finding: the raw page archive is about 91 % of today's growth

`ingestion/entsog_ingestion.py:archive_entsog_pages` appends every page of every ENTSOG
query as a new row in `raw_payload_archives`, holding the exact text **and** its parsed JSON
(`entsog_transport.py:raw_archive_values`). There is no deduplication by `payload_sha256` and
no pruning tool for this table (audit events and job records have one). The production
schedule reads ENTSOG hourly with a 7-gas-day look-back, so each closed gas day is re-archived
about 168 times. Measured: 19 pages of 1,000 records are 17.5 MB of JSON and 4.5 MB on disk
after PostgreSQL's TOAST compression.

- Today: about **107 MB a day, 39 GB a year**, against about 10 MB a day for every other table
  together.
- With hourly ENTSOG data (scenario B): about **3.2 GB a day, 1.2 TB a year**.

The archive is a deliberate lineage control (raw to canonical, CR raw-archive lineage), so the
answer is not to drop it. Keeping each distinct page once (skip a page whose digest equals
the last held page for the same query) and moving pages older than a few weeks to compressed
files in object storage keeps the lineage and removes most of the growth. The model's "raw
kept once" line assumes twice the public records a day at 235 bytes each, in the database,
and half that size once moved to zstd files (measured 2.0 times smaller than TOAST on the
synthetic pages). This needs an ADR and a code change (section 3.4, ADR-P1).

### 1.5 Finding: retention today keeps months, not years

`application/retention.py` (run by `scripts/ops/prune_runtime_data.py`) deletes market quotes
after 30 days and market observations after 90 days; the demo feed prunes its own ticks after
48 hours; audit events default to 365 days. A 15-year history of settlements and curves is
therefore not kept if the prune runs. The projection below assumes every observation is kept
for the whole horizon, because the owner asked for 15 years. Which tables keep everything,
which keep a summary (for example a daily close instead of every quote) and which keep months
only is a decision for the owner (ADR-P2); it changes the size far more than any hardware
choice.

## 2 Projection

### 2.1 Scenarios

| | A: today's source set | B: plus planned sources (main scenario) | C: aggressive, tick-level exchange data |
| --- | --- | --- | --- |
| ENTSOG | daily flows, capacity ranges | hourly and daily Physical Flow, Nomination, Renomination and Allocation for about 800 series: 80,000 rows a day (estimate) | as B |
| Other TSOs | none direct | THE, GTS, NaTran, Fluxys, National Gas within-day: 20,000 rows a day (estimate) | as B |
| Storage, LNG terminals | GIE NWE, 11 series | GIE across the EU, about 510 series (estimate) | as B |
| Power | ENTSO-E 4 zones, Elexon | about 40 bidding zones at 15 minutes: prices, load, load forecast, generation by type, cross-border: 85,000 rows a day (estimate); Elexon in full | as B |
| Curves | 8 gas hubs, 520 settlements a day | plus power (10 markets), carbon (EUA, UKA) and intraday indices: 2,160 a day (estimate) | as B |
| Weather | none | ECMWF at 200 points, 192 forecast steps a day: 38,400 rows (estimate) | as B |
| Vessels | cargo file imports | AIS for the LNG fleet, one position per vessel per 10 minutes: 804 vessels times 144 = 115,200 rows a day | AIS at the native rate: Class A reports every 2 to 10 s underway and every 3 minutes at anchor ([USCG Navigation Center](https://www.navcen.uscg.gov/node/84)); 60 % underway gives about 4.3 million rows a day (estimate) |
| Exchange | none | none | top of book for 300 instruments (gas hubs, power, carbon on ICE Endex, EEX and Trayport) at one update a second over 10 trading hours: 10.8 million quotes and 200,000 trade prints a trading day (estimate; full depth would be 10 to 50 times more and is not modelled) |
| Outages, news, firm data | as today | 10 times today | as B |
| Events, opportunities, audit, runs | as today | 10 times today (estimate) | as B |

Published anchors for the estimates: 804 active LNG vessels and 437 Mt of trade in 2025
([IGU World LNG Report 2026, via IIF-IIR](https://iifiir.org/en/news/world-lng-report-2026-north-american-exports-drive-record-growth-for-global-lng-trade));
ICE TTF futures and options traded a record 103 million contracts in 2025
([ICE press release](https://www.businesswire.com/news/home/20251215274852/en)); EEX Group
gas volume 8,823.2 TWh and power 13,493.7 TWh in 2025
([EEX Group annual volumes](https://www.eex.com/fileadmin/Global/News/EEX/EEX_Press_Release/2026/20260113_EEX_Group_Y2025_Volumes_Final.pdf));
ACER collects more than 80 million transaction records a day under REMIT
([ACER REMIT Quarterly Q1 2026](https://www.acer.europa.eu/sites/default/files/REMIT/REMIT%20Reports%20and%20Recommendations/REMIT%20Quarterly/ACER-REMIT-Quarterly-Q1-2026.pdf)).
No exchange publishes quote or message counts for its gas screens; scenario C's tick rate is
an estimate and the biggest uncertainty in this report.

### 2.2 The arithmetic (change any cell)

Rows a day times bytes a row gives MB a day; times 365 gives a year. Compressed figures divide
by the ratio in the last column (section 2.3). Ticks count 255 trading days a year. "Back-fill"
says whether 5 years of history is loaded at year 0.

| Stream | A rows a day | B rows a day | C rows a day | Bytes a row | A MB a day | B MB a day | C MB a day | Back-fill | Compression |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ENTSOG flows and operational data | 830 | 80,000 | 80,000 | 831 | 0.69 | 66.5 | 66.5 | yes | 10x |
| ENTSOG capacity ranges | 470 | 470 | 470 | 831 | 0.39 | 0.39 | 0.39 | yes | 10x |
| Other TSOs direct | 0 | 20,000 | 20,000 | 600 | 0 | 12.0 | 12.0 | yes | 10x |
| GIE AGSI+ and ALSI | 15 | 510 | 510 | 376 | 0.01 | 0.19 | 0.19 | yes | 10x |
| ENTSO-E | 1,545 | 85,000 | 85,000 | 373 | 0.58 | 31.7 | 31.7 | yes | 10x |
| Elexon | 200 | 2,000 | 2,000 | 373 | 0.07 | 0.75 | 0.75 | yes | 10x |
| National Gas | 120 | 120 | 120 | 600 | 0.07 | 0.07 | 0.07 | yes | 10x |
| FX, rates, EIA | 12 | 12 | 12 | 300 | 0.004 | 0.004 | 0.004 | yes | 10x |
| Settlements and curves | 520 | 2,160 | 2,160 | 471 | 0.24 | 1.02 | 1.02 | yes | 10x |
| ECMWF forecasts | 0 | 38,400 | 38,400 | 600 | 0 | 23.0 | 23.0 | no | 10x |
| AIS LNG positions | 0 | 115,200 | 4,300,000 | 300 | 0 | 34.6 | 1,290 | yes (licensed history) | 10x |
| Exchange quotes | 0 | 0 | 10,800,000 | 888 | 0 | 0 | 6,700 (trading-day average) | yes (licensed history) | 20x |
| Exchange trade prints | 0 | 0 | 200,000 | 523 | 0 | 0 | 73 | yes | 20x |
| REMIT and TSO UMMs | 100 | 1,000 | 1,000 | 1,500 | 0.15 | 1.5 | 1.5 | yes | 5x |
| Tariff versions | 35 | 35 | 35 | 1,000 | 0.04 | 0.04 | 0.04 | no | 5x |
| News | 20 | 200 | 200 | 3,000 | 0.06 | 0.6 | 0.6 | no | 5x |
| Firm data | 1,000 | 10,000 | 10,000 | 400 | 0.4 | 4.0 | 4.0 | yes (the firm's ETRM history) | 5x |
| LNG cargo updates | 50 | 500 | 500 | 1,000 | 0.05 | 0.5 | 0.5 | no | 5x |
| Market events and deliveries | 2,000 | 20,000 | 20,000 | 958 | 1.9 | 19.2 | 19.2 | no | 5x |
| Opportunity evaluations and versions | 1,640 | 3,440 | 3,440 | 1,507 (A), 2,290 (B) | 2.5 | 7.9 | 7.9 | no | 5x |
| Audit events | 2,000 | 10,000 | 10,000 | 1,000 | 2.0 | 10.0 | 10.0 | no | 5x |
| Runs, issues, revisions, alerts | 700 | 9,000 | 9,000 | 1,357 to 1,400 | 0.95 | 12.6 | 12.6 | no | 5x |
| **Canonical total** | **11,257** | **398,047** | **12.3 million** | | **10.1** | **226.5** | **8,255** | | |
| Raw archive as built | 456,000 records | 13.5 million records | as B | 235 | **107** | **3,177** | 3,177 | | 2x in zstd files |
| Raw archive kept once | 2 times public records | | | 235 | 1.3 | 87.4 | 87.4 | public sources, once | 2x |

The raw back-fill (5 years of public pages archived once) adds 1.2 GB for A and 80 GB for B
and C.

### 2.3 Compression: what the ratios rest on

Measured here (demo data exported to Parquet with pyarrow, codec zstd, against PostgreSQL's
on-disk bytes per row including indexes):

| Table | PostgreSQL bytes a row | Parquet zstd bytes a row | Ratio |
| --- | --- | --- | --- |
| `market_quotes` | 888 | 39.2 | 22.7x |
| `market_trades` | 523 | 24.7 | 21.2x |
| `flow_observations` | 831 | 23.9 | 34.8x |
| `market_observations` | 471 | 10.5 | 44.9x |
| `power_observations` | 373 | 8.5 | 43.9x |
| `lng_observations` | 356 | 27.3 | 13.0x |
| `storage_observations` | 376 | 34.7 | 10.8x |
| `market_events` | 676 | 89.0 | 7.6x |
| `raw_payload_archives` (synthetic ENTSOG pages, against TOAST) | 235,843 a page | 115,254 a page | 2.0x |

Published: Tiger Data says columnar compression reduces size "by up to 10x, with over 90 %
compression rates" ([Tiger Data blog](https://www.tigerdata.com/blog/postgres-toast-vs-timescale-compression));
one third-party production report measured 220 GB to 25 GB, 88.6 %
([DEV Community](https://dev.to/polliog/timescaledb-compression-from-150gb-to-15gb-90-reduction-real-production-data-bnj));
NYC taxi data was 6.8 times smaller in Parquet zstd than in CSV
([MotherDuck](https://motherduck.com/learn/csv-vs-parquet-benchmark/)). The demo's simulated,
repetitive metadata flatters the measured ratios, so the model uses the lower figures: 10x for
observations (in line with the published 90 %), 20x for ticks, 5x for text-heavy and
operational tables, and 2x for the raw archive.

### 2.4 Size at years 0, 5, 10 and 15

Year 0 is the end of the 5-year back-fill. Year 10 is 10 years of operation, **15 years of
data: the owner's horizon** (headline). Year 15 adds five more years of operation as a
stretch. "Rows as stored" is PostgreSQL as the platform stores rows today; "compressed" applies
section 2.3. Raw archive kept once (the recommended policy); the as-built archive follows.

| Scenario | Year 0 | Year 5 | Year 10 (15 years of data) | Year 15 |
| --- | --- | --- | --- | --- |
| A, rows as stored | 6 GB | 27 GB | **48 GB** | 69 GB |
| A, compressed | 1.2 GB | 5.7 GB | **10 GB** | 15 GB |
| **B (main), rows as stored** | 358 GB | 931 GB | **1.50 TB** | 2.08 TB |
| **B (main), compressed** | 69 GB | 200 GB | **0.33 TB** | 0.46 TB |
| C, rows as stored | 15.0 TB | 30.2 TB | **45.5 TB** | 60.7 TB |
| C, compressed | 0.92 TB | 1.89 TB | **2.87 TB** | 3.85 TB |
| *With the raw archive as built:* | | | | |
| A, as built | 6 GB | 220 GB | 434 GB | 648 GB |
| B, as built | 358 GB | 6.57 TB | **12.8 TB** | 19.0 TB |
| B, as built, raw moved to zstd files | 69 GB | 3.02 TB | 5.97 TB | 8.92 TB |

C "rows as stored" is shown to make the point: tick data does not belong in row-store tables
with per-row provenance JSON. Stored in a column store or Parquet it is about 2.9 TB.

Sensitivity: if B's daily volume grows 10 % a year instead of staying flat, the canonical data
at year 10 is about 1.6 TB instead of 1.1 TB (rows as stored, raw archive excluded).

### 2.5 Growth a year

| Scenario | Canonical, rows as stored | Canonical, compressed | Raw kept once | Raw as built |
| --- | --- | --- | --- | --- |
| A | 3.7 GB | 0.7 GB | 0.5 GB | 39 GB |
| B (main) | 83 GB | 10 GB | 32 GB (16 GB in zstd files) | 1,160 GB |
| C | 3,013 GB | 180 GB | 32 GB | 1,160 GB |

### 2.6 Multipliers: indexes, free space, WAL, backups and replicas

Indexes are already inside every measured bytes-per-row figure. On top of the primary's data:

| Multiplier | Value used | Why |
| --- | --- | --- |
| Free space and bloat | 1.25 times the data | autovacuum leaves free space in updated tables (estimate) |
| Hot standby | 1 more copy of the primary | the existing backup and DR foundation; a replica is a full copy |
| Read replica (stage 2) | 1 more copy | research and Power Query reads off the primary |
| Backups | 1 times the primary's data | two full backups at about 2x compression (estimate) |
| WAL archive for point-in-time recovery | 2 times a day's writes, kept 14 days | WAL is larger than the rows written because of full-page images (estimate) |

Footprint at year 10 (15 years of data), raw archive kept once:

| Scenario | Primary | Primary, standby, backups and WAL | Plus a read replica |
| --- | --- | --- | --- |
| A, rows as stored | 48 GB | 167 GB | 227 GB |
| A, compressed | 10 GB | 36 GB | 49 GB |
| **B, rows as stored** | 1.50 TB | **5.3 TB** | 7.1 TB |
| **B, compressed** | 0.33 TB | **1.2 TB** | 1.6 TB |
| C, compressed | 2.87 TB | 10.3 TB | 13.9 TB |

### 2.7 Data rate, peaks and bursts

| Case | A | B (main) | C |
| --- | --- | --- | --- |
| Average | 0.13 canonical rows a second; 5.3 raw records a second; about 1.4 kB a second | 4.6 rows a second; about 3.6 kB a second | 142 rows a second averaged over the year; 300 a second over trading hours |
| Hourly ENTSOG read | about 19,000 records in about a minute (run time estimate): about 320 records and 0.3 MB of page text a second | as built: 563,000 records a run (7 days times 80,470), about 940 records and 0.9 MB of page text a second over a 10-minute run (estimate); with the archive kept once and the look-back reading only what changed, the new hour's few thousand rows | as B |
| Gas-day rollover (05:00 UTC in winter; ENTSOG D-1, GIE, National Gas and TSO publications cluster around it) | about 25,000 records within the hour, peaks near 400 a second for a minute (estimate) | about 100,000 rows within the hour; design peak **1,000 rows and 1 MB a second** for a minute (estimate) | as B, while ticks run |
| Day-ahead power publication (about 12:45 CET) | 384 prices | about 40 zones times 96 prices = 3,840 rows, plus forecasts, within minutes | as B |
| ECMWF run released | none | 9,600 rows (200 points, one run's steps) within minutes | as B |
| REMIT outage storm | 500 UMMs in 10 minutes (estimate): under 1 row a second, 0.75 MB in all | 2,000 gas and power UMMs in an hour: under 1 a second | as B |
| Settlement and curve import | 520 rows in one importer transaction, seconds | 2,160 rows | as B |
| Tick bursts (news, the close) | none | none | 10 times the average: 3,000 ticks and 2.7 MB a second; design peak **5,000 rows and 5 MB a second** (estimate) |

What one host measured (4-core development container, PostgreSQL 16):

| Path | Measured | Source |
| --- | --- | --- |
| Outbox publish | about 230 events a second, one process | [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 4 |
| Outbox delivery to a no-op consumer | 1,300 to 1,900 a second, one process | [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 4 |
| Tick ingestion through `ingest_ticks` (batches of 500, evaluation off, pure-Python `pg8000` driver) | 1,500 ticks a second, one process | this report (scratch benchmark) |
| Server-side insert of quote rows with all indexes (one `INSERT ... SELECT` of 448,770 rows) | about 14,000 rows a second (32 s) | this report |
| Evaluation after a TTF price event | 5.2 to 6.5 s for the four evaluators that read it | [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 8 |

**Headroom.** B's design peak of 1,000 rows a second is 14 times below what one PostgreSQL
server wrote here, and its event rate (about 20,000 a day, bursts of hundreds a second) is
well inside the outbox's measured throughput. A burst of outage messages costs evaluation
time, not storage or transport: doc 15's targeted path already evaluates each affected
evaluator once per batch. C's 5,000 rows a second is only 2.8 times below the server-side
figure and above one Python writer, so tick capture at that rate needs bulk loading into a
column store (section 3).

## 3 Recommended infrastructure by stage

### 3.1 Options weighed

Costs are list prices from the cited pages (excluding VAT) or marked estimates. Operational
effort is an estimate for this team.

| Option | Licence | Worth adding when | Trigger metric: move now | Monthly cost, managed | Monthly cost, self-hosted | Operational effort |
| --- | --- | --- | --- | --- | --- | --- |
| PostgreSQL 16 plus the transactional outbox (in use; ADR 2, 24, 28) | PostgreSQL Licence | now | (already in place) | Aiven for PostgreSQL from 75 USD (Startup, 1 node), 180 USD (Business, 2 nodes), 270 USD (Premium, 3 nodes) ([Aiven](https://aiven.io/pricing/postgresql)); RDS `db.m7g.xlarge` compute in Frankfurt about 293 USD before storage and Multi-AZ ([Bytebase price index](https://www.bytebase.com/dbcost/rds/instance/db.m7g.xlarge/), third-party) | Hetzner AX102 (Ryzen 9 7950X3D, 128 GB, 2 x 1.92 TB NVMe) 259 EUR plus 129 EUR set-up ([Hetzner](https://www.hetzner.com/dedicated-rootserver/ax102?country=DE)); two for primary and standby | 1 to 3 days a month self-hosted (patching, backup drill, monitoring) (estimate); less managed |
| Native range partitioning by month (ADR 24's next step) | PostgreSQL | a table passes about 50 million rows or a time-range read misses its budget after indexing (ADR 24); the PostgreSQL docs' rule of thumb is a table larger than the server's memory ([PostgreSQL 16 docs](https://www.postgresql.org/docs/16/ddl-partitioning.html)) | B: ENTSOG (29 million rows a year), ENTSO-E (31 million) and AIS (42 million) pass 50 million at the back-fill (5 years of ENTSOG at B's rate is about 146 million rows), or within 14 to 21 months of new data without one; A: never within 15 years (largest table about 8.5 million rows) | 0 | 0 | 2 to 4 weeks once (unique keys must include the partition key, which touches upserts; doc 18's migration rules apply), then automatic |
| Parquet on object storage, read with DuckDB (cold history, research bundles) | Parquet: Apache 2.0; DuckDB: MIT ([DuckDB FAQ](https://duckdb.org/faq.html)) | partitions exist and the hot database is mostly old months | hot database above the server's memory, or backups and restores take longer than the recovery target | object storage: Hetzner 6.49 EUR a month including 1 TB, about 6.47 EUR for each further TB ([Hetzner](https://www.hetzner.com/storage/object-storage/pricing/)) | same; DuckDB runs in-process | 1 to 2 weeks for the export job and manifests; little after |
| Read replica | PostgreSQL | analysts' and Power Query reads compete with the desk | primary CPU above 60 % sustained, or desk reads miss doc 15's budgets during research runs | one more node on the plan | one more AX102, 259 EUR | about a day to set up; monitoring of lag |
| TimescaleDB (hypertables, columnstore compression, continuous aggregates) | compression and continuous aggregates are in the Community edition under the Timescale License (TSL), not Apache 2.0 ([Tiger Data licences](https://www.tigerdata.com/legal/licenses)) | only if partitioning and Parquet miss a stated size or aggregate target (doc 18: DEFER) | not reached in A or B | not priced here | 0 licence; same server | extension upgrades tied to PostgreSQL upgrades; legal review; migration of unique keys to hypertables |
| Kafka (self-managed or managed) | Apache Software Foundation project, Apache Licence 2.0 ([Apache Kafka](https://kafka.apache.org/)) | doc 15 section 4's triggers: sustained outbox lag, ticks evaluated one by one, outside consumers needing replay, 100 times today's events | none is close in A or B; in C, only if ticks must reach several systems | Aiven's estimator: about 276 USD at 0.1 MB/s, 622 USD at 1 MB/s ([Aiven](https://aiven.io/pricing/kafka)) | 3 brokers on small servers, a few hundred EUR (estimate) | a new system to secure, upgrade and recover: 2 to 5 days a month (estimate); the dual-write problem ADR 28 avoided |
| Redpanda | Community Edition licence: cannot be offered "as a commercial streaming or queuing service", 50-core limit, Tiered Storage and Iceberg Topics need an enterprise licence ([Redpanda docs](https://docs.redpanda.com/current/get-started/licensing/overview)) | not recommended | | | | |
| Apache Iceberg tables over the Parquet files | Apache 2.0 ([Wikipedia](https://en.wikipedia.org/wiki/Apache_Iceberg)) | several engines or customers must read one consistent snapshot, or schemas must evolve in place | a second analytical engine, or a customer analytics team, needs the same tables | catalogue service fees vary (not priced) | a catalogue to run | 2 to 4 weeks, then compaction and snapshot expiry (estimate) |
| ClickHouse (tick store and fast analytics) | server Apache 2.0 ([Altinity](https://altinity.com/blog/clickhouse-is-apache-2-0)) | the firm licenses and keeps tick data (C) | ticks kept beyond days, or above about 1,000 a second sustained | ClickHouse Cloud: storage 22 to 27.50 USD a TB-month; compute 0.18 to 0.40 USD a unit-hour (2 vCPU, 8 GiB) ([ClickHouse pricing](https://clickhouse.com/pricing.md)); 2 units always on in Germany about 420 to 580 USD (estimate from those rates) | one AX102, 259 EUR | 1 to 2 weeks, then 1 to 2 days a month (estimate) |

**Licences against AGENTS.md rule 18 and the dependency policy.**
`docs/legal/DEPENDENCY_LICENSE_REVIEW.md` fails GPL-family, SSPL, BUSL, Elastic, Commons
Clause, PolyForm and unknown licences.

- *TimescaleDB (TSL).* The TSL is not a non-commercial licence: it allows internal business use
  and "Value Added Products or Services" whose main offering is not the database, provided
  customers are told of the TSL and are "prohibited, either contractually or technically,
  from defining, redefining, or modifying the database schema"; it forbids offering it as a
  database-as-a-service ([Tiger Data licences](https://www.tigerdata.com/legal/licenses)).
  Eurogas Nexus as a product would fit the value-added clause, but the schema condition has to
  hold in every customer installation (customers run the migrations and own the server), and
  the policy's audit would treat the TSL as unknown until reviewed. It needs a legal review
  and an ADR before any use. Its main benefit here, compression of old data, is available
  without it (partitions and Parquet). Recommendation: do not adopt; agree with doc 18's
  DEFER.
- *Redpanda.* Its source-available licence with the commercial-service restriction is
  BUSL-family and the features that matter at scale are enterprise-licensed. Excluded.
- *Kafka, Iceberg, Parquet, ClickHouse server, DuckDB.* Apache 2.0 or MIT: acceptable.

### 3.2 Stages

| Stage | When | Run | Add | Monthly (estimate) |
| --- | --- | --- | --- | --- |
| **Now** (A, and B as its sources are built) | today to the first planned sources | PostgreSQL 16 primary and hot standby; the outbox and `LISTEN/NOTIFY` (ADR 28); off-site backups to object storage; the existing backup and restore drill | the raw-archive policy (ADR-P1) and a retention decision (ADR-P2): the cheapest capacity there is | two AX102-class servers and object storage: about 550 to 700 EUR self-hosted (the larger NVMe options are priced in Hetzner's configurator, not on the page cited); a managed equivalent roughly 2 to 4 times that (estimate) |
| **Mid-term** (B in operation, years 1 to 5) | a table passes 50 million rows (at B's back-fill, or 14 to 21 months after B's sources land) | the same PostgreSQL pair | monthly range partitions and BRIN on the large observation tables (ADR 24); months older than 2 to 3 years exported to Parquet zstd on object storage, read with DuckDB for research, backtests and model fits (ADR-P3); a read replica when the CPU trigger is met (ADR-P4) | plus about 260 EUR for a replica; object storage a few EUR |
| **At 15 years** (B; C if ticks are licensed) | about 1.5 TB of rows, 0.33 TB if compressed | PostgreSQL hot window (2 to 3 years, about 0.35 TB) on the same class of server; cold history in Parquet (about 0.3 TB) | for C only: ClickHouse for ticks (ADR-P5); Iceberg only if several engines share the history (ADR-P6); Kafka only on doc 15's triggers (ADR-P7) | B: unchanged plus storage growth of a few EUR a year; C: plus 260 to 600 EUR for the tick store |

Hardware turns over every 4 to 5 years anyway; buying for year 15 now would waste money that
the next generation of servers would give for less.

### 3.3 Cheapest setup with at least 10 times headroom (main scenario)

Two dedicated servers of the AX102 class (128 GB memory, NVMe in RAID 1, the 2 x 3.84 TB disk
option) as PostgreSQL primary and hot standby, plus object storage for backups, the WAL
archive and cold Parquet history.

| Need at 15 years (B) | Capacity | Headroom |
| --- | --- | --- |
| Hot database, a 2-year window of canonical data and kept-once raw pages (2 x 115 GB) plus 25 % free space: about 0.29 TB (estimate from section 2.5) | 3.84 TB usable on each server (a 3-year window, about 0.43 TB, gives about 9x; the 7.68 TB disk option about 18x) | about 13x |
| Peak write rate: 1,000 rows a second | about 14,000 rows a second measured on a 4-core container (the AX102 has 16 cores) | 14x or more |
| Events: bursts of hundreds a second | outbox 230 published and 1,300 to 1,900 delivered a second, one process | about 10x, more with a second worker |
| Hot working set in memory | 128 GB against a hot index set of tens of GB (estimate) | several times |
| Cold history and backups: about 0.3 TB Parquet plus about 1.5 TB of backups and WAL | object storage priced by the TB | no limit that matters |

Even the rows-as-stored 15-year total (1.5 TB, no cold tier) fits on one such server with
2.5 times headroom, so the cold tier is a cost and speed choice, not a hard limit. This is
roughly 550 to 700 EUR a month (estimate), and it never constrains the platform: the next step
in every direction (a replica, a bigger disk, a cold tier) is additive and needs no rewrite.

### 3.4 Proposed future decisions (ADRs for the owner; none is taken here)

| Id | Proposed decision | Trigger to take it | Evidence it needs |
| --- | --- | --- | --- |
| ADR-P1 | Raw archive: keep each distinct page once (by digest and query), keep the exact text only (the parsed JSON is reproducible), move pages older than N weeks to zstd files in object storage with their digests, retention per source | now: it is about 91 % of growth today | a replay test from archived files; lineage tests unchanged |
| ADR-P2 | Retention per table: which keep 15 years, which keep a summary (daily close instead of every quote), which keep months | before any back-fill | the owner's and customers' record-keeping needs (REMIT, audit) |
| ADR-P3 | Cold tier: monthly partitions older than 2 to 3 years exported to Parquet on object storage with manifests; DuckDB as the reader for research and backtests | when partitions exist and the hot database passes the server's memory | export and re-import round trip; as-of reads across the boundary |
| ADR-P4 | Read replica for research and Power Query reads | primary CPU above 60 % sustained, or desk reads miss their budget during research | measured read latency with and without the replica |
| ADR-P5 | Tick store (ClickHouse) beside PostgreSQL | the firm licenses tick data and keeps it beyond days | ingest benchmark at C's design peak; entitlement checks on every read |
| ADR-P6 | Iceberg tables over the Parquet history | a second engine or a customer analytics team needs consistent snapshots | catalogue choice and its operation |
| ADR-P7 | A broker fed from the outbox | a doc 15 section 4 trigger is measured | outbox lag at load; consumer list |

### 3.5 Doc 18's big-data proposals against this sizing

Doc 18 (in progress on `research/agentic-decision-architecture`) reviews Codex's assessment,
whose technology table is `docs/architecture/AGENTIC_DECISION_ARCHITECTURE_PROPOSAL.md` on that
branch ("18-36 month architecture and lifecycle policy"). Read on 2026-11-25:

| Codex proposal | Its decision | What this sizing says |
| --- | --- | --- |
| PostgreSQL 16 baseline | ADOPT_NOW | **Supported.** A and B fit one primary with more than 10x headroom for 15 years. |
| Declarative partitioning | DESIGN_INTERFACE_NOW | **Supported for B, premature for A.** Under A no table reaches 50 million rows in 15 years. Under B the ENTSOG, ENTSO-E and AIS tables pass it at their 5-year back-fill, or 14 to 21 months after their sources land without one, so designing the time-based query paths and identity now is right; migrating before B's sources exist is premature. |
| TimescaleDB | DEFER | **Supported.** Its benefit is matched by partitions and Parquet; its licence needs review (section 3.1). Update 2026-11-26: built as an optional extension, off by default (ADR Decision 39, `docs/deployment/TIMESCALEDB.md`); the licence review is in `docs/legal/DEPENDENCY_LICENSE_REVIEW.md`. Turning it on stays deferred until a deployment measures the need. |
| DuckDB and Parquet | DESIGN_INTERFACE_NOW | **Supported, and it is the main lever.** Measured 8 to 45 times smaller than rows as stored; it carries B's history at 0.33 TB. |
| Kafka-compatible contracts | DESIGN_INTERFACE_NOW | **Contracts supported; a broker premature.** B's events average a fraction of a row a second against a measured outbox of hundreds a second. Only C's ticks, and only if many systems consume them, approach a broker's case. |
| Iceberg-compatible analytical storage | DESIGN_INTERFACE_NOW | **Format compatibility supported; a catalogue premature** until a second engine or a customer needs shared snapshots (ADR-P6). |
| pgvector, Temporal | DESIGN_INTERFACE_NOW | Outside this sizing: neither changes data size or rate materially. |

## 4 Benchmarks

### 4.1 What each publishes

Only public sources; volumes are given only where published.

| Firm | What it uses (published) | Published volumes and rates | How comparable to our job |
| --- | --- | --- | --- |
| **Hudson River Trading** (HFT) | an in-house distributed filesystem, Blobby: FoundationDB for metadata, 6+3 erasure coding, 8 MB chunks on XFS, NVMe and HDD clusters, replacing Lustre and NFS filers (Aug 2025) ([HRT](https://www.hudsonrivertrading.com/hrtbeat/distributed-filesystem-for-scalable-research/)) | "hundreds of petabytes"; chunk servers with "hundreds of terabytes" each; no node or throughput figures | Not comparable: research storage for exchange tick data and models |
| **Jane Street** (HFT and market making) | Superstore, a distributed columnar database on Apache Parquet, CockroachDB metadata (being replaced); earlier Postgres and Vertica; OCaml throughout; Snowflake and Databricks considered and not chosen (Signals and Threads ep. 28, Jun 2026) ([Signals and Threads](https://signalsandthreads.com/building-a-data-warehouse-from-scratch/)); a Texas data centre with 4,032 GPUs in 56 racks ([Jane Street](https://www.janestreet.com/culture/street-view/a-look-inside-our-newest-data-center/)) | warehouse sized at 10 PB for "some eight figure amount of money"; "many billions" of order-decision records a day; hundreds of thousands of CPU cores and over 10,000 GPUs | Not comparable in scale; the pattern (Postgres first, then columnar Parquet when history outgrew one machine) is the one this report recommends |
| **Citadel Securities** (market maker) | Google Cloud for quantitative research since 2017: on-demand and preemptible VMs, centralised data lakes, 200 Gbps networking (Apr 2024) ([Google Cloud](https://cloud.google.com/transform/citadel-securities-reimagine-quantitative-reseach-cloud-scale-speed?e=48754805)); FPGA and C++ for the latency-critical path ([Citadel Securities](https://www.citadelsecurities.com/careers/career-perspectives/engineering-the-systems-behind-modern-market-making/)) | more than 1 million cores at once; "more than $400 billion in trades a day"; no data volume published | Not comparable: equities and options market making |
| Bloomberg (market-data vendor, for scale) | feeds storage moved from local disk to cloud storage (SREcon23 APAC) ([USENIX](https://www.usenix.org/conference/srecon23apac/presentation/kasichayanula)) | "300 billion unique events per day" | A vendor's whole feed; the firm would buy a slice of it |
| US options feed (OPRA), for scale | ([Databento](https://databento.com/blog/beyond-40-gbps-processing-opra-in-real-time)) | over 200 billion quotes and NBBO updates a day; bursts above 50 Gbps | What "tick-level" means at the extreme; European gas screens are orders of magnitude smaller (no published count) |
| **Shell** Trading and Supply | Azure Data Factory, ADLS, Azure Databricks, Microsoft Fabric, PySpark, Power BI; Endur and Nucleus ETRMs ([job ad](https://nodeflair.com/jobs/shell-sr-data-engineer-etrm-556303)); group-wide, Databricks on Azure for "petabyte scale datasets" (2020, not trading-specific) ([Databricks case study](https://databricks.com/wp-content/uploads/2020/12/Shell-Case-Study-FINAL.pdf)) | no trading volume published | Close: physical and financial gas, LNG and power |
| **BP** (Trading and Shipping) | Dataiku for ML-driven quantitative trading, in-house Python connectors (2023) ([Dataiku](https://community.dataiku.com/t5/Dataiku-Frontrunner-Awards/bp-T-amp-S-ML-Driven-Quantitative-Trading/ta-p/37141)); group-wide Databricks SQL, Unity Catalog, Delta Sharing, 43 % cloud cost cut ([Databricks session](https://www.databricks.com/dataaisummit/session/bp-cut-cloud-spend-43-and-speed-critical-jobs-days-8-hours-databricks), segment not named) | business scale only: over 300 ships at sea, about 240 Mt moved a year, over 12,000 customers; no data volume | Close |
| **Equinor** and **Danske Commodities** (Equinor's trading company) | Omnia, a tenant platform in Azure; EurekaML for gas traders on Azure ML, Synapse, Cosmos DB, Data Lake, Data Factory, Power BI (Jun 2023) ([Microsoft](https://www.microsoft.com/en/customers/story/1650901391366121376-equinor-energy-azure-en-notway)); Danske Commodities' data platform team of 15: Python, C#, SQL, Spark, Hadoop, **Kafka**, MSSQL, MongoDB, Databricks, Snowflake, Airflow, Prefect, Dagster ([Danske Commodities](https://danskecommodities.com/vacancies/senior-data-platform-engineer)) | none published | Closest: European gas and power trading |
| **Trafigura** (Market Risk) | Python, PySpark, Spark, Databricks, Delta Lake, Snowflake, **PostgreSQL, TimescaleDB, ClickHouse, kdb+**, MongoDB; data from Bloomberg, Reuters, ICE, CME, Platts ([job ad](https://echojobs.io/job/trafigura-market-risk-data-engineer-87y60)) | none published | Close (risk on commodity books) |
| **Uniper** (gas and power) | Kafka on Confluent Cloud as the trade lifecycle backbone between algorithmic trading, dispatch and invoicing; Flink for ETL (Jun 2024, Confluent's field CTO) ([Kai Waehner](https://kai-waehner.de/blog/2024/06/28/energy-trading-with-apache-kafka-and-flink)) | none published | Close; vendor-written source |

### 4.2 How comparable the jobs are

The HFT firms make markets in microseconds on exchange tick data across hundreds of thousands
of instruments; their storage is for research over every tick and their compute is for model
training. Eurogas Nexus supports decisions on a physical gas portfolio at hourly and daily
granularity: flows, storage, cargoes, nominations, curves, outages. Its decisive inputs arrive
a few thousand times a day, not billions. Energy majors' trading arms are closer: the same
public fundamentals, licensed ETRM and exchange data, and many internal systems to connect.
None publishes its data volume. Our estimate (not published): a major's trading data is
scenario C plus vessel tracking for every commodity fleet and gridded weather, which is tens of
terabytes over 15 years, held across a cloud data lake because dozens of teams and systems
share it.

### 4.3 What to borrow, and what would be overspending

Borrow:

- **Columnar files for history** (Jane Street's Parquet, the majors' Delta Lake and Databricks):
  our measured 8 to 45 times reduction makes 15 years cheap (ADR-P3).
- **One governed catalogue** of datasets with lineage and entitlements (Unity Catalog at BP):
  the platform already has the source registry, provenance and entitlement families; keep the
  Parquet manifests under the same rules.
- **A stream bus when many systems share one feed** (Uniper, Danske Commodities): only when the
  platform has independent consumers, which today it does not.
- **A time-series or column store for ticks** (Trafigura lists TimescaleDB, ClickHouse and kdb+):
  only if tick data is kept (C).

Overspending:

- Petabyte filesystems, GPU clusters, FPGA paths and million-core research grids: they serve
  a job this product does not do (AGENTS.md rule 8: no execution).
- A cloud lakehouse (Databricks, Snowflake) for under 2 TB: a well-run PostgreSQL and object
  storage cost a fraction and keep the single source of truth (ADR 2).
- Kafka and a three-broker cluster before a doc 15 trigger: a second place for state and a new
  failure mode, for a rate the outbox carries with 10 times headroom.

### 4.4 Not sourced

- **Citadel Securities' data volume**: no public figure found; its footnotes page failed to load
  (counted as tried).
- **Vitol**: the job ad found had expired and named no stack; nothing usable.
- **Shell, BP, Equinor and Trafigura trading data volumes and rates**: not published; the
  stacks above come from job ads and vendor case studies.
- **Quote and message counts on ICE Endex, EEX and Trayport gas screens**: not published
  (licensed); scenario C's rate is an estimate.
- **GIIGNL fleet and terminal tables**: members only; the fleet count is IGU's.
- **AWS RDS list prices**: the AWS page's tables did not render for the reader; a third-party
  price index is cited instead and marked as such.

## 5 How to rerun the measurement

`scripts/capacity/measure_db.py` prints rows, heap, index, TOAST and total bytes and bytes per
row per table. It is read-only (a `READ ONLY` transaction of catalogue `SELECT`s on
PostgreSQL; `mode=ro` on SQLite), never prints the database URL, and is not in the customer
image's script allowlist (`scripts/release/runtime_artifact_policy.json`), so it does not ship.

```bash
python scripts/capacity/measure_db.py                    # RUNTIME_STORE_DATABASE_URL
python scripts/capacity/measure_db.py --top 25 --exact   # count(*) per table
python scripts/capacity/measure_db.py --json > sizes.json
```

On the real store, replace the bytes-per-row column of section 2.2 with the measured values,
and the rows-a-day column with the growth between two runs a week apart divided by seven.
Test: `tests/unit/test_capacity_measure_db.py`.

## Sources

Read 2026-11-25. Pages that refused or failed are listed in section 4.4.

- ENTSOG TP API manual v3.0: https://transparency.entsog.eu/api/archiveDirectories/8/api-manual/ENTSOG_TP_API_UserManual_v3.0.pdf
- USCG Navigation Center, AIS: https://www.navcen.uscg.gov/node/84
- IGU World LNG Report 2026 (IIF-IIR summary): https://iifiir.org/en/news/world-lng-report-2026-north-american-exports-drive-record-growth-for-global-lng-trade
- ACER REMIT Quarterly Q1 2026: https://www.acer.europa.eu/sites/default/files/REMIT/REMIT%20Reports%20and%20Recommendations/REMIT%20Quarterly/ACER-REMIT-Quarterly-Q1-2026.pdf
- ICE, TTF records 2025: https://www.businesswire.com/news/home/20251215274852/en
- EEX Group 2025 volumes: https://www.eex.com/fileadmin/Global/News/EEX/EEX_Press_Release/2026/20260113_EEX_Group_Y2025_Volumes_Final.pdf
- EPEX SPOT, 15-minute MTU go-live: https://www.epexspot.com/en/news/market-coupling-steering-committee-confirms-go-live-15-minute-mtu-sdac-trading-day-30
- Tiger Data licences: https://www.tigerdata.com/legal/licenses
- Tiger Data, TOAST vs compression: https://www.tigerdata.com/blog/postgres-toast-vs-timescale-compression
- TimescaleDB compression, production report: https://dev.to/polliog/timescaledb-compression-from-150gb-to-15gb-90-reduction-real-production-data-bnj
- MotherDuck, CSV vs Parquet: https://motherduck.com/learn/csv-vs-parquet-benchmark/
- PostgreSQL 16 partitioning: https://www.postgresql.org/docs/16/ddl-partitioning.html
- Redpanda licensing: https://docs.redpanda.com/current/get-started/licensing/overview
- Apache Kafka: https://kafka.apache.org/
- Apache Iceberg: https://en.wikipedia.org/wiki/Apache_Iceberg
- DuckDB FAQ: https://duckdb.org/faq.html
- ClickHouse licence: https://altinity.com/blog/clickhouse-is-apache-2-0
- ClickHouse Cloud pricing: https://clickhouse.com/pricing.md
- Aiven PostgreSQL pricing: https://aiven.io/pricing/postgresql
- Aiven Kafka pricing: https://aiven.io/pricing/kafka
- Hetzner AX102: https://www.hetzner.com/dedicated-rootserver/ax102?country=DE
- Hetzner Object Storage pricing: https://www.hetzner.com/storage/object-storage/pricing/
- Bytebase RDS price index: https://www.bytebase.com/dbcost/rds/instance/db.m7g.xlarge/
- Hudson River Trading, Blobby: https://www.hudsonrivertrading.com/hrtbeat/distributed-filesystem-for-scalable-research/
- Jane Street, Signals and Threads ep. 28: https://signalsandthreads.com/building-a-data-warehouse-from-scratch/
- Jane Street, data centre: https://www.janestreet.com/culture/street-view/a-look-inside-our-newest-data-center/
- Google Cloud, Citadel Securities: https://cloud.google.com/transform/citadel-securities-reimagine-quantitative-reseach-cloud-scale-speed?e=48754805
- Citadel Securities, engineering: https://www.citadelsecurities.com/careers/career-perspectives/engineering-the-systems-behind-modern-market-making/
- USENIX SREcon23 APAC, Bloomberg: https://www.usenix.org/conference/srecon23apac/presentation/kasichayanula
- Databento, OPRA: https://databento.com/blog/beyond-40-gbps-processing-opra-in-real-time
- Shell job ad: https://nodeflair.com/jobs/shell-sr-data-engineer-etrm-556303
- Shell, Databricks case study: https://databricks.com/wp-content/uploads/2020/12/Shell-Case-Study-FINAL.pdf
- bp T&S, Dataiku: https://community.dataiku.com/t5/Dataiku-Frontrunner-Awards/bp-T-amp-S-ML-Driven-Quantitative-Trading/ta-p/37141
- bp, Databricks session: https://www.databricks.com/dataaisummit/session/bp-cut-cloud-spend-43-and-speed-critical-jobs-days-8-hours-databricks
- Equinor, Microsoft: https://www.microsoft.com/en/customers/story/1650901391366121376-equinor-energy-azure-en-notway
- Danske Commodities job ad: https://danskecommodities.com/vacancies/senior-data-platform-engineer
- Trafigura job ad: https://echojobs.io/job/trafigura-market-risk-data-engineer-87y60
- Uniper, Kafka and Flink: https://kai-waehner.de/blog/2024/06/28/energy-trading-with-apache-kafka-and-flink
