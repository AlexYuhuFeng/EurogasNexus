# Tariff publisher registry (TAR-1)

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
around 1 October and the turn of the year. An automated publisher is polled **hourly** from
1 May to 15 July, 1 to 10 October and 15 December to 10 January, and **daily** otherwise; the
scheduler passes this to the ENTSOG read as `--entsog-tariffs-max-age-hours` (1 or 24).

Freshness alerts (monitoring, category `data_source`, routed to the data operator):

- `tariff_publisher_stale:<publisher>`: an automated publisher not read successfully within
  its stale threshold (3 days for ENTSOG and the CAM calendar);
- `tariff_publication_missed:entsog-tp`: operators that hold a yearly reserve price on ENTSOG
  whose next tariff period has none past the NC TAR deadline (30 days before the July yearly
  auction preceding that period). It names the operators.

A capacity window (a yearly or quarterly auction, an LNG slot offer, a secondary window)
opening within three days raises an `info` alert in category `capacity`, routed to scheduling
(owner OPERATIONS, escalation TRADER). Monthly auctions do not alert: they run every month.

## Publishers

| Id | Publisher | Access | Reuse | Publishes | What it really exposes |
| --- | --- | --- | --- | --- | --- |
| `entsog-tp` | ENTSOG Transparency Platform, `tariffsfulls` | `api` (polled; source `src-entsog`) | `permitted` (TP Terms of Use Rev. 3 Art. 5, cite "ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/") | tariffs | Each TSO's reserve price per interconnection point, direction, product and tariff period, in the operator's unit and currency, with a common-unit figure. No publication time, and in practice no indicative/final flag: a period not yet started is stored indicative until it starts, and a figure whose common unit disagrees with the operator's is indicative for review. 42 of the 108 points in scope had no tariff (19-11-2026); National Gas figures are refused (unit mismatch) and come through `tso-entries`. |
| `cam-nc-calendar` | CAM network code standard auction calendar (Regulation (EU) 2017/459, Art. 11 to 13) | `rule` | `permitted` (dates computed from the rule; EU legal acts reusable with acknowledgement) | capacity auctions | Yearly auction on the first Monday of July, quarterly on the first Monday of August, November, February and May, monthly on the third Monday for the next month; bidding opens 09:00 Brussels time (08:00 UTC winter, 07:00 UTC summer). Checked against FGSZ's published 2026/27 calendar (fixture `tests/fixtures/tariffs/cam_auction_calendar_2026_27.json`, with URL and retrieval date): every firm yearly, quarterly and monthly date and hour matches. ENTSOG's calendar and the booking platform remain authoritative. |
| `entsog-auction-calendar` | ENTSOG CAM NC auction calendar | `manual` | `not_reviewed` (entsog.eu website terms forbid redistributing site content without consent) | capacity auctions | A yearly PDF on entsog.eu, published by January. A date it moves is imported as a notice by the desk. |
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

## Versions, indicative and final

Every register row becomes a version in `tariff_versions` (migration 0083, ADR Decision 34)
with publisher, facility, product, unit, currency, period, status and its basis, publication
and retrieval times, source URL and content hash. A changed figure or status is a new version;
the older one is kept and stamped superseded, so `GET /api/tariffs?as_of=` answers what was
held at an instant and `history=true` lists every version. A change from indicative to final
is its own kind (`status_change`, `INDICATIVE->FINAL`) and publishes a `tariff.changed`
event at a higher priority; it is never silent. Valuations name the version and basis of the
tariff they priced (`tariff_version`, `tariff_status_basis` in the snapshot input's detail) and
keep labelling an indicative tariff "indicative".

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
