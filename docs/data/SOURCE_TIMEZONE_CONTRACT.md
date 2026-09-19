# Source Timezone Contract

Status: **current** (M1-P0, delivered 2026-09-19). Implementation:
`src/eurogas_nexus/domain/ingestion/source_timezone.py`. Tests:
`tests/ingestion/test_source_timezone_contract.py`.

## 1. The defect this closes

Commercial readiness item **M1-P0**: *ENTSOG timezone normalization unproven; naive timestamps
treated as UTC → ENTSOG flow/capacity periods can be shifted or mis-labelled.*

The parser behind the public-source normalizers did this:

```python
if value.tzinfo is None:
    return value.replace(tzinfo=UTC)     # a bare 06:00 becomes 06:00Z
```

ENTSOG publishes gas-day periods on the Central European clock, where the gas day starts at
**06:00 CET / 06:00 CEST** — the convention this repository's frozen calendar
`EU-CAM-UTC-2025` encodes as **05:00Z / 04:00Z** (`docs/product/GAS_DAY_CALENDAR_COMPATIBILITY.md`,
`src/eurogas_nexus/domain/market/gas_day.py`). Reading a bare `06:00` as UTC therefore placed every
flow and capacity period **one hour early in winter and two hours early in summer**, and a period
that disagrees with the gas day it belongs to is a wrong answer, not a formatting detail.

## 2. The rule, in one place

Each source declares its timestamp semantics once, in `SOURCE_TIMEZONE_CONTRACTS`:

| Source | Datasets | Declared zone | Payload key that may override | Bare value |
|---|---|---|---|---|
| `ENTSOG` | `operationaldatas` | `Europe/Berlin` (the platform's CET/CEST) | `timeZone` (`CET`, `CEST`, `UTC`, `Z`) | read on the declared zone |
| `ENTSOG` | `operatorpointdirections` | `Europe/Berlin` | `timeZone` | read on the declared zone |
| `GIE` | `agsi`, `alsi` | **not proven** | — | **refused** |
| anything else | — | not proven | — | **refused** |

The parser obeys the declaration:

1. **An explicit offset is trusted.** `2026-01-15T06:00:00+01:00` is 05:00Z, and `Z` is UTC,
   whatever the declaration says. A provider's own statement is never reinterpreted.
2. **A bare value is read in the declared zone**, or in the zone the payload itself declares and the
   contract supports (`{"timeZone": "CET"}`). Winter `06:00` → 05:00Z; summer `06:00` → 04:00Z.
3. **A zone that cannot be proven is refused.** A payload that declares a zone the contract does not
   support (`WET`, `America/New_York`, a typo) raises `unsupported_source_timezone` **for the whole
   payload**, because every instant in it would otherwise be mislabelled. A bare instant under a
   contract with no declared zone raises `unprovable_source_timezone`.
4. **An unreadable value is a row-level skip**, not a refusal: `parse_source_instant` returns `None`
   and the row is dropped, as before. Only an *unplaceable* instant stops the ingest.

Why WET is refused rather than treated as UTC: its winter offset happens to be zero and its summer
offset is `+01:00`, so "WET is close enough to UTC" is exactly the reasoning that produced this
defect.

## 3. What is asserted

`tests/ingestion/test_source_timezone_contract.py` (11 cases) holds each fixture to an exact UTC
instant:

- **CET (winter)** `2026-01-15T06:00:00` → `2026-01-15T05:00:00Z`, and the test asserts it is *not*
  `06:00Z` — the value the old parser produced;
- **CEST (summer)** `2026-05-29T06:00:00` → `2026-05-29T04:00:00Z`;
- **offset-bearing** `+01:00`, `+02:00`, `+00:00` (WET stated explicitly) and `Z` → trusted;
- **DST boundaries** for 2026 (29 March and 25 October): the switch days resolve to 04:00Z and
  05:00Z respectively; a local time inside the spring-forward gap resolves forward
  (`02:30` → `01:30Z`) and an ambiguous autumn time resolves to the first offset
  (`02:30` → `00:30Z`), both documented rather than silently dropped;
- **unsupported zone** `WET` (and other unknown tokens) → `unsupported_source_timezone` for both the
  flow and the capacity normalizer;
- **unprovable zone** → `unprovable_source_timezone`, including the live GIE case below;
- **agreement** — a flow row and a capacity row covering one gas day resolve to the same UTC period.

`tests/ingestion/test_public_source_ingestion.py` keeps the offset fixture and adds the naive one, so
the provider-shaped payloads and the contract cases are held together.

## 4. What changed in behaviour, and what did not

- Naive ENTSOG periods shift by the offset the platform's clock implies: 06:00 → 05:00Z (winter) or
  04:00Z (summer). **No historical rows are rewritten** — the same policy the gas-day correction
  followed (M0-P0): a corrected rule applies to new ingestion and leaves persisted evidence intact.
- Offset-bearing payloads are unchanged, which is what the live feeds appear to send today.
- A GIE payload whose `updatedAt` has no offset is now **refused** instead of being read as UTC. The
  gas-day dates in the same payload are unaffected: they are dates, and they go through the CAM
  calendar. The old test fixture carried a bare `updatedAt`, which no real AGSI/ALSI payload does;
  the fixture now carries `+02:00` and the refusal case has its own test.
- The **GIE zone is deliberately left unproven** for the freshness stamp. Declaring one without
  evidence would repeat the original mistake with a different zone; refusing it is the honest state
  until GIE's own documentation is cited here.

## 5. Integration-time check (recorded, not claimed)

This module states the zone from **repository evidence** — the frozen gas-day calendar and the
existing provider-shaped fixtures — not from a machine-read copy of the provider's manual. One check
belongs to integration, with live access:

- confirm the ENTSOG Transparency Platform's default response zone for `operationaldatas` (the
  request currently sends no `timeZone` parameter, so the platform default applies), and either cite
  the manual here or pin the request with `timeZone=UTC` and record the offset-bearing response as
  the expected shape;
- confirm whether GIE AGSI/ALSI `updatedAt` always carries an offset in production; if it does, the
  refusal is an unreachable guard rather than an operational constraint.

The safety property does not depend on those confirmations: an unsupported declared zone and an
unprovable bare instant both refuse the payload loudly instead of shifting its periods. What the
confirmations change is whether the *default* reading of a bare ENTSOG value is right — and the
fail-closed path makes that a visible failure rather than a silent hour.

## 6. Related records

- `docs/product/GAS_DAY_CALENDAR_COMPATIBILITY.md` — the CAM gas-day calendars and their versions.
- `docs/product/COMMERCIAL_READINESS_BACKLOG.md` — M0-P0 (calendar, complete) and M1-P0 (this).
- `docs/product/PROFESSIONAL_AUDIENCE_REVIEW.md` — why this ranks first among next steps: every
  audience's trust in a period rests on it.
