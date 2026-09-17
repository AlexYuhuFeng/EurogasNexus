"""Data Product catalogue read service (Architecture V2 Wave 4).

Composes the declared catalogue (``domain/data_platform/products.py``) with the
two runtime facts a business user is allowed to see
(``07_DATA_PLATFORM.md`` section 3):

- the per-principal entitlement verdict, evaluated with the existing fail-closed
  helpers; and
- a freshness/provenance summary measured from the canonical runtime tables.

The service is the one place that decides what "restricted" means on this
surface: a product whose required family the caller is not entitled to is
reported as restricted with **no** provenance at all. It is never omitted and
never presented as zero rows, because a zero would read as a measured fact about
licensed data the caller may not see.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from eurogas_nexus.domain.data_platform.products import (
    DataProduct,
    DataProductAvailability,
    DataProductConfidence,
    data_products,
    evaluate_product_entitlement,
)
from eurogas_nexus.domain.dataops.contracts import FreshnessState
from eurogas_nexus.domain.monitoring.freshness import (
    FreshnessStatus,
    evaluate_freshness,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps the API import DB-free
    from sqlalchemy.orm import Session

CATALOGUE_VERSION = "data-products.v1"


def build_data_product_catalogue(
    principal: AuthenticatedPrincipal,
    *,
    session: Session | None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Build the Data Product catalogue read model for one principal.

    Args:
        principal: The authenticated principal the catalogue is rendered for.
        session: Open SQLAlchemy session, or ``None`` when no runtime database is
            configured. Without a session every allowed product reports
            ``UNKNOWN`` freshness rather than fabricated zeroes.
        now_utc: Evaluation clock; injectable for deterministic tests.

    Returns:
        A dict with ``catalogue_version``, ``generated_at_utc``,
        ``runtime_available``, the per-product entries and an
        ``entitlement_summary`` count block.
    """

    now = _as_utc(now_utc or datetime.now(UTC))
    provenance = _load_provenance(session)
    products = [
        _product_entry(product, principal=principal, provenance=provenance, now_utc=now)
        for product in data_products()
    ]
    restricted = [entry for entry in products if entry["restricted"]]
    return {
        "catalogue_version": CATALOGUE_VERSION,
        "generated_at_utc": now.isoformat(),
        "runtime_available": session is not None,
        "products": products,
        "entitlement_summary": {
            "total_products": len(products),
            "allowed_products": len(products) - len(restricted),
            "restricted_products": len(restricted),
        },
    }


def _load_provenance(session: Session | None) -> dict[str, dict[str, Any]]:
    """Read the provenance summary for every table the catalogue can reference."""

    if session is None:
        return {}
    declared = sorted({table for product in data_products() for table in product.provenance_tables})
    if not declared:
        return {}
    from eurogas_nexus.db.repositories.data_platform import table_provenance_summary

    return table_provenance_summary(session, declared)


def _product_entry(
    product: DataProduct,
    *,
    principal: AuthenticatedPrincipal,
    provenance: Mapping[str, dict[str, Any]],
    now_utc: datetime,
) -> dict[str, Any]:
    """Render one catalogue entry, including its entitlement verdict."""

    entitlement = evaluate_product_entitlement(principal, product)
    entry: dict[str, Any] = {
        "product_id": product.product_id,
        "business_name": product.business_name,
        "description": product.description,
        "domain": product.domain,
        "availability": {
            "state": product.availability.value,
            "note": product.availability_note,
        },
        "time_basis": {
            "basis": product.time_basis.value,
            "gas_day_calendar": product.gas_day_calendar,
            "freshness_expectation_minutes": product.freshness_expectation_minutes,
        },
        "source_families": list(product.source_families),
        "simulated_families": list(product.simulated_families),
        "entitlement_families": list(product.entitlement_families),
        "served_by": [
            {
                "kind": surface.kind.value,
                "reference": surface.reference,
                "description": surface.description,
            }
            for surface in product.served_by
        ],
        "provenance_tables": list(product.provenance_tables),
        "restricted": not entitlement.allowed,
        "entitlement": {
            "status": "allowed" if entitlement.allowed else "restricted",
            "reason": entitlement.reason,
            "required_family_count": entitlement.required_family_count,
            "granted_family_count": entitlement.granted_family_count,
            "restricted_family_count": entitlement.restricted_family_count,
            "note": entitlement.note,
        },
        "provenance": None,
        "human_review_required": True,
    }
    if entitlement.allowed:
        entry["provenance"] = _provenance_entry(
            product, provenance=provenance, now_utc=now_utc
        )
    return entry


def _provenance_entry(
    product: DataProduct,
    *,
    provenance: Mapping[str, dict[str, Any]],
    now_utc: datetime,
) -> dict[str, Any]:
    """Measure the freshness/provenance summary of one allowed product."""

    tables = [
        _table_entry(table, provenance.get(table))
        for table in product.provenance_tables
    ]
    source_systems = _source_system_entries(product, provenance)
    declared_labels = set(product.source_families)
    simulated_labels = set(product.simulated_families)
    declared_with_rows = {
        item["label"]
        for item in source_systems
        if item["label"] in declared_labels and item["row_count"]
    }
    simulated_with_rows = {
        item["label"]
        for item in source_systems
        if item["label"] in simulated_labels and item["row_count"]
    }
    row_count = sum(item["row_count"] for item in source_systems)
    last_observed = _max_iso(item["last_observed_at_utc"] for item in source_systems)
    freshness_status = _freshness_state(
        product,
        row_count=row_count,
        last_observed_at_utc=_parse_iso(last_observed),
        now_utc=now_utc,
    )
    confidence = _confidence(
        product,
        declared_with_rows=declared_with_rows,
        simulated_with_rows=simulated_with_rows,
        freshness_status=freshness_status,
    )
    return {
        "as_of_utc": last_observed,
        "row_count": row_count,
        "freshness": {
            "status": freshness_status.value,
            "expectation_minutes": product.freshness_expectation_minutes,
            "last_observed_at_utc": last_observed,
        },
        "confidence": confidence.value,
        "quality_flags": _quality_flags(
            product,
            row_count=row_count,
            declared_with_rows=declared_with_rows,
            simulated_with_rows=simulated_with_rows,
            freshness_status=freshness_status,
            provenance_available=bool(provenance),
        ),
        "source_systems": source_systems,
        "tables": tables,
    }


def _table_entry(table: str, summary: Mapping[str, Any] | None) -> dict[str, Any]:
    """Render one provenance table row."""

    if summary is None:
        return {
            "table": table,
            "row_count": 0,
            "last_observed_at_utc": None,
            "labels": [],
            "measured": False,
        }
    return {
        "table": table,
        "row_count": summary["row_count"],
        "last_observed_at_utc": summary["last_observed_at_utc"],
        "labels": list(summary["labels"]),
        "measured": True,
    }


def _source_system_entries(
    product: DataProduct,
    provenance: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate each declared/simulated family across the product's tables."""

    entries: list[dict[str, Any]] = []
    for label in product.observed_source_systems:
        row_count = 0
        observed: list[str] = []
        for table in product.provenance_tables:
            summary = provenance.get(table)
            if summary is None:
                continue
            for item in summary["labels"]:
                if item["label"] == label:
                    row_count += int(item["row_count"])
                    if item["last_observed_at_utc"]:
                        observed.append(item["last_observed_at_utc"])
        entries.append(
            {
                "label": label,
                "row_count": row_count,
                "last_observed_at_utc": _max_iso(observed),
                "simulated": label in set(product.simulated_families),
                "declared": label in set(product.source_families),
            }
        )
    return entries


def _freshness_state(
    product: DataProduct,
    *,
    row_count: int,
    last_observed_at_utc: datetime | None,
    now_utc: datetime,
) -> FreshnessState:
    """Map the shared freshness evaluation onto the data-ops state vocabulary."""

    if product.freshness_expectation_minutes is None:
        return FreshnessState.NOT_EXPECTED if row_count else FreshnessState.MISSING
    status = evaluate_freshness(
        product.freshness_expectation_minutes,
        last_observed_at_utc,
        now_utc=now_utc,
    )
    if status is FreshnessStatus.LIVE:
        return FreshnessState.FRESH
    if status is FreshnessStatus.STALE:
        return FreshnessState.STALE
    return FreshnessState.MISSING if not row_count else FreshnessState.UNKNOWN


def _confidence(
    product: DataProduct,
    *,
    declared_with_rows: set[str],
    simulated_with_rows: set[str],
    freshness_status: FreshnessState,
) -> DataProductConfidence:
    """Derive read-side confidence from measured facts only."""

    if product.availability in {
        DataProductAvailability.DECLARED_ONLY,
        DataProductAvailability.NOT_IMPLEMENTED,
    }:
        return DataProductConfidence.UNKNOWN
    if not declared_with_rows and not simulated_with_rows:
        return DataProductConfidence.UNKNOWN
    if not declared_with_rows:
        return DataProductConfidence.LOW
    if len(declared_with_rows) < len(product.source_families):
        return DataProductConfidence.MEDIUM
    if freshness_status in {FreshnessState.STALE, FreshnessState.MISSING}:
        return DataProductConfidence.MEDIUM
    if freshness_status is FreshnessState.FRESH:
        return DataProductConfidence.HIGH
    return DataProductConfidence.MEDIUM


def _quality_flags(
    product: DataProduct,
    *,
    row_count: int,
    declared_with_rows: set[str],
    simulated_with_rows: set[str],
    freshness_status: FreshnessState,
    provenance_available: bool,
) -> list[str]:
    """Return stable quality flags describing the measured provenance."""

    flags: list[str] = []
    if product.availability is DataProductAvailability.NOT_IMPLEMENTED:
        flags.append("SURFACE_NOT_IMPLEMENTED")
    if product.availability is DataProductAvailability.DECLARED_ONLY:
        flags.append("NO_SOURCE_IMPLEMENTATION")
    if product.provenance_tables and not provenance_available:
        flags.append("RUNTIME_DATABASE_NOT_CONFIGURED")
    elif row_count == 0:
        flags.append("NO_RUNTIME_ROWS")
    elif not declared_with_rows and simulated_with_rows:
        flags.append("SIMULATED_SUBSTITUTE_ONLY")
    if declared_with_rows and len(declared_with_rows) < len(product.source_families):
        flags.append("DECLARED_FAMILY_WITHOUT_ROWS")
    if freshness_status is FreshnessState.STALE:
        flags.append("SOURCE_STALE")
    return flags


def _max_iso(values: Any) -> str | None:
    """Return the newest ISO timestamp from an iterable of ISO strings."""

    candidates = [value for value in values if value]
    if not candidates:
        return None
    return max(candidates, key=_parse_iso_or_min)


def _parse_iso_or_min(value: str) -> datetime:
    """Parse an ISO timestamp for ordering; unparsable values sort first."""

    parsed = _parse_iso(value)
    return parsed if parsed is not None else datetime.min.replace(tzinfo=UTC)


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO timestamp, returning ``None`` when it is not parsable."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    """Normalize a timestamp to aware UTC (naive timestamps are UTC)."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
