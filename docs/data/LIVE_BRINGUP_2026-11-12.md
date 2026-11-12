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
   legacy volume column, which is empty for native rows. To be fixed with the single
   unit authority (NUM-01).
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
