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
| GB demand (National Gas) | 107 | 86 | to 11 Nov | ok |
| REMIT outages | 0 | – | – | not run: file import only, no live collector yet |
| ECMWF forecasts | 0 | – | – | not run: needs series bindings first |

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
   continental sum (about 278 mcm/d at 11 kWh/m3) is plausible, not verified.
5. **REMIT has no live collector** (DATA-03) and **ECMWF needs series bindings** before a
   first run.
6. **A 72-hour unattended scheduler run has not been done.** This run was operator-invoked
   commands. The scheduler run is the remaining part of DATA-01.
7. **ENTSOG publishes rows for the open and the next gas day.** They are stored; consumers
   that need closed days must filter on the period end, as the balance does.

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

## Reproducing

```bash
python scripts/ops/certify_public_source.py --source entsog --operator <id>
python scripts/ops/certify_public_source.py --source gie --operator <id>
python scripts/ops/ingest_public_sources.py --source entsog-reference --limit 20000
python scripts/ops/ingest_public_sources.py --source entsog --source entsog-capacity \
  --entsog-lookback-gas-days 7 --limit 50000 --entsog-page-size 1000
python scripts/ops/ingest_public_sources.py --source gie-agsi --source gie-alsi \
  --gie-country nwe --limit 600
python scripts/ops/ingest_public_sources.py --source ecb
python scripts/ops/data_quality_report.py
```

Keys (GIE, ENTSO-E, EIA) come from the environment or the credential store, never from the
repository.
