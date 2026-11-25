"""The news source registry (NEWS-1): which publishers the product may read, and on what terms.

Every source is one :class:`NewsSource` with its publisher, where it is read (a feed address or
the REMIT messages the platform already holds), its language, how often it may be polled, and
its reuse terms as they were read: the licence, a short quotation, the page it was read on and
the day. A source is polled only when its terms permit reuse in a commercial product
(``reuse == "permitted"``) **and** a feed address is recorded; otherwise it is listed with the
reason it is not read (:func:`poll_refusal`). Licensed news (wire services, price reporters) is
never polled: it reaches the product only through the customer's own entitlement, as licensed
market data does (AGENTS.md rule 18).

What is kept of an item is bounded by the terms too: ``store == "summary"`` keeps the title,
link, times and the feed's own summary; ``store == "title_only"`` keeps the title, link and
times only (the reader follows the link for the text).

No credential, account or sign-up is needed for any listed source, and the poller reads a
source's ``robots.txt`` before its feed (``application/news_ingest``). The engineering record of
each source's terms is ``docs/integration/NEWS_SOURCE_REGISTRY.md``; legal confirms the current
terms before a production deployment, as for every row of ``docs/legal/DATA_SOURCE_TERMS.md``.

Import-safe: no database, web or network import.

新闻来源登记册：每个来源的发布方、读取地址、语言、轮询间隔，以及读取到的再利用条款（许可、
引文、页面与日期）。只有条款允许商业再利用且登记了订阅地址的来源才会被轮询；授权新闻
（通讯社、价格报告机构）从不轮询。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

#: Kinds of source: messages the platform already holds, or a public feed.
KINDS = ("remit_held", "rss", "atom")
#: What the terms allow: ``permitted`` (commercial reuse with attribution), ``forbidden``
#: (no reuse without the publisher's consent), ``licensed`` (the customer's own entitlement
#: only), ``unknown`` (terms not read yet: not polled).
REUSE = ("permitted", "forbidden", "licensed", "unknown")
#: What is kept of an item.
STORE = ("summary", "title_only")


@dataclass(frozen=True, slots=True)
class NewsSource:
    """One publisher the registry knows, with the terms it is read under."""

    source_id: str
    publisher: str
    title: str
    kind: str
    #: The feed polled; ``None`` when no address is recorded (the source is not polled).
    feed_url: str | None
    #: The publisher's own site; a feed address must be on this host.
    home_url: str
    language: str
    #: Least minutes between two polls of the source.
    poll_minutes: int
    reuse: str
    store: str
    licence: str
    #: A short quotation of the terms, as read.
    terms_quote: str
    terms_url: str
    #: The day the terms were read (ISO date), or ``""`` when they were not read.
    terms_read_on: str
    #: The credit every item carries.
    attribution: str
    #: Whether the feed address was confirmed by a successful poll before it was recorded.
    feed_confirmed: bool = False
    notes: str = ""

    @property
    def home_host(self) -> str:
        return (urlsplit(self.home_url).hostname or "").lower()


_EC_TERMS = (
    '"content owned by the EU on this website is licensed under the Creative Commons '
    'Attribution 4.0 International (CC BY 4.0) licence ... reuse is allowed, provided '
    'appropriate credit is given and changes are indicated"; logos and third-party content '
    "are excluded"
)

NEWS_SOURCES: tuple[NewsSource, ...] = (
    NewsSource(
        source_id="remit-umm",
        publisher="Inside-information platforms (REMIT UMM)",
        title="REMIT urgent market messages already held by the platform",
        kind="remit_held",
        feed_url=None,
        home_url="https://transparency.entsog.eu/",
        language="en",
        poll_minutes=5,
        reuse="permitted",
        store="summary",
        licence="Per platform (ENTSOG TP Terms of Use Art. 5; GIE IIP; others need written "
        "confirmation at import)",
        terms_quote="Held under the REMIT row of docs/legal/DATA_SOURCE_TERMS.md: the import "
        "records the platform and refuses a platform without published reuse terms unless "
        "the firm confirmed them",
        terms_url="docs/legal/DATA_SOURCE_TERMS.md",
        terms_read_on="2026-11-14",
        attribution="REMIT UMM as published by the market participant; platform in the "
        "message's source reference",
        feed_confirmed=True,
        notes="No outbound read: items are made from the stored messages (latest version per "
        "message). The most reliable gas news: an operator's own statement of unavailability.",
    ),
    NewsSource(
        source_id="ec-energy-news",
        publisher="European Commission, Directorate-General for Energy",
        title="Energy news and announcements",
        kind="rss",
        feed_url=None,
        home_url="https://energy.ec.europa.eu/",
        language="en",
        poll_minutes=60,
        reuse="permitted",
        store="summary",
        licence="CC BY 4.0 (Commission Decision 2011/833/EU on the reuse of Commission "
        "documents)",
        terms_quote=_EC_TERMS,
        terms_url="https://commission.europa.eu/legal-notice_en",
        terms_read_on="2026-11-24",
        attribution="© European Union, CC BY 4.0; summary shortened",
        notes="Feed address not yet recorded: the page was not reachable from the build "
        "environment, so nothing is polled until an operator records it (same host).",
    ),
    NewsSource(
        source_id="eurlex-oj-energy",
        publisher="Publications Office of the European Union (EUR-Lex)",
        title="Official Journal: energy acts and notices",
        kind="rss",
        feed_url=None,
        home_url="https://eur-lex.europa.eu/",
        language="en",
        poll_minutes=360,
        reuse="permitted",
        store="summary",
        licence="Commission Decision 2011/833/EU; EUR-Lex reuse policy",
        terms_quote='"You can reuse EUR-Lex data, free of charge, subject to copyright '
        'conditions."',
        terms_url="https://eur-lex.europa.eu/content/help/data-reuse/reuse-contents-eurlex-"
        "details.html",
        terms_read_on="2026-11-24",
        attribution="© European Union, https://eur-lex.europa.eu",
        notes="EUR-Lex offers predefined RSS feeds; the feed for energy acts was not readable "
        "from the build environment, so the address is to be recorded by an operator.",
    ),
    NewsSource(
        source_id="acer-news",
        publisher="European Union Agency for the Cooperation of Energy Regulators (ACER)",
        title="ACER news and press releases",
        kind="rss",
        feed_url=None,
        home_url="https://www.acer.europa.eu/",
        language="en",
        poll_minutes=360,
        reuse="permitted",
        store="title_only",
        licence="ACER legal notice: reproduction for commercial and non-commercial purposes "
        "with the Agency acknowledged",
        terms_quote='Information may be reproduced "for non-commercial and commercial '
        'purposes" "provided that the Agency is always acknowledged as the source of the '
        'material"; the same notice prohibits reuse of "Licensed Material"',
        terms_url="https://www.acer.europa.eu/legal-notice",
        terms_read_on="2026-11-24",
        attribution="Source: ACER",
        notes="Titles and links only, because the notice also restricts 'Licensed Material' "
        "without saying which; the site footer links an RSS feed whose address was not read.",
    ),
    NewsSource(
        source_id="govuk-desnz",
        publisher="UK Department for Energy Security and Net Zero (GOV.UK)",
        title="DESNZ news, policy papers and announcements",
        kind="atom",
        feed_url="https://www.gov.uk/government/organisations/"
        "department-for-energy-security-and-net-zero.atom",
        home_url="https://www.gov.uk/",
        language="en",
        poll_minutes=60,
        reuse="permitted",
        store="summary",
        licence="Open Government Licence v3.0",
        terms_quote='"Most content on GOV.UK is subject to Crown copyright protection and is '
        'published under the Open Government Licence"; "We make most of the content on '
        'GOV.UK available through feeds for other websites and applications to use."',
        terms_url="https://www.gov.uk/help/terms-conditions",
        terms_read_on="2026-11-24",
        attribution="Contains public sector information licensed under the Open Government "
        "Licence v3.0",
        notes="Feed address follows GOV.UK's organisation feed pattern and was not read from the "
        "build environment; the first successful poll (news_source_polls.last_success_at_utc) "
        "confirms it.",
    ),
)

#: Sources considered and left out, with the reason. None of them is polled.
EXCLUDED_SOURCES: tuple[NewsSource, ...] = (
    NewsSource(
        source_id="wire-and-price-reporters",
        publisher="Reuters, Bloomberg, Argus, ICIS, S&P Global Platts, Montel",
        title="Licensed news and price-reporting services",
        kind="rss",
        feed_url=None,
        home_url="https://www.reuters.com/",
        language="en",
        poll_minutes=0,
        reuse="licensed",
        store="title_only",
        licence="Per-subscriber licence",
        terms_quote="Licensed per subscriber (docs/legal/DATA_SOURCE_TERMS.md, licensed "
        "families)",
        terms_url="docs/legal/DATA_SOURCE_TERMS.md",
        terms_read_on="",
        attribution="",
        notes="A paid news feed would be a licensed family under GOV-1, read with the "
        "customer's own credentials; none is shipped or polled.",
    ),
    NewsSource(
        source_id="eex-website",
        publisher="EEX AG",
        title="EEX website news",
        kind="rss",
        feed_url=None,
        home_url="https://www.eex.com/",
        language="en",
        poll_minutes=0,
        reuse="forbidden",
        store="title_only",
        licence="EEX website copyright notice",
        terms_quote='"... may be copied, reprinted, published, transmitted ... without the '
        'prior written approval of EEX AG" except "a single copy for exclusive personal, '
        'non-commercial use"',
        terms_url="https://www.eex.com/en/disclaimer",
        terms_read_on="2026-11-18",
        attribution="",
        notes="Reuse in a commercial product needs EEX's written approval.",
    ),
    NewsSource(
        source_id="lng-operator-sites",
        publisher="Fluxys LNG, Elengy",
        title="LNG terminal operators' websites",
        kind="rss",
        feed_url=None,
        home_url="https://www.fluxys.com/",
        language="en",
        poll_minutes=0,
        reuse="forbidden",
        store="title_only",
        licence="Operators' legal notices",
        terms_quote='Fluxys: "No reproduction ... without the prior written consent of '
        'Fluxys"; Elengy: reproduction "without the express permission of Elengy is strictly '
        'forbidden"',
        terms_url="docs/legal/DATA_SOURCE_TERMS.md",
        terms_read_on="2026-11-18",
        attribution="",
        notes="Their outages reach the product as REMIT messages, which they must publish.",
    ),
    NewsSource(
        source_id="national-regulators-unread",
        publisher="Bundesnetzagentur, CRE, ARERA, Ofgem and other national regulators",
        title="National regulators' press releases",
        kind="rss",
        feed_url=None,
        home_url="https://www.bundesnetzagentur.de/",
        language="de",
        poll_minutes=0,
        reuse="unknown",
        store="title_only",
        licence="Not read",
        terms_quote="",
        terms_url="",
        terms_read_on="",
        attribution="",
        notes="Terms not read in this build; each is added with its quoted terms once read.",
    ),
)

NEWS_SOURCES_BY_ID: dict[str, NewsSource] = {
    source.source_id: source for source in (*NEWS_SOURCES, *EXCLUDED_SOURCES)
}


def news_source(source_id: str) -> NewsSource:
    """The registered source, or ``KeyError``."""

    try:
        return NEWS_SOURCES_BY_ID[source_id]
    except KeyError as exc:
        raise KeyError(f"news source {source_id!r} is not in the registry") from exc


def feed_url_refusal(source: NewsSource, url: str) -> str:
    """Why ``url`` may not be read as this source's feed, or ``""``.

    A feed address must be ``https`` and on the publisher's own host (with or without its
    ``www.``) or a subdomain of that host, so an operator cannot point a permitted source at
    another publisher: ``www.gov.uk`` admits ``gov.uk`` but not every ``*.gov.uk`` site.
    """

    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        return "a feed address must be https"
    if parts.username or parts.password:
        return "a feed address carries no credentials"
    home = source.home_host
    base = home.removeprefix("www.")
    if not base or not (host in {home, base} or host.endswith("." + home)):
        return f"{host or 'the address'} is not the publisher's host {home}"
    return ""


def poll_refusal(source: NewsSource, *, feed_url: str | None = None) -> str:
    """Why the source may not be polled now, or ``""`` (see the module text)."""

    if source.kind == "remit_held":
        return "made from the REMIT messages the platform holds; nothing is fetched"
    if source.reuse != "permitted":
        return f"reuse is {source.reuse}: not polled"
    if not source.terms_read_on:
        return "terms not read: not polled"
    address = feed_url or source.feed_url
    if not address:
        return "no feed address recorded"
    return feed_url_refusal(source, address)


def registry_rows() -> list[dict[str, object]]:
    """Every source, polled or not, as the API and the docs list it."""

    rows = []
    for source in (*NEWS_SOURCES, *EXCLUDED_SOURCES):
        refusal = poll_refusal(source)
        rows.append(
            {
                "source_id": source.source_id,
                "publisher": source.publisher,
                "title": source.title,
                "kind": source.kind,
                "feed_url": source.feed_url,
                "home_url": source.home_url,
                "language": source.language,
                "poll_minutes": source.poll_minutes,
                "reuse": source.reuse,
                "store": source.store,
                "licence": source.licence,
                "terms_quote": source.terms_quote,
                "terms_url": source.terms_url,
                "terms_read_on": source.terms_read_on or None,
                "attribution": source.attribution,
                "feed_confirmed": source.feed_confirmed,
                "polled": refusal == "",
                "included": source in NEWS_SOURCES,
                "not_polled_because": refusal or None,
                "notes": source.notes,
            }
        )
    return rows


__all__ = [
    "EXCLUDED_SOURCES",
    "KINDS",
    "NEWS_SOURCES",
    "NEWS_SOURCES_BY_ID",
    "REUSE",
    "STORE",
    "NewsSource",
    "feed_url_refusal",
    "news_source",
    "poll_refusal",
    "registry_rows",
]
