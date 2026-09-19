"""How each provider's timestamps are to be read — declared, versioned, and fail-closed.

Commercial readiness item **M1-P0**: *ENTSOG timezone normalization unproven; naive timestamps
treated as UTC → ENTSOG flow/capacity periods can be shifted or mis-labelled.* The parser this
module replaces did exactly that: ``datetime.replace(tzinfo=UTC)`` for any value without an offset,
which turns an ENTSOG gas day published as ``06:00`` in local time into ``06:00Z`` — an hour early
in winter, two hours early in summer.

The rule now has one home. Every source declares, once:

- the zone its instants are published in (or ``None`` when that is not proven),
- the payload key that may **override** it (and the tokens that override is allowed to name),
- what to do with a value that carries no offset: read it in the declared zone, or refuse it.

and the parser obeys the declaration:

- an instant that carries an explicit offset is **trusted** — never reinterpreted;
- an instant without one is read in the **declared** zone, or in the zone the payload itself
  declares and this contract supports;
- an instant whose zone cannot be proven is **refused**, never assumed to be UTC. A payload that
  declares a zone this contract does not support is refused whole, because every instant in it
  would otherwise be mislabelled.

Evidence and limits are in ``docs/data/SOURCE_TIMEZONE_CONTRACT.md``; the ENTSOG declaration is
consistent with the gas-day calendar this repository froze in M0-P0 (06:00 CET / 06:00 CEST =
05:00Z / 04:00Z), and the manual confirmation of the platform's default zone is an integration-time
check recorded there rather than a claim made here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

#: Central European Time with European Union daylight-saving rules. The platform's ``CET`` token
#: means CET/CEST (winter UTC+1, summer UTC+2), which is exactly ``Europe/Berlin``'s rule set.
_CENTRAL_EUROPEAN = ZoneInfo("Europe/Berlin")
_UTC = ZoneInfo("UTC")

#: Tokens a payload may use for Central European Time, in the spellings providers actually emit.
_CENTRAL_EUROPEAN_TOKENS = ("CET", "CEST", "EUROPE/BERLIN", "CENTRAL EUROPEAN TIME")
_UTC_TOKENS = ("UTC", "Z", "GMT", "EUROPE/LONDON")


class SourceTimezoneError(ValueError):
    """A payload whose instants cannot be placed in time without guessing.

    Raised rather than skipped, because guessing is the defect being fixed: the codes are stable so
    an operator sees *which* input could not be placed, and the ingest refuses the payload instead
    of writing periods that are an hour or two out.
    """

    def __init__(self, code: str, message: str, *, source_system: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.source_system = source_system


@dataclass(frozen=True)
class SourceTimezoneContract:
    """One source's declared timestamp semantics.

    Args:
        source_system: The registry id of the source (``ENTSOG``, ``GIE``, ...).
        datasets: Datasets this declaration covers; empty means all of them.
        declared_zone: The zone the source publishes its instants in, or ``None`` when that is not
            proven — in which case a value without an offset is refused.
        zone_key: The payload key that may state the zone (``timeZone`` for ENTSOG). ``None`` when
            the payload never states one.
        supported_tokens: Tokens the ``zone_key`` may name, mapped to the zone they mean. A token
            outside this map is refused: a zone the contract does not support must not fall back to
            UTC, because its summer offset may differ from its winter one.
        evidence: Where the declaration comes from, so a reader can disagree with it.
    """

    source_system: str
    declared_zone: ZoneInfo | None
    datasets: tuple[str, ...] = ()
    zone_key: str | None = None
    supported_tokens: tuple[tuple[str, ZoneInfo], ...] = ()
    evidence: str = ""

    def supports(self, dataset: str | None) -> bool:
        """Whether this declaration covers a dataset (an empty declaration covers all)."""

        return not self.datasets or (dataset or "") in self.datasets

    def zone_for_token(self, token: str) -> ZoneInfo:
        """The zone a payload token names, or a refusal naming the token."""

        normalized = token.strip().upper()
        for name, zone in self.supported_tokens:
            if normalized == name:
                return zone
        raise SourceTimezoneError(
            "unsupported_source_timezone",
            (
                f"{self.source_system} declares the response time zone {token!r}, which this "
                "contract does not support; refusing the payload rather than reading its instants "
                "as UTC."
            ),
            source_system=self.source_system,
        )


#: The declarations. One place, so no normalizer decides for itself what a bare timestamp means.
SOURCE_TIMEZONE_CONTRACTS: tuple[SourceTimezoneContract, ...] = (
    SourceTimezoneContract(
        source_system="ENTSOG",
        datasets=("operationaldatas",),
        declared_zone=_CENTRAL_EUROPEAN,
        zone_key="timeZone",
        supported_tokens=(
            ("CET", _CENTRAL_EUROPEAN),
            ("CEST", _CENTRAL_EUROPEAN),
            ("UTC", _UTC),
            ("Z", _UTC),
        ),
        evidence=(
            "ENTSOG Transparency Platform operational data publishes gas-day periods on the "
            "Central European clock (06:00 CET / 06:00 CEST), which is the convention this "
            "repository's frozen gas-day calendar EU-CAM-UTC-2025 encodes as 05:00Z / 04:00Z. "
            "Manual confirmation of the platform's default response zone is recorded as an "
            "integration-time check in docs/data/SOURCE_TIMEZONE_CONTRACT.md."
        ),
    ),
    SourceTimezoneContract(
        source_system="GIE",
        datasets=("agsi", "alsi"),
        # Not proven for the feed's `updatedAt` freshness stamp: the gas-day dates it publishes go
        # through the CAM calendar instead, so a bare instant here is refused rather than shifted.
        declared_zone=None,
        zone_key=None,
        supported_tokens=(("UTC", _UTC), ("Z", _UTC)),
        evidence=(
            "docs/data/SOURCE_TIMEZONE_CONTRACT.md section 2: the AGSL/ALSI gas-day dates are "
            "handled by the CAM calendar; the `updatedAt` freshness stamp has no proven zone in "
            "this repository, so a value without an offset is refused."
        ),
    ),
)


def contract_for(source_system: str, dataset: str | None = None) -> SourceTimezoneContract:
    """The declaration covering one source and dataset.

    A source with no declaration gets a contract that refuses every bare instant: an undeclared
    source is exactly the case this module exists to stop guessing about.
    """

    for contract in SOURCE_TIMEZONE_CONTRACTS:
        if contract.source_system == source_system and contract.supports(dataset):
            return contract
    return SourceTimezoneContract(
        source_system=source_system,
        declared_zone=None,
        evidence="no declaration: undeclared sources refuse instants without an offset",
    )


def resolve_payload_zone(
    contract: SourceTimezoneContract,
    payload: dict[str, object] | None,
) -> ZoneInfo | None:
    """The zone a payload declares, or the contract's own.

    A payload that states a zone the contract does not support is refused here — before any row is
    interpreted — because every instant in it would otherwise be read in the wrong zone.
    """

    if contract.zone_key and payload:
        stated = payload.get(contract.zone_key)
        if isinstance(stated, str) and stated.strip():
            return contract.zone_for_token(stated)
    return contract.declared_zone


def parse_source_instant(
    value: object,
    *,
    contract: SourceTimezoneContract,
    zone: ZoneInfo | None,
) -> datetime | None:
    """One provider instant, in UTC, or a refusal when its zone cannot be proven.

    Args:
        value: The raw field value (ISO-8601, with or without an offset).
        contract: The source's declaration.
        zone: The zone resolved for this payload (``None`` when the contract declares none).

    Returns:
        The instant in UTC, or ``None`` when the field is empty or unreadable. An unreadable value
        is a row-level problem and the caller skips the row; an *unplaceable* one is not, and is
        raised.

    Raises:
        SourceTimezoneError: ``unprovable_source_timezone`` when the value carries no offset and no
            zone is proven for it.
    """

    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        # An explicit offset is the provider's own statement and is never reinterpreted.
        return parsed.astimezone(UTC)
    if zone is None:
        raise SourceTimezoneError(
            "unprovable_source_timezone",
            (
                f"{contract.source_system} instant {value!r} carries no offset and this contract "
                "proves no zone for it; refusing it rather than reading it as UTC."
            ),
            source_system=contract.source_system,
        )
    return parsed.replace(tzinfo=zone).astimezone(UTC)
