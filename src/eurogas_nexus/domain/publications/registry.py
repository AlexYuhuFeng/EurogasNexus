"""The watched publications: everything public the desk needs, where it is, and whether the
product may fetch and keep it.

Owner's principle (2026-11-28, extending AGENTS.md rule 19): the desk is two people and cannot
watch websites. What they need and is publicly published, the product gets from where it is
published, when it is published, and tells them; nobody types it in. Bounded by rule 18:
publicly viewable is not the same as free to collect.

One :class:`WatchedPublication` per publication. ``verdict`` is the terms finding recorded in
``docs/legal/DATA_SOURCE_TERMS.md`` ("Watched publications, checked 2026-11-28"):

``fetch``            the terms allow storing it for the firm's internal use: the product fetches
                     it at ``interval_minutes``, detects a change by the SHA-256 of the
                     document, parses it and keeps the previous record;
``hand_maintained``  the terms forbid storing it: the desk keeps a file (``hand_file``) and the
                     product reminds them, with the link, to check it against the publisher's
                     page by a date;
``link_only``        viewable, not storable (or the terms could not be read): the product shows
                     the link and fetches nothing.

A publication is fetched only when its verdict is ``fetch`` **and** it names its entry in the
legal register (``terms_section``): no entry, no fetch (:func:`fetch_refusal`). Nobody accepts
terms, registers or signs up anywhere on the owner's behalf; ``delivery`` says where an
announcement reaches the desk (``web``, ``platform`` behind a booking-platform account, or
``email`` to subscribers only), and nothing here reads a mailbox.

Import-safe: no database, web or network import.

监控的公开发布物登记：发布方、确切位置、条款结论（可获取 / 人工维护并提醒核对 / 仅链接）、
检查间隔与解析器。没有法律登记条目就不获取。
"""

from __future__ import annotations

from dataclasses import dataclass, field

FETCH = "fetch"
HAND_MAINTAINED = "hand_maintained"
LINK_ONLY = "link_only"
VERDICTS = (FETCH, HAND_MAINTAINED, LINK_ONLY)

KINDS = (
    "trading_calendar",
    "capacity_auctions",
    "lng_slots",
    "storage_auctions",
    "reference_prices",
)
DELIVERY = ("web", "platform", "email")
HUBS = ("NBP", "TTF", "ZTP", "THE", "PVB")

#: The legal register's section every entry below is recorded in.
TERMS_SECTION = "Watched publications, checked 2026-11-28"
CHECKED_ON = "2026-11-28"
#: Shortest interval any publication is checked at (an hour): calendars change rarely and
#: announcements hourly at most, unless a publisher states a limit of its own.
MIN_INTERVAL_MINUTES = 60


@dataclass(frozen=True)
class WatchedPublication:
    """One publication the desk relies on, with the terms it is (or is not) read under."""

    publication_id: str
    title: str
    publisher: str
    kind: str
    hubs: tuple[str, ...]
    #: The exact public location: the page that carries or links the document.
    url: str
    #: What is published there: ``xlsx``, ``pdf``, ``html``, ``xml api``, ``platform``.
    document_format: str
    verdict: str
    #: The legal register's section holding the finding; empty means no entry (never fetched).
    terms_section: str
    terms_quote: str
    terms_url: str
    #: Whether the page answered from the build environment on :data:`CHECKED_ON`.
    verified_live: bool
    interval_minutes: int | None = None
    parser: str | None = None
    delivery: str = "web"
    attribution: str = ""
    #: The tariff-book publisher its records land under (``domain/tariffs/publishers``).
    tariff_publisher_id: str | None = None
    #: For a hand-maintained calendar: the venue code in ``reference_data/desk/
    #: trading_calendars.toml`` the desk keeps.
    hand_venue: str | None = None
    notes: str = ""
    terms_checked_on: str = CHECKED_ON
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict:
        return {
            "publication_id": self.publication_id,
            "title": self.title,
            "publisher": self.publisher,
            "kind": self.kind,
            "hubs": list(self.hubs),
            "url": self.url,
            "document_format": self.document_format,
            "verdict": self.verdict,
            "terms_section": self.terms_section,
            "terms_quote": self.terms_quote,
            "terms_url": self.terms_url,
            "terms_checked_on": self.terms_checked_on,
            "verified_live": self.verified_live,
            "interval_minutes": self.interval_minutes,
            "delivery": self.delivery,
            "attribution": self.attribution,
            "hand_venue": self.hand_venue,
            "notes": self.notes,
        }


_ICE_TERMS = (
    '"we hereby grant you a limited license ... to download and print copies of any content '
    '... but only for your own personal, non-commercial use ... The foregoing license does not '
    'include use of any data mining, robots or similar data gathering or extraction methods."'
)
_EEX_TERMS = (
    '"Neither this website nor the contents made available therein ... may be copied, '
    "reprinted, published, transmitted, transferred, disseminated or distributed in any manner "
    'without the prior written approval of EEX AG." Only "a single copy for exclusive personal, '
    'non-commercial use" is permitted (checked 2026-11-18, unchanged).'
)
_ENTSOG_SITE_TERMS = (
    'Art. 4.1: "You may download, store and use the contents of this Website provided you keep '
    'intact all trademark, copyright and other proprietary notices indicated." Art. 4.2: not to '
    '"make the contents ... available to any other party" without consent. Art. 4.4: indicate '
    'the source "ENTSOG and/or its members" and the title of the section.'
)
_FLUXYS_TERMS = (
    'Fluxys legal notice: "No reproduction, rental, lease, download ... without the prior '
    'written consent of Fluxys" (checked 2026-11-18).'
)
_ENAGAS_TERMS = (
    'Legal notice §6: contents "may not be subject to further modification, copying, '
    'alteration, transformation, reproduction ... without the express authorization of their '
    'owners"; "any use of the contents of the Page ... is strictly prohibited" outside the '
    "expressly authorised cases."
)
_NOT_READ = "Terms not read: the site could not be read from the build environment."

WATCHED_PUBLICATIONS: tuple[WatchedPublication, ...] = (
    # ------------------------------------------------------------------ trading calendars
    WatchedPublication(
        publication_id="eex-trading-calendar",
        title="EEX trading calendar (natural gas spot and derivatives)",
        publisher="European Energy Exchange (EEX)",
        kind="trading_calendar",
        hubs=("NBP", "TTF", "ZTP", "THE", "PVB"),
        url="https://www.eex.com/en/trading-resources/trading-information/calendar",
        document_format="xlsx",
        verdict=HAND_MAINTAINED,
        terms_section=TERMS_SECTION,
        terms_quote=_EEX_TERMS,
        terms_url="https://www.eex.com/en/disclaimer",
        verified_live=True,
        hand_venue="EEX",
        notes=(
            "The page links 'Natural Gas Trading Calendar 2026' (xlsx) and the EEX Group calendar "
            "(eex-group.com, same terms). EEX's own derivatives holiday calendar states that gas "
            "derivatives trade on 24 and 31 December 08:00 to 13:00 CET: the hand file lists "
            "both days as closed, so the desk checks them."
        ),
    ),
    WatchedPublication(
        publication_id="ice-endex-trading-schedule",
        title="ICE Endex trading schedule (TTF, THE, ZTP, PEG gas futures)",
        publisher="ICE Endex",
        kind="trading_calendar",
        hubs=("TTF", "ZTP", "THE"),
        url="https://www.ice.com/publicdocs/ICE_Endex_Trading_Schedule.pdf",
        document_format="pdf",
        verdict=HAND_MAINTAINED,
        terms_section=TERMS_SECTION,
        terms_quote=_ICE_TERMS,
        terms_url="https://www.ice.com/terms-of-use",
        verified_live=True,
        hand_venue="ICE_ENDEX",
        notes="Holiday notices for specific contracts: https://www.ice.com/holidays.",
    ),
    WatchedPublication(
        publication_id="ice-futures-europe-trading-schedule",
        title="ICE Futures Europe trading schedule (UK NBP natural gas)",
        publisher="ICE Futures Europe",
        kind="trading_calendar",
        hubs=("NBP",),
        url="https://www.ice.com/publicdocs/Trading_Schedule.pdf",
        document_format="pdf",
        verdict=HAND_MAINTAINED,
        terms_section=TERMS_SECTION,
        terms_quote=_ICE_TERMS,
        terms_url="https://www.ice.com/terms-of-use",
        verified_live=True,
        hand_venue="ICE_FUTURES_EUROPE",
        notes="UK natural gas closes on UK bank holidays as well as the exchange holidays.",
    ),
    # ------------------------------------------------------------------ capacity auctions
    WatchedPublication(
        publication_id="entsog-cam-auction-calendar",
        title="ENTSOG CAM network code auction calendar",
        publisher="ENTSOG",
        kind="capacity_auctions",
        hubs=("TTF", "ZTP", "THE", "PVB"),
        url="https://www.entsog.eu/capacity-allocation-mechanisms-nc",
        document_format="xlsx",
        verdict=FETCH,
        terms_section=TERMS_SECTION,
        terms_quote=_ENTSOG_SITE_TERMS,
        terms_url="https://www.entsog.eu/privacy-policy-and-terms-use",
        verified_live=True,
        interval_minutes=24 * 60,
        parser="entsog_cam_calendar",
        attribution="Source: ENTSOG and/or its members, CAM NC Auction Calendar",
        tariff_publisher_id="entsog-auction-calendar",
        notes=(
            "Yearly, quarterly and monthly auctions, firm and interruptible, with the offer-level "
            "publication date; day-ahead and within-day are standing rules. Kept for the firm's "
            "own use only, never passed to another party (Art. 4.2). Applies at EU "
            "interconnection points; NBP's interconnectors (IUK, BBL) sell on PRISMA."
        ),
    ),
    WatchedPublication(
        publication_id="prisma-auctions",
        title="PRISMA capacity platform: auction offers, LNG and storage offers",
        publisher="PRISMA European Capacity Platform",
        kind="capacity_auctions",
        hubs=("NBP", "TTF", "ZTP", "THE", "PVB"),
        url="https://www.prisma-capacity.eu/",
        document_format="platform",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=(
            "The public site publishes no reuse terms (imprint and legal documents read); offers "
            "and results are behind a platform account under the PRISMA GTCs, which nobody "
            "accepts on the owner's behalf."
        ),
        terms_url="https://www.prisma-capacity.eu/legal-documents",
        verified_live=True,
        delivery="platform",
        notes="Auction dates follow ENTSOG's calendar; PRISMA also sends a newsletter by e-mail.",
    ),
    WatchedPublication(
        publication_id="gsa-platform-auctions",
        title="GSA Platform auctions (GAZ-SYSTEM)",
        publisher="GAZ-SYSTEM",
        kind="capacity_auctions",
        hubs=(),
        url="https://gsaplatform.eu/",
        document_format="platform",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote="Not read: the site answered with a web-firewall error page on 2026-11-28.",
        terms_url="https://gsaplatform.eu/",
        verified_live=False,
        delivery="platform",
        notes="Polish and neighbouring points; none of the desk's five hubs.",
    ),
    WatchedPublication(
        publication_id="rbp-auctions",
        title="Regional Booking Platform auctions (FGSZ)",
        publisher="FGSZ",
        kind="capacity_auctions",
        hubs=(),
        url="https://rbp.eu/",
        document_format="platform",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=(
            "Not read: the site is a script application with no terms reachable without signing "
            "in; www.rbp.eu was not reachable (proxy 502)."
        ),
        terms_url="https://rbp.eu/",
        verified_live=False,
        delivery="platform",
        notes="Central and south-east European points; none of the desk's five hubs.",
    ),
    # ------------------------------------------------------------------ LNG slots
    WatchedPublication(
        publication_id="fluxys-lng-zeebrugge-slots",
        title="Zeebrugge LNG terminal: slot offers and secondary capacity",
        publisher="Fluxys LNG",
        kind="lng_slots",
        hubs=("ZTP",),
        url="https://www.fluxys.com/en/natural-gas-and-biomethane/empowering-you/tariffs/"
        "tariff_fluxyslng-lng",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=_FLUXYS_TERMS,
        terms_url="https://www.fluxys.com/en/legalnotice",
        verified_live=True,
        notes="The firm can record Fluxys's written permission (LNG terminal register, CP-11).",
    ),
    WatchedPublication(
        publication_id="dunkerque-lng-slots",
        title="Dunkerque LNG terminal: capacity booking",
        publisher="Dunkerque LNG (Fluxys group)",
        kind="lng_slots",
        hubs=("ZTP",),
        url="https://www.fluxys.com/fr/natural-gas-and-biomethane/shipper-journey/capacity-booking",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=_FLUXYS_TERMS,
        terms_url="https://www.fluxys.com/fr/legalnotice",
        verified_live=True,
        notes="www.dunkerquelng.com now redirects to fluxys.com, under the Fluxys legal notice.",
    ),
    WatchedPublication(
        publication_id="grain-lng-uioli-board",
        title="Isle of Grain LNG: use-it-or-lose-it bulletin board (berthing slots)",
        publisher="Grain LNG",
        kind="lng_slots",
        hubs=("NBP",),
        url="https://www.grainlng.com/operational-information",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=(
            '"You may make a print copy for personal use, provided proprietary notices are '
            'included. You may not distribute, reverse engineer, or commercially exploit Website '
            'or Services content except as permitted by law."'
        ),
        terms_url="https://www.grainlng.com/terms-and-conditions",
        verified_live=True,
        delivery="email",
        notes=(
            "Released slots are advertised on the board; bids go by e-mail to Grain LNG on a "
            "Short Term Access Confirmation Notice (registered users)."
        ),
    ),
    WatchedPublication(
        publication_id="gate-terminal-slots",
        title="Gate terminal (Rotterdam): slot and secondary capacity offers",
        publisher="Gate terminal",
        kind="lng_slots",
        hubs=("TTF",),
        url="https://www.gate.nl/",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=_NOT_READ + " (gate.nl: proxy 502 on 2026-11-28).",
        terms_url="https://www.gate.nl/",
        verified_live=False,
    ),
    WatchedPublication(
        publication_id="det-lng-auctions",
        title="Deutsche Energy Terminal (Wilhelmshaven, Brunsbüttel, Stade): capacity auctions",
        publisher="Deutsche Energy Terminal",
        kind="lng_slots",
        hubs=("THE",),
        url="https://energy-terminal.de/en/capacity-marketing/trader-information",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=(
            "The imprint publishes no reuse terms (only image copyrights); written confirmation "
            "needed. Auctions and offers run on PRISMA."
        ),
        terms_url="https://energy-terminal.de/en/imprint",
        verified_live=True,
        delivery="platform",
        notes="Wilhelmshaven commercial management passed to Gasfin Services on 1 April 2026.",
    ),
    WatchedPublication(
        publication_id="deutsche-regas-mukran",
        title="Deutsche ReGas (Mukran): capacity offers",
        publisher="Deutsche ReGas",
        kind="lng_slots",
        hubs=("THE",),
        url="https://deutsche-regas.de/en/",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote="Not read: the site is a script application; its imprint text did not load.",
        terms_url="https://deutsche-regas.de/en/imprint",
        verified_live=False,
    ),
    WatchedPublication(
        publication_id="enagas-lng-capacity",
        title="Spanish LNG terminals: capacity offer and allocation (Enagás GTS)",
        publisher="Enagás",
        kind="lng_slots",
        hubs=("PVB",),
        url="https://www.enagas.es/en/energy-transition/gas-network/"
        "infrastructure-supply-capacity-allocation/",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=_ENAGAS_TERMS,
        terms_url="https://www.enagas.es/en/legal-notice/",
        verified_live=True,
    ),
    # ------------------------------------------------------------------ storage
    WatchedPublication(
        publication_id="uniper-storage-offers",
        title="Uniper Energy Storage: storage offers and auctions (DE)",
        publisher="Uniper Energy Storage",
        kind="storage_auctions",
        hubs=("THE",),
        url="https://www.uniper.energy/",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=_NOT_READ + " (the site answered 403).",
        terms_url="https://www.uniper.energy/",
        verified_live=False,
    ),
    WatchedPublication(
        publication_id="fluxys-loenhout-storage",
        title="Loenhout storage (BE): capacity offers",
        publisher="Fluxys Belgium",
        kind="storage_auctions",
        hubs=("ZTP",),
        url="https://www.fluxys.com/",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=_FLUXYS_TERMS,
        terms_url="https://www.fluxys.com/en/legalnotice",
        verified_live=True,
    ),
    WatchedPublication(
        publication_id="enagas-storage",
        title="Spanish underground storage: capacity allocation (Enagás GTS)",
        publisher="Enagás",
        kind="storage_auctions",
        hubs=("PVB",),
        url="https://www.enagas.es/en/energy-transition/gas-network/"
        "infrastructure-supply-capacity-allocation/",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=_ENAGAS_TERMS,
        terms_url="https://www.enagas.es/en/legal-notice/",
        verified_live=True,
    ),
    # ------------------------------------------------------------------ reference prices
    WatchedPublication(
        publication_id="the-imbalance-prices",
        title="Trading Hub Europe: positive and negative imbalance prices",
        publisher="Trading Hub Europe",
        kind="reference_prices",
        hubs=("THE",),
        url="https://www.tradinghub.eu/en-gb/Publications/Prices/Imbalance-Prices",
        document_format="xml api",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=(
            'Website disclaimer: "Die Vervielfältigung von Informationen oder Daten ... bedarf der '
            'vorherigen schriftlichen Zustimmung von Trading Hub Europe" (reproducing information '
            "or data needs THE's prior written consent). The DataExport API manual invites "
            "automated retrieval without a key, but grants no reuse licence."
        ),
        terms_url="https://www.tradinghub.eu/en-gb/Home/Disclaimer",
        verified_live=True,
        notes=(
            "API: https://api.tradinghub.eu/api/dataexport/xmlexport/PricesEnergyImbalance "
            "(standard tier: 20 requests a second, 3,000 an hour). One written consent from "
            "THE would make it a fetched source."
        ),
    ),
    WatchedPublication(
        publication_id="national-gas-smp",
        title="National Gas: system marginal buy and sell prices (GB cash-out)",
        publisher="National Gas Transmission",
        kind="reference_prices",
        hubs=("NBP",),
        url="https://data.nationalgas.com/",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=(
            "Website terms: no reuse licence; the information \"has been developed for "
            'information purposes only and not for financial analysis purposes". The Gas Data '
            "Portal publishes no licence of its own."
        ),
        terms_url="https://www.nationalgas.com/our-policies/terms-and-conditions",
        verified_live=True,
    ),
    WatchedPublication(
        publication_id="mibgas-prices",
        title="MIBGAS: PVB daily reference prices",
        publisher="MIBGAS",
        kind="reference_prices",
        hubs=("PVB",),
        url="https://www.mibgas.es/en",
        document_format="html",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=(
            'Legal notice: "Sin citar la fuente queda prohibida la reproducción total o parcial, '
            '... y cualquier otro acto que no haya sido expresamente autorizado" (without citing '
            "the source, reproduction is prohibited, as is any act not expressly authorised): "
            "not a clear permission to store."
        ),
        terms_url="https://www.mibgas.es/en/cccontent/legal-notice",
        verified_live=True,
    ),
    WatchedPublication(
        publication_id="eex-ngp",
        title="EEX gas market transparency: neutral gas price (TTF, THE) files",
        publisher="European Energy Exchange (EEX)",
        kind="reference_prices",
        hubs=("TTF", "THE"),
        url="https://www.eex.com/en/markets/natural-gas/gas-market-transparency",
        document_format="csv",
        verdict=LINK_ONLY,
        terms_section=TERMS_SECTION,
        terms_quote=_EEX_TERMS,
        terms_url="https://www.eex.com/en/disclaimer",
        verified_live=True,
        notes="The 2026-11-18 finding stands: EEX data only through the firm's own licence.",
    ),
)

_BY_ID = {item.publication_id: item for item in WATCHED_PUBLICATIONS}
if len(_BY_ID) != len(WATCHED_PUBLICATIONS):  # pragma: no cover - guarded by a test too
    raise RuntimeError("two watched publications share an id")


def watched_publication(publication_id: str) -> WatchedPublication:
    """One publication by id (``KeyError`` when unknown)."""

    return _BY_ID[publication_id]


def fetch_refusal(item: WatchedPublication) -> str | None:
    """Why the product does not fetch ``item``, or ``None`` when it may."""

    if not item.terms_section:
        return "no entry in the legal register: not fetched"
    if item.verdict == HAND_MAINTAINED:
        return "the publisher's terms forbid storing it: the desk keeps it by hand"
    if item.verdict == LINK_ONLY:
        return "viewable, not storable: link only"
    if not item.url.startswith("https://"):
        return "the recorded location is not an https address"
    if not item.parser:
        return "no parser for this publication"
    if item.interval_minutes is None or item.interval_minutes < MIN_INTERVAL_MINUTES:
        return "no check interval within the publisher's limits"
    return None


__all__ = [
    "CHECKED_ON",
    "DELIVERY",
    "FETCH",
    "HAND_MAINTAINED",
    "HUBS",
    "KINDS",
    "LINK_ONLY",
    "MIN_INTERVAL_MINUTES",
    "TERMS_SECTION",
    "VERDICTS",
    "WATCHED_PUBLICATIONS",
    "WatchedPublication",
    "fetch_refusal",
    "watched_publication",
]
