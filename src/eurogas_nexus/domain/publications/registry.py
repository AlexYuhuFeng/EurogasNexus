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
                     the link and fetches nothing;
``consented``        the website terms forbid storing it, but its publisher gave written consent
                     to use what it makes publicly available for the firm's own use, no resale
                     (owner, 2026-11-28; ``domain/publications/consents``): fetched like
                     ``fetch`` while the consent record exists and an administrator has not
                     withdrawn it. A consented publication with no parser yet is "consented,
                     not yet implemented"; one whose site refuses automated reading stays
                     "consented, but the site refuses automated reading" with the response.

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
CONSENTED = "consented"
VERDICTS = (FETCH, HAND_MAINTAINED, LINK_ONLY, CONSENTED)
#: Verdicts the product fetches under (the second only while the consent is in force).
FETCHED_VERDICTS = (FETCH, CONSENTED)

KINDS = (
    "trading_calendar",
    "capacity_auctions",
    "lng_slots",
    "storage_auctions",
    "reference_prices",
    "exchange_prices",
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
    #: The publisher's consent record (``reference_data/publisher_consents.toml``) a
    #: ``consented`` publication is fetched under.
    consent_publisher: str | None = None
    #: The source system fetched prices are stored under (a consented family).
    source_family: str | None = None
    #: For a fetched exchange calendar: the venue of the desk's calendar file it replaces.
    calendar_venue: str | None = None
    #: The site refused automated reading: the exact response, as recorded.
    site_refusal: str = ""
    #: How far back the publisher's own history goes, and what the first read fetches.
    history: str = ""

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
            "consent_publisher": self.consent_publisher,
            "source_family": self.source_family,
            "calendar_venue": self.calendar_venue,
            "site_refusal": self.site_refusal,
            "history": self.history,
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
#: Every consented publication's terms line: the website terms as read, then the consent.
_CONSENT = ("; superseded for the firm's own use by the publisher's written consent reported "
            "by the owner on 2026-11-28 (publicly available data, own use, no resale).")
#: Polite reading of a consented price source: no more often than this (six hours), well
#: inside every publisher's stated limits; the first read fetches the history once.
PRICE_INTERVAL_MINUTES = 6 * 60
_NOT_YET = "Consented; not yet implemented: no parser for this publication yet."

WATCHED_PUBLICATIONS: tuple[WatchedPublication, ...] = (
    # ------------------------------------------------------------------ trading calendars
    WatchedPublication(
        publication_id="eex-trading-calendar",
        title="EEX natural gas trading calendar (exchange holidays and expiry dates)",
        publisher="European Energy Exchange (EEX)",
        kind="trading_calendar",
        hubs=("NBP", "TTF", "ZTP", "THE", "PVB"),
        url="https://www.eex.com/en/trading-resources/trading-information/calendar",
        document_format="xlsx",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_EEX_TERMS + _CONSENT,
        terms_url="https://www.eex.com/en/disclaimer",
        verified_live=True,
        interval_minutes=24 * 60,
        parser="eex_gas_calendar",
        attribution="Source: EEX, Natural Gas Trading Calendar",
        hand_venue="EEX",
        calendar_venue="EEX",
        consent_publisher="eex",
        history="The current year's workbook (Natural Gas Trading Calendar 2026); expiry dates "
                "of every listed maturity from January 2019.",
        notes=(
            "The page links 'Natural Gas Trading Calendar <year>' (xlsx): its sheet '<year> "
            "Natural Gas Holidays' lists the natural gas futures exchange holidays, and "
            "'Physical Futures' each maturity's last trading day. The hand file stays as the "
            "fallback while nothing has been read."
        ),
    ),
    WatchedPublication(
        publication_id="eex-holiday-calendar",
        title="EEX holiday calendar, derivatives (shortened hours on 24 and 31 December)",
        publisher="European Energy Exchange (EEX)",
        kind="trading_calendar",
        hubs=("NBP", "TTF", "ZTP", "THE", "PVB"),
        url="https://www.eex.com/en/trading-resources/trading-information/calendar",
        document_format="pdf",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_EEX_TERMS + _CONSENT,
        terms_url="https://www.eex.com/en/disclaimer",
        verified_live=True,
        interval_minutes=24 * 60,
        parser="eex_holiday_calendar",
        attribution="Source: EEX, Holiday Calendar Derivatives & Emissions Spot",
        calendar_venue="EEX",
        consent_publisher="eex",
        history="One standing document: \"applicable continuously for all years until further "
                "notice\".",
        notes=(
            "Settles the hand file's open question: \"Gas and Freight derivatives are offered "
            "for trading on 24th and 31st December from 08:00 am to 13:00 CET\". Both days are "
            "early closes for EEX gas, not closed days (the hand file listed them closed)."
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
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_ICE_TERMS + _CONSENT,
        terms_url="https://www.ice.com/terms-of-use",
        verified_live=True,
        interval_minutes=24 * 60,
        parser="ice_endex_schedule",
        attribution="Source: ICE Endex Trading Schedule",
        hand_venue="ICE_ENDEX",
        calendar_venue="ICE_ENDEX",
        consent_publisher="ice",
        history="The current schedule: 2026 and 2027.",
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
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_ICE_TERMS + _CONSENT,
        terms_url="https://www.ice.com/terms-of-use",
        verified_live=True,
        interval_minutes=24 * 60,
        parser="ifeu_schedule",
        attribution="Source: ICE Futures Europe Trading Schedule",
        hand_venue="ICE_FUTURES_EUROPE",
        calendar_venue="ICE_FUTURES_EUROPE",
        consent_publisher="ice",
        history="The current schedule: 2026 and 2027 with the Christmas appendices.",
        notes="UK natural gas also closes on UK bank holidays; read for UK natural gas only.",
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
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=(
            "The public site publishes no reuse terms (imprint and legal documents read); offers "
            "and results are behind a platform account under the PRISMA GTCs, which nobody "
            "accepts on the owner's behalf" + _CONSENT
        ),
        terms_url="https://www.prisma-capacity.eu/legal-documents",
        verified_live=True,
        delivery="platform",
        consent_publisher="prisma",
        notes=("Consented; not yet implemented. The auction offers per point (IUK, BBL and the "
               "points into TTF, ZTP, THE and PVB) live on the platform behind an account, which "
               "the consent does not reach; the public site carries market news and urgent "
               "market messages only. The standard auction dates for every EU interconnection "
               "point come from ENTSOG's calendar (fetched)."),
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
        notes="Polish and neighbouring points; none of the desk's five hubs. Not covered by the "
              "consents of 2026-11-28.",
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
        notes="Central and south-east European points; none of the desk's five hubs. Not "
              "covered by the consents of 2026-11-28.",
    ),
    # ------------------------------------------------------------------ LNG slots
    WatchedPublication(
        publication_id="fluxys-lng-zeebrugge-slots",
        title="Zeebrugge LNG terminal: slot offers and secondary capacity",
        publisher="Fluxys LNG",
        kind="lng_slots",
        hubs=("ZTP",),
        url="https://www.fluxys.com/en/natural-gas-and-biomethane/products-services/"
        "lng-primary-and-secondary-market",
        document_format="html",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_FLUXYS_TERMS + _CONSENT,
        terms_url="https://www.fluxys.com/en/legalnotice",
        verified_live=True,
        consent_publisher="fluxys",
        interval_minutes=PRICE_INTERVAL_MINUTES,
        parser="fluxys_lng_slots",
        attribution="Source: Fluxys LNG, Primary & secondary market (news)",
        history="The newest four slot or auction news items the page links (2025 on).",
        notes=("The Primary & secondary market page (Zeebrugge/Dunkirk) links Fluxys LNG's "
               "news; a regasification slot sale names each slot (arrival, code), its size "
               "and the auction day and time in Belgian time. Recorded as slot notices the "
               "regas auction desk opens a case from. Bidding is on Fluxys's auction "
               "website; nothing here bids."),
    ),
    WatchedPublication(
        publication_id="dunkerque-lng-slots",
        title="Dunkerque LNG terminal: capacity booking",
        publisher="Dunkerque LNG (Fluxys group)",
        kind="lng_slots",
        hubs=("ZTP",),
        url="https://www.fluxys.com/en/natural-gas-and-biomethane/products-services/"
        "lng-primary-and-secondary-market",
        document_format="html",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_FLUXYS_TERMS + _CONSENT,
        terms_url="https://www.fluxys.com/fr/legalnotice",
        verified_live=True,
        consent_publisher="fluxys",
        interval_minutes=PRICE_INTERVAL_MINUTES,
        parser="fluxys_lng_slots_dunkerque",
        attribution="Source: Fluxys LNG, Primary & secondary market (news)",
        history="The newest four slot or auction news items the page links.",
        notes=("The same Fluxys LNG page as Zeebrugge, read for Dunkirk items; "
               "www.dunkerquelng.com now redirects to fluxys.com. No Dunkirk slot item was "
               "listed on 2026-11-28."),
    ),
    WatchedPublication(
        publication_id="grain-lng-uioli-board",
        title="Isle of Grain LNG: use-it-or-lose-it bulletin board (berthing slots)",
        publisher="Grain LNG",
        kind="lng_slots",
        hubs=("NBP",),
        url="https://www.grainlng.com/operational-information",
        document_format="html",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=(
            '"You may make a print copy for personal use, provided proprietary notices are '
            'included. You may not distribute, reverse engineer, or commercially exploit Website '
            'or Services content except as permitted by law."' + _CONSENT
        ),
        terms_url="https://www.grainlng.com/terms-and-conditions",
        verified_live=True,
        delivery="email",
        consent_publisher="grain-lng",
        interval_minutes=PRICE_INTERVAL_MINUTES,
        parser="grain_uioli",
        attribution="Source: Grain LNG, UIOLI Bulletin Board",
        history="The board as it stands; a slot no longer listed is withdrawn.",
        notes=("Released berthing slots are listed one date a line under 'Please see below the "
               "currently available slots:'. No auction window is published: bids go by e-mail "
               "on a Short Term Access Confirmation Notice (registered users), so a slot's "
               "opening is the day the product first saw it. robots.txt carries "
               "'Content-Signal: search=yes, ai-train=no'; the product trains nothing."),
    ),
    WatchedPublication(
        publication_id="gate-terminal-slots",
        title="Gate terminal (Rotterdam): slot and secondary capacity offers",
        publisher="Gate terminal",
        kind="lng_slots",
        hubs=("TTF",),
        url="https://www.gate.nl/",
        document_format="html",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_NOT_READ + " (gate.nl: proxy 502 on 2026-11-28)" + _CONSENT,
        terms_url="https://www.gate.nl/",
        verified_live=False,
        consent_publisher="gate-terminal",
        notes=("Consented; not yet implemented: www.gate.nl and gate.nl could not be reached "
               "from the build environment on 2026-11-28 (the proxy answered 'CONNECT tunnel "
               "failed, response 502'), so its page layout is unknown. Not a refusal by Gate."),
    ),
    WatchedPublication(
        publication_id="det-lng-auctions",
        title="Deutsche Energy Terminal (Wilhelmshaven, Brunsbüttel, Stade): capacity auctions",
        publisher="Deutsche Energy Terminal",
        kind="lng_slots",
        hubs=("THE",),
        url="https://energy-terminal.de/en/capacity-marketing/trader-information",
        document_format="html",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=(
            "The imprint publishes no reuse terms (only image copyrights). Auctions and offers "
            "run on PRISMA" + _CONSENT
        ),
        terms_url="https://energy-terminal.de/en/imprint",
        verified_live=True,
        delivery="platform",
        consent_publisher="deutsche-energy-terminal",
        interval_minutes=24 * 60,
        parser="det_trader_information",
        attribution="Source: Deutsche Energy Terminal, Trader Information",
        history="The page as it stands; a terminal no longer 'Auction running' is withdrawn.",
        notes=("Each terminal's status ('Auction running', 'No Auction Planned') and the "
               "auction information, with the bidding window where the page states one "
               "('from <day> to <day>'). Bidding is on PRISMA. Wilhelmshaven commercial "
               "management passed to Gasfin Services on 1 April 2026."),
    ),
    WatchedPublication(
        publication_id="deutsche-regas-mukran",
        title="Deutsche ReGas (Mukran): capacity offers",
        publisher="Deutsche ReGas",
        kind="lng_slots",
        hubs=("THE",),
        url="https://deutsche-regas.de/en/",
        document_format="html",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote="Not read: the site is a script application; its imprint text did not load"
                    + _CONSENT,
        terms_url="https://deutsche-regas.de/en/imprint",
        verified_live=False,
        consent_publisher="deutsche-regas",
        notes=("Consented; not yet implemented: https://deutsche-regas.de/en/ and its robots.txt "
               "both answer HTTP 200 with the same 6,144-byte page shell whose text is drawn by "
               "a script; the page itself carries no offer. Ask Deutsche ReGas for a file or "
               "a documented address."),
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
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_ENAGAS_TERMS + _CONSENT,
        terms_url="https://www.enagas.es/en/legal-notice/",
        verified_live=True,
        consent_publisher="enagas",
        notes=("Consented; not yet implemented: the allocation page answers HTTP 200 but its "
               "text is drawn by a script (only the copyright line is in the page). Spanish "
               "LNG slots and storage are allocated on Enagás GTS's capacity platform. Ask "
               "Enagás for a file or a documented address."),
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
        notes="Not covered by the consents of 2026-11-28.",
    ),
    WatchedPublication(
        publication_id="fluxys-loenhout-storage",
        title="Loenhout storage (BE): capacity offers",
        publisher="Fluxys Belgium",
        kind="storage_auctions",
        hubs=("ZTP",),
        url="https://www.fluxys.com/en/natural-gas-and-biomethane/products-services/"
        "ztp-storage-products-on-offer",
        document_format="html",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_FLUXYS_TERMS + _CONSENT,
        terms_url="https://www.fluxys.com/en/legalnotice",
        verified_live=True,
        consent_publisher="fluxys",
        notes=("Consented; not yet implemented: the Products on Offer page lists first-come-first-"
               "served storage products with a capacity graph and no auction window; storage "
               "subscription windows are announced as Fluxys news. Next: read those news "
               "items as the LNG ones are read."),
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
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_ENAGAS_TERMS + _CONSENT,
        terms_url="https://www.enagas.es/en/legal-notice/",
        verified_live=True,
        consent_publisher="enagas",
        notes=("Consented; not yet implemented: the allocation page answers HTTP 200 but its "
               "text is drawn by a script (only the copyright line is in the page). Spanish "
               "LNG slots and storage are allocated on Enagás GTS's capacity platform. Ask "
               "Enagás for a file or a documented address."),
    ),
    # ------------------------------------------------------------------ reference prices
    WatchedPublication(
        publication_id="the-imbalance-prices",
        title="Trading Hub Europe: VTP daily average and imbalance prices",
        publisher="Trading Hub Europe",
        kind="reference_prices",
        hubs=("THE",),
        url="https://api.tradinghub.eu/api/dataexport/xmlexport/PricesEnergyImbalance",
        document_format="xml api",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=(
            'Website disclaimer: "Die Vervielfältigung von Informationen oder Daten ... bedarf der '
            'vorherigen schriftlichen Zustimmung von Trading Hub Europe" (reproducing information '
            "or data needs THE's prior written consent). The DataExport API manual invites "
            "automated retrieval without a key, but grants no reuse licence" + _CONSENT
        ),
        terms_url="https://www.tradinghub.eu/en-gb/Home/Disclaimer",
        verified_live=True,
        interval_minutes=PRICE_INTERVAL_MINUTES,
        parser="the_prices",
        attribution="Source: Trading Hub Europe, DataExport PricesEnergyImbalance",
        consent_publisher="trading-hub-europe",
        source_family="THE",
        history="From gas day 2021-10-01 (THE's publication start); read once in full, then "
                "the last seven gas days at each check.",
        notes=(
            "Documented open API (manual https://api.tradinghub.eu/api/dataexport/manual/en): "
            "no key; a User-Agent naming the client is mandatory; standard tier 20 requests a "
            "second, 3,000 an hour; ETag and If-None-Match supported; the previous gas day is "
            "preliminary until replaced by the final value. The VTP daily average price is a "
            "reference index for the gas day, not a quote."
        ),
    ),
    WatchedPublication(
        publication_id="national-gas-smp",
        title="National Gas: SAP and system marginal buy and sell prices (GB cash-out)",
        publisher="National Gas Transmission",
        kind="reference_prices",
        hubs=("NBP",),
        url="https://api.nationalgas.com/operationaldata/v1/publications/gasday",
        document_format="json api",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=(
            "Website terms: no reuse licence; the information \"has been developed for "
            'information purposes only and not for financial analysis purposes". The Gas Data '
            "Portal publishes no licence of its own" + _CONSENT
        ),
        terms_url="https://www.nationalgas.com/our-policies/terms-and-conditions",
        verified_live=True,
        interval_minutes=PRICE_INTERVAL_MINUTES,
        parser="national_gas_prices",
        attribution="Source: National Gas Transmission, Gas Operational Data API",
        consent_publisher="national-gas",
        source_family="NATIONAL_GAS_PRICES",
        history="Five years rolling (the API's stated depth); read once in yearly requests, "
                "then the last ten gas days at each check.",
        notes=(
            "Documented API (data.nationalgas.com, APIs: Gas Operational Data, POST "
            "/publications/gasday; catalogue items PUBOB603 SAP, PUBOB604 SMP Buy, PUBOB605 SMP "
            "Sell, Actual Day, p/kWh, published 12:00 D+1). One request may not exceed days x "
            "items of 3,600."
        ),
    ),
    WatchedPublication(
        publication_id="mibgas-prices",
        title="MIBGAS: PVB daily prices (day-ahead, month-ahead, quarter, year)",
        publisher="MIBGAS",
        kind="reference_prices",
        hubs=("PVB",),
        url="https://www.mibgas.es/en/file-access",
        document_format="csv",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=(
            'Legal notice: "Sin citar la fuente queda prohibida la reproducción total o parcial, '
            '... y cualquier otro acto que no haya sido expresamente autorizado" (without citing '
            "the source, reproduction is prohibited, as is any act not expressly authorised)"
            + _CONSENT
        ),
        terms_url="https://www.mibgas.es/en/cccontent/legal-notice",
        verified_live=True,
        interval_minutes=PRICE_INTERVAL_MINUTES,
        parser="mibgas_prices",
        attribution="Source: MIBGAS, MIBGAS_Data_<year>.csv (file access)",
        consent_publisher="mibgas",
        source_family="MIBGAS",
        history="Yearly CSV files from 2016 (2015 is published as a workbook only); read once, "
                "then the current year's file at each check.",
        notes=(
            "The file-access page links one MIBGAS_Data_<year>.csv a year (the MIBGAS daily "
            "price per product and trading day). MIBGAS offers no documented API; the files are "
            "the publisher's own download. robots.txt allows /en/file-access."
        ),
    ),
    WatchedPublication(
        publication_id="eex-ngp",
        title="EEX gas market transparency: TTF neutral gas price (60-day file)",
        publisher="European Energy Exchange (EEX)",
        kind="reference_prices",
        hubs=("TTF",),
        url="https://www.eex.com/en/markets/natural-gas/gas-market-transparency",
        document_format="csv",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_EEX_TERMS + _CONSENT,
        terms_url="https://www.eex.com/en/disclaimer",
        verified_live=True,
        interval_minutes=PRICE_INTERVAL_MINUTES,
        parser="eex_ngp",
        attribution="Source: EEX, TTF Neutral Gas Price (gas market transparency)",
        consent_publisher="eex",
        source_family="EEX_PUBLIC",
        history="Sixty delivery days (the file's own window); kept from the first read on, so "
                "the product's history grows by a day a day.",
        notes=(
            "The page links https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_60_Days.csv "
            "(conditional requests: ETag and Last-Modified). THE, PEG, ZTP and NBP have no "
            "neutral gas price file on the page."
        ),
    ),
    # ------------------------------------------------------------------ exchange prices
    WatchedPublication(
        publication_id="eex-market-data",
        title="EEX public market data: natural gas spot and futures tables",
        publisher="European Energy Exchange (EEX)",
        kind="exchange_prices",
        hubs=("TTF", "THE", "ZTP", "PVB", "NBP"),
        url="https://www.eex.com/en/market-data/natural-gas",
        document_format="html",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_EEX_TERMS + _CONSENT,
        terms_url="https://www.eex.com/en/disclaimer",
        verified_live=True,
        consent_publisher="eex",
        notes=(
            "Consented; not yet implemented. The market-data pages carry no prices in the page "
            "itself: a script draws the spot and futures tables from a data service EEX does "
            "not document for automated reading, so the product does not read it. Ask EEX how "
            "they prefer the public end-of-day tables to be read (a file, or a documented "
            "address)."
        ),
    ),
    WatchedPublication(
        publication_id="ice-futures-end-of-day",
        title="ICE: end-of-day TTF and UK NBP natural gas futures prices",
        publisher="Intercontinental Exchange (ICE)",
        kind="exchange_prices",
        hubs=("TTF", "NBP"),
        url="https://www.ice.com/products/27996665/Dutch-TTF-Natural-Gas-Futures/data",
        document_format="html",
        verdict=CONSENTED,
        terms_section=TERMS_SECTION,
        terms_quote=_ICE_TERMS + _CONSENT,
        terms_url="https://www.ice.com/terms-of-use",
        verified_live=True,
        consent_publisher="ice",
        notes=(
            "Consented; not yet implemented. The product page's text carries the contract "
            "calendar (first and last trading days) but no price: prices are drawn by the "
            "page's script from a data service ICE does not document for automated reading. "
            "ice.com is also behind a bot filter that, on 2026-11-28, once answered the "
            "product's robots.txt read with HTTP 200 and a page titled \"Attention Required! | "
            "Cloudflare\" (\"Sorry, you have been blocked\"), and answered normally a moment "
            "later. Ask ICE how they prefer end-of-day prices to be read."
        ),
    ),
)

_BY_ID = {item.publication_id: item for item in WATCHED_PUBLICATIONS}
if len(_BY_ID) != len(WATCHED_PUBLICATIONS):  # pragma: no cover - guarded by a test too
    raise RuntimeError("two watched publications share an id")


def watched_publication(publication_id: str) -> WatchedPublication:
    """One publication by id (``KeyError`` when unknown)."""

    return _BY_ID[publication_id]


def fetch_refusal(item: WatchedPublication) -> str | None:
    """Why the product does not fetch ``item``, or ``None`` when it may.

    Pure: a consent an administrator withdrew is checked against the runtime store by the
    watch itself (``application/publication_watch``), on top of this.
    """

    if not item.terms_section:
        return "no entry in the legal register: not fetched"
    if item.verdict == HAND_MAINTAINED:
        return "the publisher's terms forbid storing it: the desk keeps it by hand"
    if item.verdict == LINK_ONLY:
        return "viewable, not storable: link only"
    if item.verdict == CONSENTED:
        from eurogas_nexus.domain.publications.consents import publisher_consent

        if publisher_consent(item.consent_publisher) is None:
            return "the terms forbid storing it and no written consent is recorded: not fetched"
        if item.site_refusal:
            return ("consented, but the site refuses automated reading; ask the publisher how "
                    "they prefer to be read")
        if not item.parser:
            return "consented, not yet implemented"
    if not item.url.startswith("https://"):
        return "the recorded location is not an https address"
    if not item.parser:
        return "no parser for this publication"
    if item.interval_minutes is None or item.interval_minutes < MIN_INTERVAL_MINUTES:
        return "no check interval within the publisher's limits"
    return None


def unfetched_state(item: WatchedPublication) -> str | None:
    """The state a publication the product does not fetch is shown in (``None``: fetched)."""

    if item.verdict in (HAND_MAINTAINED, LINK_ONLY):
        return item.verdict
    refusal = fetch_refusal(item)
    if refusal is None:
        return None
    if item.verdict == CONSENTED and item.site_refusal:
        return "site_refuses"
    if item.verdict == CONSENTED and not item.parser:
        return "not_implemented"
    return "link_only"


__all__ = [
    "CHECKED_ON",
    "CONSENTED",
    "FETCHED_VERDICTS",
    "PRICE_INTERVAL_MINUTES",
    "unfetched_state",
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
