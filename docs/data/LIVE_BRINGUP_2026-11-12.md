# First live bring-up of the public sources (2026-11-12)

The first run of the product's connectors against the live public platforms, on PostgreSQL
16 migrated to head. Before this, no source had been shown working outside fixtures. This
page records what was run, what arrived, and every defect the live data exposed.

Scope: public and free-key sources only. No licensed price feed was touched. The store is
a local development database, not a customer deployment, so this is evidence for the
adapters, not a certification of any installation (gate G16 stays with the customer).

## What arrived

Measured with `scripts/ops/data_quality_report.py` after the run.

| Dataset | Rows | Series | Period | Status |
|---|---|---|---|---|
| ENTSOG reference (connection points, operator point directions) | 789 + 1,283 | – | current | complete read |
| ENTSOG physical flows | 5,510 | 805 | 5 to 12 Nov | ok; about 790 rows a closed gas day at about 530 points |
| ENTSOG capacity (four indicators) | 10,423 | 3,925 | 5 to 12 Nov | ok |
| GIE AGSI storage, Europe total | 4,800 | 1 | 2013-09 to 10 Nov | ok |
| GIE AGSI storage, BE DE DK FR GB NL | 600 each | 6 | to 10 Nov | ok; GB carries no inventory |
| GIE ALSI LNG, Europe total and BE DE FR NL | 4,800 + 600 each | 5 | to 10 Nov | ok |
| ECB FX reference | 6 | 6 | 11 Nov | ok |
| SONIA, €STR, SOFR | 95 | 3 | 28 Sep to 11 Nov | ok |
| Henry Hub (EIA) | 27 | 1 | to 3 Nov | ok (EIA publishes about a week behind) |
| ENTSO-E power: BE DE-LU FR NL | 13,908 | 24 | 4 to 12 Nov | ok; 15-minute prices |
| GB demand (National Gas) | 107 | 86 | to 11 Nov | ok (scheduled since 14 Nov, see below) |
| REMIT outages | 0 | – | – | not run: file import only (GIE IIP collector since 14 Nov, ENTSOG transmission UMMs since 16 Nov, see below) |
| ECMWF forecasts | 0 | – | – | not run: needs series bindings first; decoder (ecCodes) absent, see "Data gaps" (16 Nov) |

With this data the north-west Europe balance returns measured history for the first time.
For gas day 10 November: pipeline landings 4,629 GWh/d, LNG send-out 2,159 GWh/d, net
storage withdrawal 2,516 GWh/d, supply call 9,304 GWh/d.

## Defects found and fixed

| # | Defect | Consequence | Fix |
|---|---|---|---|
| 1 | ENTSOG paging stopped at the first short page and reported the read complete. The platform returns fewer records than the raw span it counts (509 of 1,000) while thousands remain. | Most of a gas day was missing, including the UK, the Netherlands, France, Italy and Spain. | `entsog_transport.py`: stride by the limit; exhaustion from `meta.total` (rows-left for flows, grand total for reference) or the 404 past the end. |
| 2 | Nothing could produce the certification record that ENTSOG and GIE ingestion requires. | Live ingestion was blocked for every deployment. | `scripts/ops/certify_public_source.py`: bounded live sample, normaliser dry run, shape check, recorded evidence with expiry. |
| 3 | A gate-blocked source reported `ok: true` with no rows. | A blocked run read as a successful one. | Structured failure and nonzero exit. |
| 4 | ENTSO-E day-ahead documents now hold two auctions per day at 15 minutes; both mapped to one observation id. | The power import failed on PostgreSQL. | Keep the coupling auction (classification sequence 1). |
| 5 | GIE ingestion fetched only the Europe total; the balance reads storage and LNG by country. | The balance could never fill from live data. | `--gie-country` (and `nwe`) reads each country's series. |
| 6 | The balance summed a volume column the native ENTSOG adapter leaves empty. | Norwegian supply read 0.0: a wrong number, not a missing one. | `application/pipeline_supply.py`: energy as published. |
| 7 | The balance matched landing points by name fragments. | It took the Dunkerque LNG terminal as a pipeline landing and counted one Dornum flow twice (two point keys publish it identically) and one Emden flow twice (both sides' meters). | A registry of ENTSOG point key and operator, one row per physical landing. |

## Findings not yet fixed

1. **Flows are reported by both operators at an interconnection.** 593 point-days carry two
   rows. Any consumer that sums flows by point double counts. The balance is repaired;
   `physical.py`, `analysis.py`, `research_data.py` and the agent bridge still read the
   legacy volume column, which is empty for native rows. **Closed 2026-11-13**, see below.
2. **Great Britain is absent from ENTSO-E and from GIE.** ENTSO-E returns no GB power
   data and AGSI carries no GB storage inventory. GB power needs Elexon; GB storage and
   LNG need National Gas. The balance's GB side is therefore pipeline landings only.
3. **UK terminals mix Norwegian and UK shelf gas.** ENTSOG publishes Easington and
   St Fergus as terminal totals. The registry says so; a Norway-only figure needs
   Gassco's own publication.
4. **The landing-point registry needs a practitioner's check** against Gassco totals. The
   continental sum (about 278 mcm/d at 11 kWh/m3) is plausible, not verified. See
   "Dornum: independent opinion (2026-11-14)" below.
5. **REMIT has no live collector** (DATA-03) and **ECMWF needs series bindings** before a
   first run. REMIT **partly closed 2026-11-14**: storage and LNG UMMs from GIE IIP are
   collected on the scheduler (see "Data defects, second round"); production and
   transmission UMMs still need a file import. ECMWF unchanged.
6. **A 72-hour unattended scheduler run has not been done.** This run was operator-invoked
   commands. The scheduler run is the remaining part of DATA-01. A 77-minute precursor ran
   on 14 November, see "Unattended ingestion (2026-11-14)" below.
7. **ENTSOG publishes rows for the open and the next gas day.** They are stored; consumers
   that need closed days must filter on the period end, as the balance does. **Closed
   2026-11-13** with item 8, see "Provider revisions and open gas days" below.
8. **Provider revisions refused a whole batch.** Any changed value refused the refresh
   (`*_revision_requires_history`), so the newest days kept their first values. **Closed
   2026-11-13**, see below.

### Item 2 closed (2026-11-13)

Great Britain is now loaded from two keyless sources: Elexon for power
(`docs/operations/POWER_DATA.md`) and National Gas for storage and LNG
(`docs/operations/GB_GAS_SUPPLY.md`, `scripts/ops/ingest_national_gas_supply.py`). The
first run (`--days 10 --commit`) stored 10 storage and 10 LNG rows for gas days
3-12 November; 12 November is nomination-based (provisional) and has no stock yet.

| Gas day | GB storage stock TWh | Withdrawal GWh | Injection GWh | GB LNG stock TWh | LNG send-out GWh |
|---|---|---|---|---|---|
| 9 Nov | 10.407 | 612.6 | 0.0 | 9.002 | 570.0 |
| 10 Nov | 9.969 | 437.3 | 0.0 | 8.418 | 581.3 |
| 11 Nov | 9.780 | 213.4 | 4.3 | 8.854 | 544.4 |
| 12 Nov (provisional) | - | 78.5 | 43.7 | - | 508.5 |

With GB included, the balance for 10 November reads LNG 2,740.2 GWh (was 2,158.9) and
storage net withdrawal 2,953.0 GWh (was 2,515.7). The balance now stops at the last day
every storage/LNG source has reported, since National Gas publishes a day or two before
GIE; GB stock is left out of the fill figure because no GB working capacity is published.

### Item 1 closed (2026-11-13): every flow reader takes one operator, energy as published

Each operator at an interconnection reports the point from its own side: its `entry` is
flow into its system, its `exit` flow out. At ITP-00011 on 10 November HR reported exit
25.4 GWh and entry 0; HU reported entry 25.4 GWh and exit 0. Adding the operators' rows
counts the flow twice, and choosing an operator per point *and direction* can take it once
as entry and again as exit. The rule, in one place
(`application/pipeline_supply.py`, `OPERATOR_SELECTION_RULE` / `select_operator_rows`):

> One operator per ENTSOG point and gas day: the operator the landing registry names for
> that point, else the operator key that sorts first among those reporting a value at that
> point that day. Entry and exit are both that operator's report, so direction is relative
> to its system; other operators' copies are not added.

Energy comes from `row_energy_gwh` (the native payload's energy when no original value was
kept). No reader turns energy into volume: none needs mcm/d, and no point-specific GCV is
published.

| Reader | Before | After |
|---|---|---|
| Agent bridge (`db_bridge.flow_rows`, `network.get_flow_context`) | native rows dropped: no flows at all | one operator; `energy_gwh_d`, `flow_mcm_d` null, `operator_key`; the rule in the result |
| Analysis snapshot (`analysis.py`, glossary usage) | native rows dropped (0 of 50 live rows) | 47 rows with energy (`flow_mwh_per_day`), one operator; usage no longer averages entry with exit |
| Research datasets (`research_data.py`) | `flow.mcm_d.*` empty; duplicates per day | new `flow.gwh_d.<point>.<dir>` (energy as published), one value per day; `flow.mcm_d` holds published volumes only |
| Map situation (`map_situation.py`) | latest row per point/direction from whichever operator came first | chosen operator, `operator_key` shown; energy via the shared helper |
| `/api/physical/flows` volume mode | native energy rows withheld silently | same rows (contract unchanged), plus a warning pointing to `quantity_basis=native` |

Live per-day figures for gas day 10 November (GWh/d, after; before: no figure):

| Point | Operator chosen | Exit | Entry |
|---|---|---|---|
| ITP-00011 (HR to HU) | HR-TSO-0001 | 25.425 | 0.0 |
| ITP-00027 (HU to SK) | HU-TSO-0001 | 124.539 | 0.0 |
| ITP-00005 | UK-TSO-0001 | 32.422 | not reported |

Two points that publish one flow under different keys (Dornum ITP-00126 and ITP-00525)
are still two points to a generic reader; only the landing registry knows they are one.

### Pipeline completeness rule (2026-11-13)

ENTSOG fills a gas day point by point over the following day or two (live: 7 of 10 landing
points for 11 November, 2,907.9 GWh; 3 for 12 November, 258.2 GWh). `landed_supply` keeps
a day only when at least as many registry landing points reported a value as the median
over the 28 days before it. A point reporting zero has reported, so a genuine outage still
shows as low supply. Left-out days are named in the balance's
`assumptions.pipeline_incomplete_days`, with `pipeline_complete_through` and a warning.

The projected inventory now subtracts only the draw on the facilities in it (GB storage,
with no published working capacity, stays in the supply call but not in the fill): each
forecast day's storage residual less the 14-day average GB net withdrawal. Live check: the
AGSI inventory fell 2.53 TWh from 9 to 10 November against 2.52 TWh drawn from those
facilities and 2.95 TWh region-wide. The projection also starts from the stock on the last
measured day rather than the newest storage day.

The Sources page counted rows only for sources named in its code, so National Gas, Elexon,
ENTSO-E, EIA and the rate administrators read 0. It now counts by `source_system` over
every observation table in one statement (rates by benchmark, since ECB also publishes
FX). Live: NATIONAL_GAS 20, ELEXON 1,185, ENTSOE 13,908, EIA 27, ECB_ESTR 33, BOE 32,
NYFED 30; ENTSOG, GIE and ECB unchanged.

### Data-correctness round and back-fill (2026-11-13)

**Back-fill.** ENTSOG physical flows for the balance's landing points (16 point-directions:
the registry's ten plus ITP-00525, ITP-00105 and exit sides) in 31-day windows, 20 Sep 2025
to 4 Nov 2026 (`--entsog-from/--entsog-to`, `to` is inclusive; 496 rows a window, one 495);
National Gas storage and LNG for 410 gas days (`ingest_national_gas_supply.py`, new `--end`
for 30-day steps); GIE AGSI/ALSI per NWE country refreshed to 11 Nov (`--limit 5`). Refused,
existing rows kept: a refresh of 5-13 Nov for ITP-00080, -00097, -00126, -00525 entry and the
AGSI Europe total (`*_revision_requires_history`), and AGSI for LU (`gie_product_mismatch`).

**Open-day snapshots.** 189 ENTSOG rows for 12 Nov were stored at 11:56 UTC that day, while
the day was open (Dornum 157.8 GWh against about 740). The revision rule then refuses the
full-day value, so the snapshot would read as the day's flow once the day closed.
`pipeline_supply.published_after_close` (received at or after the period end) now gates the
balance's landings and the map. Rows are kept; the ingestion of open days is unchanged.

**Dornum.** ITP-00525 (Dornum GASPOOL, OGE, no adjacent operator) equals ITP-00126 (Dornum /
NETRA, OGE) to the kWh on all 47 entry and 48 exit days held, with different bookings and
nominations. It is the first entry of `SAME_PHYSICAL_POINT`, applied inside
`select_operator_rows`. `scripts/ops/flow_point_alias_candidates.py` lists candidate pairs
and changes nothing. Open candidate, not applied: ITP-00188 (GUD) and ITP-00126 (OGE) agree
within 0.042 % on every day, through a 25 % swing, while their bookings differ 3x. If they
are one meter, the registry counts about 0.7 TWh/d of Dornum twice. This needs Gassco's
Dornum figure to decide.

**Other changes.** The map shows each point's newest closed gas day with `gas_day` and
`operator_key`; the operator rule now stays on the previous day's operator while it reports.
Research datasets take provenance, export policy and entitlement from each row's own
`source_system` (GB storage and LNG credited to National Gas, GB power to Elexon), with the
attribution from the connector manifest. The Sources page reports a failed count as null
with a warning, not 0. The balance warns when its call falls back to a 28-day average far
from the last week, or when its seasonal normal rests on one year.

**Balance after back-fill** (13 Nov, 14:20 UTC): 418 measured days, 20 Sep 2025 to 11 Nov
2026; 12 Nov left out as partly reported.

| Gas day | Call | Norway + UK terminals | LNG | Storage draw | Inventory TWh | Fill % |
|---|---|---|---|---|---|---|
| 11 Nov (measured) | 9,829.7 | 4,638.2 | 2,769.1 | 2,422.4 | - | - |
| 12 Nov | 9,452 | 4,622 | 2,584 | 2,245 | 340.56 | 64.1 |
| 15 Nov | 10,215 | 4,622 | 2,584 | 3,009 | 333.36 | 62.8 |
| 19 Nov | 12,893 | 4,622 | 2,584 | 5,687 | 315.30 | 59.4 |

Figures are GWh/d. The call method is the seasonal normal plus the recent anomaly. The only
earlier year is 2025, so the forecast replays the 17-21 Nov 2025 cold spell: a call of 9.9
to 12.8 TWh/d then. The balance now says so. From 17 Nov the days carry the flag
`withdrawal_above_recent_maximum`. Plausibility:

- LNG at 2.6-2.8 TWh/d is in range.
- Landings split into Norway scope 3.01 TWh/d and UK terminals 1.6 TWh/d. Norway is in
  range only with Dornum counted twice; see above.
- Fill of 64.1 % matches GIE's own per-country fill: DE 57.7, NL 62.2, FR 79.1, BE 67.3,
  DK 88.5. It is low for mid-November because German and Dutch stocks peaked near 61 % and
  66 % this season. This is not a calculation error.

### Provider revisions and open gas days (2026-11-13)

**Why the guard existed.** `upsert_revision_safe_observation_rows` (GIE, then ENTSOG via
RFC-0005) refused any changed value because there was no history: overwriting would have
carried the new value back to the row's first receipt, a look-ahead for any as-of read.
RFC-0005 left provider revision history as separate work; no ADR forbids it.

**Rule now** (`docs/operations/DATA_REVISIONS.md`, migration `0062_observation_revisions`):
a later value under the same source and natural key replaces the current row and the
replaced version is appended to `observation_revisions` in the same transaction; the row
keeps its first receipt in `observed_at_utc` and records `revised_at_utc`. Identity changes
and older replays are still refused. As-of reads (balance history, research datasets) take
the version known at the time. An ENTSOG flow received while its gas day was open is
stored, replaced by the first receipt after the close (reason `period_closed`), and never
read as a closed day: `pipeline_supply.CLOSED_DAY_RULE` now gates the agent bridge, the
analysis snapshot and research series as well as the balance and the map.

**Live result**, refresh of 5-13 Nov over the 16 landing point-directions in one run (the
run refused on 13 Nov): succeeded, 133 records: 7 inserted, 119 unchanged, 7 updated, of
which 4 revised (exactly the four previously refused: ITP-00080, -00097, -00126, -00525
entry for 12 Nov) and 3 open-day snapshots closed (the exit sides, value 0).

| 12 Nov, entry | Before (received 12 Nov 11:56 UTC, day open) | After (received 13 Nov 14:50 UTC) |
|---|---|---|
| Dornum ITP-00126 (OGE) | 157.794 GWh | 756.730 GWh |
| Dornum ITP-00525 (alias) | 157.794 GWh | 756.730 GWh |
| Emden ITP-00080 (OGE) | 82.225 GWh | 387.237 GWh |
| Nybro ITP-00097 | 18.228 GWh | 90.192 GWh |

The Dornum revision record holds `original_value` 157793678.9 kWh/d, received
2026-11-12 11:56:14 UTC, superseded 2026-11-13 14:50:36 UTC, reason `value_changed`, with
both page references. GIE (NWE countries and the Europe total, `--limit 5`): the Europe
AGSI total, refused on 13 Nov, now revises 4 days (7-10 Nov; inventory down by up to
0.14 TWh, 8 Nov withdrawal 3.579 to 3.724 TWh/d); countries unchanged; AGSI LU still fails
`gie_product_mismatch` (no storage in LU). The scheduler's own ENTSOG/GIE attempt
(`run_ingestor_attempt`, 7-day rolling lookback): GIE succeeded with 10 revised; ENTSOG flow
and capacity succeeded (capacity revised 4 in one run) but the attempt as a whole fails on
two older defects in the bundled reference read, see below.

**Balance.** 12 Nov is still left out, correctly: 8 of 10 landing points now report it as
a closed day (3 before; 2,980.5 GWh from those 8), but ENTSOG has no 12 Nov row yet for
Easington and St Fergus, and GIE publishes 12 Nov on the evening of 13 Nov. The balance
reads through 11 Nov (landings 4,638.2 GWh/d), unchanged.

**Open, found during this run.**

- The scheduler runs `src-entsog` without `--limit`, so the ingestor's default of 20
  records applies: the reference read is partial (`entsog_partial_reference_refused`) and
  flows get 4 records.
- Re-running the ENTSOG reference replacement fails on PostgreSQL: deleting
  `reference_nodes` violates `reference_tso_access_points_point_id_fkey` (SQLAlchemy
  `f405`). It worked on the first, empty-table run. Either blocks an unattended
  `src-entsog` run.

Both **closed 2026-11-14**, see below.

### Unattended ingestion (2026-11-14)

**Scheduler read bounds.** `run_dataops_scheduler.py` now passes each public source the
bounds of a complete read, from one table (`_SOURCE_BOUNDS`, documented in
`docs/operations/PRODUCTION_SOURCE_OPERATIONS.md`): ENTSOG `--limit 50000
--entsog-page-size 1000 --entsog-max-pages 50` (the transport's hard cap), GIE `--limit 30
--gie-country nwe`. An ENTSOG query that stops at its bound fails the attempt
(`QUALITY_REJECTED entsog_read_bound_reached`, not retried); it no longer passes with a
warning. Measured live, 7-day rolling window, all points: flows 6,742-6,777 raw records in
7 pages, capacity 12,160-12,227 in 15 pages, every query `provider_offset_exhausted`.

**Reference refresh.** The first bounded run exposed a third defect: an
`operatorpointdirections` page of 1,000 rows is about 3 MB and was refused as
`entsog_response_too_large` (2 MB limit; measured 302,522 bytes per 100 rows). That dataset
now pages at 400 (`ENTSOG_DATASET_MAX_PAGE_SIZE`). The replacement no longer deletes:
`upsert_reference_snapshot` upserts in place under the stable ids and **retires** a point the
provider no longer publishes (`data_quality = 'retired_by_provider'`, `retired_at_utc` in
its metadata) instead of deleting it, because flows, access points and operator mappings
reference it; current-network listings leave retired rows out, a read by id still returns
it, and a later read that carries the point restores it. The reference is re-read at most
once a day (`--entsog-reference-max-age-hours 24`; a skipped refresh reports
`status: skipped_fresh`), since the network changes rarely and the scheduler runs ENTSOG
hourly. Live: complete read 789 + 1,283 records, 2,733 rows upserted, 0 retired, on the
existing tables; repeated at once with no max age: same counts, no FK error.

**Scheduler attempts** (`run_ingestor_attempt`, as `execute_claimed_runs` calls it, no
extra flags), two in a row each:

| Run | Source | Result | Inserted | Updated (revised) | Unchanged | Notes |
|---|---|---|---|---|---|---|
| 13 Nov 15:44 | src-gie | succeeded | 0 | 0 | 330 | 11 series, no LU failure |
| 13 Nov 15:46 | src-entsog | succeeded | 0 | 0 | 16,727 | reference refreshed (2,733) |
| 14 Nov 01:03 | src-gie | succeeded | 11 | 30 (30) | 289 | 12 Nov arrived; AGSI Europe total and NL revised 13 days each, ALSI Europe total and DE 2 each |
| 14 Nov 01:03 | src-entsog | succeeded | 264 | 161 (161) | 16,424 | reference `skipped_fresh` |

(The 15:44 GIE and ENTSOG run before the page-size fix had already stored this window:
flows 1,035 inserted, 138 revised; capacity 1,929 inserted, 70 revised.)

**GIE country set.** `--gie-country nwe` asked for every product in every NWE country.
Checked live: AGSI for LU answers with an LNG-shaped placeholder (`gie_product_mismatch`),
so every GIE run exited 1; GB answers "United Kingdom (Pre-Brexit)" with status N and "-"
in every field for both products; ALSI for DK and LU answers status N placeholders. Now
`GIE_UNPUBLISHED_COUNTRIES` (AGSI: GB, LU; ALSI: GB, DK, LU) is never requested, whether
named or implied by `nwe` (a warning names each one left out), and a row with no value in
any value column is not stored (`skipped_records`); a series that returns only such rows
fails `gie_no_published_values`. The 601 AGSI GB and 1,803 ALSI DK/GB/LU rows already
stored are exactly these placeholders (every value null; none has revision history; the
raw pages stay archived). They should be removed:
`scripts/ops/purge_gie_placeholder_rows.py` counts them (dry run, verified live: storage GB
601; LNG DK 601, GB 601, LU 601) and `--commit` deletes them. **Not yet run against this
store**: the deletion was held for the owner's approval. Until it runs the data-quality
report still shows the 7 % / 20 % blank rows; afterwards blanks fall to zero because nothing
that is not data is stored, while the blank check itself is unchanged.

**National Gas revisions.** `ingest_national_gas_supply.py` wrote with the in-place upsert,
so an allocation replacing a nomination, or stock arriving later, overwrote the row with no
history under its first receipt (a look-ahead for as-of reads). It now writes through
`upsert_revision_safe_observation_rows` with GIE's value fields plus the `basis` and
`provisional` metadata as revisable; each change is a `value_changed` record whose
`changed_fields` says what moved. Tested on PostgreSQL (nomination to allocation with stock
filling in, an equal final figure, an identity change refused). The other writers to the
four observation tables are the ENTSOG and GIE paths, already revision-safe. Power
(`db/repositories/power.py`) still replaces in place; this is a documented limitation in
`docs/operations/DATA_REVISIONS.md` (no look-ahead, earlier value lost).

**Freshness.** The Sources page, the data-ops freshness read and the data-platform
provenance summary took `max(observed_at_utc)`, so a source that only revised looked
stale. They now take the later of first receipt and `revised_at_utc`
(`last_received_column`); as-of reads and lateness keep first-seen semantics. The
data-quality report's age is the newest period's age and is unchanged.

**Test isolation.** `test_analysis_provider_path_checks_the_invocation_not_only_the_payload`
failed whenever the live-work environment was sourced. The cause was not the database URL
(the root `conftest.py` already clears it) but `DEEPSEEK_API_KEY`: the test made a real
provider request (401 with a dummy key) instead of answering
`LLM_PROVIDER_CREDENTIAL_MISSING`. The root conftest now also clears every credential
variable the connector manifests declare (DeepSeek, GIE, EIA, ENTSO-E, the LLM key) outside
`tests/integration`. Checked: `tests/security` and `tests/unit` pass with
`RUNTIME_STORE_DATABASE_URL` pointing at a throwaway SQLite file and with dummy provider keys
set.

**Soak precursor (14 November, 01:11-02:28 UTC, 77 minutes).** The real loop,
`run_dataops_scheduler.py --interval-seconds 60 --scan-limit 10 --run-limit 10
--entsog-lookback-gas-days 7` (all ENTSOG points), against this store with the keys. The
script has no option to shorten schedules and none was edited; an operator enabled GIE and
ENTSO-E (`set_source_enabled`) and requested one run of every enabled source
(`request_operator_run`, MANUAL) at the start, so each source ran at least once; the
schedule then ran Elexon (30 min), ENTSOG and ENTSO-E (hourly). The daily sources were not
due in the window. 71 loop iterations, all `ok`; no retry, no failure. Counts are the
scheduler's own `ingestion_runs` rows; revisions are `observation_revisions` rows written
in the window.

| Source | Attempts | Succeeded | Failed | Received | Inserted | Updated | Unchanged | Revised |
|---|---|---|---|---|---|---|---|---|
| src-entsog | 2 (1 manual, 1 scheduled) | 2 (with warnings: open gas day, N/A exemptions skipped) | 0 | 38,006 | 13 | 127 | 33,556 | 127 (flows 119, capacity 8) |
| src-gie | 1 | 1 | 0 | 330 | 0 | 0 | 330 | 0 |
| src-national-gas-supply | 1 | 1 | 0 | 10 | 2 | 2 | 6 | 2 |
| src-entsoe | 2 (1 + 1) | 2 | 0 | 8,738 | 3,456 | 44 | 5,238 | 44, no history (see DATA_REVISIONS) |
| src-elexon | 3 (1 + 2) | 3 | 0 | 615 | 176 | 0 | 439 | 0 |
| src-ecb | 1 | 1 | 0 | 12 | 12 | 0 | 0 | - |
| src-ecb-estr | 1 | 1 | 0 | 7 | 1 | 0 | 6 | - |
| src-boe | 1 | 1 | 0 | 6 | 1 | 0 | 5 | - |
| src-nyfed | 1 | 1 | 0 | 6 | 2 | 0 | 4 | - |
| src-eia | 1 | 1 | 0 | 8 | 6 | 0 | 2 | - |

The National Gas revisions are the first live ones: gas day 12 November moved from
nomination to allocation and received its stock (storage withdrawal 78.465 to 78.495 GWh,
injection 43.698 to 43.740 GWh, stock 9.734 TWh; LNG send-out 508.46 to 509.55 GWh, stock
9.162 TWh), each kept with its first receipt (13 Nov 09:36 UTC).

**Found during the soak, not fixed.**

- *ENTSOG capacity rows overlap.* **Closed 2026-11-14**, see "Data defects, second
  round". The data-quality report now shows 531 capacity keys
  (point, direction, type, operator, period start) held twice. ENTSOG publishes capacity
  over validity ranges and re-splits them between reads (a value valid 12-13 Nov in the
  12 Nov read is valid 12-14 Nov in the 13 Nov read); the observation id includes the
  period end, so both rows stand. A reader that sums capacity per day can count a day
  twice. It needs a rule for superseded ranges (the later receipt covering the same start
  replaces the earlier), which is a change to the ENTSOG capacity identity, not done here.
- *Power revisions are frequent*: 44 ENTSO-E values replaced in two runs, without history.
  **Closed 2026-11-14** (history kept since migration 0063), see below.
- The soak covered no GIE or daily-rate scheduled slot; the 72-hour run will.
- `tests/api/test_nwe_balance_api.py::test_partly_reported_newest_pipeline_days_are_left_out`
  fails between 00:00 and 05:00 UTC (also on the unchanged tree): it builds "today's" gas
  day from the calendar date, so before 05:00 UTC yesterday's gas day is still open.

Output: the scratchpad's `soak/scheduler.jsonl` (loop and attempt events) and
`soak/counts.txt`.

### Data defects, second round (2026-11-14)

Four open items from the soak: overlapping ENTSOG capacity, power revisions without
history, GB demand off the scheduler, and no live outage source. Migration
`0063_resplit_power_revisions` (expand-only, reversible; applied to this store).

**ENTSOG capacity: one value per gas day.** Measured first, 12,647 rows, 3,925 series: 539
(point, direction, type, operator, start) keys held two or three times (480 twice, 59
three times); 168 of them with different values, 371 the same value over a different end;
the newer read's range was longer in 308 keys and shorter in 231; 462 further overlaps
start on different days. The provider splits ranges at its query window's edge and re-dates
day-ahead values: UGS-00397 firm technical entry was 13 Nov - 1 Dec 64.37 GWh/d in the
12 Nov read and 13-14 Nov 28.13 GWh/d plus 14 Nov - 1 Dec 64.37 GWh/d in the 13 Nov read;
FNC-00010 exit had a range to 2036 re-split at each read.

Decision: keep the ranges and resolve them, not one row per gas day. Ranges reach 2036, so
a daily table would hold millions of rows or cut forward capacity off at the query
window, and changing the observation id would break replay of every stored row. Every
range is the provider's statement at its receipt, so keeping them keeps as-of reads exact
with no new store. The rule (`application/capacity_resolution.py`): per point, direction,
type and instant, the covering range received last; one operator per point as for flows.
Ingestion adds one thing: a range re-published after a later range had re-split it takes
the new receipt, with a `range_resplit` history record
(`db/repositories/capacity_ranges.py`), so going back to an earlier split is not lost.
Readers through it: the physical capacity API (`/api/physical/capacity`, both modes; each
row's period is where its value holds) and the agent bridge (`capacity_rows`, now with
energy as published). The map, analysis/glossary usage, research datasets and route costing
do not read `capacity_observations` (they read REMIT messages and contract
`capacity_profiles`). After: UGS-00397 entry reads 7-13 Nov 24 kWh/d, 13-14 Nov
28,127,976 kWh/d, 14 Nov - 1 Dec 64,367,976 kWh/d, one value a day; the data-quality report
shows 0 duplicate keys and reports 1,431 overlapping ranges as a fact.

Existing rows: nothing to delete (each is history). `scripts/ops/capacity_range_resplits.py`
(dry run by default) counts overlaps and replays the archived ENTSOG pages with the new
ingestion rule. Dry run on this store: 539 repeated keys (168 with different values), 1,431
overlapping rows, 2,362 rows no instant is read from (superseded or the other operator's
copy); replay of 5 archived reads (107 pages): 0 receipts to move, 0 series-days changed.
`--commit` is not needed now and was not run.

**Power revisions keep history.** `observation_revisions` had check constraints naming the
four gas tables and two reasons, so a migration was needed (0063 widens both and adds
`power_observations.revised_at_utc`). The row keeps its first `published_at_utc` and
`ingested_at_utc`; a revision is available from its receipt. The parser caps
`published_at_utc` at the regulatory deadline, the same for the first and the revised
publication of an actual, so the earlier in-place update made a revised actual readable
from the deadline: a look-ahead, not "no value" as DATA_REVISIONS said. Research datasets
now take power through `all_versions`; gas-for-power and the fundamentals read current
values only (no as-of read of power). First live run (`src-entsoe` through the scheduler's
attempt, 06:54 UTC): 4,394 records, 297 inserted, 175 revised with history, 3,922 unchanged;
Elexon 245 unchanged. The data-quality report's `rev 7d` now shows power (ENTSO-E 175,
Elexon 0).

**GB demand on the scheduler.** Its own connector `src-national-gas-demand` (system
`NATIONAL_GAS_DEMAND`, every 6 h, on by default): one script, one table and one freshness,
where GIE's AGSI and ALSI share `src-gie` because they share one ingestion path. The script
gained `--days N --json` (the N gas days ending yesterday, both ids); the strict
`--date-from/--date-to --ids` form is unchanged. Freshness and the Sources page read the
demand table (it has no `source_system`). Live through the scheduler's attempt (06:33 UTC):
36 publications read, 12 inserted, 24 already stored; the report shows the dataset `ok`
(last gas day 12 Nov, 55 h, limit 72 h).

**Outages: GIE IIP collector.** Probed live (no scraping): `https://iip.gie.eu/api` returns
the UMMs as JSON, 50 a page, newest first, 13,204 messages in 265 pages, with earlier
versions under `prev`; the GIE AGSI/ALSI key is accepted in `x-key` (HTTP 200).
`https://api.gie.eu/api/v3/reports/umm`, which the platform calls behind it, answers 401
("only accessible via mTLS or bearer token"). Registration and the key are mandatory per the
API page; the API documentation is shown only after registration. Terms on the same page:
reuse in any way with GIE clearly credited, matching `docs/legal/DATA_SOURCE_TERMS.md`.
IIP carries storage (SSO) and LNG (LSO) operators only; no transmission operator publishes
there. Built: `ingestion/gie_iip.py` maps records to ACER fields for the importer's own
normaliser; `scripts/ops/ingest_remit_iip.py --days/--commit/--json`; `src-remit-umm` made
schedulable (every 30 min, off by default, needs the GIE key). Live backfill (`--days 90`):
25 pages, 1,250 messages, 1,588 versions stored (467 messages). The outage list then shows
56 live or upcoming outages within 90 days (55 storage, 1 LNG); 5 active ones carry a
daily figure, 192.4 GWh/d together (largest Bierwang 90.7 GWh/d, Bergermeer entry
31.2 GWh/d to 17 Nov). The map places 7 of the outages within 14 days and counts 25 as
unlocated (no matching EIC or name in the reference network). The balance reads Norwegian
outages only (zone `NO`): none on IIP, so the balance is unchanged. 17 of the 56 are in
kWh/h and some in GWh, GWh/h or TWh: they keep their unit and have no daily figure.
The platform relays an upstream rate limit as HTTP 200 with an error envelope; two of four
scheduler attempts in the minutes after the backfill failed `iip_upstream_refused` after
two retries, the next two succeeded (245 versions unchanged).

**Data quality after** (14 Nov 07:05 UTC):

```
dataset                    status        rows series last period       age h  dup  blank short days rev 7d
ENTSOG flows               ok           13173    806 2026-11-14T05:00    2.1    0      0    0/419      265
ENTSOG capacity            ok           12647   3925 2026-11-14T06:00    1.1    0      0    0/612      109
GIE storage (AGSI)         ok            7812      6 2026-11-12T05:00   50.1    0      0    0/4802      28
GIE LNG (ALSI)             ok            7210      5 2026-11-12T05:00   50.1    0      0    0/4802       4
GB storage (National Gas)  ok             411      1 2026-11-13T05:00   26.1    0      0    0/410        1
GB LNG (National Gas)      ok             411      1 2026-11-13T05:00   26.1    0      0    0/410        1
ECB FX reference           ok              12      6 2026-11-13T00:00   31.1    0      0    0/1          -
Overnight rates            ok              99      3 2026-11-12T00:00   55.1    0      0    0/0          -
Henry Hub (EIA)            ok              33      1 2026-11-11T00:00   79.1    0      0    0/33         -
Power (ENTSO-E)            warning      17661     24 2026-11-14T22:45  -15.7    0      0    2/10       175
    warning: 2 of 10 closed days hold under 90% of the usual 24 series.
GB power (Elexon)          ok            1397      4 2026-11-14T06:30    0.6    0      0    0/7          0
GB demand (National Gas)   ok             119     96 2026-11-12T00:00   55.1    0      0    0/0          -
Outages (REMIT UMM)        ok            1588   1588 2026-11-14T06:13    0.9    0      0    0/0          -
```

**Found, not fixed.**

- GB demand D+1 publishes partial values in the morning (gas day 12 Nov: 0 at 10:20,
  24.93 at 11:20, 242.62 at 12:20, 239.60 at 14:20 mscm). The research target mapper takes
  the latest revision by `available_at` (local receipt), then `record_id`; every revision
  downloaded in one run shares one receipt, so the "latest" is decided by a hash and can
  be the 0 or the 24.93. **Closed 2026-11-14**, see "Data defects, third round".
- REMIT units: kWh/h, GWh, GWh/h and TWh messages carry no daily figure, so the outage
  totals leave them out (17 of 56 upcoming outages are kWh/h). **Closed 2026-11-14**.
- Power (ENTSO-E) short days 4 and 11 Nov: not investigated here. **Closed 2026-11-14**.

### Dornum: independent opinion (2026-11-14)

The owner obtained an independent opinion that the three Dornum records (OGE ITP-00126,
GUD ITP-00188, Dornum GASPOOL ITP-00525) are the same physical gas, and that deduplicated
ENTSOG deliveries matched Gassco's German country total within about 1 % in an independent
reconstruction; Emden deliveries are separate and additive. This agrees with our own
evidence (ITP-00188 tracks ITP-00126 within 0.042 % over 46 days, through a 25 % swing).

Status: **probable double count of about 0.7 TWh/d in Norwegian landings** (the registry
still counts ITP-00188 beside ITP-00126). The owner has deferred the fix. The pending step is
verification against Gassco's published Dornum and Emden figures; only then is ITP-00188
added to `SAME_PHYSICAL_POINT`. No code was changed for this.

**Verification attempt (2026-11-14): inconclusive against Gassco's figures.** Gassco
publishes terminal flows only on Gassco FLOW (`umm.gassco.no`), which opens with a
terms-and-conditions page that must be accepted before any data; accepting it on the
owner's behalf was not permitted in this session, so no Gassco number was read. Gassco
publishes nothing on ENTSOG for its side: ENTSOG lists ITP-00208 "Dornum (EPT1 & EPT2)",
ITP-00209 "Emden (EPT1)" and ITP-00210 "Emden (NPT)" under Gassco (NO-TSO-0001) with
`hasData` false, and operational data for them returns 404. What was found:

- ENTSOG's own reference has **one** Norwegian-side Dornum point (ITP-00208) with **two**
  adjacent German operators, GUD (DE-TSO-0005) and OGE (DE-TSO-0009). That fits both
  readings (each reports the whole flow, or each its share).
- Gassco's terminal page (gassco.eu, Germany) describes ERF Dornum as doing "fiscal
  metering of quality and volume and flow control of the delivery into the downstream
  NETRA system", with gas also routed 48 km to Emden for delivery there: one fiscal meter
  into NETRA. Qualitative only.
- ENTSOG, closed gas days, entry (GWh/d):

| Gas day | ITP-00126 OGE | ITP-00188 GUD | GUD vs OGE | 126 + 188 | Emden ITP-00080 |
|---|---|---|---|---|---|
| 3 Nov | 738.3 | 738.0 | -0.042 % | 1,476.4 | 430.8 |
| 4 Nov | 735.9 | 736.0 | +0.004 % | 1,471.9 | 432.3 |
| 5 Nov | 780.4 | 780.3 | -0.013 % | 1,560.6 | 377.2 |
| 6 Nov | 738.9 | 738.8 | -0.006 % | 1,477.7 | 429.2 |
| 7 Nov | 735.4 | 735.3 | -0.017 % | 1,470.7 | 434.7 |
| 8 Nov | 738.6 | 738.5 | -0.006 % | 1,477.1 | 433.1 |
| 9 Nov | 734.8 | 734.8 | +0.006 % | 1,469.6 | 409.4 |
| 10 Nov | 742.2 | 742.2 | +0.001 % | 1,484.4 | 411.2 |
| 11 Nov | 746.0 | 745.9 | -0.014 % | 1,491.9 | 414.9 |
| 12 Nov | 756.7 | 756.8 | +0.006 % | 1,513.5 | 387.2 |

  At an assumed GCV of 11.1 kWh/Sm3 (about 40 MJ/Sm3; Gassco's own GCV not read), through
  the unit authority: ITP-00126 alone is 66 to 70 mcm/d; ITP-00126 + ITP-00188 is 133 to
  141 mcm/d.

Conclusion: **inconclusive** by the brief's test (no Gassco figure compared). The evidence
that exists still points to a duplicate: two operators equal to within 0.042 % every day
through a 25 % swing while their bookings differ threefold, one Norwegian-side point and
one fiscal meter into NETRA. The deciding step is a Gassco FLOW Dornum figure for 5-10
gas days, which needs the owner to accept Gassco's terms (and, for anything beyond a
one-off check, Gassco's written confirmation of reuse, `docs/legal/DATA_SOURCE_TERMS.md`).
No balance code was changed; nothing from Gassco is stored.

### Data defects, third round (2026-11-14)

Five items: GB demand partial values, REMIT units, unplaced outages, ENTSO-E short days and
the Dornum check (above).

**GB demand: the day's figure, not a stage.** The research target mapper did not pick a
hash in the end: its default receipt order refused equal receipts
(`AMBIGUOUS_RECEIPT_TIE`), and on live data every gas day has several stages received
together, so it refused every read; a tie-break by `(available_at, record_id)` would have
returned 1.28 and 22.90 mscm for 3 and 4 Nov. The provider's own history (1 Nov 2025 to
12 Nov 2026, 2,215 D+1 and 372 D+6 publications, read from the public portal into the
scratchpad only) gives the shape: D+1 stages at 09:20, 10:20 and 11:20 are 0 to 31 % of
the day; from 12:20 the figure is normally the full day (median 0.13 % from D+6), but the
provider published 999,150 mscm (29 Aug), 38-40 mscm (2, 3, 8 May) and 196.27 against a
settled 111.17 (28 Sep) at 12:20, each corrected at the next publication; D+6 arrives at
10:20 (winter) or 11:20 (summer) on day X+6. The rule (`application/gb_demand.py`,
`GB_DEMAND_DAY_RULE`; `docs/operations/DATA_REVISIONS.md`): order by the provider's clocks,
availability stays the receipt; D+6 when received (`settled`); else the latest D+1 made at
or after 12:00 on X+1 when the one before it agrees within 2 % (`provisional`); else no
value, with the reason. Over that year it returned a value before D+6 for all but 6 gas
days, never a stage or one of the outliers; the largest gap to D+6 among returned values
(10.2 %, 28 Aug) is a provider revision made three days later. A 2 % tolerance withheld 10
revision jumps for a day until confirmed (0.5 %: 36).

Readers of `national_gas_actual_demand`: values are read only by the research target path
(`read_demand_target_revisions` then `build_demand_target_rows`, used by the weather-demand
runtime, its operator CLI and the prediction runtime); it now applies the rule under its new
default policy `PROVIDER_PUBLICATION_ORDER_V1`. The Sources page, data-ops freshness and the
data-quality report count rows or take receipt times, not values.
`application/research/demand_inputs.project_rest_demand_targets` reads values but has no
caller outside its own tests; it was left unchanged (it already orders by provider clock
within one receipt) and should be routed through the rule or removed.

Live, value returned for each gas day as of 14 Nov 12:20 UTC (mscm):

| Gas day | Research targets before (receipt order) | Tie-break by (receipt, record id) | Research targets after | Day reader after |
|---|---|---|---|---|
| 3 Nov | refused (ambiguous receipt) | 1.28364 | 227.611 | 227.611 (settled) |
| 4 Nov | refused | 22.9004 | 229.115 | 229.115 (settled) |
| 5 Nov | refused | 249.797 | 249.797 | 249.797 (settled) |
| 6 Nov | refused | 257.067 | 257.081 | 257.081 (settled) |
| 7 Nov | refused | 252.06 | 252.06 | 252.06 (settled) |
| 8 Nov | refused | 256.002 | 256.002 | 256.002 (provisional) |
| 9 Nov | refused | 289.963 | 289.963 | 289.963 (provisional) |
| 10 Nov | refused | 284.171 | 284.147 | 284.147 (provisional) |
| 11 Nov | refused | 261.275 | 261.275 | 261.275 (provisional) |
| 12 Nov | refused | 242.622 | 239.595 | 239.595 (provisional) |

**REMIT units.** One conversion, `remit_umm.daily_figure`, applied by the normaliser and
again on read (`docs/operations/REMIT_OUTAGES.md`, "Daily figures and units"): hourly rates
times the gas day's 23/24/25 hours; GWh/TWh with no rate on storage is working gas volume,
not a flow, so no daily figure (Gas Storage Denmark's 8,590 GWh technical is its working
volume; an average over the event would read as a flow that does not exist); EPE-H's
"469.2 GWh/h" (11 TWh/d for one site) is refused as a unit error. The balance's Norwegian
outage read uses the same function. Of 56 live or upcoming outages: daily figure 36 before,
53 after; GWh/d total 1,323.0 to 1,942.8 (active 192.4 to 343.6); unconverted 3, named
(GWh 1, TWh 1, GWh/h 1). No stored row was rewritten.

**Outages on the map.** Placed in the 14-day horizon: 7 of 32 before, 16 after (EIC 7,
unique site name 9: Bierwang, Bergermeer x2, SEDIANE B, Etzel ESE x3, Etzel x2). The
locator's name step used to take the first of several reference points with the same name;
it now places only on one place and lists every miss with its reason. GIE's AGSI/ALSI
listing gives facility identity (EIC, name, country, operator) but no coordinates, and its
names placed nothing the message names did not, so no loader was built. Still unlocated
(16 outages, 7 facilities):

| Facility (message) | EIC | Operator | Outages | Why |
|---|---|---|---|---|
| EPE-H | 21W000000000066U | Uniper Energy Storage | 4 | "Epe" names two places in the reference network |
| Gas Storage Denmark (GSD) | 45W000000000241K | GSD | 3 | two sites (Stenlille, Lille Torup); the message names neither |
| UGS-Etzel-ESE-MET | 21W000000000055Z | MET Speicher | 3 | no reference point named Etzel ESE MET |
| CUGS Mogilno | 53ZPL0000602319I | Gas Storage Poland | 2 | no ENTSOG point for Mogilno; not in GIE's listing |
| GSF GIM Sanok - UGS PMG Brzeźnica | 53ZPL0000402311B | Gas Storage Poland | 2 | ENTSOG has the group (GIM Sanok), not the site |
| Nüttermoor 4 H-Gas | 37W000000000105E | EWE Gasspeicher | 1 | ENTSOG names "Nüttermoor H1 and H4"; not an exact name |
| Klaipeda LNG Terminal FSRU Independence | none | KN Energies | 1 | no EIC; ENTSOG names "Klaipeda (LNG)"; not an exact name |

**ENTSO-E short days.** Two causes, neither the 15-minute/hourly mix (the rule counts
series per day; Belgian hourly generation counts the same as 15-minute series) nor DST.
4 Nov is where the stored history begins (day-ahead prices from 23:00 UTC, the CET midnight
of 5 Nov; actuals from 5 Nov): partial by construction. The report no longer judges a
dataset's first stored day. 11 Nov: DE-LU gas, solar and onshore wind generation (A75)
were missing from 10 Nov 08:45 to 12 Nov 01:00 UTC. The provider has them; when the
bring-up read on 12 Nov 12:13 they were not yet published, and the scheduler's rolling
two-day window (`src-entsoe --days 2`) never reached back. The scheduler now reads seven
days. Re-fetched through the normal script (`ingest_power.py --zone DE_LU --days 6
--commit`): 480 inserted, 543 revised with history (late actuals, typically 50 MW on
60 GW load), 2,512 unchanged. Power now shows 0 short days.

**Data quality after** (14 Nov 12:34 UTC):

```
dataset                    status        rows series last period       age h  dup  blank short days rev 7d
ENTSOG flows               ok           13173    806 2026-11-14T05:00    7.6    0      0    0/418      265
ENTSOG capacity            ok           12647   3925 2026-11-14T06:00    6.6    0      0    0/611      109
GIE storage (AGSI)         ok            7812      6 2026-11-12T05:00   55.6    0      0    0/4801      28
GIE LNG (ALSI)             ok            7210      5 2026-11-12T05:00   55.6    0      0    0/4801       4
GB storage (National Gas)  ok             411      1 2026-11-13T05:00   31.6    0      0    0/409        1
GB LNG (National Gas)      ok             411      1 2026-11-13T05:00   31.6    0      0    0/409        1
ECB FX reference           ok              12      6 2026-11-13T00:00   36.6    0      0    0/0          -
Overnight rates            ok              99      3 2026-11-12T00:00   60.6    0      0    0/0          -
Henry Hub (EIA)            ok              33      1 2026-11-11T00:00   84.6    0      0    0/32         -
Power (ENTSO-E)            ok           18141     24 2026-11-14T22:45  -10.2    0      0    0/9        662
GB power (Elexon)          warning       1397      4 2026-11-14T06:30    6.1    0      0    0/6          0
    warning: Latest period is 6 h old; expected within 6 h.
GB demand (National Gas)   ok             119     96 2026-11-12T00:00   60.6    0      0    0/0          -
Outages (REMIT UMM)        ok            1588   1588 2026-11-14T06:13    6.4    0      0    0/0          -
```

The Elexon warning is age only: no scheduler ran after 06:54 UTC. The GIE placeholder rows
(AGSI GB, ALSI DK/GB/LU) are no longer in the store (removed before this round, not by it),
hence 0 blanks.

### Identity, boundary checks and the freshness contract (2026-11-14)

Five items: ONT-01 (which ontology decides what), ONT-02 (identity resolved once, never
guessed), ONT-03 (one boundary check for importers), FRESH-01 (one freshness contract) and
DATA-05 (TSO tariffs are manual registers). No migration; no new route.

**Authority.** [ONTOLOGY_AUTHORITY.md](../ontology/ONTOLOGY_AUTHORITY.md) names the three
ontologies (the executable `domain/ontology/` package, the generated GRM OWL file, the
research energy ontology with `source_entity_mappings`) and what each decides, and traces
ENTSOG point ITP-00106 from the provider record (423,450,000 kWh/d) to the canonical id
`ent:point:ITP-00106`, the stored row, the feature `flow.gwh_d.ITP-00106.entry`
(423.45 GWh/d), a dataset snapshot and `/api/research/datasets`. The trace runs as
`tests/contract/test_ontology_worked_example.py`.

**Identity.** One resolver (`application/identity_resolution.py`) backed by
`source_entity_mappings` and the built-in identities in
`domain/ontology/source_identity.py` (GIE countries, ENTSO-E and Elexon zones, National
Gas publications and aggregates). The ENTSOG reference ingest now writes the provider's
point and operator keys as mappings. The heuristic call sites are gone: the first word of a
product taken as a hub in `projections/daily_closes.py`, `storage_nomination_composition.py`,
`db/repositories/backtest.py`, `market_intelligence/normalized_view.py` and
`route_cost/portfolio_network.py`; the substring hub match in `contract_intake.py` and
`desk_text.hub_for_zone` (which read THE out of "NETHERLANDS"); contract hubs now also
consult the deployment's `delivery_point` mappings. Live, after a reference read through
the normal script (`ingest_public_sources.py --source entsog-reference --limit 50000
--entsog-page-size 1000`: 789 + 1,283 records, 2,733 rows upserted, 0 retired; 853 point
and 53 operator mappings written):

| Source | Identifiers stored | Resolved | Quarantined | Rows carrying them |
|---|---|---|---|---|
| ENTSOG | 751 | 730 | 21 (19 point keys, 2 operators) | 122 capacity rows |
| GIE | 11 | 11 | 0 | 0 |
| National Gas supply | 2 | 2 | 0 | 0 |
| National Gas demand | 2 | 2 | 0 | 0 |
| ENTSO-E | 4 | 4 | 0 | 0 |
| Elexon | 1 | 1 | 0 | 0 |

The 21 quarantined ENTSOG identifiers are all in `capacity_observations`, none in flows:
capacity validity ranges for points ENTSOG no longer lists in its reference (ITP-00044
Dragor 2014-2019, ITP-00199 Bunder-Tief to 2021, PRD-00158 to 00161, UGS-00394 Etzel ESE
operated by DE-TSO-0013, and others) plus operators DE-TSO-0013 and FI-TSO-0001. They are
listed on the Sources page (`unresolved_identifiers` on `src-entsog`, the total in the
posture summary), not mapped by name. Dry runs of the other ingestors report the same
check: ENTSO-E DE_LU, NL, BE, FR one zone each, resolved; Elexon GB resolved; National Gas
supply storage and LNG resolved; the GIE IIP collector quarantined none of 245 message
versions (3 days).

**Boundary checks.** `domain/ontology/boundary.check_boundary` (market, hub, unit, product,
period; reason codes in `BoundaryReason`) is called by the settlement, ETRM, quote and REMIT
file imports and the contract save. Existing importer tests pass unchanged (the ETRM message keeps
"trades in"); every code has a test (`tests/unit/test_boundary_validation.py`). The IIP
collector quarantines a reversed event instead of refusing the page.

**Freshness contract.** Each manifest declares its datasets' period thresholds
(`DatasetFreshness`); the data-quality report reads them (its `max_age_hours` table is
gone) and splits overnight rates into SONIA, €STR and SOFR, one per connector. Every
manifest now declares its `FreshnessPolicy` explicitly; GIE's normal age moved from 360 to
1,500 minutes because it is read once a day. Source Center's verdict now uses the policy
(stale beyond `stale_after_minutes`), not the display field `freshness_minutes`. Live
contract at 13:36 UTC (the scheduler was not running, so stored next runs are overdue):

| Dataset | Expected | Last received (UTC) | Next expected (UTC) | State |
|---|---|---|---|---|
| ENTSOG flows | every 60 min; stale after 6 h; period 54 h | 14 Nov 02:12 | 14 Nov 03:11, overdue | stale |
| ENTSOG capacity | every 60 min; stale after 6 h; period 54 h | 14 Nov 02:13 | 14 Nov 03:11, overdue | stale |
| GIE storage (AGSI) | daily 09:00 Brussels; period 72 h | 14 Nov 01:03 | 14 Nov 08:00, overdue | current |
| GIE LNG (ALSI) | daily 09:00 Brussels; period 72 h | 14 Nov 01:03 | 14 Nov 08:00, overdue | current |
| GB storage (National Gas) | every 3 h; period 72 h | 14 Nov 01:15 | 14 Nov 04:11, overdue | current |
| GB LNG (National Gas) | every 3 h; period 72 h | 14 Nov 01:15 | 14 Nov 04:11, overdue | current |
| ECB FX reference | daily 16:10 Berlin, weekdays; period 96 h | 14 Nov 01:13 | 14 Nov 15:10 | current |
| SONIA (BoE) | daily 10:15 London, weekdays; period 120 h | 14 Nov 01:13 | 14 Nov 10:15, overdue | current |
| €STR (ECB) | daily 08:15 Berlin, weekdays; period 120 h | 14 Nov 01:13 | 14 Nov 07:15, overdue | current |
| SOFR (NY Fed) | daily 08:30 New York, weekdays; period 120 h | 14 Nov 01:15 | 14 Nov 13:30, overdue | current |
| Henry Hub (EIA) | daily 17:10 New York, weekdays; period 264 h | 11 Nov 18:00 | 14 Nov 22:10 | late |
| Power (ENTSO-E) | every 60 min; period 30 h | 14 Nov 12:17 | 14 Nov 03:11, overdue | current |
| GB power (Elexon) | every 30 min; period 6 h | 14 Nov 06:55 | 14 Nov 02:41, overdue | late |
| GB demand (National Gas) | every 6 h; period 72 h | 14 Nov 06:33 | 14 Nov 19:36 (no scheduler state) | current |
| Outages (REMIT UMM) | every 30 min; period 336 h | 14 Nov 06:39 | scheduler disabled | current |
| 8 TSO tariff registers | manual register | - | not scheduled | manual |

Licensed feeds and simulators not connected read `never`; WM/Reuters and BFIX imports,
the weather template and the model service read `manual`.

**Tariffs.** The eight TSO tariff connectors are `integration = manual_register`: the
Sources page says "Manual register" (English and Chinese labels), the connector card is never in
"Needs attention", the dataops freshness engine returns `NOT_EXPECTED`, the category's next
action is "update the register". Registry snapshot: only the `integration` lines (8
registered sources changed, a new `integration` field on 39 source definitions) and GIE's
policy changed.

**Data quality after** (14 Nov 13:37 UTC; thresholds from the manifests, the same values):

```
dataset                    status        rows series last period       age h  dup  blank short days rev 7d
ENTSOG flows               ok           13173    806 2026-11-14T05:00    8.6    0      0    0/418      265
ENTSOG capacity            ok           12647   3925 2026-11-14T06:00    7.6    0      0    0/611      109
GIE storage (AGSI)         ok            7812      6 2026-11-12T05:00   56.6    0      0    0/4801      28
GIE LNG (ALSI)             ok            7210      5 2026-11-12T05:00   56.6    0      0    0/4801       4
GB storage (National Gas)  ok             411      1 2026-11-13T05:00   32.6    0      0    0/409        1
GB LNG (National Gas)      ok             411      1 2026-11-13T05:00   32.6    0      0    0/409        1
ECB FX reference           ok              12      6 2026-11-13T00:00   37.6    0      0    0/0          -
SONIA (BoE)                ok              33      1 2026-11-11T00:00   85.6    0      0    0/0          -
€STR (ECB)                 ok              34      1 2026-11-12T00:00   61.6    0      0    0/0          -
SOFR (NY Fed)              ok              32      1 2026-11-12T00:00   61.6    0      0    0/0          -
Henry Hub (EIA)            ok              33      1 2026-11-11T00:00   85.6    0      0    0/32         -
Power (ENTSO-E)            ok           18141     24 2026-11-14T22:45   -9.1    0      0    0/9        662
GB power (Elexon)          warning       1397      4 2026-11-14T06:30    7.1    0      0    0/6          0
    warning: Latest period is 7 h old; expected within 6 h.
GB demand (National Gas)   ok             119     96 2026-11-12T00:00   61.6    0      0    0/0          -
Outages (REMIT UMM)        ok            1588   1588 2026-11-14T06:13    7.4    0      0    0/0          -
```

**Found, not fixed.**

- `markets.py` lists ETF as an alias of TTF; the contract intake and desk text treat ETF as
  the Danish hub. A contract naming ETF resolves to TTF (as positions already did).
  **Closed 2026-11-15**: ETF and GTF are Danish markets of their own (see
  [ONTOLOGY_AUTHORITY.md](../ontology/ONTOLOGY_AUTHORITY.md)); the audit found no stored row
  naming them in this store.
- Dataset entity ids `ent:point:`, `ent:storage_site:`, `ent:bidding_zone:` are not in the
  research ontology's `CanonicalEntityType`; GIE "storage sites" are country aggregates.
- `application/source_operations.py` keeps an older freshness-SLA table
  (`evaluate_source_sla`) with no caller; it disagrees with the manifests (GIE 360 min).
- `freshness_minutes` on each manifest is still a display field beside the policy (EIA
  and the rate sources show 1,440 while their policy says 2,880).
- `public_sources._market_hub_code` still takes the first word of an ENTSOG market-area
  label as a code for reference market hubs; it is reference-network bundle code, left to
  that work.
- Rows whose provider identifier is quarantined are stored and listed, not withheld from
  readers: the hub readers never guess, but a flow or capacity row with an unmapped point
  key is still read by point key. **Closed 2026-11-15**, see "Quarantine withholds" below.

### Quarantine withholds (2026-11-15)

A row whose provider identifier does not resolve is now withheld from every reader, not only
listed. Decision: resolve at read time, not flag at ingest. One SQL condition
(`application/identity_resolution.identity_clause`, rule `WITHHOLDING_RULE`) is added to every
query that serves or sums flow, capacity, storage, LNG or power rows: the map, the balance and
pipeline landings, physical flows and capacity, storage and LNG lists, research datasets, the
agent bridge and capability handlers, gas-for-power. A flag at ingest would have needed a
back-fill of stored rows and a second rewrite at every release; read-time resolution keeps the
rows untouched (history, as-of reads and the Sources list keep them), takes effect for a new
mapping at the next read, and needs no migration. `tests/contract/test_identity_withholding_readers.py`
fails when a module queries those tables without the condition, so a new reader cannot forget.

Rules: ENTSOG rows are checked on the point key and, when the row states one, the operator key,
and only once the store holds the provider's reference mappings (before the first reference
read nothing can be judged, so nothing is withheld). GIE, National Gas and power-zone
identifiers are checked against the built-in lists. An identifier mapped to two entities is
withheld. The Sources page marks each listed identifier `withheld: true`; rows without an
operator key are no longer listed as an empty operator identifier.

Live, 15 Nov (no data rewritten):

| | Before | After |
|---|---|---|
| ENTSOG identifiers listed | 21 (19 point keys, 2 operators) | 21 |
| Capacity rows carrying them (point 94 + operator 28, 15 rows carry both) | 107 served | 107 withheld of 12,647 |
| Flow, storage, LNG, power rows withheld | 0 | 0 |

All 107 withheld capacity ranges are still valid today (the longest to 2054), so capacity
reads served them until now. The SQL condition and the Python resolver agree row for row.

**Releasing an identifier.** When an operator has established what a quarantined identifier
names (for example a point key ENTSOG no longer lists, checked against the operator's own
publication), add its mapping:

```bash
python scripts/ops/release_quarantined_identifier.py --source-id src-entsog \
  --entity-type entsog_point --identifier ITP-00044 --evidence "who checked what"   # dry run
python scripts/ops/release_quarantined_identifier.py ... --commit
```

The dry run prints the current resolution and the withheld rows per table before and after,
then rolls back. Setting the mapping's `mapping_status` to `RETIRED` withholds the rows again.

### Reference network bundle (2026-11-14)

The reference read of this store built the shipped NWE network bundle
(`docs/operations/REFERENCE_NETWORK_BUNDLE.md`, licence position in
`docs/legal/DATA_SOURCE_TERMS.md`): 318 points, 267 with an ENTSOG map position, 288
schematic zone links. 64 of the 718 points in the operator point directions have no
connection-point map position (51 in the NWE scope), among them five balance landing points:
Dornum ITP-00126 and ITP-00188, Emden ITP-00080, ITP-00081 and ITP-00160. The map counts
them, and the flows reported at them, as not located (`unlocated.network_points`,
`unlocated.flows`) instead of dropping them silently. Read-only against this store.

### Data gaps: outages, Dornum, weather, facility identity (2026-11-16)

Four open items: transmission and production outages, Dornum against Gassco, ECMWF weather in
the balance, and outages the map cannot place. No migration.

**Transmission outages from ENTSOG.** ENTSOG does publish UMMs:
`https://transparency.entsog.eu/api/v1/urgentmarketmessages` answered 200 (after connection
resets on the first tries) with 93 message versions from 19 TSOs, oldest published 2021,
newest 15 Nov 2026; it pages like `operationaldatas` (`sort=id` echoed, total = rows left
capped at the limit, 404 past the end; `from`/`to` are ignored for this dataset). 38 are
`Gas` (unavailability: transmission system 30, other 5, compressor station 3; kWh/d 30,
kWh/h 8), 55 `Other` (no capacity). No Norwegian, no production message, and none from GTS,
National Gas or Energinet. `interruptions` also exists (interrupted interruptible capacity at
points, a capacity product, not a facility unavailability); not collected. Built:
`ingestion/entsog_umm.py` (ACER field mapping for the importer's normaliser),
`scripts/ops/ingest_remit_entsog.py --days/--commit/--json`, connector `src-entsog-umm`
(hourly, on by default, no key; its own connector because the scheduler runs one script per
source), dataset freshness "Outages (ENTSOG UMM)" (late after 90 days: none May-Sep 2026),
the ENTSOG platform in the REMIT register, citation with download date on every row. Live
back-fill (`--days 90 --commit`): 93 read, 38 unavailability versions in the window, 2
messages held back (ENTSOG flags their newest version `isLatestVersion=No`: GRTgaz
Deutschland VIP France-Germany `...P013`, NaTran `...S001`), 35 versions of 28 messages
stored, operators 19/19 resolved. Stored versions by operator: OGE 15, GRTgaz/NaTran
Deutschland 9, NaTran 4, terranets bw 3, Fluxys 2, Thyssengas 1, Elering 1; asset type
transmission (OGE's include its storage connection points, e.g. "Speicher Bierwang Entry"). 27 live outages, 1,043.9 GWh/d together; 20 of the 27 in
the map's 14-day horizon placed by EIC. Balance Norwegian outage read: 0 before, 0 after
(none in zone NO).

*Defect found and fixed.* The normaliser read `Inactive` as `active` ("inactive" contains
"active", tested first), and readers dropped only dismissed events, so an event its operator
had declared over stayed a live outage. Now `inactive` is read and, like `dismissed`, ends the
event in the outage list, map, Today and the balance (`remit_umm.ENDED_STATUSES`). GIE IIP
versions already stored keep the misread status until the IIP collector next reads them
(its 90-day re-read was refused by GIE's upstream rate limit, `iip_upstream_refused`, four
times on 16 Nov; the scheduler's 2-day window corrects new and revised messages).

**Dornum against Gassco: nothing openly published.** Checked 16 Nov, no terms accepted:
`umm.gassco.no` redirects to `/disclaimer` ("Gassco FLOW Terms & conditions", an
`acceptDisclaimer` button); `flow.gassco.no` reset the connection; `umm.gassco.no/api` 404;
ENTSOG's Gassco-side points (ITP-00208 Dornum EPT1 & EPT2, ITP-00209/-00210 Emden) were
recorded on 14 Nov with `hasData` false and 404 for operational data (re-check on 16 Nov
reset by the host); the Norwegian Offshore Directorate's FactPages and norskpetroleum.no
publish monthly and annual production and exports, not daily terminal deliveries. Gassco's
own "Principles for publication on umm.gassco.no" (PDF linked from the disclaimer page)
says what Gassco FLOW shows: real-time *daily aggregated nominations* for the current gas
day, updated every 5 minutes, for Dornum, "Aggregated Europipe Metering Station", Nybro,
Dunkerque, Zeebrugge, Easington, St Fergus/Vesterled, SEGAL entry, other exits and the NCS
sum, and historical final daily aggregated nominations up to two years back, shown as
graphs. Nothing was changed; ITP-00188 stays out of `SAME_PHYSICAL_POINT`.

What the owner would do. Open https://umm.gassco.no/ and read the terms page: in short, the
information is what Gassco had when published, from third parties too, not exhaustive or
complete, must not be used as the legal or factual basis for a decision, and neither Gassco
nor Gassled is responsible for its correctness or timeliness; it says nothing about reuse,
so a stored or shown figure still needs Gassco's written confirmation
(`docs/legal/DATA_SOURCE_TERMS.md`). Once accepted, read the historical final daily
nomination for **Dornum** (and "Aggregated Europipe Metering Station") for 5-10 closed gas
days, e.g. 3-12 Nov 2026, in MSm3/d. Compare with ENTSOG at an assumed 11.1 kWh/Sm3 (Gassco's
GCV not read; state the one used), 3-12 Nov: ITP-00126 alone was 735-780 GWh/d, 66-70
MSm3/d; ITP-00126 + ITP-00188 was 1,470-1,561 GWh/d, 132-141 MSm3/d (table in "Dornum:
independent opinion" above). Gassco's Dornum day by day near ITP-00126 alone (within a few per
cent: the GCV and the nomination-versus-allocation gap) means **duplicate**: add ITP-00188 to
`SAME_PHYSICAL_POINT`; near the sum means **additive**; anything between, or a Dornum figure
that only matches with the Europipe Metering Station added, is inconclusive. Gassco
publishes nominations, not metered flow; a small daily gap is expected either way.

**ECMWF weather: stopped at the decoder.** What exists: the bounded open-data transport
(index plus HTTP byte range, about 0.3 MB per field), the operator CLI
`scripts/ops/ingest_ecmwf_forecasts.py` (explicit run, steps and point bindings), append-only
persistence with issue time and receipt (`append_ecmwf_forecast`, as-of reads), degree-day
features over a reviewed region profile (`compute_weather_degree_days`,
`WeatherRegionProfile`, owner-approved `NWE_WEATHER_PROFILE` with weights summing to one),
and the balance *scenario* (POST) that consumes them. The GET balance does not. Checked
live: the 2t field of run 2026-11-16 00z, +24 h is a 314,215-byte GRIB2 message with data
representation template 5.42 (CCSDS); decoding it needs ecCodes, which is in no lock file
(`requirements*.lock`) and not installed here. Per the brief, no decoder was added. Options:
(1) `eccodes` 2.50.1 (Apache-2.0) with its binary wheels `eccodeslib` 2.50.0.34 (9.0 MB) and
`eckitlib` 2.5.0.34 (36.2 MB), plus numpy (only in the scientific-CI lock), cffi (locked),
attrs and findlibs, as an optional extra installed only on the ingesting host, after the
dependency licence review covers the bundled native libraries; (2) the distribution's
ecCodes package on that host; (3) `imagecodecs` (BSD-3-Clause, 27.7 MB) for CCSDS with our
own GRIB2 section handling: more decoding code to own; (4) a hand-written CCSDS decoder: not
recommended (a wrong number is worse than a missing one). Also open, and the owner's: the
NWE region profile (which points, which weights) does not exist in the store and the design
leaves it to review; no weights were invented. History without an account: data.ecmwf.int
lists the last 4 run dates (13-16 Nov); the AWS replica the code allows from 2023-01-18
answered `SlowDown` (HTTP 503) to every probe, so its depth was not confirmed here; that is
past *forecasts*, not observations; ERA5 needs a CDS account. Nothing changed in the balance:
it still says "No heating-degree-day inputs supplied" and replays 2025. Its forecast on 16
Nov (last measured day 12 Nov, call 8,923 GWh/d): 13 Nov 9,521; 15 Nov 10,251; 17 Nov 11,631;
19 Nov 12,929; 22 Nov 13,601 GWh/d, from 17 Nov flagged `withdrawal_above_recent_maximum`.
No weather-driven figure exists to compare, and none is claimed.

**Outages the map cannot place.** GIE's AGSI+/ALSI listing (169 rows, 159 EICs, 10 EICs
listed twice) is loaded as identity (`scripts/ops/ingest_gie_facilities.py`, canonical
entity `ent:gas_facility:<EIC>` and a `src-gie`/`gie_facility` mapping; retired, never
deleted). The reference facility table requires coordinates, so identity lives in the
identity tables. The map matches an unplaced outage to a GIE facility by EIC, else by GIE's
exact name; a facility whose EIC is an ENTSOG point EIC (29 of 159) is placed there, the
others are listed as known facilities with no published position. 14-day horizon, 57
outages: placed 36 / known 0 / unlocated 21 before; 36 / 14 / 7 after.

| Facility (message) | EIC | Outages | Before | After |
|---|---|---|---|---|
| EPE-H | 21W000000000066U | 5 | unlocated ("Epe" names two places) | known: UGS Epe Uniper H-Gas, DE, Uniper |
| UGS-Etzel-ESE-MET | 21W000000000055Z | 3 | unlocated | known: UGS Etzel ESE (MET), DE, MET Speicher |
| Gas Storage Denmark (GSD) | 45W000000000241K | 3 | unlocated | known: VGS GSD (Lille Torup, Stenlille), DK; two sites, no main one published |
| Klaipeda LNG Terminal FSRU Independence | none | 1 | unlocated | known by GIE's exact name: Klaipėda LNG Terminal (FSRU Independence), LT |
| Nüttermoor 4 H-Gas | 37W000000000105E | 1 | unlocated | known: UGS Nüttermoor H-4 (GIE lists it under NL) |
| Zone MND ESG Entry (OGE) | 37Y000000000386Q | 1 | unlocated | known: VGS Zone MND ESG (Stockstadt, Hähnlein), DE |
| CUGS Mogilno | 53ZPL0000602319I | 1 | unlocated | unlocated: not in GIE's listing; only the group GIM Kawerna is, and the message does not name it |
| 6 transmission points (Värska, SPNS2U, Emden EMS/EPT, Speicher Gronau-Epe H1/H4, Epe H) | ENTSOG UMM EICs | 6 | unlocated | unlocated: EIC not in ENTSOG's reference |

GSD Sanok/Brzeźnica from the 14 Nov list has ended and is no longer in the horizon. Not done:
linking a GIE facility to ENTSOG storage points through the operator (ENTSOG names the storage
operator by key, `DE-SSO-0001`, which needs ENTSOG's operator list to meet GIE's operator EIC;
the `operators` endpoint did not answer on 16 Nov).

## Reproducing

```bash
python scripts/ops/certify_public_source.py --source entsog --operator <id>
python scripts/ops/certify_public_source.py --source gie --operator <id>
python scripts/ops/ingest_public_sources.py --source entsog-reference --limit 50000 \
  --entsog-page-size 1000
python scripts/ops/purge_gie_placeholder_rows.py   # dry run; --commit deletes
python scripts/ops/run_dataops_scheduler.py --interval-seconds 60 --entsog-lookback-gas-days 7
python scripts/ops/ingest_public_sources.py --source entsog --source entsog-capacity \
  --entsog-lookback-gas-days 7 --limit 50000 --entsog-page-size 1000
python scripts/ops/ingest_public_sources.py --source gie-agsi --source gie-alsi \
  --gie-country nwe --limit 600
python scripts/ops/ingest_public_sources.py --source ecb
python scripts/ops/ingest_public_sources.py --source entsog --entsog-from 2025-09-20 \
  --entsog-to 2025-10-20 --entsog-point-direction <landing point-directions> --limit 5000
python scripts/ops/ingest_national_gas_supply.py --days 30 --end 2025-10-28 --commit
python scripts/ops/flow_point_alias_candidates.py --days 30 --tolerance 0.0005
python scripts/ops/data_quality_report.py
python scripts/ops/capacity_range_resplits.py            # dry run; --commit records moves
python scripts/ops/ingest_national_gas_demand.py --json --days 8
python scripts/ops/ingest_remit_iip.py --days 90 --commit --json
python scripts/ops/ingest_power.py --zone DE_LU --days 6 --commit
python scripts/ops/ingest_public_sources.py --source entsog-reference --limit 50000 \
  --entsog-page-size 1000 --json        # also writes ENTSOG identity mappings; "identity"
python scripts/ops/ingest_remit_iip.py --days 3 --json   # dry run; "quarantined"
python scripts/ops/ingest_remit_entsog.py --days 90 --commit --json
python scripts/ops/ingest_gie_facilities.py --commit --json

python scripts/ops/build_reference_network_bundle.py --version 2026-11-14 --downloaded 2026-11-14
python scripts/ops/ingest_public_sources.py --source entsog --entsog-from 2026-11-05 \
  --entsog-to 2026-11-13 --entsog-point-direction <landing point-directions> \
  --limit 5000 --entsog-page-size 1000
```

Keys (GIE, ENTSO-E, EIA) come from the environment or the credential store, never from the
repository.

## Capacity reads and legacy volume-only rows (2026-11-15)

`/api/physical/capacity` returned no row for ENTSOG fixture rows that carried only a volume,
and returned the demo row. Cause: `physical_native_rates.row_volume_admissible`. An ENTSOG
row with neither native column (`normalizer_version`, `native_rate_json`) is a row stored
before native units, and its `capacity_mcm_d` was converted from ENTSOG's kWh/d with an
assumed calorific value. The volume read withholds it with the "legacy ENTSOG" warning; the
native read filters it out in SQL. The demo row is not ENTSOG, so a finite volume is
admitted. Neither the identity withholding clause nor the capacity resolver was the cause.

Decision: withholding is correct (a converted volume with an unknown calorific value is a
wrong number, not a missing one), and such rows will exist in an upgraded customer store.
Two defects fixed around it: the native read was silent (now it warns
`LEGACY_ENTSOG_NOT_NATIVE_WARNING` for flows and capacity when legacy rows are in scope),
and a legacy range received after a native range took part in the capacity resolution, won
it and was then withheld, hiding a verified native value (legacy rows are now left out of
the resolution). Remedy for an upgraded store: re-ingest the window from ENTSOG; native
rows are written beside the legacy ones (`entsog-*-n1-` ids).
