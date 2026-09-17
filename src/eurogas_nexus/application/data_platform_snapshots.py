"""Analysis Snapshot application service (Architecture V2 Wave 4).

Builds a persisted Analysis Snapshot descriptor from the data that actually
exists at creation time (``07_DATA_PLATFORM.md`` section 6). The rules this
service enforces:

1. **Measure, never fabricate.** Every version reference is derived from a real
   count and timestamp read from the canonical runtime tables. A field with no
   implementation is recorded with an explicit
   :class:`~eurogas_nexus.domain.data_platform.snapshots.AvailabilityState` of
   ``UNAVAILABLE`` plus a stable reason code - never a placeholder value.
2. **The schema accepts the value later.** Fields are stored individually, so
   the day a producer appears the column is filled without a shape change.
3. **The Active Context is first-class.** The context the snapshot was taken in
   is persisted with the descriptor (``02_ARCHITECTURE_CONSTITUTION.md`` rule 31).
4. **Entitlement context is recorded, not inferred later.** Which families the
   creating principal held is part of the descriptor, so a reader can tell
   whether a restricted source could have contributed.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from eurogas_nexus.domain.data_platform.products import (
    data_products,
    evaluate_product_entitlement,
)
from eurogas_nexus.domain.data_platform.snapshots import (
    ACTIVE_CONTEXT_KEYS,
    ANALYSIS_SNAPSHOT_SCHEMA_VERSION,
    UNSUPPORTED_ACTIVE_CONTEXT_KEYS,
    AvailabilityState,
    DescriptorFieldState,
    SnapshotDescriptor,
)
from eurogas_nexus.domain.dataops.entitlement import allowed_source_families
from eurogas_nexus.domain.market.gas_day import (
    EU_CAM_UTC_CALENDAR,
    gas_day_label,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps the API import DB-free
    from sqlalchemy.orm import Session

#: Time basis recorded on every snapshot created today. Market and physical
#: products are gas-day based; the descriptor states it explicitly so a reader
#: never has to guess (``docs/architecture/UI_CONTENT_STANDARDS.md`` time basis).
DEFAULT_TIME_BASIS = "gas_day"

_UNAVAILABLE_REASON_NO_DB = "RUNTIME_DATABASE_NOT_CONFIGURED"
_UNAVAILABLE_REASON_NO_ROWS = "NO_RUNTIME_ROWS"
_UNAVAILABLE_REASON_NOT_IMPLEMENTED = "PRODUCER_NOT_IMPLEMENTED"


def build_analysis_snapshot(
    principal: AuthenticatedPrincipal,
    *,
    session: Session | None,
    active_context: Mapping[str, Any] | None = None,
    manual_assumptions: Mapping[str, Any] | None = None,
    as_of_utc: datetime | None = None,
    now_utc: datetime | None = None,
) -> SnapshotDescriptor:
    """Build one Analysis Snapshot descriptor from available runtime data.

    Args:
        principal: The authenticated principal creating the snapshot.
        session: Open SQLAlchemy session, or ``None`` when no runtime database is
            configured (the descriptor then records that fact per field).
        active_context: Active Context values accepted from the request.
        manual_assumptions: Operator-supplied assumptions for this analysis.
        as_of_utc: The instant the analysis context is valid as of; defaults to
            ``now_utc``.
        now_utc: Creation clock; injectable for deterministic tests.

    Returns:
        A descriptor ready to persist. It is not written here: the caller owns
        the transaction (see ``db/repositories/data_platform.py``).
    """

    now = _as_utc(now_utc or datetime.now(UTC))
    as_of = _as_utc(as_of_utc or now)
    provenance = _load_provenance(session)
    runtime_available = session is not None

    market_data_versions, market_state = _market_data_versions(provenance, runtime_available)
    network_version, network_state = _network_capacity_version(provenance, runtime_available)
    portfolio_version, portfolio_state = _portfolio_version(provenance, runtime_available)
    contract_versions, contract_state = _contract_resource_versions(
        provenance, runtime_available
    )
    tariff_fx, tariff_state = _tariff_fx(provenance, runtime_available)
    weather_assumptions, weather_state = _weather_demand_assumptions()
    assumptions = dict(manual_assumptions or {})
    assumptions_state = DescriptorFieldState(
        field="manual_assumptions",
        state=AvailabilityState.AVAILABLE if assumptions else AvailabilityState.UNAVAILABLE,
        detail=(
            f"{len(assumptions)} operator-supplied assumption(s) recorded."
            if assumptions
            else "No manual assumption was supplied with this snapshot."
        ),
        unavailable_reason="" if assumptions else "NO_MANUAL_ASSUMPTIONS_SUPPLIED",
    )
    model_versions = _model_calculation_versions()
    entitlement_context, entitlement_state = _entitlement_context(principal)

    context = _validated_context(active_context)
    warnings = _warnings(
        runtime_available=runtime_available,
        weather_state=weather_state,
        entitlement_context=entitlement_context,
    )
    return SnapshotDescriptor(
        snapshot_id=f"asnap-{uuid4().hex[:24]}",
        schema_version=ANALYSIS_SNAPSHOT_SCHEMA_VERSION,
        as_of_utc=as_of,
        gas_day=gas_day_label(as_of, calendar=EU_CAM_UTC_CALENDAR),
        gas_day_calendar=EU_CAM_UTC_CALENDAR,
        time_basis=DEFAULT_TIME_BASIS,
        created_at_utc=now,
        created_by=principal.name or principal.principal_id,
        market_data_versions=market_data_versions,
        network_capacity_version=network_version,
        portfolio_version=portfolio_version,
        contract_resource_versions=contract_versions,
        tariff_fx=tariff_fx,
        weather_demand_assumptions=weather_assumptions,
        manual_assumptions=assumptions,
        model_calculation_versions=model_versions,
        entitlement_context=entitlement_context,
        field_states=(
            market_state,
            network_state,
            portfolio_state,
            contract_state,
            tariff_state,
            weather_state,
            assumptions_state,
            DescriptorFieldState(
                field="model_calculation_versions",
                state=AvailabilityState.AVAILABLE,
                detail="Declared engine and schema versions resolved from release constants.",
            ),
            entitlement_state,
        ),
        active_context=context,
        source_refs=tuple(_source_refs(provenance)),
        warnings=warnings,
    )


def _load_provenance(session: Session | None) -> dict[str, dict[str, Any]]:
    """Read the provenance summary for every table a snapshot references."""

    if session is None:
        return {}
    from eurogas_nexus.db.repositories.data_platform import table_provenance_summary

    return table_provenance_summary(session, sorted(_SNAPSHOT_TABLES))


#: Canonical tables each section 6 field derives its version reference from.
_SNAPSHOT_TABLES: tuple[str, ...] = (
    "market_observations",
    "market_quotes",
    "screen_order_observations",
    "capacity_observations",
    "flow_observations",
    "storage_observations",
    "lng_observations",
    "fx_observations",
    "tso_tariffs",
    "upstream_resource_contracts",
    "capacity_profiles",
    "route_candidates",
    "reference_nodes",
    "reference_edges",
    "reference_facilities",
    "reference_tso_access_points",
    "portfolio_pnl_snapshots",
)


def _market_data_versions(
    provenance: Mapping[str, dict[str, Any]],
    runtime_available: bool,
) -> tuple[dict[str, Any], DescriptorFieldState]:
    """Version reference for the market observations an analysis consumed."""

    tables = ("market_observations", "market_quotes", "screen_order_observations")
    payload = _version_payload(provenance, tables)
    return payload, _state_for(
        "market_data_versions",
        payload,
        runtime_available=runtime_available,
        available_detail="Market observation and quote versions resolved from the runtime tables.",
    )


def _network_capacity_version(
    provenance: Mapping[str, dict[str, Any]],
    runtime_available: bool,
) -> tuple[dict[str, Any], DescriptorFieldState]:
    """Version reference for the network topology and capacity state."""

    tables = (
        "capacity_observations",
        "reference_nodes",
        "reference_edges",
        "reference_facilities",
        "reference_tso_access_points",
    )
    payload = _version_payload(provenance, tables)
    return payload, _state_for(
        "network_capacity_version",
        payload,
        runtime_available=runtime_available,
        available_detail="Reference network and capacity versions resolved from runtime tables.",
    )


def _portfolio_version(
    provenance: Mapping[str, dict[str, Any]],
    runtime_available: bool,
) -> tuple[dict[str, Any], DescriptorFieldState]:
    """Version reference for the imported position and valuation state."""

    tables = ("screen_order_observations", "portfolio_pnl_snapshots", "capacity_profiles")
    payload = _version_payload(provenance, tables)
    return payload, _state_for(
        "portfolio_version",
        payload,
        runtime_available=runtime_available,
        available_detail="Imported order, valuation and capacity profile versions resolved.",
    )


def _contract_resource_versions(
    provenance: Mapping[str, dict[str, Any]],
    runtime_available: bool,
) -> tuple[dict[str, Any], DescriptorFieldState]:
    """Version reference for operator-owned contracts and resource options."""

    tables = ("upstream_resource_contracts", "route_candidates")
    payload = _version_payload(provenance, tables)
    return payload, _state_for(
        "contract_resource_versions",
        payload,
        runtime_available=runtime_available,
        available_detail="Upstream contract and route candidate versions resolved.",
    )


def _tariff_fx(
    provenance: Mapping[str, dict[str, Any]],
    runtime_available: bool,
) -> tuple[dict[str, Any], DescriptorFieldState]:
    """Version reference for tariff rows and FX reference rates."""

    tables = ("tso_tariffs", "fx_observations")
    payload = _version_payload(provenance, tables)
    return payload, _state_for(
        "tariff_fx",
        payload,
        runtime_available=runtime_available,
        available_detail="Tariff and ECB FX versions resolved from the runtime tables.",
    )


def _weather_demand_assumptions() -> tuple[dict[str, Any], DescriptorFieldState]:
    """Weather/demand assumptions: explicitly unavailable today.

    No weather ingestion path exists in this repository, so recording a value
    here would be fabrication. The reason code matches the warning the weather
    surface already returns.
    """

    payload = {
        "status": AvailabilityState.UNAVAILABLE.value,
        "source_systems": ["Weather"],
        "reason": "WEATHER_SOURCE_NOT_CONFIGURED",
        "detail": (
            "No weather, HDD or CDD producer is implemented; /api/weather/* returns an "
            "empty list with WEATHER_SOURCE_NOT_CONFIGURED."
        ),
    }
    return payload, DescriptorFieldState(
        field="weather_demand_assumptions",
        state=AvailabilityState.UNAVAILABLE,
        detail=payload["detail"],
        unavailable_reason="WEATHER_SOURCE_NOT_CONFIGURED",
    )


def _model_calculation_versions() -> dict[str, Any]:
    """Declared model, solver and schema versions of this platform build."""

    from eurogas_nexus.domain.agents.research_plan import PLAN_SCHEMA_VERSION
    from eurogas_nexus.domain.agents.strategy_ir import STRATEGY_IR_SCHEMA_VERSION
    from eurogas_nexus.domain.research.ontology import ONTOLOGY_SCHEMA_VERSION
    from eurogas_nexus.ingestion.simulated_market_prices import SIMULATOR_VERSION
    from eurogas_nexus.release.constants import (
        API_CONTRACT_VERSION,
        BACKTEST_ENGINE_VERSION,
        RUN_SCHEMA_VERSION,
        SOLVER_VERSION,
        STRATEGY_SCHEMA_VERSION,
    )
    from eurogas_nexus.version import APPLICATION_VERSION

    return {
        "application_version": APPLICATION_VERSION,
        "api_contract_version": API_CONTRACT_VERSION,
        "analysis_snapshot_schema_version": ANALYSIS_SNAPSHOT_SCHEMA_VERSION,
        "gas_day_calendar": EU_CAM_UTC_CALENDAR,
        "solver_version": SOLVER_VERSION,
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
        "strategy_schema_version": STRATEGY_SCHEMA_VERSION,
        "strategy_run_schema_version": RUN_SCHEMA_VERSION,
        "research_ontology_schema_version": ONTOLOGY_SCHEMA_VERSION,
        "research_plan_schema_version": PLAN_SCHEMA_VERSION,
        "strategy_ir_schema_version": STRATEGY_IR_SCHEMA_VERSION,
        "market_simulator_version": SIMULATOR_VERSION,
    }


def _entitlement_context(
    principal: AuthenticatedPrincipal,
) -> tuple[dict[str, Any], DescriptorFieldState]:
    """Entitlement context of the creating principal.

    Records the *scope the backend can express today*
    (``DATA:<family>`` from ``principal.data_scopes``) and how many declared
    data products the principal cannot see, so a reader can tell whether a
    restricted family could have contributed. This is evaluated from the
    declared catalogue and the existing fail-closed helper only - a snapshot
    descriptor is lineage metadata, not a commercial-data read. Family names the
    principal is not entitled to are counted, never listed.
    """

    verdicts = [
        evaluate_product_entitlement(principal, product) for product in data_products()
    ]
    restricted = [verdict for verdict in verdicts if not verdict.allowed]
    payload = {
        "principal_id": principal.principal_id,
        "role": principal.role,
        "roles": list(principal.roles),
        "auth_method": principal.auth_method,
        "entitled_source_families": sorted(allowed_source_families(principal)),
        "data_entitlement_refs": [f"DATA:{scope}" for scope in principal.data_scopes],
        "evaluated_product_count": len(verdicts),
        "restricted_product_count": len(restricted),
        "restricted_family_count": sum(
            verdict.restricted_family_count for verdict in restricted
        ),
        "unsupported_scope_kinds": ["ORGANIZATION", "PORTFOLIO", "MARKET", "REGION"],
    }
    return payload, DescriptorFieldState(
        field="entitlement_context",
        state=AvailabilityState.AVAILABLE,
        detail="Entitlement context recorded for the creating principal.",
    )


def _validated_context(active_context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep only declared Active Context keys with scalar values."""

    if not active_context:
        return {}
    context: dict[str, Any] = {}
    for key, value in active_context.items():
        if key not in ACTIVE_CONTEXT_KEYS:
            continue
        if isinstance(value, str | int | float | bool) or value is None:
            context[key] = value
    return context


def _warnings(
    *,
    runtime_available: bool,
    weather_state: DescriptorFieldState,
    entitlement_context: Mapping[str, Any],
) -> tuple[str, ...]:
    """Collect the explicit limitations a snapshot reader must see."""

    warnings: list[str] = []
    if not runtime_available:
        warnings.append("RUNTIME_DATABASE_NOT_CONFIGURED")
    if weather_state.state is not AvailabilityState.AVAILABLE:
        warnings.append("WEATHER_DEMAND_ASSUMPTIONS_UNAVAILABLE")
    if int(entitlement_context.get("restricted_product_count") or 0) > 0:
        warnings.append("CREATOR_ENTITLEMENT_LIMITED")
    if UNSUPPORTED_ACTIVE_CONTEXT_KEYS:
        warnings.append("ACTIVE_CONTEXT_DIMENSIONS_UNSUPPORTED")
    return tuple(warnings)


def _version_payload(
    provenance: Mapping[str, dict[str, Any]],
    tables: tuple[str, ...],
) -> dict[str, Any]:
    """Build a version reference block from the provenance summary."""

    from eurogas_nexus.domain.data_platform.snapshots import descriptor_content_hash

    entries = []
    sources: list[str] = []
    for table in tables:
        summary = provenance.get(table)
        if summary is None:
            entries.append(
                {"table": table, "row_count": None, "last_observed_at_utc": None, "measured": False}
            )
            continue
        entries.append(
            {
                "table": table,
                "row_count": summary["row_count"],
                "last_observed_at_utc": summary["last_observed_at_utc"],
                "measured": True,
            }
        )
        sources.extend(item["label"] for item in summary["labels"])
    measured_rows = sum(int(entry["row_count"] or 0) for entry in entries)
    return {
        "tables": entries,
        "measured_row_count": measured_rows,
        "source_systems": sorted(set(sources)),
        "version_ref": descriptor_content_hash({"tables": entries}),
    }


def _state_for(
    field: str,
    payload: Mapping[str, Any],
    *,
    runtime_available: bool,
    available_detail: str,
) -> DescriptorFieldState:
    """Declare availability for a version-reference field."""

    measured = int(payload.get("measured_row_count") or 0)
    if not runtime_available:
        return DescriptorFieldState(
            field=field,
            state=AvailabilityState.UNAVAILABLE,
            detail="No runtime database is configured; no version reference could be measured.",
            unavailable_reason=_UNAVAILABLE_REASON_NO_DB,
        )
    if measured == 0:
        return DescriptorFieldState(
            field=field,
            state=AvailabilityState.UNAVAILABLE,
            detail="The runtime tables for this field hold no rows; no version to reference.",
            unavailable_reason=_UNAVAILABLE_REASON_NO_ROWS,
        )
    return DescriptorFieldState(
        field=field,
        state=AvailabilityState.AVAILABLE,
        detail=available_detail,
    )


def _source_refs(provenance: Mapping[str, dict[str, Any]]) -> list[str]:
    """Return lineage references for the tables that actually hold rows."""

    return [
        f"{table}:rows={summary['row_count']}"
        for table, summary in sorted(provenance.items())
        if summary.get("row_count")
    ]


def _as_utc(value: datetime) -> datetime:
    """Normalize a timestamp to aware UTC (naive timestamps are UTC)."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
