"""RFC0006 receipt-bound EEX TTF NGP append-or-verify persistence.

The EEX NGP adapter keeps the official source reference, its exact published
price/volume text and the explicit response receipt in the canonical
``market_observations`` row. This module is the repository boundary for that
shape:

- it reuses the existing generic locked append-or-verify helper with an explicit
  ``MarketObservationRecord`` semantic field set;
- the semantic comparison includes the exact source price/volume and the
  receipt-bound status/calendar metadata, but deliberately excludes the
  observed/receipt instant, raw archive identity, ingestion run id and payload
  hash, so a later capture of unchanged content keeps the first receipt and
  first lineage;
- a same-identity semantic change is refused with
  :class:`EexNgpRevisionRequiresHistoryError` rather than overwritten, because
  no append-only revision history exists;
- the helper owns one savepoint and never commits: a mixed batch rolls back all
  canonical writes while the caller's previously archived raw capture survives.

Only a row that validates as the canonical EEX TTF NGP receipt-bound shape can
enter this boundary. Price authority is delegated to
:func:`eurogas_nexus.domain.market_intelligence.source_price.resolve_source_price`;
a forged canonical Float, a missing/forged exact text or a zero/non-positive
volume is an explicit invalid-observation refusal, never a silently stored
approximation.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GieRevisionRaceError,
    GieRevisionRequiresHistoryError,
    upsert_revision_safe_observation_rows,
)
from eurogas_nexus.domain.market_intelligence.source_price import (
    STATUS_EXACT,
    SourcePrice,
    resolve_source_price,
)
from eurogas_nexus.domain.observations.market import ObservationFreshness

SOURCE_SYSTEM = "EEX"
SOURCE_DATASET = "ttf-ngp-15min"
SOURCE_REFERENCE = "eex-ttf-ngp-15-mins"
MARKET_VENUE = "EEX"
PRODUCT = "TTF NGP"
UNIT = "EUR/MWh"
CURRENCY = "EUR"
RECEIPT_NORMALIZER_VERSION = "eex-ngp-receipt-v1"
RECEIPT_IDENTITY_PREFIX = "eex-ngp-r1-"
_AVAILABILITY_BASIS = "response_receipt"

#: Canonical columns compared by the existing locked append-or-verify helper.
#: ``observed_at_utc`` is intentionally absent: a later capture of the same
#: provider key must verify against the stored row without rewriting its first
#: receipt. ``metadata_json`` is compared only through the explicit allowlist
#: below.
EEX_NGP_SEMANTIC_FIELDS: tuple[str, ...] = (
    "market_venue",
    "product",
    "price",
    "unit",
    "currency",
    "period_start_utc",
    "period_end_utc",
    "source_system",
    "source_reference",
    "source_record_id",
    "freshness",
    "quality_score",
    "research_only",
)

#: Metadata that describes the provider value or its receipt-bound contract.
#: Receipt/archive/run/hash/availability-instant churn is deliberately unlisted,
#: so a new capture is not mistaken for a provider revision.
EEX_NGP_SEMANTIC_METADATA_KEYS: tuple[str, ...] = (
    "index_value_exact",
    "index_value_raw",
    "index_volume_mwh_exact",
    "index_volume_raw",
    "revision_status",
    "revision_status_raw",
    "provisional",
    "gas_day_calendar",
    "gas_day_calendar_evidence",
    "period_basis",
    "normalizer_version",
    "availability_basis",
    "publication_time_basis",
    "publication_time_utc",
)

_RECEIPT_ID_PATTERN = re.compile(r"eex-ngp-r1-[0-9a-f]{48}")
_STATUSES = frozenset({"final", "temporary"})


class EexNgpPersistenceError(RuntimeError):
    """Base class for a typed EEX NGP persistence refusal."""

    code = "eex_ngp_persistence_error"


class EexNgpRevisionRequiresHistoryError(EexNgpPersistenceError):
    """A same-identity EEX NGP row carries different semantic content."""

    code = "eex_ngp_revision_requires_history"

    def __init__(self, message: str, *, changed_fields: tuple[str, ...] = ()) -> None:
        self.changed_fields = tuple(changed_fields)
        super().__init__(message)


class EexNgpRevisionRaceError(EexNgpPersistenceError):
    """A concurrent write could not be confirmed as ours or as an existing row."""

    code = "eex_ngp_revision_race_unresolved"


class EexNgpInvalidObservationError(EexNgpPersistenceError):
    """A row is not the canonical receipt-bound EEX NGP observation shape."""

    code = "eex_ngp_invalid_observation"


def upsert_eex_ngp_observation_rows(
    session: Session,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Append-or-verify canonical EEX NGP receipt-bound market observations.

    Args:
        session: Caller-owned session. This helper opens one savepoint and never
            commits; the caller owns the outer transaction and its authorization.
        rows: Rows produced by the receipt-bound mapper and stamped with their
            exact archive lineage.

    Returns:
        ``{"inserted": n, "unchanged": m}`` for the batch.

    Raises:
        EexNgpInvalidObservationError: A row is malformed, claims a non-EEX
            identity, is not in the receipt namespace, or does not resolve to
            exact source-price/volume evidence.
        EexNgpRevisionRequiresHistoryError: An existing natural key differs on a
            semantic column or allowlisted metadata.
        EexNgpRevisionRaceError: A concurrent conflict could not be confirmed.
    """

    _validate_rows(rows)
    try:
        with session.begin_nested():
            return upsert_revision_safe_observation_rows(
                session,
                _market_observation_model(),
                rows,
                semantic_fields=EEX_NGP_SEMANTIC_FIELDS,
                semantic_metadata_keys=EEX_NGP_SEMANTIC_METADATA_KEYS,
            )
    except GieRevisionRequiresHistoryError as error:
        changed = tuple(error.changed_fields)
        rendered = ", ".join(changed) if changed else "unknown"
        raise EexNgpRevisionRequiresHistoryError(
            (
                "EEX NGP revision requires append-only history: refusing to overwrite "
                f"an existing receipt-bound observation with changed semantic field(s) "
                f"[{rendered}]. The original measurement is kept and the batch is "
                "refused as a whole."
            ),
            changed_fields=changed,
        ) from None
    except GieRevisionRaceError:
        raise EexNgpRevisionRaceError(
            "EEX NGP natural-key conflict could not be confirmed as inserted or as an "
            "existing row; refusing to report a phantom write."
        ) from None


def resolve_eex_ngp_source_price(row: Mapping[str, Any]) -> SourcePrice:
    """Resolve one canonical row's exact EEX source price evidence.

    The caller can use this to inspect the validated exact decimal before any
    arithmetic. A status other than ``exact`` means the row must not be treated
    as exact source-price authority.
    """

    metadata = row.get("metadata_json")
    return resolve_source_price(
        source_system=_optional_text(row.get("source_system")),
        source_reference=_optional_text(row.get("source_reference")),
        numeric_price=row.get("price"),
        metadata=metadata if isinstance(metadata, Mapping) else None,
        unit=_optional_text(row.get("unit")),
        currency=_optional_text(row.get("currency")),
    )


def _market_observation_model() -> Any:
    """Import lazily so this repository module has no model import cycle."""

    from eurogas_nexus.db.models import MarketObservationRecord

    return MarketObservationRecord


def _validate_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise EexNgpInvalidObservationError(
            "EEX NGP persistence requires at least one canonical observation row."
        )
    if not isinstance(rows, list):
        raise EexNgpInvalidObservationError(
            "EEX NGP observation rows must be supplied as a list."
        )

    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise EexNgpInvalidObservationError(
                "Every EEX NGP observation row must be a mapping."
            )
        observation_id = _required_text(row.get("observation_id"), field="observation_id")
        if _RECEIPT_ID_PATTERN.fullmatch(observation_id) is None:
            raise EexNgpInvalidObservationError(
                "EEX NGP observation identity is not the deterministic eex-ngp-r1 namespace."
            )
        if observation_id in seen:
            raise EexNgpInvalidObservationError(
                "EEX NGP batch repeats one receipt-bound observation identity."
            )
        seen.add(observation_id)

        _require_equal(row, "source_system", SOURCE_SYSTEM)
        # Keep the original authority reference; never replace it with a URL.
        _require_equal(row, "source_reference", SOURCE_REFERENCE)
        _require_equal(row, "market_venue", MARKET_VENUE)
        _require_equal(row, "product", PRODUCT)
        _require_equal(row, "unit", UNIT)
        _require_equal(row, "currency", CURRENCY)
        _require_equal(row, "freshness", ObservationFreshness.UNKNOWN.value)
        if row.get("research_only") is not True:
            raise EexNgpInvalidObservationError(
                "EEX NGP observations must remain explicitly research-only."
            )
        _required_text(row.get("source_record_id"), field="source_record_id")

        start = _required_aware(row.get("period_start_utc"), field="period_start_utc")
        end = _required_aware(row.get("period_end_utc"), field="period_end_utc")
        if end <= start:
            raise EexNgpInvalidObservationError(
                "EEX NGP delivery period must end after it starts."
            )
        _required_aware(row.get("observed_at_utc"), field="observed_at_utc")

        price = row.get("price")
        if isinstance(price, bool) or not isinstance(price, int | float):
            raise EexNgpInvalidObservationError(
                "EEX NGP canonical price must be a JSON number."
            )
        if not math.isfinite(float(price)):
            raise EexNgpInvalidObservationError(
                "EEX NGP canonical price must be finite."
            )

        metadata = row.get("metadata_json")
        if not isinstance(metadata, Mapping):
            raise EexNgpInvalidObservationError(
                "EEX NGP observation metadata must be a mapping."
            )
        _require_equal(metadata, "source_system", SOURCE_SYSTEM, prefix="metadata_json")
        _require_equal(
            metadata, "source_reference", SOURCE_REFERENCE, prefix="metadata_json"
        )
        _require_equal(metadata, "source_dataset", SOURCE_DATASET, prefix="metadata_json")
        _require_equal(metadata, "index", "NGP", prefix="metadata_json")
        _require_equal(
            metadata, "normalizer_version", RECEIPT_NORMALIZER_VERSION, prefix="metadata_json"
        )
        _require_equal(
            metadata, "availability_basis", _AVAILABILITY_BASIS, prefix="metadata_json"
        )
        if "publication_time_utc" not in metadata or metadata["publication_time_utc"] is not None:
            raise EexNgpInvalidObservationError(
                "EEX NGP receipt-bound metadata must keep publication_time_utc explicitly null."
            )
        status = metadata.get("revision_status")
        if status not in _STATUSES:
            raise EexNgpInvalidObservationError(
                "EEX NGP revision status must be final or temporary."
            )
        if not isinstance(metadata.get("gas_day_calendar"), str) or not metadata[
            "gas_day_calendar"
        ].strip():
            raise EexNgpInvalidObservationError(
                "EEX NGP metadata must name the evidenced delivery calendar."
            )
        if not isinstance(metadata.get("gas_day_calendar_evidence"), str) or not metadata[
            "gas_day_calendar_evidence"
        ].strip():
            raise EexNgpInvalidObservationError(
                "EEX NGP metadata must retain the delivery-calendar evidence."
            )

        resolution = resolve_eex_ngp_source_price(row)
        if resolution.status != STATUS_EXACT or resolution.exact_decimal is None:
            raise EexNgpInvalidObservationError(
                
                    "EEX NGP row does not carry validated exact source-price evidence "
                    f"(status={resolution.status!r}, issue={resolution.issue_code!r}); "
                    "a forged Float or missing/zero volume is refused."
                
            )
        if resolution.executable_quote is not False:
            raise EexNgpInvalidObservationError(
                "EEX NGP exact rows must deny executable-quote semantics."
            )
        volume = resolution.volume_decimal
        if not isinstance(volume, Decimal) or volume <= 0:
            raise EexNgpInvalidObservationError(
                "EEX NGP exact rows require a positive exact index volume."
            )


def _require_equal(
    values: Mapping[str, Any],
    key: str,
    expected: str,
    *,
    prefix: str | None = None,
) -> None:
    value = values.get(key)
    if value != expected:
        label = f"{prefix}.{key}" if prefix else key
        raise EexNgpInvalidObservationError(
            f"EEX NGP {label} must equal the canonical {expected!r} identity."
        )


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EexNgpInvalidObservationError(
            f"EEX NGP {field} must be a nonempty string."
        )
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _required_aware(value: object, *, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EexNgpInvalidObservationError(
            f"EEX NGP {field} must be an aware datetime."
        )
    try:
        return value.astimezone(UTC)
    except (OverflowError, OSError, ValueError):
        raise EexNgpInvalidObservationError(
            f"EEX NGP {field} cannot be normalized to UTC."
        ) from None


__all__ = [
    "EEX_NGP_SEMANTIC_FIELDS",
    "EEX_NGP_SEMANTIC_METADATA_KEYS",
    "EexNgpInvalidObservationError",
    "EexNgpPersistenceError",
    "EexNgpRevisionRaceError",
    "EexNgpRevisionRequiresHistoryError",
    "RECEIPT_IDENTITY_PREFIX",
    "RECEIPT_NORMALIZER_VERSION",
    "SOURCE_DATASET",
    "SOURCE_REFERENCE",
    "SOURCE_SYSTEM",
    "resolve_eex_ngp_source_price",
    "upsert_eex_ngp_observation_rows",
]
