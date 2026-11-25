"""Who publishes public tariffs and capacity notices, where, how often, and on what terms.

One entry per publisher. ``access`` says how the platform gets its figures:

``api``      a machine-readable public interface the platform polls (ENTSOG TP);
``rule``     computed from a published legal rule (the CAM auction calendar);
``parsed``   the publisher's own document, read by a parser, only once the firm has recorded
             the publisher's permission (the LNG terminal tariff register, CP-11);
``manual``   a page or PDF a person reads; the figure is entered by an administrator and
             reviewed by a second person (``tso_tariff_entries``), or the notice is imported
             as a file (``import_capacity_notices``). Nothing is fetched automatically.

``reuse`` records the terms finding: ``permitted`` (terms read and allow commercial use with
citation), ``needs_firm_terms`` (terms forbid reuse without written permission: left out until
the firm records it), ``not_reviewed`` (the terms could not be read from the build environment;
not automated, nothing fetched). No credential, sign-up or login is used for any entry.

``poll`` is the cadence for automated publishers, publication-aware: tariffs change once a
tariff period, and the NC TAR deadline (30 days before the July yearly auction) concentrates
publication in May to July, so the poll is hourly from 1 May to 15 July and around each
period start (1 to 10 October and 15 December to 10 January) and daily otherwise. ``stale``
is how long without a successful read before the publisher is reported stale (M6 alert).

The registry is described for people in ``docs/data/TARIFF_PUBLISHER_REGISTRY.md``; a test
holds the two in step.

费率发布方登记：数据获取方式（接口、规则、解析、人工）、更新频率与再利用条款结论。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

API = "api"
RULE = "rule"
PARSED = "parsed"
MANUAL = "manual"
ACCESS = (API, RULE, PARSED, MANUAL)

PERMITTED = "permitted"
NEEDS_FIRM_TERMS = "needs_firm_terms"
NOT_REVIEWED = "not_reviewed"
REUSE = (PERMITTED, NEEDS_FIRM_TERMS, NOT_REVIEWED)

KINDS = ("platform", "regulation", "tso", "lng_terminal", "storage", "booking_platform", "desk")

#: (month, day) ranges, inclusive, in which an automated publisher is polled hourly.
PUBLICATION_SEASONS: tuple[tuple[tuple[int, int], tuple[int, int]], ...] = (
    ((5, 1), (7, 15)),
    ((10, 1), (10, 10)),
    ((12, 15), (12, 31)),
    ((1, 1), (1, 10)),
)


@dataclass(frozen=True)
class Poll:
    """How often an automated publisher is read, in minutes."""

    base_minutes: int
    season_minutes: int
    stale_after_minutes: int

    def interval_minutes(self, on: date | datetime) -> int:
        day = on.date() if isinstance(on, datetime) else on
        key = (day.month, day.day)
        if any(start <= key <= end for start, end in PUBLICATION_SEASONS):
            return self.season_minutes
        return self.base_minutes


@dataclass(frozen=True)
class Publisher:
    """One publisher of tariffs or capacity notices."""

    publisher_id: str
    name: str
    kind: str
    countries: tuple[str, ...]
    page_url: str
    access: str
    reuse: str
    publishes: tuple[str, ...]  # tariffs, capacity_auctions, lng_slots, secondary_capacity
    terms: str
    #: The source family entitlement and metering apply to (public families need no grant).
    source_family: str
    licensed: bool = False
    #: The scheduled data-ops source that reads it, if any.
    source_id: str | None = None
    api_url: str | None = None
    poll: Poll | None = None
    notes: str = ""
    checked_on: str = "2026-11-24"
    facilities: tuple[str, ...] = field(default_factory=tuple)

    @property
    def automated(self) -> bool:
        return self.access in {API, RULE} or (self.access == PARSED and self.reuse == PERMITTED)

    def to_json(self) -> dict:
        return {
            "publisher_id": self.publisher_id,
            "name": self.name,
            "kind": self.kind,
            "countries": list(self.countries),
            "page_url": self.page_url,
            "api_url": self.api_url,
            "access": self.access,
            "automated": self.automated,
            "reuse": self.reuse,
            "publishes": list(self.publishes),
            "terms": self.terms,
            "source_family": self.source_family,
            "source_id": self.source_id,
            "poll_minutes": None if self.poll is None else self.poll.base_minutes,
            "season_poll_minutes": None if self.poll is None else self.poll.season_minutes,
            "stale_after_minutes": None if self.poll is None else self.poll.stale_after_minutes,
            "notes": self.notes,
            "checked_on": self.checked_on,
        }


_NOT_REACHABLE = (
    "Its site could not be reached from the build environment on 2026-11-24 (egress refused), "
    "so its terms were not reviewed and nothing is fetched."
)

PUBLISHERS: tuple[Publisher, ...] = (
    Publisher(
        publisher_id="entsog-tp",
        name="ENTSOG Transparency Platform (tariffsfulls)",
        kind="platform",
        countries=("EU",),
        page_url="https://transparency.entsog.eu/",
        api_url="https://transparency.entsog.eu/api/v1/tariffsfulls",
        access=API,
        reuse=PERMITTED,
        publishes=("tariffs",),
        terms=(
            "ENTSOG TP Terms of Use Rev. 3 Art. 5: download, store and use with the citation "
            "'ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/' (docs/legal/DATA_SOURCE_"
            "TERMS.md)."
        ),
        source_family="ENTSOG",
        source_id="src-entsog",
        poll=Poll(base_minutes=24 * 60, season_minutes=60, stale_after_minutes=3 * 24 * 60),
        notes=(
            "The cross-TSO base: each TSO's reserve price per point, direction, product and "
            "tariff period, in its own unit and currency. Read one point per query, 2 s apart. "
            "No tariff at 42 of the 108 points in scope (19-11-2026); National Gas figures "
            "refused (unit mismatch). ENTSOG states no publication time and, in practice, no "
            "status: a period not yet started is indicative until it starts."
        ),
    ),
    Publisher(
        publisher_id="cam-nc-calendar",
        name="CAM network code standard auction calendar (Regulation (EU) 2017/459)",
        kind="regulation",
        countries=("EU",),
        page_url="https://eur-lex.europa.eu/eli/reg/2017/459/oj",
        access=RULE,
        reuse=PERMITTED,
        publishes=("capacity_auctions",),
        terms=(
            "Dates computed from the regulation's own rule; no text is reproduced. EU legal acts "
            "may be reused, commercially included, with acknowledgement (Commission Decision "
            "2011/833/EU). EUR-Lex refused the build environment on 2026-11-24; Articles 11 to "
            "13 were read on legislation.gov.uk's copy of the regulation."
        ),
        source_family="EU_REGULATION",
        poll=Poll(base_minutes=24 * 60, season_minutes=24 * 60, stale_after_minutes=3 * 24 * 60),
        notes=(
            "Yearly (first Monday of July), quarterly (first Monday of August, November, "
            "February, May) and monthly (third Monday) auctions computed from Art. 11 to 13; "
            "labelled rule-derived. Checked against FGSZ's published 2026/27 calendar."
        ),
    ),
    Publisher(
        publisher_id="entsog-auction-calendar",
        name="ENTSOG CAM NC auction calendar (yearly PDF)",
        kind="platform",
        countries=("EU",),
        page_url="https://www.entsog.eu/",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("capacity_auctions",),
        terms=(
            "entsog.eu website terms Art. 4.2 forbid redistributing website content without "
            "consent (the Transparency Platform has its own terms); the calendar is a PDF on "
            "the website, so it is read by a person, not stored."
        ),
        source_family="ENTSOG",
        notes=(
            "Authoritative over the rule-derived dates; published by January each year. A "
            "date it moves is imported as a notice from the desk's own file."
        ),
    ),
    Publisher(
        publisher_id="prisma",
        name="PRISMA capacity platform (auction offers and results)",
        kind="booking_platform",
        countries=("DE", "NL", "BE", "FR", "AT", "IT", "DK", "PL", "CZ"),
        page_url="https://www.prisma-capacity.eu/",
        access=MANUAL,
        reuse=NEEDS_FIRM_TERMS,
        publishes=("capacity_auctions",),
        terms=(
            "No published reuse terms for platform data; written confirmation needed "
            "(docs/legal/DATA_SOURCE_TERMS.md, REMIT row). Left out until the firm records it."
        ),
        source_family="PRISMA",
        notes="Offers and results need a platform account; none is used.",
    ),
    Publisher(
        publisher_id="tso-entries",
        name="Transmission tariffs entered from operators' own publications",
        kind="desk",
        countries=("GB", "NL", "BE", "FR", "ES", "NO", "CH"),
        # Each entry cites its own operator document; there is no single page.
        page_url="",
        access=MANUAL,
        reuse=PERMITTED,
        publishes=("tariffs",),
        terms=(
            "A person reads the operator's public document and enters the charge with its URL, "
            "publication date and place; a second person reviews it (four eyes). No automated "
            "retrieval, so the operator's site terms are not engaged."
        ),
        source_family="operator-input",
        notes=(
            "Legs ENTSOG lacks or whose ENTSOG figures are refused: National Gas, GTS, Fluxys "
            "Belgium, NaTran, Enagás, Gassco, Swiss transit. A candidate is indicative; a "
            "reviewed entry carries the operator's own status."
        ),
    ),
    Publisher(
        publisher_id="register-documents",
        name="Tariff register rows transcribed from operators' published documents",
        kind="desk",
        countries=("NL", "GB", "BE"),
        page_url="",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("tariffs",),
        terms=(
            "Rows an administrator loaded into the tariff register from an operator's document "
            "(BBL, IUK, National Gas charging statements); each row cites its document and URL. "
            "Kept as loaded; a row without an https source is not versioned."
        ),
        source_family="operator-input",
    ),
    Publisher(
        publisher_id="national-gas",
        name="National Gas Transmission (GB NTS charging statements, IP reserve prices)",
        kind="tso",
        countries=("GB",),
        page_url="https://www.nationalgas.com/",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("tariffs",),
        terms=_NOT_REACHABLE,
        source_family="NATIONAL_GAS",
        notes="Published per day of capacity (p/kWh/d); entered through tso-entries.",
    ),
    Publisher(
        publisher_id="gts",
        name="Gasunie Transport Services (NL tariff decisions)",
        kind="tso",
        countries=("NL",),
        page_url="https://www.gasunietransportservices.nl/",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("tariffs",),
        terms=_NOT_REACHABLE,
        source_family="operator-input",
        notes="Balgzand exit to BBL, Gate and Eems LNG entry: entered through tso-entries.",
    ),
    Publisher(
        publisher_id="fluxys-belgium",
        name="Fluxys Belgium (transmission tariff lists)",
        kind="tso",
        countries=("BE",),
        page_url="https://www.fluxys.com/",
        access=MANUAL,
        reuse=NEEDS_FIRM_TERMS,
        publishes=("tariffs",),
        terms=(
            "Fluxys legal notice: no reproduction or download of the site's content without "
            "Fluxys's prior written consent (checked 2026-11-18)."
        ),
        source_family="operator-input",
        notes="Zeebrugge LNG and ZPT entry: entered with the firm's permission only.",
    ),
    Publisher(
        publisher_id="natran",
        name="NaTran (FR transmission tariffs)",
        kind="tso",
        countries=("FR",),
        page_url="https://www.natran.fr/",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("tariffs",),
        terms=_NOT_REACHABLE,
        source_family="operator-input",
    ),
    Publisher(
        publisher_id="enagas",
        name="Enagás (ES transmission tariffs and LNG slot programme)",
        kind="tso",
        countries=("ES",),
        page_url="https://www.enagas.es/",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("tariffs", "lng_slots"),
        terms=_NOT_REACHABLE,
        source_family="operator-input",
    ),
    Publisher(
        publisher_id="fluxys-lng",
        name="Fluxys LNG (Zeebrugge regasification tariff and price simulator)",
        kind="lng_terminal",
        countries=("BE",),
        page_url=(
            "https://www.fluxys.com/en/natural-gas-and-biomethane/empowering-you/tariffs/"
            "tariff_fluxyslng-lng"
        ),
        access=PARSED,
        reuse=NEEDS_FIRM_TERMS,
        publishes=("tariffs", "lng_slots"),
        terms=(
            "Fluxys legal notice forbids reproduction or download without prior written "
            "consent (checked 2026-11-18). Parser exists; nothing is read until the firm "
            "records Fluxys LNG's permission (LNG terminal register, CP-11)."
        ),
        source_family="operator-input",
        facilities=("zeebrugge",),
    ),
    Publisher(
        publisher_id="elengy",
        name="Elengy (Montoir, Fos Cavaou, Fos Tonkin access tariffs, SMART SPOT)",
        kind="lng_terminal",
        countries=("FR",),
        page_url="https://www.elengy.com/en/our-services/pricing-conditions/our-access-tariffs",
        access=PARSED,
        reuse=NEEDS_FIRM_TERMS,
        publishes=("tariffs", "lng_slots"),
        terms=(
            "Elengy legal notice: reproduction without Elengy's express permission is "
            "forbidden (checked 2026-11-18). Parser exists; gated on the firm's permission."
        ),
        source_family="operator-input",
        facilities=("montoir", "fos-cavaou", "fos-tonkin"),
    ),
    Publisher(
        publisher_id="det",
        name="Deutsche Energy Terminal (Brunsbüttel, Wilhelmshaven auction results)",
        kind="lng_terminal",
        countries=("DE",),
        page_url="https://energy-terminal.de/en/news",
        access=PARSED,
        reuse=NEEDS_FIRM_TERMS,
        publishes=("tariffs", "lng_slots"),
        terms=(
            "The imprint publishes no reuse terms; written confirmation needed (checked "
            "2026-11-18). Parser exists; gated on the firm's permission."
        ),
        source_family="operator-input",
        facilities=("brunsbuttel", "wilhelmshaven"),
    ),
    Publisher(
        publisher_id="gate-terminal",
        name="Gate terminal (Rotterdam; exempt, slots offered by the operator)",
        kind="lng_terminal",
        countries=("NL",),
        page_url="https://www.gate.nl/",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("lng_slots", "secondary_capacity"),
        terms=_NOT_REACHABLE,
        source_family="operator-input",
        notes="Exempt terminal: no public price list for a new booking; slot offers imported.",
    ),
    Publisher(
        publisher_id="dunkerque-lng",
        name="Dunkerque LNG (exempt; slots offered by the operator)",
        kind="lng_terminal",
        countries=("FR",),
        page_url="https://www.dunkerquelng.com/",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("lng_slots", "secondary_capacity"),
        terms=_NOT_REACHABLE,
        source_family="operator-input",
    ),
    Publisher(
        publisher_id="uniper-storage",
        name="Uniper Energy Storage (DE and AT storage tariffs)",
        kind="storage",
        countries=("DE", "AT"),
        page_url="https://www.uniper.energy/",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("tariffs", "secondary_capacity"),
        terms=_NOT_REACHABLE,
        source_family="operator-input",
        notes="Negotiated storage: published standard bundles as PDF; not fetched.",
    ),
    Publisher(
        publisher_id="storengy",
        name="Storengy (FR regulated storage tariffs)",
        kind="storage",
        countries=("FR",),
        page_url="https://www.storengy.com/",
        access=MANUAL,
        reuse=NOT_REVIEWED,
        publishes=("tariffs", "capacity_auctions"),
        terms=_NOT_REACHABLE,
        source_family="operator-input",
        notes="French storage is sold by auction under CRE rules; dates imported as notices.",
    ),
)

_BY_ID = {item.publisher_id: item for item in PUBLISHERS}
if len(_BY_ID) != len(PUBLISHERS):  # pragma: no cover - guarded by a test too
    raise RuntimeError("two publishers share an id")


def publisher(publisher_id: str) -> Publisher | None:
    """One publisher by id, or ``None``."""

    return _BY_ID.get(publisher_id)


def lng_publisher_for(terminal_id: str) -> str | None:
    """The publisher of a terminal id (``zeebrugge:term`` -> ``fluxys-lng``)."""

    prefix = terminal_id.split(":", 1)[0].lower()
    for item in PUBLISHERS:
        if item.kind == "lng_terminal" and prefix in item.facilities:
            return item.publisher_id
    return None


__all__ = [
    "ACCESS",
    "API",
    "KINDS",
    "MANUAL",
    "NEEDS_FIRM_TERMS",
    "NOT_REVIEWED",
    "PARSED",
    "PERMITTED",
    "PUBLICATION_SEASONS",
    "PUBLISHERS",
    "REUSE",
    "RULE",
    "Poll",
    "Publisher",
    "lng_publisher_for",
    "publisher",
]
