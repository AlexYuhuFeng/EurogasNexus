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
GWh/h and TWh. Only GWh/d, kWh/d and mcm/d carry a daily figure
(`unavailable_gwh_d`, `capacity_impact_mcm_d`); the rest stay in their unit (no time or
calorific conversion is assumed).

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
