"""Deterministic tags for a news item: what it names and what kind of event it is (NEWS-1).

Tagging needs no model, so the news core works with AI switched off. Two passes over the
title and summary:

* **Entities** from the platform's ontology and a reviewed gazetteer: gas hubs (the market
  registry, ``domain/ontology/markets``; a hub code matches only as written in capitals, so "the"
  is never Trading Hub Europe), countries, LNG terminals, pipelines, transmission and supply
  operators (TSOs), fields and processing plants, and the vessels of the firm's own cargoes
  (passed in by the caller, never guessed). Each entity names its country and, where it is a
  fact of where the asset sits or lands, the hubs it serves: a terminal sits in a hub's market
  area; a pipeline lands gas at a hub's market area (Langeled at Easington: NBP). Nothing is
  inferred from flows or prices.
* **Event types** from closed keyword lists: ``outage``, ``sanction``, ``policy``,
  ``weather``, ``strike``, ``geopolitical``; a REMIT message is always an ``outage``.
  ``capacity_change`` is set when an outage or a capacity word is stated.

A tag says what the text names, not that the text is right; the item's source and its link
travel with it.

新闻确定性标注：按本体与审定的地名表识别枢纽、国家、接收站、管道、TSO、气田与公司船舶；
按封闭关键词表识别事件类型。无需模型。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

EVENT_TYPES = ("outage", "sanction", "policy", "weather", "strike", "geopolitical")
ENTITY_KINDS = ("hub", "country", "terminal", "pipeline", "tso", "field", "vessel")


@dataclass(frozen=True, slots=True)
class Entity:
    """One thing an item names."""

    entity_id: str
    kind: str
    name: str
    country: str = ""
    #: Hubs the entity serves as a matter of where it sits or lands (see the module text).
    hubs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "kind": self.kind,
            "name": self.name,
            "country": self.country or None,
            "hubs": list(self.hubs),
        }


@dataclass(frozen=True, slots=True)
class Tags:
    """The tags of one item."""

    entities: tuple[Entity, ...] = ()
    event_types: tuple[str, ...] = ()
    capacity_change: bool = False
    hubs: tuple[str, ...] = field(default=())
    countries: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict[str, object]:
        return {
            "entities": [entity.as_dict() for entity in self.entities],
            "event_types": list(self.event_types),
            "capacity_change": self.capacity_change,
            "hubs": list(self.hubs),
            "countries": list(self.countries),
        }


#: Country (ISO 3166 alpha-2) -> the hub whose market area it is (the market registry's own
#: country of each hub; Denmark's exchange hub ETF).
_COUNTRY_HUB = {
    "NL": "TTF", "GB": "NBP", "DE": "THE", "FR": "PEG", "BE": "ZTP", "IT": "PSV",
    "AT": "CEGH", "ES": "PVB", "DK": "ETF",
}

_COUNTRIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("NL", "Netherlands", ("Netherlands", "Dutch", "Holland")),
    ("GB", "United Kingdom", ("United Kingdom", "Britain", "British", "UK", "Great Britain")),
    ("DE", "Germany", ("Germany", "German")),
    ("FR", "France", ("France", "French")),
    ("BE", "Belgium", ("Belgium", "Belgian")),
    ("IT", "Italy", ("Italy", "Italian")),
    ("AT", "Austria", ("Austria", "Austrian")),
    ("ES", "Spain", ("Spain", "Spanish")),
    ("DK", "Denmark", ("Denmark", "Danish")),
    ("NO", "Norway", ("Norway", "Norwegian")),
    ("PL", "Poland", ("Poland", "Polish")),
    ("CZ", "Czechia", ("Czechia", "Czech Republic", "Czech")),
    ("SK", "Slovakia", ("Slovakia", "Slovak")),
    ("HU", "Hungary", ("Hungary", "Hungarian")),
    ("UA", "Ukraine", ("Ukraine", "Ukrainian")),
    ("RU", "Russia", ("Russia", "Russian")),
    ("TR", "Türkiye", ("Türkiye", "Turkey", "Turkish")),
    ("AZ", "Azerbaijan", ("Azerbaijan", "Azerbaijani")),
    ("DZ", "Algeria", ("Algeria", "Algerian")),
    ("LY", "Libya", ("Libya", "Libyan")),
    ("QA", "Qatar", ("Qatar", "Qatari")),
    ("US", "United States", ("United States", "U.S.", "USA")),
    ("NG", "Nigeria", ("Nigeria", "Nigerian")),
    ("EG", "Egypt", ("Egypt", "Egyptian")),
    ("PT", "Portugal", ("Portugal", "Portuguese")),
    ("GR", "Greece", ("Greece", "Greek")),
    ("HR", "Croatia", ("Croatia", "Croatian")),
    ("LT", "Lithuania", ("Lithuania", "Lithuanian")),
    ("FI", "Finland", ("Finland", "Finnish")),
    ("IE", "Ireland", ("Ireland", "Irish")),
    ("CH", "Switzerland", ("Switzerland", "Swiss")),
)

#: (id, kind, name, aliases, country, hubs). Reviewed by hand; a hub only where the asset sits
#: in or lands into that hub's market area.
_GAZETTEER: tuple[tuple[str, str, str, tuple[str, ...], str, tuple[str, ...]], ...] = (
    # LNG terminals.
    ("terminal:gate", "terminal", "Gate terminal", ("Gate terminal", "Gate LNG"), "NL", ("TTF",)),
    ("terminal:eemshaven", "terminal", "Eemshaven LNG", ("Eemshaven", "EemsEnergyTerminal"),
     "NL", ("TTF",)),
    ("terminal:zeebrugge", "terminal", "Zeebrugge LNG", ("Zeebrugge LNG",), "BE", ("ZTP",)),
    ("terminal:dunkerque", "terminal", "Dunkerque LNG", ("Dunkerque LNG", "Dunkirk LNG"), "FR",
     ("PEG",)),
    ("terminal:montoir", "terminal", "Montoir-de-Bretagne", ("Montoir",), "FR", ("PEG",)),
    ("terminal:fos", "terminal", "Fos (Cavaou, Tonkin)",
     ("Fos Cavaou", "Fos Tonkin", "Fos-sur-Mer"), "FR", ("PEG",)),
    ("terminal:le-havre", "terminal", "Le Havre FSRU", ("Le Havre",), "FR", ("PEG",)),
    ("terminal:grain", "terminal", "Isle of Grain", ("Isle of Grain", "Grain LNG"), "GB", ("NBP",)),
    ("terminal:south-hook", "terminal", "South Hook LNG", ("South Hook",), "GB", ("NBP",)),
    ("terminal:dragon", "terminal", "Dragon LNG", ("Dragon LNG",), "GB", ("NBP",)),
    ("terminal:wilhelmshaven", "terminal", "Wilhelmshaven", ("Wilhelmshaven",), "DE", ("THE",)),
    ("terminal:brunsbuettel", "terminal", "Brunsbüttel", ("Brunsbüttel", "Brunsbuettel"), "DE",
     ("THE",)),
    ("terminal:mukran", "terminal", "Mukran (Deutsche Ostsee)", ("Mukran", "Deutsche Ostsee"),
     "DE", ("THE",)),
    ("terminal:stade", "terminal", "Stade", ("Stade LNG",), "DE", ("THE",)),
    ("terminal:rovigo", "terminal", "Adriatic LNG (Rovigo)", ("Adriatic LNG", "Rovigo"), "IT",
     ("PSV",)),
    ("terminal:panigaglia", "terminal", "Panigaglia", ("Panigaglia",), "IT", ("PSV",)),
    ("terminal:olt", "terminal", "OLT Offshore Toscana", ("OLT", "Toscana FSRU"), "IT", ("PSV",)),
    ("terminal:piombino", "terminal", "Piombino FSRU", ("Piombino",), "IT", ("PSV",)),
    ("terminal:ravenna", "terminal", "Ravenna FSRU", ("Ravenna",), "IT", ("PSV",)),
    ("terminal:barcelona", "terminal", "Barcelona LNG", ("Barcelona LNG",), "ES", ("PVB",)),
    ("terminal:huelva", "terminal", "Huelva LNG", ("Huelva",), "ES", ("PVB",)),
    ("terminal:cartagena", "terminal", "Cartagena LNG", ("Cartagena LNG",), "ES", ("PVB",)),
    ("terminal:sagunto", "terminal", "Sagunto LNG", ("Sagunto",), "ES", ("PVB",)),
    ("terminal:bilbao", "terminal", "Bilbao LNG (BBG)", ("Bilbao LNG", "BBG"), "ES", ("PVB",)),
    ("terminal:mugardos", "terminal", "Mugardos (Reganosa)", ("Mugardos", "Reganosa"), "ES",
     ("PVB",)),
    ("terminal:swinoujscie", "terminal", "Świnoujście LNG", ("Świnoujście", "Swinoujscie"), "PL",
     ()),
    ("terminal:klaipeda", "terminal", "Klaipėda FSRU", ("Klaipėda", "Klaipeda"), "LT", ()),
    ("terminal:revithoussa", "terminal", "Revithoussa", ("Revithoussa",), "GR", ()),
    ("terminal:krk", "terminal", "Krk LNG", ("Krk LNG", "Krk"), "HR", ()),
    ("terminal:sines", "terminal", "Sines LNG", ("Sines",), "PT", ()),
    ("terminal:inkoo", "terminal", "Inkoo FSRU", ("Inkoo",), "FI", ()),
    ("terminal:ras-laffan", "terminal", "Ras Laffan", ("Ras Laffan",), "QA", ()),
    ("terminal:sabine-pass", "terminal", "Sabine Pass LNG", ("Sabine Pass",), "US", ()),
    ("terminal:freeport", "terminal", "Freeport LNG", ("Freeport LNG",), "US", ()),
    ("terminal:corpus-christi", "terminal", "Corpus Christi LNG", ("Corpus Christi",), "US", ()),
    ("terminal:cameron", "terminal", "Cameron LNG", ("Cameron LNG",), "US", ()),
    ("terminal:calcasieu", "terminal", "Calcasieu Pass", ("Calcasieu Pass",), "US", ()),
    ("terminal:plaquemines", "terminal", "Plaquemines LNG", ("Plaquemines",), "US", ()),
    ("terminal:hammerfest", "terminal", "Hammerfest LNG (Melkøya)", ("Hammerfest LNG", "Melkøya",
     "Melkoya"), "NO", ()),
    # Pipelines: the hubs of the market areas they land gas into.
    ("pipeline:langeled", "pipeline", "Langeled", ("Langeled",), "NO", ("NBP",)),
    ("pipeline:vesterled", "pipeline", "Vesterled", ("Vesterled",), "NO", ("NBP",)),
    ("pipeline:europipe", "pipeline", "Europipe I/II", ("Europipe", "Europipe II"), "NO",
     ("THE",)),
    ("pipeline:norpipe", "pipeline", "Norpipe", ("Norpipe",), "NO", ("THE",)),
    ("pipeline:zeepipe", "pipeline", "Zeepipe", ("Zeepipe",), "NO", ("ZTP",)),
    ("pipeline:franpipe", "pipeline", "Franpipe", ("Franpipe",), "NO", ("PEG",)),
    ("pipeline:iuk", "pipeline", "Interconnector (IUK)", ("Interconnector UK", "IUK"), "GB",
     ("NBP", "ZTP")),
    ("pipeline:bbl", "pipeline", "BBL", ("BBL", "Balgzand Bacton"), "NL", ("TTF", "NBP")),
    ("pipeline:nord-stream", "pipeline", "Nord Stream", ("Nord Stream",), "DE", ("THE",)),
    ("pipeline:turkstream", "pipeline", "TurkStream", ("TurkStream", "Turkish Stream"), "TR", ()),
    ("pipeline:tap", "pipeline", "Trans Adriatic Pipeline", ("Trans Adriatic Pipeline", "TAP"),
     "IT", ("PSV",)),
    ("pipeline:baltic-pipe", "pipeline", "Baltic Pipe", ("Baltic Pipe",), "PL", ()),
    ("pipeline:medgaz", "pipeline", "Medgaz", ("Medgaz",), "ES", ("PVB",)),
    ("pipeline:transmed", "pipeline", "Transmed", ("Transmed", "TransMed"), "IT", ("PSV",)),
    ("pipeline:greenstream", "pipeline", "Greenstream", ("Greenstream",), "IT", ("PSV",)),
    ("pipeline:tag", "pipeline", "Trans Austria Gasleitung", ("Trans Austria Gasleitung",), "AT",
     ("CEGH",)),
    # Transmission and supply operators.
    ("tso:gts", "tso", "Gasunie Transport Services", ("Gasunie Transport Services", "GTS",
     "Gasunie"), "NL", ("TTF",)),
    ("tso:national-gas", "tso", "National Gas Transmission", ("National Gas Transmission",
     "National Gas"), "GB", ("NBP",)),
    ("tso:oge", "tso", "Open Grid Europe", ("Open Grid Europe", "OGE"), "DE", ("THE",)),
    ("tso:gascade", "tso", "GASCADE", ("GASCADE", "Gascade"), "DE", ("THE",)),
    ("tso:ontras", "tso", "ONTRAS", ("ONTRAS",), "DE", ("THE",)),
    ("tso:grtgaz", "tso", "GRTgaz", ("GRTgaz",), "FR", ("PEG",)),
    ("tso:terega", "tso", "Teréga", ("Teréga", "Terega"), "FR", ("PEG",)),
    ("tso:fluxys", "tso", "Fluxys Belgium", ("Fluxys",), "BE", ("ZTP",)),
    ("tso:snam", "tso", "Snam", ("Snam",), "IT", ("PSV",)),
    ("tso:enagas", "tso", "Enagás", ("Enagás", "Enagas"), "ES", ("PVB",)),
    ("tso:gca", "tso", "Gas Connect Austria", ("Gas Connect Austria",), "AT", ("CEGH",)),
    ("tso:energinet", "tso", "Energinet", ("Energinet",), "DK", ("ETF",)),
    ("tso:gassco", "tso", "Gassco", ("Gassco",), "NO", ()),
    ("tso:gaz-system", "tso", "GAZ-SYSTEM", ("GAZ-SYSTEM", "Gaz-System"), "PL", ()),
    ("tso:eustream", "tso", "eustream", ("eustream", "Eustream"), "SK", ()),
    ("tso:net4gas", "tso", "NET4GAS", ("NET4GAS", "Net4Gas"), "CZ", ()),
    ("tso:gtsou", "tso", "Gas TSO of Ukraine", ("Gas TSO of Ukraine", "GTSOU"), "UA", ()),
    # Fields and processing plants.
    ("field:troll", "field", "Troll", ("Troll",), "NO", ()),
    ("field:kollsnes", "field", "Kollsnes", ("Kollsnes",), "NO", ()),
    ("field:karsto", "field", "Kårstø", ("Kårstø", "Karsto", "Kaarsto"), "NO", ()),
    ("field:nyhamna", "field", "Nyhamna", ("Nyhamna",), "NO", ()),
    ("field:ormen-lange", "field", "Ormen Lange", ("Ormen Lange",), "NO", ()),
    ("field:aasta-hansteen", "field", "Aasta Hansteen", ("Aasta Hansteen",), "NO", ()),
    ("field:oseberg", "field", "Oseberg", ("Oseberg",), "NO", ()),
    ("field:sleipner", "field", "Sleipner", ("Sleipner",), "NO", ()),
    ("field:asgard", "field", "Åsgard", ("Åsgard", "Asgard"), "NO", ()),
    ("field:snohvit", "field", "Snøhvit", ("Snøhvit", "Snohvit"), "NO", ()),
    ("field:groningen", "field", "Groningen", ("Groningen",), "NL", ("TTF",)),
    ("field:north-field", "field", "North Field", ("North Field",), "QA", ()),
)

EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "outage": (
        "outage", "outages", "unavailability", "unavailable", "unplanned", "maintenance",
        "shutdown", "shut down", "shut-in", "tripped", "force majeure", "curtailment",
        "curtailed", "reduced capacity", "interruption", "disruption", "offline", "leak",
    ),
    "sanction": (
        "sanction", "sanctions", "sanctioned", "embargo", "restrictive measures", "price cap",
        "import ban", "ban on imports", "designated", "designation", "phase-out of russian",
    ),
    "policy": (
        "regulation", "directive", "network code", "delegated act", "implementing act",
        "consultation", "official journal", "legislation", "law", "levy", "storage target",
        "filling target", "tariff", "tariffs", "regulator", "decision", "guidelines", "council",
        "parliament", "commission adopts", "methodology", "licence", "license",
    ),
    "weather": (
        "cold snap", "cold spell", "heatwave", "heat wave", "storm", "temperatures",
        "freezing", "frost", "hurricane", "low wind", "wind speeds", "high winds", "strong winds",
        "gale", "gales", "fog", "snow", "drought",
    ),
    "strike": (
        "strike", "strikes", "industrial action", "walkout", "walk-out", "union", "unions",
        "labour dispute", "labor dispute",
    ),
    "geopolitical": (
        "war", "conflict", "attack", "attacks", "military", "sabotage", "invasion",
        "ceasefire", "tensions", "missile", "drone", "red sea", "strait of hormuz", "suez",
        "blockade", "geopolitical",
    ),
}
_CAPACITY_WORDS = ("capacity", "send-out", "sendout", "flows", "throughput")


def _word_pattern(words: Iterable[str], *, case_sensitive: bool = False) -> re.Pattern[str]:
    alternatives = sorted({re.escape(word) for word in words}, key=len, reverse=True)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<![\w])(" + "|".join(alternatives) + r")(?![\w])", flags)


_EVENT_PATTERNS = {kind: _word_pattern(words) for kind, words in EVENT_KEYWORDS.items()}
_CAPACITY = _word_pattern(_CAPACITY_WORDS)


def _hub_entities() -> list[tuple[re.Pattern[str], Entity]]:
    from eurogas_nexus.domain.ontology.markets import Commodity, MarketStatus, markets

    out = []
    for market in markets(commodity=(Commodity.NATURAL_GAS,), include=(MarketStatus.ACTIVE,)):
        if market.country not in _COUNTRY_HUB and market.code not in _COUNTRY_HUB.values():
            continue
        entity = Entity(f"hub:{market.code}", "hub", market.code, market.country, (market.code,))
        # Codes only in capitals; the full name in any case.
        out.append((_word_pattern((market.code, *market.aliases), case_sensitive=True), entity))
        out.append((_word_pattern((market.name,)), entity))
    return out


_COMPILED: list[tuple[re.Pattern[str], Entity]] | None = None


def _compiled() -> list[tuple[re.Pattern[str], Entity]]:
    global _COMPILED
    if _COMPILED is None:
        table = _hub_entities()
        for code, name, forms in _COUNTRIES:
            hub = _COUNTRY_HUB.get(code)
            entity = Entity(f"country:{code}", "country", name, code, (hub,) if hub else ())
            short = tuple(form for form in forms if form.isupper() or "." in form)
            words = tuple(form for form in forms if form not in short)
            table.append((_word_pattern(words), entity))
            if short:
                table.append((_word_pattern(short, case_sensitive=True), entity))
        for entity_id, kind, name, aliases, country, hubs in _GAZETTEER:
            entity = Entity(entity_id, kind, name, country, hubs)
            acronyms = tuple(alias for alias in aliases if alias.isupper())
            words = tuple(alias for alias in aliases if not alias.isupper())
            if words:
                table.append((_word_pattern(words), entity))
            if acronyms:
                table.append((_word_pattern(acronyms, case_sensitive=True), entity))
        _COMPILED = table
    return _COMPILED


def gazetteer_size() -> int:
    """How many distinct entities the tagger knows (vessels aside)."""

    return len({entity.entity_id for _, entity in _compiled()})


def tag_text(
    text: str,
    *,
    vessels: Iterable[str] = (),
    remit: bool = False,
    zone_hubs: Iterable[str] = (),
) -> Tags:
    """The tags of ``text`` (see the module text).

    Args:
        text: Title and summary of the item.
        vessels: The names of the firm's own cargoes' vessels, matched as whole names.
        remit: The item is a REMIT unavailability message (always an ``outage``).
        zone_hubs: Hubs the source itself states (a REMIT message's balancing zone).
    """

    found: dict[str, Entity] = {}
    for pattern, entity in _compiled():
        if pattern.search(text):
            found.setdefault(entity.entity_id, entity)
    for vessel in vessels:
        name = " ".join(str(vessel).split())
        if len(name) >= 3 and _word_pattern((name,)).search(text):
            found.setdefault(f"vessel:{name.casefold()}", Entity(f"vessel:{name.casefold()}",
                                                                 "vessel", name))
    for hub in zone_hubs:
        found.setdefault(f"hub:{hub}", Entity(f"hub:{hub}", "hub", hub, "", (hub,)))
    events = [kind for kind in EVENT_TYPES if _EVENT_PATTERNS[kind].search(text)]
    if remit and "outage" not in events:
        events.insert(0, "outage")
    ordered = tuple(sorted(found.values(), key=lambda e: (ENTITY_KINDS.index(e.kind),
                                                          e.entity_id)))
    hubs = sorted({hub for entity in ordered for hub in entity.hubs})
    countries = sorted({entity.country for entity in ordered if entity.country})
    capacity = "outage" in events and (remit or bool(_CAPACITY.search(text)))
    return Tags(
        entities=ordered,
        event_types=tuple(events),
        capacity_change=capacity,
        hubs=tuple(hubs),
        countries=tuple(countries),
    )


def zone_hub(balancing_zone: str | None) -> str | None:
    """The hub of a REMIT balancing zone when the zone names one (a code or its country)."""

    from eurogas_nexus.domain.ontology.identity import resolve_hub

    text = (balancing_zone or "").strip()
    if not text:
        return None
    if text.upper() in _COUNTRY_HUB:
        return _COUNTRY_HUB[text.upper()]
    resolution = resolve_hub(text)
    return resolution.hub if resolution.resolved and resolution.hub in _COUNTRY_HUB.values() \
        else None


__all__ = [
    "ENTITY_KINDS",
    "EVENT_KEYWORDS",
    "EVENT_TYPES",
    "Entity",
    "Tags",
    "gazetteer_size",
    "tag_text",
    "zone_hub",
]
