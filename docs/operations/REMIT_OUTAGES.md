# REMIT outages (gas UMMs)

Operators of gas production, storage, LNG and transmission facilities must publish
unavailability as urgent market messages (UMMs) under REMIT Article 4, on an
inside-information platform, in the fields ACER's Manual of Procedures defines. Norwegian
field and processing outages (Troll, Kollsnes, Nyhamna) move NBP and TTF within minutes,
so desks follow these messages closely.

## GIE Inside Information Platform (scheduled)

GIE's IIP carries the UMMs of European storage (SSO) and LNG (LSO) operators. Its API
(`https://iip.gie.eu/api`, JSON, newest submissions first, 50 messages a page, each with its
earlier versions under `prev`) is free; registration is mandatory and the personal key goes
in the `x-key` header. GIE's AGSI/ALSI key (`GIE_API_KEY`) is accepted (checked 2026-11-14).
The API documentation itself is only shown to registered users.

```bash
python scripts/ops/ingest_remit_iip.py --days 7                    # dry run: counts only
python scripts/ops/ingest_remit_iip.py --days 2 --commit --json    # what the scheduler runs
```

- Only `unavailabilityOfGasFacilitiesReport` messages are kept (storage, injection,
  withdrawal, compressor and regasification unavailability); "other market information"
  has no capacity. Transmission operators do not publish on IIP: transmission and
  production UMMs still come by file import below.
- `messageId` ends in `_<version>`: the part before is the message, the number its
  version. `published`, `from` and `to` are UTC; each equals the `Z` time in the ACER XML
  the record embeds (150 of 150 checked).
- Records are mapped to ACER field names (`ingestion/gie_iip.py`) and read by the same
  normaliser as file imports; each version is stored once (`db/repositories/remit.py`).
- The read stops when a page holds nothing submitted in the window; reaching
  `--max-pages` (40) first fails with `iip_read_bound_reached`. The platform relays an
  upstream rate limit (429) as HTTP 200 with an error envelope: the script waits and retries
  twice, then fails `iip_upstream_refused` and the scheduler retries the run.
- Scheduler: source `src-remit-umm`, every 30 minutes, two days of submissions; off by
  default (it needs the GIE key, as `src-gie`).
- Credit: "Source: GIE Inside Information Platform (IIP/GIE)" wherever the data is shown
  or exported; GIE may disable a key whose use does not credit it.

First run (14 Nov 2026, `--days 90 --commit`): 25 pages, 1,250 messages, 1,588 message
versions stored (467 messages); 56 live or upcoming outages in the next 90 days (55
storage, 1 LNG). Units as published: GWh/d 30, kWh/h 17, mcm/d 5, one each of kWh/d, GWh,
GWh/h and TWh.

## Daily figures and units

One function derives the daily figure, `domain/observations/remit_umm.daily_figure`, used
by the normaliser (file import and IIP alike) and again on every read from the stored unit
and capacity, so rows stored before a unit converted read the same as new ones. Each
outage row says how its figure was made (`daily_basis`):

| Published unit | Daily figure | `daily_basis` |
|---|---|---|
| GWh/d, MWh/d, kWh/d, mcm/d, MSm3/d | converted through the unit authority (`domain/ontology/quantity.py`) | `per_day` |
| kWh/h, MWh/h, GWh/h | rate x the hours of the gas day (23, 24 or 25 at the clock changes, `domain/market/gas_day.py`): the gas day of the event start when stored, the current gas day for a live event when read; the rate itself in `unavailable_gwh_h` | `per_hour_x_24h` (or `23h`, `25h`) |
| GWh, TWh (no rate), storage or LNG | none: this is working gas volume, not a flow (Gas Storage Denmark: technical 8,590 GWh, its working volume); the amount is in `unavailable_total_gwh` | `unconverted:working_volume_not_rate` |
| GWh, TWh (no rate), other assets | the average per 24 hours over the event when its end is known, labelled | `event_average` |
| any unit where one facility would exceed 2,000 GWh/d or 200 mcm/d | none: a unit error (EPE-H "GWh/h", 469.2 technical, is 11 TWh/d) | `unconverted:implausible_for_unit:<unit>` |
| unknown | none | `unconverted:unknown_unit:<unit>` |

Energy and volume are never converted into each other here (no calorific value is
assumed); a stored GWh/d figure that came with a volume message is kept (`stored`).
Like GWh/d messages, the daily figure of an hourly rate is the capacity lost per gas day
while the event runs, not the energy lost over a partial day.

Nothing is dropped silently: the outage list (`GET /api/physical/outages`) carries
`meta.unit_summary` (`with_daily_figure`, `unconverted_count`, `unconverted_units`,
`unconverted_reasons`) and a warning naming the units left out of daily totals; the map
payload carries the same as `outage_units`.

Live, 14 Nov 2026 (56 live or upcoming outages): before, 36 carried a daily figure
(GWh/d total 1,323.0, active 192.4); after, 53 (GWh/d total 1,942.8, active 343.6); 3
unconverted, named: GWh 1 and TWh 1 (working volume), GWh/h 1 (implausible).

## Placing outages on the map

`application/map_situation._Locator` (`LOCATION_MATCH_RULE`), in order of reliability:
the EIC exactly; the exact name when it names one place; the site name without bracketed
notes or generic words (UGS, storage, LNG) compared with the whole reference name and each
side of an ENTSOG `A / B` point, when it names one place. A node and a facility at the same
coordinates are one place (`points_at_place` says how many reference points share it).
Nothing fuzzy: an ambiguous or unknown name stays unlocated, and the map payload lists each
in `unlocated_outages` with the reason.

The reference network is ENTSOG's connection points; REMIT names the storage facility
(21W... EICs) that ENTSOG rarely carries. GIE's AGSI/ALSI listing endpoints
(`/api/about?show=listing`, the existing GIE key) give per-facility identity (EIC, name,
country, operator, type) for 159 storage and LNG facilities, but no coordinates, so they
cannot place an outage by themselves; on the live outages their names added no unique
match beyond the message's own name, so no loader was built. Live (14-day horizon, 32
outages): 7 placed before, 16 after (EIC 7, site name 9). See
`docs/data/LIVE_BRINGUP_2026-11-12.md` for the 16 left unplaced and why.

## Import

Export the messages from the platform your desk follows (EEX Transparency, GIE IIP, Gassco
UMM, or another platform) as JSON or CSV, then:

```bash
python scripts/ops/import_remit_umm.py --platform GIE_IIP --file umm_export.json --dry-run
python scripts/ops/import_remit_umm.py --platform GIE_IIP --file umm_export.json
# A platform whose reuse terms are not published needs written confirmation first:
python scripts/ops/import_remit_umm.py --platform EEX_TP --terms-confirmed --file eex.csv
```

Accepted fields (case, spaces and underscores ignored): message id, version, publication
date/time, event status (Active/Inactive/Dismissed), type of unavailability
(Planned/Unplanned), event start, event stop, affected asset name, EIC and type, balancing
zone, direction, unit of measure, technical/available/unavailable capacity, reason, market
participant, remarks. Nested JSON such as `affectedAsset: {name, eic}` is read as well.
Times without an offset are read as UTC, as ACER requires. A file with any unreadable
message is refused as a whole.

Every message version is stored; readers use the latest version of each message and drop
dismissed events. Capacity stays in the published unit; `capacity_impact_mcm_d` is filled
only for volume units (mcm/d, MSm3/d) and `unavailable_gwh_d` only for energy units, so no
calorific value is assumed.

**Boundary check (ONT-03).** Every message's event period is checked by
`domain/ontology/boundary.check_boundary`: an event that ends before it starts is refused
with reason `period_reversed`. A file import is refused whole, naming the message and the
reason; the scheduled IIP collector leaves that one message out and lists it under
`quarantined` (message id, reason, detail) in its `--json` output, so one bad provider
record does not refuse the page. A unit with no daily figure is not refused: it is stored as
published and reported as `unconverted:<reason>` (above).

Storage and LNG messages from GIE IIP arrive through the scheduled collector above; use
the import for production and transmission messages (Gassco, EEX Transparency, PRISMA)
until a collector for those platforms exists.

## Where it shows

- Market → Capacity & Events → **Outages**: live and upcoming events (90 days), soonest first.
- `GET /api/physical/outages?horizon_days=90&asset_type=production` and the SDK's
  `fetch_outages`.

## Terms

UMMs are inside information operators are obliged to publish. Each platform sets its own
reuse terms; confirm commercial reuse for the platform you export from (see
[DATA_SOURCE_TERMS.md](../legal/DATA_SOURCE_TERMS.md)).
