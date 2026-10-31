# REMIT outages (gas UMMs)

Operators of gas production, storage, LNG and transmission facilities must publish
unavailability as urgent market messages (UMMs) under REMIT Article 4, on an
inside-information platform, in the fields ACER's Manual of Procedures defines. Norwegian
field and processing outages (Troll, Kollsnes, Nyhamna) move NBP and TTF within minutes,
so desks follow these messages closely.

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

Run the import on a schedule (every 5 to 15 minutes during trading hours) from the same
host as the other ingestion scripts until a platform API connector is built.

## Where it shows

- Market → Capacity & Events → **Outages**: live and upcoming events (90 days), soonest first.
- `GET /api/physical/outages?horizon_days=90&asset_type=production` and the SDK's
  `fetch_outages`.

## Terms

UMMs are inside information operators are obliged to publish. Each platform sets its own
reuse terms; confirm commercial reuse for the platform you export from (see
[DATA_SOURCE_TERMS.md](../legal/DATA_SOURCE_TERMS.md)).
