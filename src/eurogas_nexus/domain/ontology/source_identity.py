"""Provider identifiers resolved to canonical entities, never guessed (ONT-02).

A provider names things by its own stable identifiers: an ENTSOG point key (``ITP-00106``)
and operator key (``BE-TSO-0001``), a GIE country code (``DE``, ``eu`` for the Europe
total), a National Gas publication id (``PUBOB637``), an ENTSO-E or Elexon bidding zone
(``DE_LU``, ``GB``). :func:`resolve_identifier` turns one into the canonical entity id the
rest of the product uses, through ``source_entity_mappings`` rows (the deployment's table)
and the built-in mappings below. An identifier that resolves to nothing is **quarantined**:
reported with a reason (``unknown_identifier``, ``ambiguous_identifier``,
``empty_identifier``) and listed for an operator, never matched by a name fragment or a
first word.

Canonical ids are the ones the research datasets already carry
(``ent:point:<key>``, ``ent:storage_site:<code>``, ``ent:lng_terminal:<code>``,
``ent:bidding_zone:<zone>``, ``ent:market_hub:<code>``), so a stored snapshot's entity ids
do not change. Hubs in free text (a delivery point, a product name) resolve through
``ontology.identity.resolve_hub`` with the deployment's ``delivery_point`` mappings.

Pure: no database. ``application.identity_resolution`` loads the table.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

#: Entity types a provider identifier can name, and the canonical id prefix of each.
ENTITY_PREFIX: Mapping[str, str] = {
    "entsog_point": "ent:point",
    "entsog_operator": "ent:operator",
    "gie_storage_country": "ent:storage_site",
    "gie_lng_country": "ent:lng_terminal",
    "national_gas_storage": "ent:storage_site",
    "national_gas_lng": "ent:lng_terminal",
    "national_gas_publication": "ent:publication",
    "bidding_zone": "ent:bidding_zone",
    "market_hub": "ent:market_hub",
    "delivery_point": "ent:market_hub",
    # One storage site or LNG terminal by its EIC, from GIE's facility listing (identity
    # only: GIE publishes no position). Not the country aggregates above.
    "gie_facility": "ent:gas_facility",
}

QUARANTINE_REASONS = ("empty_identifier", "unknown_identifier", "ambiguous_identifier")

#: Countries GIE AGSI+/ALSI publish under (ISO 3166 alpha-2, ``eu`` the Europe total as the
#: provider spells it), from the platform's country listing.
GIE_COUNTRIES = (
    "AT", "BE", "BG", "CZ", "DE", "DK", "ES", "FR", "GB", "HR", "HU", "IE", "IT", "LT",
    "LV", "NL", "PL", "PT", "RO", "SE", "SK", "eu",
)
#: Bidding zones the power connectors read (ENTSO-E A44/A65/A75; Elexon is GB).
ENTSOE_ZONES = ("GB", "NL", "DE_LU", "BE", "FR", "AT", "IT_NORD", "ES")
#: National Gas data-portal publications the connectors read.
NATIONAL_GAS_DEMAND_PUBLICATIONS = ("PUBOB637", "PUBOB652")
NATIONAL_GAS_SUPPLY_PUBLICATIONS = (
    "PUBOBJ330", "PUBOBJ336", "PUBOBJ517", "PUBOBJ521", "PUBOBJ518", "PUBOBJ1149",
    "PUBOBJ1155", "PUBOBJ1150",
)


@dataclass(frozen=True)
class SourceIdentity:
    """One mapping: a source's identifier for an entity, and the canonical entity it names."""

    source_id: str
    entity_type: str
    identifier: str
    canonical_entity_id: str
    evidence: str = ""


@dataclass(frozen=True)
class IdentifierResolution:
    source_id: str
    entity_type: str
    identifier: str
    canonical_entity_id: str | None
    #: ``mapping`` (the deployment's table), ``builtin`` or ``quarantined``.
    basis: str
    reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.canonical_entity_id is not None


def canonical_id(entity_type: str, code: str) -> str:
    """The canonical id for a provider entity type and its code."""

    return f"{ENTITY_PREFIX[entity_type]}:{code}"


def _builtin() -> tuple[SourceIdentity, ...]:
    rows: list[SourceIdentity] = []
    for code in GIE_COUNTRIES:
        rows.append(SourceIdentity("src-gie", "gie_storage_country", code,
                                   canonical_id("gie_storage_country", code),
                                   "GIE AGSI+ country series"))
        rows.append(SourceIdentity("src-gie", "gie_lng_country", code,
                                   canonical_id("gie_lng_country", code),
                                   "GIE ALSI country series"))
    for zone in ENTSOE_ZONES:
        rows.append(SourceIdentity("src-entsoe", "bidding_zone", zone,
                                   canonical_id("bidding_zone", zone), "ENTSO-E bidding zone"))
    rows.append(SourceIdentity("src-elexon", "bidding_zone", "GB",
                               canonical_id("bidding_zone", "GB"), "Elexon BMRS: GB"))
    for item in NATIONAL_GAS_DEMAND_PUBLICATIONS:
        rows.append(SourceIdentity("src-national-gas-demand", "national_gas_publication", item,
                                   canonical_id("national_gas_publication", item),
                                   "National Gas data portal publication"))
    for item in NATIONAL_GAS_SUPPLY_PUBLICATIONS:
        rows.append(SourceIdentity("src-national-gas-supply", "national_gas_publication", item,
                                   canonical_id("national_gas_publication", item),
                                   "National Gas data portal publication"))
    rows.append(SourceIdentity("src-national-gas-supply", "national_gas_storage",
                               "GB-NTS-STORAGE",
                               canonical_id("national_gas_storage", "GB-NTS-STORAGE"),
                               "GB storage aggregate (National Gas)"))
    rows.append(SourceIdentity("src-national-gas-supply", "national_gas_lng", "GB-NTS-LNG",
                               canonical_id("national_gas_lng", "GB-NTS-LNG"),
                               "GB LNG aggregate (National Gas)"))
    return tuple(rows)


#: Identifiers the product knows without a table row: providers whose identifiers are a
#: short, published, stable list. ENTSOG point and operator keys come from the provider's
#: own reference read (``application.identity_resolution.entsog_reference_identities``).
BUILTIN_SOURCE_IDENTITIES: tuple[SourceIdentity, ...] = _builtin()

MappingKey = tuple[str, str, str]


def mapping_index(identities: Iterable[SourceIdentity]) -> dict[MappingKey, set[str]]:
    """(source, entity type, identifier) -> canonical ids (more than one is ambiguous)."""

    index: dict[MappingKey, set[str]] = {}
    for item in identities:
        index.setdefault(
            (item.source_id, item.entity_type, item.identifier), set()
        ).add(item.canonical_entity_id)
    return index


def resolve_identifier(
    source_id: str,
    entity_type: str,
    identifier: str | None,
    *,
    mappings: Mapping[MappingKey, set[str]] | None = None,
) -> IdentifierResolution:
    """Resolve one provider identifier: the deployment's mappings first, then built-ins.

    No name fragment, prefix or first word is ever tried: an identifier with no mapping is
    quarantined (``unknown_identifier``); one mapped to two entities is
    ``ambiguous_identifier``.
    """

    text = str(identifier or "").strip()
    if not text:
        return IdentifierResolution(source_id, entity_type, text, None, "quarantined",
                                    "empty_identifier")
    key = (source_id, entity_type, text)
    for index, basis in ((mappings or {}, "mapping"), (_BUILTIN_INDEX, "builtin")):
        found = index.get(key)
        if not found:
            continue
        if len(found) > 1:
            return IdentifierResolution(source_id, entity_type, text, None, "quarantined",
                                        "ambiguous_identifier")
        return IdentifierResolution(source_id, entity_type, text, next(iter(found)), basis)
    return IdentifierResolution(source_id, entity_type, text, None, "quarantined",
                                "unknown_identifier")


_BUILTIN_INDEX = mapping_index(BUILTIN_SOURCE_IDENTITIES)
