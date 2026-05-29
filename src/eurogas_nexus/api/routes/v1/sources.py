"""Read-only /api/v1 source registry and ingestion routes (fixture data only)."""

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["sources"])


# ---------------------------------------------------------------------------
# Source registry routes
# ---------------------------------------------------------------------------


@router.get("/api/v1/sources")
def list_sources(request: Request) -> dict:
    """List registered source systems (fixture data, no live checks)."""
    return _envelope(_sources_with_runtime_status(), request)


@router.get("/api/v1/sources/{source_id}")
def get_source(source_id: str, request: Request) -> dict:
    """Get a single registered source by ID."""
    for src in _sources_with_runtime_status():
        if src["source_id"] == source_id:
            return _envelope(src, request)
    raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")


# ---------------------------------------------------------------------------
# Ingestion run routes
# ---------------------------------------------------------------------------


@router.get("/api/v1/ingestion-runs")
def list_ingestion_runs(
    request: Request,
    source_id: str | None = Query(None),
) -> dict:
    """List ingestion runs (fixture data only)."""
    runs = _fixture_ingestion_runs()
    if source_id:
        runs = [r for r in runs if r["source_id"] == source_id]
    return _envelope(runs, request)


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


def _envelope(data: object, request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["synthetic-fixture"],
            "lineage": ["synthetic-fixture"],
            "assumptions": ["All data is synthetic — no live source data."],
            "missing_inputs": [],
            "warnings": [
                "Synthetic fixture data. No live connectors executed."
            ],
        },
    }


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _fixture_sources() -> list[dict]:
    return [
        _src("src-ecb", "ECB", ("fx-reference-rates",), "European Central Bank FX rates", False),
        _src(
            "src-entsog", "ENTSOG", ("flows", "capacity", "outages", "ip"),
            "ENTSOG Transparency Platform", False,
        ),
        _src("src-gie", "GIE", ("agsi-storage", "alsi-lng"), "Gas Infrastructure Europe", True),
        _src(
            "src-eex", "EEX", ("power-futures", "gas-futures", "spot"),
            "European Energy Exchange", True,
        ),
        _src("src-trayport", "Trayport", ("market-data",), "Trayport market data", True),
        _src(
            "src-ice-ocm", "ICE_OCM", ("within-day", "day-ahead"),
            "ICE Endex OCM", True,
        ),
        _src(
            "src-weather", "Weather", ("temperature", "hdd", "cdd", "forecast"),
            "Weather and HDD/CDD data", True,
        ),
    ]


def _src(sid: str, system: str, datasets: tuple[str, ...], desc: str, entitled: bool) -> dict:
    return {
        "source_id": sid,
        "source_system": system,
        "datasets": list(datasets),
        "status": "registered",
        "live_record_count": 0,
        "entitlement_scope": "licensed" if entitled else "internal-research",
        "freshness_expectation_minutes": 60,
        "description": desc,
        "credential_requirements": ["api_key"] if entitled else [],
        "export_restrictions": ["internal-research-only"] if entitled else [],
    }


def _sources_with_runtime_status() -> list[dict]:
    sources = _fixture_sources()
    counts = _runtime_source_counts()
    for source in sources:
        system = source["source_system"]
        count = counts.get(system, 0)
        source["live_record_count"] = count
        if count > 0:
            source["status"] = "active"
    return sources


def _runtime_source_counts() -> dict[str, int]:
    if not _db_is_configured():
        return {}

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import (
            FlowObservationRecord,
            LngObservationRecord,
            MarketObservationRecord,
            StorageObservationRecord,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return {
                "ECB": session.query(MarketObservationRecord)
                .filter(MarketObservationRecord.source_system == "ECB")
                .count(),
                "ENTSOG": session.query(FlowObservationRecord)
                .filter(FlowObservationRecord.source_system == "ENTSOG")
                .count(),
                "GIE": (
                    session.query(StorageObservationRecord)
                    .filter(StorageObservationRecord.source_system == "GIE")
                    .count()
                    + session.query(LngObservationRecord)
                    .filter(LngObservationRecord.source_system == "GIE")
                    .count()
                ),
            }
    except sqlalchemy_error:
        return {}


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _fixture_ingestion_runs() -> list[dict]:
    return [
        {
            "run_id": "run-001",
            "source_id": "src-ecb",
            "status": "succeeded",
            "started_at_utc": "2026-05-29T06:00:00Z",
            "finished_at_utc": "2026-05-29T06:01:00Z",
            "records_ingested": 30,
            "records_failed": 0,
            "normalization": "normalized",
            "error_message": None,
            "source_reference": "synthetic-fixture",
        },
        {
            "run_id": "run-002",
            "source_id": "src-entsog",
            "status": "succeeded",
            "started_at_utc": "2026-05-29T06:00:00Z",
            "finished_at_utc": "2026-05-29T06:05:00Z",
            "records_ingested": 500,
            "records_failed": 2,
            "normalization": "normalized",
            "error_message": None,
            "source_reference": "synthetic-fixture",
        },
        {
            "run_id": "run-003",
            "source_id": "src-weather",
            "status": "failed",
            "started_at_utc": "2026-05-29T06:00:00Z",
            "finished_at_utc": "2026-05-29T06:00:30Z",
            "records_ingested": 0,
            "records_failed": 100,
            "normalization": "unknown",
            "error_message": "Mock connector: no credentials configured.",
            "source_reference": "synthetic-fixture",
        },
    ]
