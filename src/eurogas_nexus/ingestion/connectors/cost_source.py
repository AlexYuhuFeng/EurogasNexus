"""Cost-source connector framework for TSO tariffs and LNG regas slots.

Real connectors implement ``fetch_cost_observations``. Skeleton connectors
return empty payloads until a source adapter is approved and credentialed.

The generic JSON connector is fail-closed: absent, null, boolean, non-finite or
malformed financial values, unsupported units and missing provenance are refused
before a :class:`CostObservation` exists. A refusal is typed, carries the
zero-based record index and field, and never repeats the payload, URL or
credentials.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from eurogas_nexus.domain.economics.cost_observation import (
    OBSERVATION_TYPES,
    SCOPE_TYPES,
    CostObservation,
)
from eurogas_nexus.ingestion.connectors.base import ConnectorMetadata

COST_SOURCE_MAX_RECORDS = 1000
COST_SOURCE_MAX_TEXT_LENGTH = 256

_MISSING = object()
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")

_BASE_UNITS = {
    "wh": "Wh",
    "kwh": "kWh",
    "mwh": "MWh",
    "gwh": "GWh",
    "twh": "TWh",
    "btu": "Btu",
    "mmbtu": "MMBtu",
    "therm": "therm",
    "th": "th",
    "gj": "GJ",
    "mj": "MJ",
    "kj": "kJ",
    "m3": "m3",
    "mm3": "Mm3",
    "bcm": "bcm",
    "kcm": "kcm",
}
_UNIT_SUFFIXES = ("", "/d", "/day", "/h", "/hr")
_SUPPORTED_UNITS = {
    f"{base}{suffix}": f"{canonical}{suffix}"
    for base, canonical in _BASE_UNITS.items()
    for suffix in _UNIT_SUFFIXES
}


class CostSourceRefusal(ValueError):
    """Base class for stable, payload-safe cost-source refusals.

    The string form deliberately contains only the stable code, zero-based
    record index and field name. It never repeats a value, URL, payload body or
    credential.
    """

    def __init__(
        self,
        code: str,
        *,
        record_index: int | None = None,
        field: str | None = None,
    ) -> None:
        self.code = code
        self.record_index = record_index
        self.field = field
        parts = [code]
        if record_index is not None:
            parts.append(f"record_index={record_index}")
        if field is not None:
            parts.append(f"field={field}")
        super().__init__(" ".join(parts))


class CostSourceJsonRefusal(CostSourceRefusal):
    """A malformed provider payload, envelope or record."""


class CostSourceHttpRefusal(CostSourceRefusal):
    """A provider HTTP status that is neither a payload nor an empty success."""

    def __init__(self, *, status_code: int) -> None:
        self.status_code = status_code
        super().__init__("COST_SOURCE_HTTP_REFUSED", field="response")


class CostSourceTransportRefusal(CostSourceRefusal):
    """A transport failure before a usable provider response existed."""


class CostSourceConfigurationRefusal(CostSourceRefusal):
    """The connector is not configured to make a safe request."""


class CostSourceConnector(Protocol):
    """Protocol for connectors that produce cost observations."""

    @property
    def metadata(self) -> ConnectorMetadata:
        """Source metadata including freshness expectations."""

        ...

    def fetch_cost_observations(self) -> tuple[CostObservation, ...]:
        """Fetch current cost observations (never mutates runtime rows)."""

        ...


@dataclass(frozen=True)
class SkeletonCostSourceConnector:
    """Skeleton TSO/LNG cost-source connector.

    It declares the source family and returns no observations until the real
    adapter is implemented and credentialed. This is the safe default for
    offline development and for uncredentialed production deployments.
    """

    source_system: str
    datasets: tuple[str, ...]
    freshness_expectation_minutes: int = 1440

    @property
    def metadata(self) -> ConnectorMetadata:
        """Metadata for the skeleton source."""

        return ConnectorMetadata(
            source_system=self.source_system,
            datasets=self.datasets,
            entitlement_required=True,
            freshness_expectation_minutes=self.freshness_expectation_minutes,
        )

    def fetch_cost_observations(self) -> tuple[CostObservation, ...]:
        """Return an empty observation set (skeleton source)."""

        return ()


def tso_tariff_skeleton() -> SkeletonCostSourceConnector:
    """Return a TSO tariff connector skeleton."""

    return SkeletonCostSourceConnector(
        source_system="TSO_TARIFFS",
        datasets=("published_tariffs",),
        freshness_expectation_minutes=1440,
    )


def lng_slot_skeleton() -> SkeletonCostSourceConnector:
    """Return an LNG regas slot connector skeleton."""

    return SkeletonCostSourceConnector(
        source_system="LNG_SLOTS",
        datasets=("terminal_tariffs", "slot_auctions"),
        freshness_expectation_minutes=1440,
    )


class JsonCostObservationConnector:
    """Machine-readable JSON cost-source connector.

    The source URL and HTTP getter are injected so production uses the bounded
    backend HTTP client while tests use a fake. The connector does not mutate
    runtime rows; it returns normalized domain observations. The connector's
    configured source identity is authoritative, never a value from the feed.
    """

    def __init__(
        self,
        *,
        source_system: str,
        datasets: tuple[str, ...],
        url: str,
        http_get=None,
    ) -> None:
        self._source_system = source_system
        self._datasets = datasets
        self._url = url
        self._http_get = http_get

    @property
    def metadata(self) -> ConnectorMetadata:
        """Metadata for this machine-readable connector."""

        return ConnectorMetadata(
            source_system=self._source_system,
            datasets=self._datasets,
            entitlement_required=False,
            polling_supported=True,
            request_mode_supported=True,
            freshness_expectation_minutes=1440,
            export_restricted=False,
        )

    def fetch_cost_observations(self) -> tuple[CostObservation, ...]:
        """Fetch and normalize the configured JSON cost-observation feed.

        An empty feed is a successful empty result. A non-success HTTP status,
        transport failure, malformed envelope or any invalid record refuses the
        whole batch before a domain observation is created.
        """

        if not self._url:
            return ()
        if not isinstance(self._url, str):
            raise CostSourceConfigurationRefusal(
                "COST_SOURCE_CONFIGURATION_INVALID", field="url"
            )
        source_system = _connector_source_system(self._source_system)
        if self._http_get is None:
            raise CostSourceConfigurationRefusal(
                "COST_SOURCE_CONFIGURATION_INVALID", field="http_get"
            )

        try:
            response = self._http_get(self._url)
        except CostSourceRefusal:
            raise
        except Exception:
            raise CostSourceTransportRefusal(
                "COST_SOURCE_TRANSPORT_FAILED", field="response"
            ) from None

        status = getattr(response, "status_code", _MISSING)
        if status is not _MISSING:
            if isinstance(status, bool) or not isinstance(status, int):
                raise CostSourceJsonRefusal(
                    "COST_SOURCE_HTTP_STATUS_INVALID", field="status_code"
                )
            if status == 204:
                return ()
            if status != 200:
                raise CostSourceHttpRefusal(status_code=status)

        if hasattr(response, "json"):
            try:
                payload = response.json()
            except CostSourceRefusal:
                raise
            except Exception:
                raise CostSourceJsonRefusal(
                    "COST_SOURCE_JSON_MALFORMED", field="payload"
                ) from None
        else:
            payload = response

        records = _extract_records(payload)
        observations: list[CostObservation] = []
        for record_index, record in enumerate(records):
            observations.append(
                _cost_observation_from_json(
                    record,
                    source_system=source_system,
                    record_index=record_index,
                )
            )
        return tuple(observations)


def _connector_source_system(value: object) -> str:
    """Return the trusted source identity or refuse an unusable configuration."""

    if not isinstance(value, str) or not value.strip():
        raise CostSourceConfigurationRefusal(
            "COST_SOURCE_SOURCE_MISSING", field="source_system"
        )
    text = value.strip()
    if len(text) > 64 or _CONTROL_CHARACTERS.search(text):
        raise CostSourceConfigurationRefusal(
            "COST_SOURCE_CONFIGURATION_INVALID", field="source_system"
        )
    return text


def _extract_records(payload: Any) -> list[Any]:
    """Return bounded records from a list or a ``{"items": [...]}`` envelope."""

    if isinstance(payload, list | tuple):
        records = list(payload)
    elif isinstance(payload, dict):
        if payload.get("error"):
            raise CostSourceJsonRefusal("COST_SOURCE_PROVIDER_ERROR", field="error")
        if "items" not in payload:
            raise CostSourceJsonRefusal(
                "COST_SOURCE_ENVELOPE_INVALID", field="items"
            )
        items = payload["items"]
        if not isinstance(items, list | tuple):
            raise CostSourceJsonRefusal(
                "COST_SOURCE_ENVELOPE_INVALID", field="items"
            )
        records = list(items)
    else:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_ENVELOPE_INVALID", field="payload"
        )

    if len(records) > COST_SOURCE_MAX_RECORDS:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_RECORD_LIMIT_EXCEEDED", field="items"
        )
    return records


def _cost_observation_from_json(
    record: Any,
    *,
    source_system: str | None = None,
    record_index: int = 0,
) -> CostObservation:
    """Map one validated JSON record to the domain cost observation.

    ``source_system`` is normally the connector's trusted identity. It is
    optional only so direct parser checks can use the record's declared
    identity; the production fetch path always passes the connector identity.
    """

    if not isinstance(record, dict):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_RECORD_INVALID",
            record_index=record_index,
            field="record",
        )
    if source_system is None:
        source_system = _required_text(
            record,
            "source_system",
            record_index,
            max_length=64,
        )
    else:
        source_system = _connector_source_system(source_system)

    _validate_declared_source(record, source_system, record_index)
    observation_id = _observation_id(record, record_index)
    scope_type = _enum_value(
        record, "scope_type", SCOPE_TYPES, record_index, max_length=32
    )
    scope_id = _required_text(record, "scope_id", record_index, max_length=128)
    observation_type = _enum_value(
        record,
        "observation_type",
        OBSERVATION_TYPES,
        record_index,
        max_length=32,
    )
    value = _financial_value(record, record_index)
    currency = _currency(record, record_index)
    unit = _unit(record, record_index)
    effective_from_text, effective_from = _timestamp(
        record.get("effective_from_utc", _MISSING),
        "effective_from_utc",
        record_index,
        required=True,
    )
    effective_to_text, effective_to = _timestamp(
        record.get("effective_to_utc", _MISSING),
        "effective_to_utc",
        record_index,
        required=False,
    )
    if effective_to is not None and effective_to < effective_from:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_TIMESTAMP_INVALID",
            record_index=record_index,
            field="effective_to_utc",
        )
    created_at_text, _ = _timestamp(
        record.get("created_at_utc", _MISSING),
        "created_at_utc",
        record_index,
        required=False,
    )
    source_reference = _required_text(
        record,
        "source_reference",
        record_index,
        max_length=COST_SOURCE_MAX_TEXT_LENGTH,
    )

    return CostObservation(
        observation_id=observation_id,
        scope_type=scope_type,
        scope_id=scope_id,
        observation_type=observation_type,
        value=value,
        currency=currency,
        unit=unit,
        direction=_optional_text(record, "direction", record_index, max_length=16),
        capacity_product=_optional_text(
            record, "capacity_product", record_index, max_length=32
        ),
        firmness=_optional_text(record, "firmness", record_index, max_length=32),
        gas_year=_optional_text(record, "gas_year", record_index, max_length=16),
        effective_from_utc=effective_from_text,
        effective_to_utc=effective_to_text,
        source_system=source_system,
        source_reference=source_reference,
        document_id=_optional_text(
            record, "document_id", record_index, max_length=128
        ),
        entitlement_scope=_entitlement_scope(record, record_index),
        status=_optional_text(record, "status", record_index, max_length=32)
        or "ACTIVE",
        manual_review_required=_manual_review_required(record, record_index),
        superseded_by=_optional_text(
            record, "superseded_by", record_index, max_length=128
        ),
        created_at_utc=created_at_text or "",
    )


def _validate_declared_source(
    record: dict, source_system: str, record_index: int
) -> None:
    """Ensure an optional declared source cannot override the connector."""

    declared = record.get("source_system", _MISSING)
    if declared is _MISSING:
        return
    declared_text = _text(
        declared,
        "source_system",
        record_index,
        max_length=64,
        required=True,
    )
    if declared_text.casefold() != source_system.casefold():
        raise CostSourceJsonRefusal(
            "COST_SOURCE_SOURCE_MISMATCH",
            record_index=record_index,
            field="source_system",
        )


def _observation_id(record: dict, record_index: int) -> str:
    """Return the declared observation id without fabricating one."""

    primary = record.get("observation_id", _MISSING)
    alias = record.get("id", _MISSING)
    if primary is _MISSING and alias is _MISSING:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_FIELD_MISSING",
            record_index=record_index,
            field="observation_id",
        )

    primary_value = None
    if primary is not _MISSING:
        primary_value = _text(
            primary,
            "observation_id",
            record_index,
            max_length=128,
            required=True,
        )
    alias_value = None
    if alias is not _MISSING:
        alias_value = _text(
            alias,
            "id",
            record_index,
            max_length=128,
            required=True,
        )
    if primary_value is not None and alias_value is not None:
        if primary_value != alias_value:
            raise CostSourceJsonRefusal(
                "COST_SOURCE_FIELD_INVALID",
                record_index=record_index,
                field="observation_id",
            )
    return primary_value or alias_value


def _enum_value(
    record: dict,
    field: str,
    allowed: frozenset[str],
    record_index: int,
    *,
    max_length: int,
) -> str:
    """Return a required enum field, case-normalized and closed to unknowns."""

    text = _required_text(record, field, record_index, max_length=max_length)
    normalized = text.upper()
    if normalized not in allowed:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_ENUM_INVALID",
            record_index=record_index,
            field=field,
        )
    return normalized


def _financial_value(record: dict, record_index: int) -> float:
    """Return a present, finite, non-negative numeric value (zero is valid)."""

    value = record.get("value", _MISSING)
    if value is _MISSING or value is None:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_FIELD_MISSING",
            record_index=record_index,
            field="value",
        )
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_FIELD_INVALID",
            record_index=record_index,
            field="value",
        )
    if isinstance(value, Decimal) and not value.is_finite():
        raise CostSourceJsonRefusal(
            "COST_SOURCE_VALUE_NOT_FINITE",
            record_index=record_index,
            field="value",
        )
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_VALUE_NOT_FINITE",
            record_index=record_index,
            field="value",
        ) from None
    if not math.isfinite(number):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_VALUE_NOT_FINITE",
            record_index=record_index,
            field="value",
        )
    if number < 0:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_VALUE_NEGATIVE",
            record_index=record_index,
            field="value",
        )
    return number


def _currency(record: dict, record_index: int) -> str:
    """Return a declared ISO-4217-shaped currency code; never a default."""

    text = _required_text(record, "currency", record_index, max_length=8)
    normalized = text.upper()
    if not _CURRENCY_CODE.fullmatch(normalized):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_CURRENCY_INVALID",
            record_index=record_index,
            field="currency",
        )
    return normalized


def _unit(record: dict, record_index: int) -> str:
    """Return a recognized financial unit/basis; never a default."""

    text = _required_text(record, "unit", record_index, max_length=32)
    canonical = _SUPPORTED_UNITS.get(text.lower())
    if canonical is None:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_UNIT_UNSUPPORTED",
            record_index=record_index,
            field="unit",
        )
    return canonical


def _manual_review_required(record: dict, record_index: int) -> bool:
    """Return the explicit review flag, defaulting only to the safe True."""

    value = record.get("manual_review_required", _MISSING)
    if value is _MISSING or value is None:
        return True
    if not isinstance(value, bool):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_FIELD_INVALID",
            record_index=record_index,
            field="manual_review_required",
        )
    return value


def _entitlement_scope(record: dict, record_index: int) -> tuple[str, ...]:
    """Return declared entitlement scopes as an immutable tuple of names."""

    value = record.get("entitlement_scope", _MISSING)
    if value is _MISSING or value is None:
        return ()
    if not isinstance(value, list | tuple) or len(value) > 64:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_FIELD_INVALID",
            record_index=record_index,
            field="entitlement_scope",
        )
    return tuple(
        _text(
            item,
            "entitlement_scope",
            record_index,
            max_length=64,
            required=True,
        )
        for item in value
    )


def _required_text(
    record: dict, field: str, record_index: int, *, max_length: int
) -> str:
    """Return a required text field, refusing absence and empty values."""

    return _text(
        record.get(field, _MISSING),
        field,
        record_index,
        max_length=max_length,
        required=True,
    )


def _optional_text(
    record: dict, field: str, record_index: int, *, max_length: int
) -> str | None:
    """Return an optional text field, treating absent/null as truly absent."""

    return _text(
        record.get(field, _MISSING),
        field,
        record_index,
        max_length=max_length,
        required=False,
    )


def _text(
    value: object,
    field: str,
    record_index: int,
    *,
    max_length: int,
    required: bool,
) -> str | None:
    """Validate one text field without echoing its value in an error."""

    if value is _MISSING or value is None:
        if required:
            raise CostSourceJsonRefusal(
                "COST_SOURCE_FIELD_MISSING",
                record_index=record_index,
                field=field,
            )
        return None
    if not isinstance(value, str):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_FIELD_INVALID",
            record_index=record_index,
            field=field,
        )
    text = value.strip()
    if not text:
        if required:
            raise CostSourceJsonRefusal(
                "COST_SOURCE_FIELD_MISSING",
                record_index=record_index,
                field=field,
            )
        return None
    if len(text) > max_length or _CONTROL_CHARACTERS.search(text):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_FIELD_INVALID",
            record_index=record_index,
            field=field,
        )
    return text


def _timestamp(
    value: object,
    field: str,
    record_index: int,
    *,
    required: bool,
) -> tuple[str | None, datetime | None]:
    """Validate an explicit ISO-8601 timestamp with a real UTC offset."""

    if value is _MISSING or value is None:
        if required:
            raise CostSourceJsonRefusal(
                "COST_SOURCE_FIELD_MISSING",
                record_index=record_index,
                field=field,
            )
        return None, None
    if not isinstance(value, str):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_TIMESTAMP_INVALID",
            record_index=record_index,
            field=field,
        )
    text = value.strip()
    if not text:
        if required:
            raise CostSourceJsonRefusal(
                "COST_SOURCE_FIELD_MISSING",
                record_index=record_index,
                field=field,
            )
        return None, None
    if len(text) > 64 or _CONTROL_CHARACTERS.search(text):
        raise CostSourceJsonRefusal(
            "COST_SOURCE_TIMESTAMP_INVALID",
            record_index=record_index,
            field=field,
        )
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_TIMESTAMP_INVALID",
            record_index=record_index,
            field=field,
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CostSourceJsonRefusal(
            "COST_SOURCE_TIMESTAMP_INVALID",
            record_index=record_index,
            field=field,
        )
    return text, parsed


def secondary_transfer_skeleton() -> SkeletonCostSourceConnector:
    """Return a secondary-capacity transfer connector skeleton."""

    return SkeletonCostSourceConnector(
        source_system="SECONDARY_TRANSFER",
        datasets=("secondary_capacity", "transfer_prices"),
        freshness_expectation_minutes=1440,
    )


def lng_auction_skeleton() -> SkeletonCostSourceConnector:
    """Return an LNG regas slot auction connector skeleton."""

    return SkeletonCostSourceConnector(
        source_system="LNG_AUCTIONS",
        datasets=("slot_auctions", "auction_clearing_prices"),
        freshness_expectation_minutes=1440,
    )


COST_SOURCE_SKELETONS = {
    "TSO_TARIFFS": tso_tariff_skeleton,
    "LNG_SLOTS": lng_slot_skeleton,
    "SECONDARY_TRANSFER": secondary_transfer_skeleton,
    "LNG_AUCTIONS": lng_auction_skeleton,
}
