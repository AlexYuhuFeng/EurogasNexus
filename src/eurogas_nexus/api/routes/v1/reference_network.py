"""Read-only /api/v1/reference-network routes."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["reference-network"])


# ---------------------------------------------------------------------------
# Node routes
# ---------------------------------------------------------------------------


@router.get("/api/v1/reference-network/nodes")
def list_nodes(
    request: Request,
    country: str | None = Query(None, max_length=2),
    node_type: str | None = Query(None),
) -> dict:
    """List reference network nodes."""
    nodes = _db_nodes(country=country.upper() if country else None, node_type=node_type)
    if nodes is None:
        nodes = _fixture_nodes()
        if country:
            nodes = [n for n in nodes if n["country"] == country.upper()]
        if node_type:
            nodes = [n for n in nodes if n["node_type"] == node_type]
        return _envelope(nodes, request, source="synthetic-fixture")

    return _envelope(nodes, request, source="postgresql")


@router.get("/api/v1/reference-network/nodes/{node_id}")
def get_node(node_id: str, request: Request) -> dict:
    """Get a single reference network node by ID."""
    node = _db_node(node_id)
    if node is not None:
        return _envelope(node, request, source="postgresql")

    if _db_is_configured():
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")

    for fixture_node in _fixture_nodes():
        if fixture_node["id"] == node_id:
            return _envelope(fixture_node, request, source="synthetic-fixture")
    raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")


# ---------------------------------------------------------------------------
# Edge routes
# ---------------------------------------------------------------------------


@router.get("/api/v1/reference-network/edges")
def list_edges(
    request: Request,
    from_node_id: str | None = Query(None),
    to_node_id: str | None = Query(None),
) -> dict:
    """List reference network edges."""
    edges = _db_edges(from_node_id=from_node_id, to_node_id=to_node_id)
    if edges is None:
        edges = _fixture_edges()
        if from_node_id:
            edges = [e for e in edges if e["from_node_id"] == from_node_id]
        if to_node_id:
            edges = [e for e in edges if e["to_node_id"] == to_node_id]
        return _envelope(edges, request, source="synthetic-fixture")

    return _envelope(edges, request, source="postgresql")


@router.get("/api/v1/reference-network/edges/{edge_id}")
def get_edge(edge_id: str, request: Request) -> dict:
    """Get a single reference network edge by ID."""
    edge = _db_edge(edge_id)
    if edge is not None:
        return _envelope(edge, request, source="postgresql")

    if _db_is_configured():
        raise HTTPException(status_code=404, detail=f"Edge '{edge_id}' not found.")

    for fixture_edge in _fixture_edges():
        if fixture_edge["id"] == edge_id:
            return _envelope(fixture_edge, request, source="synthetic-fixture")
    raise HTTPException(status_code=404, detail=f"Edge '{edge_id}' not found.")


# ---------------------------------------------------------------------------
# Facility routes
# ---------------------------------------------------------------------------


@router.get("/api/v1/reference-network/facilities")
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
        facilities = _fixture_facilities()
        if facility_type:
            facilities = [f for f in facilities if f["facility_type"] == facility_type]
        if country:
            facilities = [f for f in facilities if f["country"] == country.upper()]
        return _envelope(facilities, request, source="synthetic-fixture")

    return _envelope(facilities, request, source="postgresql")


@router.get("/api/v1/reference-network/facilities/{facility_id}")
def get_facility(facility_id: str, request: Request) -> dict:
    """Get a single reference facility by ID."""
    facility = _db_facility(facility_id)
    if facility is not None:
        return _envelope(facility, request, source="postgresql")

    if _db_is_configured():
        raise HTTPException(status_code=404, detail=f"Facility '{facility_id}' not found.")

    for fixture_facility in _fixture_facilities():
        if fixture_facility["id"] == facility_id:
            return _envelope(fixture_facility, request, source="synthetic-fixture")
    raise HTTPException(status_code=404, detail=f"Facility '{facility_id}' not found.")


# ---------------------------------------------------------------------------
# Market hub routes
# ---------------------------------------------------------------------------


@router.get("/api/v1/reference-network/market-hubs")
def list_market_hubs(request: Request) -> dict:
    """List reference market hubs."""
    hubs = _db_market_hubs()
    if hubs is None:
        return _envelope(_fixture_market_hubs(), request, source="synthetic-fixture")

    return _envelope(hubs, request, source="postgresql")


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
    """Wrap data in a research-safe response envelope."""
    source_label = "runtime-postgresql" if source == "postgresql" else "synthetic-fixture"
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source_label],
            "lineage": [source_label],
            "assumptions": ["All data is synthetic; no real vendor or operator data."],
            "missing_inputs": [],
            "warnings": [
                "Synthetic fixture data only. Do not use for commercial decisions."
            ],
        },
    }


# ---------------------------------------------------------------------------
# Synthetic fixtures (no real vendor data)
# ---------------------------------------------------------------------------


def _fixture_nodes() -> list[dict]:
    return [
        _node("node-ttf", "TTF Hub", "hub", "NL", 52.37, 4.90),
        _node("node-nbp", "NBP Hub", "hub", "GB", 52.63, -1.14),
        _node("node-peg", "PEG Nord", "hub", "FR", 49.26, 2.47),
        _node("node-ncg", "NCG Hub", "hub", "DE", 51.34, 6.56),
        _node("node-psv", "PSV Hub", "hub", "AT", 48.21, 16.37),
        _node("node-zeebrugge", "Zeebrugge", "interconnection", "BE", 51.33, 3.20, 1.2e6),
        _node("node-emden", "Emden Entry", "entry_point", "DE", 53.37, 7.20, 2.5e6),
        _node("node-bacton", "Bacton Terminal", "entry_point", "GB", 52.85, 1.47, 1.8e6),
        _node("node-dunkerque", "Dunkerque LNG", "lng", "FR", 51.04, 2.38, 1.5e6),
        _node("node-gate", "Gate LNG", "lng", "NL", 51.90, 4.30, 1.3e6),
        _node("node-mallnow", "Mallnow", "interconnection", "DE", 52.54, 14.28, 0.8e6),
        _node("node-tarvisio", "Tarvisio", "interconnection", "IT", 46.51, 13.58, 1.0e6),
    ]


def _node(
    id_: str,
    name: str,
    node_type: str,
    country: str,
    lat: float,
    lon: float,
    capacity: float | None = None,
) -> dict:
    return {
        "id": id_,
        "name": name,
        "node_type": node_type,
        "country": country,
        "lat": lat,
        "lon": lon,
        "capacity_boe_d": capacity,
    }


def _fixture_edges() -> list[dict]:
    return [
        _edge("edge-1", "node-ttf", "node-ncg", 200),
        _edge("edge-2", "node-ncg", "node-psv", 750),
        _edge("edge-3", "node-zeebrugge", "node-ttf", 180),
        _edge("edge-4", "node-nbp", "node-zeebrugge", 220),
        _edge("edge-5", "node-peg", "node-ncg", 500),
        _edge("edge-6", "node-emden", "node-ncg", 250),
        _edge("edge-7", "node-bacton", "node-zeebrugge", 200),
        _edge("edge-8", "node-dunkerque", "node-peg", 260),
        _edge("edge-9", "node-gate", "node-ttf", 100),
        _edge("edge-10", "node-mallnow", "node-ncg", 150),
    ]


def _edge(id_: str, from_id: str, to_id: str, length: float) -> dict:
    return {
        "id": id_,
        "from_node_id": from_id,
        "to_node_id": to_id,
        "edge_type": "pipeline",
        "length_km": length,
    }


def _fixture_facilities() -> list[dict]:
    return [
        _fac("fac-zee-lng", "Zeebrugge LNG", "lng_terminal", "BE", 51.33, 3.20, 1.0e6),
        _fac("fac-gate-lng", "Gate LNG", "lng_terminal", "NL", 51.90, 4.30, 1.3e6),
        _fac("fac-dunk-lng", "Dunkerque LNG", "lng_terminal", "FR", 51.04, 2.38, 1.5e6),
        _fac("fac-bacton", "Bacton Terminal", "border_point", "GB", 52.85, 1.47, 1.8e6),
        _fac("fac-emden", "Emden Entry", "border_point", "DE", 53.37, 7.20, 2.5e6),
        _fac("fac-mallnow", "Mallnow Comp.", "compressor", "DE", 52.54, 14.28, 0.8e6),
        _fac("fac-haidach", "Haidach", "storage", "AT", 47.95, 13.22, 0.5e6),
    ]


def _fac(
    id_: str,
    name: str,
    facility_type: str,
    country: str,
    lat: float,
    lon: float,
    capacity: float | None = None,
) -> dict:
    return {
        "id": id_,
        "name": name,
        "facility_type": facility_type,
        "country": country,
        "lat": lat,
        "lon": lon,
        "capacity_boe_d": capacity,
    }


def _fixture_market_hubs() -> list[dict]:
    return [
        _hub("hub-ttf", "TTF", "TTF", "NL", "Primary European gas trading hub"),
        _hub("hub-nbp", "NBP", "NBP", "GB", "UK gas trading hub"),
        _hub("hub-peg", "PEG", "PEG", "FR", "French gas trading hub"),
        _hub("hub-ncg", "NCG", "NCG", "DE", "German gas trading hub"),
        _hub("hub-psv", "PSV", "PSV", "AT", "Austrian gas trading hub"),
        _hub("hub-eex", "EEX", "EEX", "DE", "Power and gas exchange"),
        _hub("hub-ice", "ICE OCM", "ICE-OCM", "GB", "ICE Endex OCM gas trading"),
    ]


def _hub(id_: str, name: str, code: str, country: str, desc: str) -> dict:
    return {
        "id": id_,
        "name": name,
        "hub_code": code,
        "country": country,
        "description": desc,
    }
