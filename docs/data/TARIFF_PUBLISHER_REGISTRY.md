# Tariff publisher registry (TAR-1, TAR-2)

Who publishes the public tariffs and capacity notices the platform holds, how each is read,
how often, and on what terms. The registry is code (`src/eurogas_nexus/domain/tariffs/publishers.py`);
this page describes it for people, and `tests/domain/test_tariff_book_domain.py` keeps the two in
step (every publisher id below is in the code, and the reverse). `GET /api/tariffs/publishers`
serves it with each publisher's live state; Sources → Infrastructure → Tariff book shows it.

Checked 2026-11-24. No credential, sign-up or login is used for any publisher; nothing behind
a login is read; no figure is invented. A publisher whose figures exist only as a PDF or web
page is recorded here with its page and the access `manual`, and its figures reach the
platform only when a person enters them (four eyes) or imports a notice file.

## How a publisher is read

| Access | Meaning |
| --- | --- |
| `api` | A public machine-readable interface the platform polls on a schedule. |
| `rule` | Computed from a published legal rule, and labelled rule-derived wherever it is shown. |
| `parsed` | The publisher's own document, read by a parser, only once the firm has recorded the publisher's permission (LNG terminal register, CP-11). |
| `manual` | A page or PDF a person reads. A tariff is entered by an administrator with its URL and publication date and reviewed by a second person (`/api/route-cost/tariff-entries`); a capacity notice is imported from a file (`scripts/ops/tariff_book.py import-notices`). Nothing is fetched. |

| Reuse | Meaning |
| --- | --- |
| `permitted` | Terms read; they allow commercial use with citation. |
| `needs_firm_terms` | Terms forbid reuse without written permission: left out of every read until the firm records it. |
| `not_reviewed` | The site could not be reached from the build environment on 2026-11-24 (egress refused), so its terms were not read. Not automated; nothing fetched. |

## Polling and freshness

Tariffs change once a tariff period. NC TAR (Regulation (EU) 2017/460, Art. 29 and 32) has
operators publish reserve prices for the next tariff period 30 days before the annual yearly
capacity auction (first Monday of July), so publication bunches in May to July, with updates
around 1 October and the turn of the year. Since TAR-2 an automated publisher is polled
**hourly** in the windows the operators it carries publish in (1 March to 10 April before the
April tariff and storage years, 1 May to 15 July before the July yearly auction, 15 September
to 10 October before the gas year, 15 November to 10 January before the calendar year) and
**every 6 hours** otherwise (TAR-1: hourly in narrower windows, daily otherwise). The
scheduler passes this to the ENTSOG read as `--entsog-tariffs-max-age-hours` at nine tenths of
the interval (0.9 or 5.4), so the next hourly run reads a point again rather than skipping it.

**Achievable latency.** The ENTSOG source job itself runs hourly, so a reserve price ENTSOG
republishes is held, versioned and on the outbox within about an hour in a window and six
hours outside one, plus the read of the points in scope (one point every 2 s, about 4 minutes
for the 108 points); from the version to the opportunity consumer is milliseconds (TAR1-4).
How long ENTSOG takes to republish what a TSO files on its own site cannot be measured: ENTSOG
states no publication time. A publisher read by hand (`manual`) is as fast as the person who
enters it. Polling faster than hourly would need the whole ENTSOG job run more often, which
was not done.

Freshness alerts (monitoring, category `data_source`, routed to the data operator):

- `tariff_publisher_stale:<publisher>`: an automated publisher not read successfully within
  its stale threshold (3 days for ENTSOG and the CAM calendar);
- `tariff_final_published:<publisher>:<facility>:<tariff year>` (TAR-2, severity `warning`,
  EN and ZH): a final version recorded in the last three days, first or newly final, grouped
  by publisher, facility and tariff year. Its `tariff.changed` event carries `new_final`,
  `tariff_year`, `published_at_utc` and `recorded_at_utc` at priority 1, and its dependency
  keys re-evaluate what used the tariff;
- `tariff_publication_missed:entsog-tp`: operators that hold a yearly reserve price on ENTSOG
  whose next tariff period has none past the NC TAR deadline (30 days before the July yearly
  auction preceding that period). It names the operators.

A capacity window (a yearly or quarterly auction, an LNG slot offer, a secondary window)
opening within three days raises an `info` alert in category `capacity`, routed to scheduling
(owner OPERATIONS, escalation TRADER). Monthly auctions do not alert: they run every month.

## Publishers

| Id | Publisher | Access | Reuse | Publishes | What it really exposes |
| --- | --- | --- | --- | --- | --- |
| `entsog-tp` | ENTSOG Transparency Platform, `tariffsfulls` | `api` (polled; source `src-entsog`) | `permitted` (TP Terms of Use Rev. 3 Art. 5, cite "ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/") | tariffs | Each TSO's reserve price per interconnection point, direction, product and tariff period, in the operator's unit and currency, with a common-unit figure. No publication time, and in practice no indicative/final flag: since TAR-2 such a row takes NC TAR Article 29 read as of the instant valued (final once in force or once the yearly auction that ran at its price has been held, else indicative; it used to be indicative until its period started), and a figure whose common unit disagrees with the operator's is indicative for review. 42 of the 108 points in scope had no tariff (19-11-2026); National Gas figures are refused (unit mismatch) and come through `tso-entries`. |
| `cam-nc-calendar` | CAM network code standard auction calendar (Regulation (EU) 2017/459, Art. 11 to 13) | `rule` | `permitted` (dates computed from the rule; EU legal acts reusable with acknowledgement) | capacity auctions | Yearly auction on the first Monday of July, quarterly on the first Monday of August, November, February and May, monthly on the third Monday for the next month; bidding opens 09:00 Brussels time (08:00 UTC winter, 07:00 UTC summer). Checked against FGSZ's published 2026/27 calendar (fixture `tests/fixtures/tariffs/cam_auction_calendar_2026_27.json`, with URL and retrieval date): every firm yearly, quarterly and monthly date and hour matches. ENTSOG's calendar and the booking platform remain authoritative. |
| `entsog-auction-calendar` | ENTSOG CAM NC auction calendar | `parsed` (fetched daily by the publication watch, `application/publication_watch.py`) | `permitted` (entsog.eu website terms Art. 4.1: download, store and use; Art. 4.2: not made available to another party; checked 2026-11-28) | capacity auctions | The yearly `.xlsx` linked from the CAM NC page, published by January: yearly, quarterly and monthly auctions, firm and interruptible, with the offer-level publication date. Its auctions are recorded as `published` notices and replace the rule-derived ones for the months it covers; a file the parser cannot read is held as "changed, needs a person to confirm" and nothing is guessed. |
| `prisma` | PRISMA capacity platform | `manual` | `needs_firm_terms` | capacity auctions | Auction offers and results need a platform account; none is used. Left out. |
| `tso-entries` | Transmission tariffs entered from operators' own publications | `manual` (four eyes) | `permitted` (a person transcribes a published charge; no automated retrieval) | tariffs | Legs ENTSOG lacks or whose ENTSOG figures are refused (National Gas, GTS, Fluxys Belgium, NaTran, Enagás, Gassco, Swiss transit). A candidate is indicative (`awaiting_review`); a reviewed entry carries the operator's own status. |
| `register-documents` | Tariff register rows loaded from operators' documents | `manual` | `not_reviewed` | tariffs | Rows an administrator loaded from a charging statement (BBL, IUK, National Gas), each citing its document. Versioned only when the row cites an https source. |
| `national-gas` | National Gas Transmission (GB) | `manual` | `not_reviewed` | tariffs | NTS charging statements and IP reserve prices (p/kWh/d), as PDFs. Entered through `tso-entries`. |
| `gts` | Gasunie Transport Services (NL) | `manual` | `not_reviewed` | tariffs | Tariff decisions as PDFs. Balgzand exit, Gate and Eems entry entered through `tso-entries`. |
| `fluxys-belgium` | Fluxys Belgium | `manual` | `needs_firm_terms` (legal notice forbids reproduction without written consent) | tariffs | Transmission tariff lists. Left out until the firm records permission. |
| `natran` | NaTran (FR) | `manual` | `not_reviewed` | tariffs | Transmission tariffs as PDFs. |
| `enagas` | Enagás (ES) | `manual` | `not_reviewed` | tariffs, LNG slots | Transmission tariffs and the LNG slot programme, as pages and PDFs. |
| `fluxys-lng` | Fluxys LNG (Zeebrugge) | `parsed` | `needs_firm_terms` | tariffs, LNG slots | Regasification tariff and price simulator; the parser exists (CP-11) but nothing is read or shown until the firm records Fluxys LNG's permission. A candidate row is indicative; a reviewed one final. |
| `elengy` | Elengy (Montoir, Fos Cavaou, Fos Tonkin) | `parsed` | `needs_firm_terms` | tariffs, LNG slots | Access tariffs and SMART SPOT offers; gated on the firm's permission. |
| `det` | Deutsche Energy Terminal (Brunsbüttel, Wilhelmshaven) | `parsed` | `needs_firm_terms` (no published reuse terms) | tariffs, LNG slots | Auction results; gated on the firm's permission. |
| `gate-terminal` | Gate terminal (Rotterdam) | `manual` | `not_reviewed` | LNG slots, secondary capacity | Exempt terminal: no public price list for a new booking. Slot offers imported as notices. |
| `dunkerque-lng` | Dunkerque LNG | `manual` | `not_reviewed` | LNG slots, secondary capacity | Exempt terminal; slot offers imported as notices. |
| `uniper-storage` | Uniper Energy Storage (DE, AT) | `manual` | `not_reviewed` | tariffs, secondary capacity | Negotiated storage; standard bundles as PDF. Not fetched. |
| `storengy` | Storengy (FR) | `manual` | `not_reviewed` | tariffs, capacity auctions | Regulated storage sold by auction under CRE rules; dates imported as notices. |

## Tariff years and publication cadence (TAR-2)

Each publisher's tariff year and how it publishes indicative and final figures for it, as the
code holds them (`Publisher.tariff_year`, `.cadence`, `.cadence_confirmed`; served by `GET
/api/tariffs/publishers`). Every version records its tariff year (`tariff_versions.tariff_year`,
migration 0088; older versions derive it from their period). A cadence marked **no** was not
confirmed from the publisher's own notices (the build environment could not reach most
operator sites): the period and status on each publication are then what count, and nothing is
assumed from the cadence. Labels: `GY 2026/27` (gas year), `CY 2027` (calendar year), `TY
2027/28 Apr-Mar` (April year).

| Id | Tariff year | Confirmed | Cadence |
| --- | --- | --- | --- |
| `entsog-tp` | per row (the publication's own period) | yes | Each TSO's own tariff period, carried on the row (gas year, calendar year or April year). NC TAR Art. 29: reserve prices for at least the next gas year are due 30 days before the July yearly auction; ENTSOG republishes what each TSO files, with no flag and no publication date. |
| `cam-nc-calendar` | none | yes | Not a tariff: auction dates computed from the CAM network code. |
| `entsog-auction-calendar` | none | yes | Not a tariff: the auction calendar, published by January each year. |
| `prisma` | none | yes | Not a tariff publisher: auction offers and results. |
| `tso-entries` | per row (the publication's own period) | yes | Each entry states the operator's own period, status and publication date. |
| `register-documents` | per row (the publication's own period) | yes | Each row states the period of the document it was transcribed from. |
| `national-gas` | gas year (1 Oct) | yes | Gas year 1 October to 30 September. An indicative notice of the IP reserve prices comes first; the final yearly IP reserve prices are published before the July yearly auction, the final quarterly IP prices and the final NTS exit capacity charges before 1 October (notice titles on nationalgas.com, 2016 to 2026). |
| `gts` | calendar year | **no** (to confirm) | Calendar year (the ACM's yearly tariff decision); the indicative and final dates are not confirmed. |
| `fluxys-belgium` | calendar year | **no** (to confirm) | Calendar year inside the CREG regulatory period; the indicative and final dates are not confirmed. |
| `natran` | April year (1 Apr) | **no** (to confirm) | Tariff year from 1 April (CRE's yearly update, as ENTSOG files NaTran's April-March period); the publication dates are not confirmed. |
| `enagas` | gas year (1 Oct) | **no** (to confirm) | Gas year 1 October (CNMC's yearly tolls); the indicative and final dates are not confirmed. |
| `fluxys-lng` | calendar year | **no** (to confirm) | Calendar year; the indicative and final dates are not confirmed. |
| `elengy` | April year (1 Apr) | **no** (to confirm) | Tariff year from 1 April (CRE's yearly update of the regulated terminal tariff); the publication dates are not confirmed. |
| `det` | none | **no** (to confirm) | Slots are sold by auction; the price is each auction's result, with no tariff year. |
| `gate-terminal` | none | **no** (to confirm) | Exempt terminal: no public tariff year; slots are priced per offer. |
| `dunkerque-lng` | none | **no** (to confirm) | Exempt terminal: no public tariff year; slots are priced per offer. |
| `uniper-storage` | unknown | **no** (to confirm) | Not confirmed (storage years commonly run from 1 April); the period on each bundle is used. |
| `storengy` | April year (1 Apr) | **no** (to confirm) | Storage year from 1 April, sold by auction under CRE rules; the publication dates are not confirmed. |

**Status as of an instant.** A valuation as of T takes the latest version held at T for the
tariff year of each gas day: final if a final was held then, else indicative, flagged. A row
whose publisher states no status (ENTSOG in practice) takes NC TAR Article 29 at T: final once
its period is in force, or once the yearly auction that ran at its reserve price has been held
(the period starts by the start of the gas year that auction sold), otherwise indicative. The
rule is re-applied on every read, so the same row reads indicative in June and final after the
July auction. A period across two tariff years is split, each gas day at its own year's tariff.
Contracted capacity the firm holds always comes first ([ADR Decision 38](../architecture/ARCHITECTURE_DECISION_RECORD.md)).

## Versions, indicative and final

Every register row becomes a version in `tariff_versions` (migration 0083, ADR Decision 34)
with publisher, facility, product, unit, currency, period, status and its basis, publication
and retrieval times, source URL and content hash. A changed figure or status is a new version;
the older one is kept and stamped superseded, so `GET /api/tariffs?as_of=` answers what was
held at an instant and `history=true` lists every version. A change from indicative to final
is its own kind (`status_change`, `INDICATIVE->FINAL`) and publishes a `tariff.changed`
event at a higher priority; it is never silent. Valuations name the version and basis of the
tariff they priced (`tariff_version`, `tariff_status_basis` in the snapshot input's detail) and
keep labelling an indicative tariff "indicative". Since TAR-2 `GET /api/tariffs/years?facility=`
shows each tariff year's indicative and final versions side by side, with their publication
dates (or that none is stated: the record time is shown, never an invented date) and which one
a valuation as of the instant asked uses.

## Published LNG terminal reference (cargo study)

`src/eurogas_nexus/reference_data/lng_terminal_published_tariffs.json`
(`domain/lng/published_tariffs.py`) holds the published regas and entry figures the Research
cargo study prices a terminal with when the firm holds neither its own terms nor a reviewed
register row. One row per figure, transcribed by a person, each with its URL, the publisher's
status (FINAL or INDICATIVE), period, publication date, the date read (26-11-2026) and a terms
note. Nothing is fetched at run time and nothing is parsed from a gated operator's site: the
figures come from the regulator's decision where there is one.

| Terminal | Hub | Figures held | Source and terms |
| --- | --- | --- | --- |
| Montoir, Fos Cavaou, Fos Tonkin (Elengy) | PEG | TNA per berthing, TQD spot and base, TVE, gas in kind (TN); ATTM7, 1 Apr 2025 to 31 Mar 2027, FINAL | CRE deliberation 2025-41 of 6 Feb 2025: public sector information, reusable with citation (CRPA L321-1) |
| Wilhelmshaven 1 and 2, Brunsbüttel (DET) | THE | Terminal fee (auction start price), gas in kind by season, FSRU CO2 factor; price sheet 2026 (carried forward, so INDICATIVE, until the 2027 sheet is approved) | BNetzA decisions BK9-25/101, /102, /104, Annex III, as published on DET's site: an official work (s. 5 UrhG); DET states no reuse terms |
| Eemshaven (EET) | TTF | Tariff cap from 1 Sep 2027 (2024 prices), INDICATIVE; nothing for an earlier month | ACM decision of 17 Jul 2025 |
| Gate (Rotterdam) | TTF | Last capacity sale price per bcm/year, INDICATIVE | Gate terminal's own tariff page (exempt terminal) |
| Isle of Grain, South Hook, Dragon | NBP | NTS entry capacity and commodity, gas year 2026/27, FINAL; no regas price (contracted or exempt) | National Gas, Notice of Transportation Charges (Oct 2026) |
| Dunkerque LNG | PEG | NaTran PITTM entry, 1 Apr 2026 to 31 Mar 2027, INDICATIVE (to check against CRE); no regas price (exempt) | NaTran's published summary |
| Zeebrugge (Fluxys LNG) | ZTP | None: the legal notice forbids reproduction; the CP-11 parser reads it once the firm records permission | |
| Mukran (Deutsche Ostsee) | THE | None: negotiated access | |

A firm's own terms for a terminal (matched by id or alias, `gate` for `gate-terminal`) stand for
the published row, which then fills only what they lack. A figure is used for an arrival month
when its period covers the month; otherwise the latest ended period is carried forward (and
reads INDICATIVE); a period starting later never prices an earlier month. Entry tariffs not
held (GTS, THE/OGE, Fluxys Belgium, NaTran at Montoir and Fos) are left out of that terminal's
netback and the result says so for each terminal. Hub forwards (ICE Endex, EEX) and the EUA
forward need a licence: on a desk without one, the hub price is the demo's simulated curve and
EUA a labelled desk standard (70 EUR/t).

## Capacity notices

`capacity_notices` holds the windows a scheduler or LNG desk plans around. The CAM standard
auctions are refreshed each hour from the rule (basis `rule_derived`, about 400 days ahead).
Notices a publisher published are imported from a CSV or JSON file
(`scripts/ops/tariff_book.py import-notices FILE --publisher ID --commit`), with the columns
`notice_id, kind (auction | lng_slot | secondary_capacity), product, title, opens_at_utc,
closes_at_utc, offers_from, offers_to, facility_kind, facility_id, facility_name, quantity,
quantity_unit, state (open | cancelled), source_url, published_at_utc`; each row needs the
publisher's own https page, the publisher must publish that kind of notice, and a publisher
whose terms need the firm's permission is refused. One refused row refuses the file.

## Adding a publisher

Add an entry to `PUBLISHERS` with its page, access, reuse finding and the date checked, and a
row here. A publisher becomes `api` only when its terms have been read and allow commercial
reuse and a public interface exists; then give it a `Poll`, a source in the scheduler and a
parser with recorded fixtures (source URL and retrieval date beside each).
