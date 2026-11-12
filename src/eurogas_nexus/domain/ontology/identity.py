"""Naming things once: a provider's or a person's text resolved to a canonical hub.

A hub used to be guessed from text: the first word of a product name, or any hub code found
as a substring of a delivery point, with NBP when nothing matched. "Rotterdam, Netherlands"
contains ``THE`` and became the German hub; a misspelt point silently became NBP and was
valued there. This module resolves a hub by rule and admits when it cannot:

1. a hub code or a registered alias as a whole word (``TTF``, ``NBP Day-Ahead``);
2. a known physical delivery point that belongs to one hub's balancing zone;
3. otherwise ``None``: unresolved, to be listed and mapped by a person, never defaulted.

The registry of delivery points is deliberately small and explicit. A deployment adds its
own through ``points`` (from its mapping table); nothing here reads a database.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from eurogas_nexus.domain.ontology.markets import Commodity, MarketStatus, markets

#: Physical entry terminals and interconnection points, by the hub whose zone they are in.
DELIVERY_POINT_HUBS: Mapping[str, str] = {
    "EASINGTON": "NBP",
    "ST FERGUS": "NBP",
    "ST. FERGUS": "NBP",
    "BACTON": "NBP",
    "TEESSIDE": "NBP",
    "BARROW": "NBP",
    "MILFORD HAVEN": "NBP",
    "ISLE OF GRAIN": "NBP",
    "GATE TERMINAL": "TTF",
    "EEMSHAVEN": "TTF",
    "ZEEBRUGGE": "ZTP",
    "DUNKERQUE": "PEG",
    "MONTOIR": "PEG",
    "FOS": "PEG",
    "DORNUM": "THE",
    "WILHELMSHAVEN": "THE",
    "BRUNSBUTTEL": "THE",
    "BAUMGARTEN": "CEGH",
}


@dataclass(frozen=True)
class HubResolution:
    """The hub a text names, and how that was decided."""

    hub: str | None
    #: ``code``, ``alias``, ``delivery_point``, ``mapping`` or ``unresolved``.
    basis: str
    text: str = ""

    @property
    def resolved(self) -> bool:
        return self.hub is not None


def _hub_names() -> dict[str, tuple[str, str]]:
    """Upper-cased code or alias -> (canonical code, ``code`` or ``alias``)."""

    names: dict[str, tuple[str, str]] = {}
    for market in markets(
        commodity=(Commodity.NATURAL_GAS, Commodity.LNG),
        include=(MarketStatus.ACTIVE, MarketStatus.SUPERSEDED),
    ):
        names[market.code.upper()] = (market.code, "code")
        for alias in market.aliases:
            names.setdefault(alias.upper(), (market.code, "alias"))
    return names


_ANY_CASE_WORD = re.compile(r"[A-Za-z0-9_]+")
#: Hub codes that are ordinary English words ("the hub" is not Trading Hub Europe).
_ENGLISH_WORDS = frozenset({"THE"})


def resolve_hub(text: str | None, *, points: Mapping[str, str] | None = None) -> HubResolution:
    """Resolve ``text`` to a hub, or say that it does not resolve.

    Args:
        text: A product name, a hub field or a delivery-point name.
        points: The deployment's own delivery-point mappings (upper-cased name -> hub),
            consulted before the built-in registry.
    """

    original = str(text or "").strip()
    upper = original.upper()
    if not upper:
        return HubResolution(None, "unresolved", original)
    names = _hub_names()
    found = {
        names[word.upper()]
        for word in _ANY_CASE_WORD.findall(original)
        # A code that is also an English word counts only as written, in capitals.
        if word.upper() in names and (word.upper() not in _ENGLISH_WORDS or word.isupper())
    }
    if len({hub for hub, _ in found}) == 1:
        hub, basis = sorted(found)[0]
        return HubResolution(hub, basis, original)
    if len(found) > 1:
        return HubResolution(None, "unresolved", original)  # two hubs named: ambiguous
    for registry, basis in ((points or {}, "mapping"), (DELIVERY_POINT_HUBS, "delivery_point")):
        matches = {
            hub
            for name, hub in registry.items()
            if re.search(rf"(?<![A-Z0-9]){re.escape(name.upper())}(?![A-Z0-9])", upper)
        }
        if len(matches) == 1:
            return HubResolution(matches.pop(), basis, original)
        if len(matches) > 1:
            return HubResolution(None, "unresolved", original)
    return HubResolution(None, "unresolved", original)
