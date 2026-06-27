"""Read-only /api/reference-network routes."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["reference-network"])


# ---------------------------------------------------------------------------
# Node routes
# ---------------------------------------------------------------------------


@router.get("/api/reference-network/nodes")
def list_nodes(
    request: Request,
    country: str | None = Query(None, max_length=2),
    node_type: str | None = Query(None),
) -> dict:
    """List reference network nodes."""
    nodes = _db_nodes(country=country.upper() if country else None, node_type=node_type)
    if nodes is None:
        return _runtime_not_configured_envelope([], request, table="reference_nodes")

    return _envelope(nodes, request, source="postgresql")


@router.get("/api/reference-network/nodes/{node_id}")
def get_node(node_id: str, request: Request) -> dict:
    """Get a single reference network node by ID."""
    node = _db_node(node_id)
    if node is not None:
        return _envelope(node, request, source="postgresql")

    if _db_is_configured():
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")

    raise _db_not_configured("reference_nodes")


# ---------------------------------------------------------------------------
# Edge routes
# ---------------------------------------------------------------------------


@router.get("/api/reference-network/edges")
def list_edges(
    request: Request,
    from_node_id: str | None = Query(None),
    to_node_id: str | None = Query(None),
) -> dict:
    """List reference network edges."""
    edges = _db_edges(from_node_id=from_node_id, to_node_id=to_node_id)
    if edges is None:
        return _runtime_not_configured_envelope([], request, table="reference_edges")

    return _envelope(edges, request, source="postgresql")


@router.get("/api/reference-network/edges/{edge_id}")
def get_edge(edge_id: str, request: Request) -> dict:
    """Get a single reference network edge by ID."""
    edge = _db_edge(edge_id)
    if edge is not None:
        return _envelope(edge, request, source="postgresql")

    if _db_is_configured():
        raise HTTPException(status_code=404, detail=f"Edge '{edge_id}' not found.")

    raise _db_not_configured("reference_edges")


# ---------------------------------------------------------------------------
# Facility routes
# ---------------------------------------------------------------------------


@router.get("/api/reference-network/facilities")
def list_facilities(
    request: Request,
    facility_type: str | None = Query(None),
    country: str | None = Query(None, max_length=2),
) -> dict:
    """List reference network facilities."""
    facilities = _db_facilities(
        facility_type=facility_type,
        country=country.upper() if country else None,
    )
    if facilities is None:
        return _runtime_not_configured_envelope([], request, table="reference_facilities")

    return _envelope(facilities, request, source="postgresql")


@router.get("/api/reference-network/facilities/{facility_id}")
def get_facility(facility_id: str, request: Request) -> dict:
    """Get a single reference facility by ID."""
    facility = _db_facility(facility_id)
    if facility is not None:
        return _envelope(facility, request, source="postgresql")

    if _db_is_configured():
        raise HTTPException(status_code=404, detail=f"Facility '{facility_id}' not found.")

    raise _db_not_configured("reference_facilities")


# ---------------------------------------------------------------------------
# Market hub routes
# ---------------------------------------------------------------------------


@router.get("/api/reference-network/market-hubs")
def list_market_hubs(request: Request) -> dict:
    """List reference market hubs."""
    hubs = _db_market_hubs()
    if hubs is None:
        return _runtime_not_configured_envelope([], request, table="reference_market_hubs")

    return _envelope(hubs, request, source="postgresql")


@router.get("/api/reference-network/tso-access")
def list_tso_access(
    request: Request,
    point_id: str | None = Query(None),
    country: str | None = Query(None, max_length=8),
    operator_key: str | None = Query(None),
    direction: str | None = Query(None, max_length=16),
) -> dict:
    """List source-owned TSO access metadata for routing eligibility checks."""
    rows = _db_tso_access_points(
        point_id=point_id,
        country=country.upper() if country else None,
        operator_key=operator_key,
        direction=direction.lower() if direction else None,
    )
    if rows is None:
        return _runtime_not_configured_envelope([], request, table="reference_tso_access_points")

    return _envelope(rows, request, source="postgresql")


# ---------------------------------------------------------------------------
# Optional PostgreSQL reads
# ---------------------------------------------------------------------------


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _session_or_none():
    if not _db_is_configured():
        return None

    from eurogas_nexus.db.session import get_session_factory

    return get_session_factory()()


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_nodes(*, country: str | None = None, node_type: str | None = None) -> list[dict] | None:
    sqlalchemy_error = _sqlalchemy_error_type()
    session = _session_or_none()
    if session is None:
        return None

    try:
        from eurogas_nexus.db.repositories.reference_network import SqlAlchemyNodeRepository

        with session:
            repo = SqlAlchemyNodeRepository(session)
            return [asdict(row) for row in repo.list_all(country=country, node_type=node_type)]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_node(node_id: str) -> dict | None:
    sqlalchemy_error = _sqlalchemy_error_type()
    session = _session_or_none()
    if session is None:
        return None

    try:
        from eurogas_nexus.db.repositories.reference_network import SqlAlchemyNodeRepository

        with session:
            row = SqlAlchemyNodeRepository(session).get_by_id(node_id)
            return asdict(row) if row else None
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_edges(
    *,
    from_node_id: str | None = None,
    to_node_id: str | None = None,
) -> list[dict] | None:
    sqlalchemy_error = _sqlalchemy_error_type()
    session = _session_or_none()
    if session is None:
        return None

    try:
        from eurogas_nexus.db.repositories.reference_network import SqlAlchemyEdgeRepository

        with session:
            repo = SqlAlchemyEdgeRepository(session)
            return [
                asdict(row)
                for row in repo.list_all(from_node_id=from_node_id, to_node_id=to_node_id)
            ]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_edge(edge_id: str) -> dict | None:
    sqlalchemy_error = _sqlalchemy_error_type()
    session = _session_or_none()
    if session is None:
        return None

    try:
        from eurogas_nexus.db.repositories.reference_network import SqlAlchemyEdgeRepository

        with session:
            row = SqlAlchemyEdgeRepository(session).get_by_id(edge_id)
            return asdict(row) if row else None
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_facilities(
    *,
    facility_type: str | None = None,
    country: str | None = None,
) -> list[dict] | None:
    sqlalchemy_error = _sqlalchemy_error_type()
    session = _session_or_none()
    if session is None:
        return None

    try:
        from eurogas_nexus.db.repositories.reference_network import SqlAlchemyFacilityRepository

        with session:
            repo = SqlAlchemyFacilityRepository(session)
            return [
                asdict(row)
                for row in repo.list_all(facility_type=facility_type, country=country)
            ]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_facility(facility_id: str) -> dict | None:
    sqlalchemy_error = _sqlalchemy_error_type()
    session = _session_or_none()
    if session is None:
        return None

    try:
        from eurogas_nexus.db.repositories.reference_network import SqlAlchemyFacilityRepository

        with session:
            row = SqlAlchemyFacilityRepository(session).get_by_id(facility_id)
            return asdict(row) if row else None
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_market_hubs() -> list[dict] | None:
    sqlalchemy_error = _sqlalchemy_error_type()
    session = _session_or_none()
    if session is None:
        return None

    try:
        from eurogas_nexus.db.repositories.reference_network import SqlAlchemyMarketHubRepository

        with session:
            return [asdict(row) for row in SqlAlchemyMarketHubRepository(session).list_all()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_tso_access_points(
    *,
    point_id: str | None = None,
    country: str | None = None,
    operator_key: str | None = None,
    direction: str | None = None,
) -> list[dict] | None:
    sqlalchemy_error = _sqlalchemy_error_type()
    session = _session_or_none()
    if session is None:
        return None

    try:
        from eurogas_nexus.db.repositories.reference_network import (
            SqlAlchemyTsoAccessPointRepository,
        )

        with session:
            repo = SqlAlchemyTsoAccessPointRepository(session)
            return [
                asdict(row)
                for row in repo.list_all(
                    point_id=point_id,
                    country=country,
                    operator_key=operator_key,
                    direction=direction,
                )
            ]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": (
                "Runtime database is configured but unavailable for reference network reads."
            ),
            "error_class": exc.__class__.__name__,
        },
    )


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


def _envelope(data: object, request: Request, *, source: str) -> dict:
    """Wrap runtime DB data in a decision-support response envelope."""
    source_label = "runtime-postgresql" if source == "postgresql" else source
    warnings: list[str] = []
    if isinstance(data, list) and not data:
        warnings.append(
            "Runtime database returned no reference-network rows; run ingestion or seed test data."
        )

    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source_label],
            "lineage": [source_label],
            "assumptions": [
                "Reference-network responses are read from the configured runtime database."
            ],
            "missing_inputs": [],
            "warnings": warnings,
        },
    }


def _runtime_not_configured_envelope(data: object, request: Request, *, table: str) -> dict:
    _ = request
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-db-not-configured"],
            "lineage": ["runtime-db-not-configured"],
            "assumptions": [
                "No runtime DB URL is configured; the API did not synthesize "
                "reference-network data."
            ],
            "missing_inputs": ["RUNTIME_STORE_DATABASE_URL", table],
            "warnings": [
                "Reference-network data is unavailable until a runtime DB is configured "
                "and populated."
            ],
        },
    }


def _db_not_configured(table: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_not_configured",
            "message": "Runtime database is not configured for reference-network reads.",
            "missing_inputs": ["RUNTIME_STORE_DATABASE_URL", table],
        },
    )

