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

## ENTSOG Transparency Platform (scheduled, transmission)

ENTSOG publishes the urgent market messages TSOs send it at
`https://transparency.entsog.eu/api/v1/urgentmarketmessages` (public, no key; found live
2026-11-16). It pages like ENTSOG's other datasets (`sort=id` echoed, `meta.total` is the rows
left capped at the limit, 404 past the end), so it is read through `ingestion/entsog_transport.py`.
The whole dataset is small (93 message versions from 19 TSOs, the oldest published 2021), so
every run reads all of it and selects locally.

```bash
python scripts/ops/ingest_remit_entsog.py --days 90                 # dry run: counts only
python scripts/ops/ingest_remit_entsog.py --days 7 --commit --json  # what the scheduler runs
```

- `messageType` `Gas` is an unavailability (transmission system, compressor station, other
  unavailability, with unit and capacities); `Other` is other market information and is not
  kept. `messageId` is `<threadId>_<versionNumber>`. Times carry their CET/CEST offset.
- Kept: versions published in the last `--days`, plus every version of an event still running
  after the window start (an outage announced in 2024 that runs to 2029 is live).
- Mapped to ACER field names (`ingestion/entsog_umm.py`), read by the importer's normaliser,
  stored once per version (`db/repositories/remit.py`) under system `ENTSOG_UMM`; asset type
  `transmission` (the publisher is a TSO, including at storage connection points such as OGE's
  "Speicher Bierwang Entry"). The balancing zone is ENTSOG's key without its dash padding
  (`DE-THE`). OGE leaves `direction` empty and names it in the point ("... Entry"); that word is
  taken as the direction, nothing else.
- Identity: the publisher's ENTSOG operator key must resolve through the mappings the ENTSOG
  reference read wrote; an unresolved one is held back (`unresolved_operator`). The asset EIC is
  the ENTSOG point EIC, which the map places exactly.
- ENTSOG flags each version `isLatestVersion`. A message whose newest version in the feed is
  flagged `No` has its current state unpublished, so it is held back
  (`latest_version_not_published`; live: GRTgaz Deutschland's VIP France-Germany `...P013` and
  NaTran's `...S001`) rather than served as current.
- Scheduler: source `src-entsog-umm`, hourly, on by default (no key). Freshness: event-driven
  and sparse (none from May to September 2026), period late after 90 days.
- Credit: "ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/" with the download date; every
  stored message carries it in its source reference (`ENTSOG_TP:terms-published:api:<UTC>`) and
  outage rows return it in `attribution` (with `platform`).

What it does not carry: no Norwegian (Gassco) or production message, and only the TSOs that
publish to ENTSOG (live: OGE, NaTran, GRTgaz/NaTran Deutschland, terranets bw, Fluxys,
Thyssengas, Elering among the unavailability messages; GTS, National Gas and Energinet none).
Production and Norwegian outages still need the file import.

First run (16 Nov 2026, `--days 90 --commit`): 93 versions read in one page; 38 unavailability
versions in the window, 2 messages held back (latest version not published), 35 versions of 28
messages stored, 19 of 19 operators resolved; 27 live or upcoming transmission outages within
90 days, all active, every one with a daily figure (20 per day, 7 hourly x 24 h), 1,043.9 GWh/d
together. The map places 20 of the 27 in its 14-day horizon by EIC (24 placements by EIC in
all, from 7). None is in the Norwegian zone, so the balance's outage read is unchanged (0).
Four GRTgaz/NaTran Deutschland messages each state 81 GWh/d off VIP France-Germany entry from
1 Oct 2026 to 2029 (`...P012`, `P014`, `P015`, `P016`): separate messages as published, stored
as four. Since 16 Nov 2026 the outage list and Today show them as one event (same asset, period
and size: `remit_umm.outage_events`, "One row per event" in docs/ux/LIVE_MAP.md) naming every
message; the plain `GET /api/physical/outages` still returns each message.

## Event status

ACER's `Inactive` means the event is over and `Dismissed` that the message was withdrawn.
Until 16 Nov 2026 the normaliser read every `Inactive` as active (it tested "active" first,
which "inactive" contains), and readers dropped only dismissed events. Now `Inactive` is read
as such and readers (outage list, map, Today, the balance's Norwegian outages) treat the
latest version `inactive` or `dismissed` as no live outage (`remit_umm.ENDED_STATUSES`).

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
country, operator, GIE type) for 159 storage and LNG facilities, but no coordinates.

**Known facilities (2026-11-16).** `scripts/ops/ingest_gie_facilities.py --commit` loads the
listing as identity: one canonical entity `ent:gas_facility:<EIC>` (name, country, operator,
type in its metadata) and one `src-gie`/`gie_facility` mapping per EIC; a facility no longer
listed is retired (mapping `RETIRED`, never deleted) and restored if it returns. The reference
facility table needs a coordinate, which these facilities do not have, so identity lives in the
identity tables. An outage the reference network cannot place is then matched to a GIE
facility (`KNOWN_FACILITY_RULE`): by EIC, else by GIE's exact name (case, accents and
punctuation ignored) when it names one facility. If the facility's EIC is also an ENTSOG
point EIC (29 of 159 are), the outage is placed at that point (`gie_facility_eic`/`_name`);
otherwise it is listed in `known_facility_outages` (facility, EIC, country as GIE lists it,
operator, how identified, its outages) and counted in `outage_placement.known_facility_no_position`,
not in `unlocated`. No coordinate is derived from a name and no alias is added.
Not done: linking a GIE facility to ENTSOG storage points through the operator (ENTSOG names
the storage operator by its ENTSOG key, e.g. `DE-SSO-0001`, at the adjacent side of a storage
point; matching that to GIE's operator EIC needs ENTSOG's operator list, which the product does
not read yet).

Live (14-day horizon, 57 outages: 30 storage/LNG, 27 transmission):

| | Placed | Known facility, no published position | Unlocated |
|---|---|---|---|
| Before the listing | 36 | 0 | 21 |
| After | 36 | 14 | 7 |

Known: UGS Epe Uniper H-Gas (DE, 5, message "EPE-H"), UGS Etzel ESE (MET) (DE, 3), VGS GSD Gas
Storage (Lille Torup, Stenlille) (DK, 3), Klaipėda LNG Terminal (FSRU Independence) (LT, 1, by
name: the message has no EIC), UGS Nüttermoor H-4 (GIE lists it under NL, 1), VGS Zone MND ESG
(DE, 1, an OGE transmission message at the storage zone). Unlocated: CUGS Mogilno (EIC not in
GIE's listing; GIE and ENTSOG carry only the group GIM Kawerna, which the message does not
name) and six transmission points whose EIC ENTSOG's reference does not carry (Värska Entry,
NaTran SPNS2U, Thyssengas Emden EMS/EPT, OGE Speicher Gronau-Epe H1/H4 and Epe H Entry).

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

Storage and LNG messages from GIE IIP and transmission messages that TSOs publish on ENTSOG
arrive through the scheduled collectors above; use the import for production and Norwegian
messages (Gassco, EEX Transparency, PRISMA) until a collector for those platforms exists.

## Where it shows

- Desk → Network → **Outages** (the panel beside the map): one row per event (90 days, and
  events ended in the last 7 days), largest capacity offline first; see "One row per event"
  in docs/ux/LIVE_MAP.md and `GET /api/physical/outages?grouped=true&ended_days=7`.
- `GET /api/physical/outages?horizon_days=90&asset_type=production` and the SDK's
  `fetch_outages`.
- `GET /api/desk/today` (the Today read): active and scheduled counts over 14 days from the
  same service the ticker and the map read (`application/remit_outages.load_outage_rows`),
  outages the map cannot place included, so the three surfaces show one number.

## Terms

UMMs are inside information operators are obliged to publish. Each platform sets its own
reuse terms; confirm commercial reuse for the platform you export from (see
[DATA_SOURCE_TERMS.md](../legal/DATA_SOURCE_TERMS.md)).
