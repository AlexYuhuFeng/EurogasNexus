"""Unified Data Platform repository (Architecture V2 Wave 4).

Two responsibilities, both DB-only:

1. **Provenance reads** for the Data Product catalogue: per canonical runtime
   table, the row count and newest observation timestamp, optionally split by
   source system. This is the read model behind the business-facing
   freshness/provenance summary
   (``07_DATA_PLATFORM.md`` sections 3 and 4).
2. **Analysis Snapshot persistence**: create, read one and list recent snapshot
   descriptors (``07_DATA_PLATFORM.md`` section 6).

The provenance reader deliberately exposes counts and timestamps only. It never
selects credential state, scheduler internals or retry traces - those belong to
the operator posture in section 4, which the Source Center already serves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    AnalysisSnapshotRecord,
    CapacityObservationRecord,
    CapacityProfileRecord,
    FlowObservationRecord,
    FxObservationRecord,
    LngObservationRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
    PortfolioPnlSnapshotRecord,
    ReferenceEdge,
    ReferenceFacility,
    ReferenceNode,
    ReferenceTsoAccessPoint,
    RouteCandidateRecord,
    ScreenOrderObservationRecord,
    StorageObservationRecord,
    TsoTariffRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.domain.data_platform.snapshots import (
    SnapshotDescriptor,
    descriptor_payload,
)


@dataclass(frozen=True, slots=True)
class _TableSpec:
    """How one canonical table is aggregated for a provenance summary.

    Attributes:
        table: Physical table name exposed to clients.
        model: The mapped SQLAlchemy model.
        label_column: Column to group by, or ``None`` for a single unlabelled
            aggregate (the table has no source-system style column).
        observed_column: Column carrying the newest-observation timestamp.
    """

    table: str
    model: Any
    label_column: Any
    observed_column: Any


def _table_specs() -> tuple[_TableSpec, ...]:
    """Return the aggregation spec for every table a data product may derive from."""

    return (
        _TableSpec(
            "market_observations",
            MarketObservationRecord,
            MarketObservationRecord.source_system,
            MarketObservationRecord.observed_at_utc,
        ),
        _TableSpec(
            "market_quotes",
            MarketQuoteRecord,
            MarketQuoteRecord.source_system,
            MarketQuoteRecord.observed_at_utc,
        ),
        _TableSpec(
            "screen_order_observations",
            ScreenOrderObservationRecord,
            ScreenOrderObservationRecord.source_system,
            ScreenOrderObservationRecord.observed_at_utc,
        ),
        _TableSpec(
            "flow_observations",
            FlowObservationRecord,
            FlowObservationRecord.source_system,
            FlowObservationRecord.observed_at_utc,
        ),
        _TableSpec(
            "capacity_observations",
            CapacityObservationRecord,
            CapacityObservationRecord.source_system,
            CapacityObservationRecord.observed_at_utc,
        ),
        _TableSpec(
            "storage_observations",
            StorageObservationRecord,
            StorageObservationRecord.source_system,
            StorageObservationRecord.observed_at_utc,
        ),
        _TableSpec(
            "lng_observations",
            LngObservationRecord,
            LngObservationRecord.source_system,
            LngObservationRecord.observed_at_utc,
        ),
        _TableSpec(
            "fx_observations",
            FxObservationRecord,
            FxObservationRecord.source_system,
            FxObservationRecord.observed_at_utc,
        ),
        _TableSpec(
            "portfolio_pnl_snapshots",
            PortfolioPnlSnapshotRecord,
            PortfolioPnlSnapshotRecord.source_system,
            PortfolioPnlSnapshotRecord.valuation_time_utc,
        ),
        # Published TSO tariff rows carry the publishing TSO, not a source
        # system; the TSO is the honest provenance label for a tariff row.
        _TableSpec(
            "tso_tariffs",
            TsoTariffRecord,
            TsoTariffRecord.tso,
            TsoTariffRecord.created_at_utc,
        ),
        # Operator-upserted contracts have no source column at all: the row
        # count and update time are the whole provenance story.
        _TableSpec(
            "upstream_resource_contracts",
            UpstreamResourceContractRecord,
            None,
            UpstreamResourceContractRecord.updated_at_utc,
        ),
        _TableSpec(
            "capacity_profiles",
            CapacityProfileRecord,
            None,
            CapacityProfileRecord.created_at_utc,
        ),
        _TableSpec(
            "route_candidates",
            RouteCandidateRecord,
            None,
            RouteCandidateRecord.created_at_utc,
        ),
        _TableSpec(
            "reference_nodes",
            ReferenceNode,
            ReferenceNode.source_system,
            ReferenceNode.created_at_utc,
        ),
        _TableSpec(
            "reference_edges",
            ReferenceEdge,
            ReferenceEdge.source_system,
            ReferenceEdge.created_at_utc,
        ),
        _TableSpec(
            "reference_facilities",
            ReferenceFacility,
            ReferenceFacility.source_system,
            ReferenceFacility.created_at_utc,
        ),
        _TableSpec(
            "reference_tso_access_points",
            ReferenceTsoAccessPoint,
            ReferenceTsoAccessPoint.source_system,
            ReferenceTsoAccessPoint.created_at_utc,
        ),
    )


#: Tables the provenance reader can aggregate, in stable order.
PROVENANCE_TABLES: tuple[str, ...] = tuple(spec.table for spec in _table_specs())


def table_provenance_summary(
    session: Session,
    tables: tuple[str, ...] | list[str],
) -> dict[str, dict[str, Any]]:
    """Return row counts and newest timestamps for the requested tables.

    Args:
        session: Active SQLAlchemy session.
        tables: Table names from :data:`PROVENANCE_TABLES`. Unknown names are
            reported with ``row_count`` 0 and no label detail, so a typo in a
            declaration is visible instead of silently empty.

    Returns:
        ``{table: {"row_count", "last_observed_at_utc", "labels": [...]}}``
        where each label entry is
        ``{"label", "row_count", "last_observed_at_utc"}``.
    """

    requested = list(dict.fromkeys(tables))
    summary: dict[str, dict[str, Any]] = {}
    specs = {spec.table: spec for spec in _table_specs()}
    for table in requested:
        spec = specs.get(table)
        if spec is None:
            summary[table] = {
                "row_count": 0,
                "last_observed_at_utc": None,
                "labels": [],
                "detail": "table is not part of the declared provenance registry",
            }
            continue
        summary[table] = _summarize_table(session, spec)
    return summary


def _summarize_table(session: Session, spec: _TableSpec) -> dict[str, Any]:
    """Aggregate one table into its provenance summary."""

    total_query = session.query(
        func.count(),
        func.max(spec.observed_column),
    )
    total, newest = total_query.one()
    labels: list[dict[str, Any]] = []
    if spec.label_column is not None:
        rows = (
            session.query(
                spec.label_column,
                func.count(),
                func.max(spec.observed_column),
            )
            .group_by(spec.label_column)
            .all()
        )
        labels = [
            {
                "label": str(label) if label is not None else "unknown",
                "row_count": int(count or 0),
                "last_observed_at_utc": _iso(observed),
            }
            for label, count, observed in rows
        ]
        labels.sort(key=lambda item: item["label"])
    return {
        "row_count": int(total or 0),
        "last_observed_at_utc": _iso(newest),
        "labels": labels,
    }


def create_analysis_snapshot(
    session: Session,
    descriptor: SnapshotDescriptor,
) -> dict[str, Any]:
    """Persist one Analysis Snapshot descriptor and return its payload.

    Args:
        session: Active SQLAlchemy session (the caller owns the transaction).
        descriptor: The descriptor built by the application service.

    Returns:
        The persisted descriptor payload, including ``content_hash``.
    """

    payload = descriptor_payload(descriptor)
    row = AnalysisSnapshotRecord(
        snapshot_id=descriptor.snapshot_id,
        schema_version=descriptor.schema_version,
        as_of_utc=_as_utc(descriptor.as_of_utc),
        gas_day=descriptor.gas_day,
        gas_day_calendar=descriptor.gas_day_calendar,
        time_basis=descriptor.time_basis,
        created_at_utc=_as_utc(descriptor.created_at_utc),
        created_by=descriptor.created_by,
        active_context_json=descriptor.active_context or None,
        market_data_versions_json=descriptor.market_data_versions or None,
        network_capacity_version_json=descriptor.network_capacity_version or None,
        portfolio_version_json=descriptor.portfolio_version or None,
        contract_resource_versions_json=descriptor.contract_resource_versions or None,
        tariff_fx_json=descriptor.tariff_fx or None,
        weather_demand_assumptions_json=descriptor.weather_demand_assumptions or None,
        manual_assumptions_json=descriptor.manual_assumptions or None,
        model_calculation_versions_json=descriptor.model_calculation_versions or None,
        entitlement_context_json=descriptor.entitlement_context or None,
        field_availability_json=[
            {
                "field": state.field,
                "state": state.state.value,
                "detail": state.detail,
                "unavailable_reason": state.unavailable_reason,
            }
            for state in descriptor.field_states
        ],
        source_refs=list(descriptor.source_refs) or None,
        warnings=list(descriptor.warnings) or None,
        content_hash=descriptor.content_hash,
    )
    session.add(row)
    session.flush()
    return {**payload, "content_hash": row.content_hash}


def get_analysis_snapshot(session: Session, snapshot_id: str) -> dict[str, Any] | None:
    """Return one persisted Analysis Snapshot by id, or ``None``.

    Args:
        session: Active SQLAlchemy session.
        snapshot_id: The reproducibility reference to resolve.

    Returns:
        The descriptor payload, or ``None`` when no such snapshot exists.
    """

    row = session.get(AnalysisSnapshotRecord, snapshot_id)
    return analysis_snapshot_payload(row) if row is not None else None


def list_analysis_snapshots(
    session: Session,
    *,
    limit: int = 50,
    gas_day: str | None = None,
    created_by: str | None = None,
) -> list[dict[str, Any]]:
    """List recent Analysis Snapshots, newest first.

    Args:
        session: Active SQLAlchemy session.
        limit: Maximum rows to return (clamped to 1..500).
        gas_day: Optional ISO gas-day label filter.
        created_by: Optional creator filter.

    Returns:
        Descriptor payloads ordered by ``created_at_utc`` descending.
    """

    query = session.query(AnalysisSnapshotRecord)
    if gas_day:
        query = query.filter(AnalysisSnapshotRecord.gas_day == gas_day)
    if created_by:
        query = query.filter(AnalysisSnapshotRecord.created_by == created_by)
    rows = (
        query.order_by(
            AnalysisSnapshotRecord.created_at_utc.desc(),
            AnalysisSnapshotRecord.snapshot_id.desc(),
        )
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [analysis_snapshot_payload(row) for row in rows]


def analysis_snapshot_payload(row: AnalysisSnapshotRecord) -> dict[str, Any]:
    """Serialize an Analysis Snapshot row to its API payload shape.

    Args:
        row: The persisted descriptor row.

    Returns:
        Dict with the section 6 fields, the declared per-field availability and
        the deterministic ``content_hash`` reproducibility reference.
    """

    return {
        "snapshot_id": row.snapshot_id,
        "schema_version": row.schema_version,
        "as_of_utc": _iso(row.as_of_utc),
        "gas_day": row.gas_day,
        "gas_day_calendar": row.gas_day_calendar,
        "time_basis": row.time_basis,
        "created_at_utc": _iso(row.created_at_utc),
        "created_by": row.created_by,
        "market_data_versions": row.market_data_versions_json,
        "network_capacity_version": row.network_capacity_version_json,
        "portfolio_version": row.portfolio_version_json,
        "contract_resource_versions": row.contract_resource_versions_json,
        "tariff_fx": row.tariff_fx_json,
        "weather_demand_assumptions": row.weather_demand_assumptions_json,
        "manual_assumptions": row.manual_assumptions_json,
        "model_calculation_versions": row.model_calculation_versions_json,
        "entitlement_context": row.entitlement_context_json,
        "active_context": row.active_context_json,
        "field_availability": row.field_availability_json or [],
        "source_refs": row.source_refs or [],
        "warnings": row.warnings or [],
        "content_hash": row.content_hash,
        "research_only": row.research_only,
        "human_review_required": row.human_review_required,
    }


def _iso(value: datetime | None) -> str | None:
    """Return an aware UTC ISO-8601 string, or ``None``."""

    return _as_utc(value).isoformat() if value is not None else None


def _as_utc(value: datetime) -> datetime:
    """Normalize a timestamp to aware UTC (naive timestamps are UTC)."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
