"""The reviewed outage-asset alias table: load and check.

An unavailability message names its asset as its publisher chooses: a site EIC the
reference network does not carry, a group's member site, a name without an EIC. The map
places an outage only on a published position, so these assets stay unlocated unless they
can be tied to an identity the product already holds. ``outage_asset_aliases.json`` holds
those ties, one reviewed entry each, with the publishers' own evidence:

- ``match.asset_eic`` or ``match.asset_name`` (the message's asset) → ``gie_facility_eic``
  (a GIE AGSI/ALSI facility; a site of a virtual storage group maps to the group);
- ``match.gie_facility_eic`` → ``reference_point_key`` (an ENTSOG reference point that is
  that facility's grid connection).

No entry carries coordinates, and none is derived from a name by similarity: the position,
when there is one, is always the reference point's own.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

ALIAS_SCHEMA = "eurogas-nexus/outage-asset-aliases/1"
ALIAS_RESOURCE = "outage_asset_aliases.json"
_MATCH_KEYS = frozenset({"asset_eic", "asset_name", "gie_facility_eic"})
_TARGET_KEYS = frozenset({"gie_facility_eic", "reference_point_key"})


def alias_path() -> Path:
    return Path(str(resources.files("eurogas_nexus.reference_data").joinpath(ALIAS_RESOURCE)))


def name_key(text: str | None) -> str:
    """Case, accents, punctuation and spacing ignored (the map's exact-name rule)."""

    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(re.split(r"[^a-z0-9]+", folded.casefold())).strip()


def validate_aliases(table: dict[str, Any]) -> list[str]:
    """Integrity problems, empty when the table is sound.

    Every entry matches on exactly one key and names exactly one target of the kind that
    key allows, carries evidence and a review date, and no match is listed twice.
    """

    problems: list[str] = []
    if table.get("schema") != ALIAS_SCHEMA:
        problems.append(f"schema is {table.get('schema')!r}, expected {ALIAS_SCHEMA!r}")
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(table.get("entries") or []):
        match = entry.get("match") or {}
        if len(match) != 1 or not set(match) <= _MATCH_KEYS:
            problems.append(f"entry {index}: match must name one of {sorted(_MATCH_KEYS)}")
            continue
        (key, value), = match.items()
        targets = [k for k in _TARGET_KEYS if entry.get(k)]
        if len(targets) != 1:
            problems.append(f"entry {index}: exactly one target is required")
        elif key == "gie_facility_eic" and targets[0] != "reference_point_key":
            problems.append(f"entry {index}: a GIE facility maps to a reference point only")
        elif key != "gie_facility_eic" and targets[0] != "gie_facility_eic":
            problems.append(f"entry {index}: a message asset maps to a GIE facility only")
        if not str(entry.get("evidence") or "").strip():
            problems.append(f"entry {index}: evidence is required")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(entry.get("reviewed") or "")):
            problems.append(f"entry {index}: reviewed date is required")
        if any(k in entry for k in ("lat", "lon", "position", "coordinates")):
            problems.append(f"entry {index}: an alias never carries a position")
        normalised = (key, name_key(value) if key == "asset_name" else str(value).upper())
        if normalised in seen:
            problems.append(f"entry {index}: {key} {value!r} is listed twice")
        seen.add(normalised)
    return problems


class OutageAliases:
    """The table indexed for the map's placement (``application/map_situation``)."""

    def __init__(self, table: dict[str, Any]) -> None:
        self.version = str(table.get("version") or "")
        self.by_asset_eic: dict[str, dict[str, Any]] = {}
        self.by_asset_name: dict[str, dict[str, Any]] = {}
        self.point_for_facility: dict[str, dict[str, Any]] = {}
        for entry in table.get("entries") or []:
            match = entry["match"]
            if "asset_eic" in match:
                self.by_asset_eic[str(match["asset_eic"]).upper()] = entry
            elif "asset_name" in match:
                self.by_asset_name[name_key(match["asset_name"])] = entry
            else:
                self.point_for_facility[str(match["gie_facility_eic"]).upper()] = entry

    def facility_for(self, *, eic: str | None, name: str | None) -> dict[str, Any] | None:
        """The reviewed entry tying a message asset to a GIE facility, if any."""

        if eic and (hit := self.by_asset_eic.get(eic.strip().upper())):
            return hit
        if name and (hit := self.by_asset_name.get(name_key(name))):
            return hit
        return None

    def point_for(self, facility_eic: str | None) -> dict[str, Any] | None:
        return self.point_for_facility.get(str(facility_eic or "").upper())


@lru_cache(maxsize=1)
def shipped_aliases() -> OutageAliases:
    table = json.loads(alias_path().read_text(encoding="utf-8"))
    problems = validate_aliases(table)
    if problems:
        raise ValueError("outage alias table is unsound: " + "; ".join(problems))
    return OutageAliases(table)
