"""Read-only /api source registry and ingestion status routes."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["sources"])


@router.get("/api/sources")
def list_sources(request: Request) -> dict:
    """List registered source systems with runtime DB counts when configured."""

    return _envelope(_sources_with_runtime_status(), request, source=_source_label())


@router.get("/api/sources/{source_id}")
def get_source(source_id: str, request: Request) -> dict:
    """Get a single registered source by ID."""

    for source in _sources_with_runtime_status():
        if source["source_id"] == source_id:
            return _envelope(source, request, source=_source_label())
    raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")


@router.get("/api/ingestion-runs")
def list_ingestion_runs(
    request: Request,
    source_id: str | None = Query(None),
) -> dict:
    """List persisted ingestion runs from the runtime DB."""

    runs = _db_ingestion_runs()
    if source_id:
        runs = [run for run in runs if run["source_id"] == source_id]
    return _envelope(runs, request, source=_source_label())


def _envelope(data: object, request: Request, *, source: str) -> dict:
    _ = request
    warnings: list[str] = []
    if source != "runtime-postgresql":
        warnings.append("Runtime database is not configured; live source counts are unavailable.")
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "lineage": [source],
            "assumptions": [
                "Source registry is static; counts and ingestion runs are read from runtime DB."
            ],
            "missing_inputs": (
                [] if source == "runtime-postgresql" else ["RUNTIME_STORE_DATABASE_URL"]
            ),
            "warnings": warnings,
        },
    }


def _registered_sources() -> list[dict]:
    return [
        _src("src-ecb", "ECB", ("fx-reference-rates",), "European Central Bank FX rates", False),
        _src(
            "src-entsog",
            "ENTSOG",
            ("connection-points", "operator-directions", "flows", "capacity", "outages", "ip"),
            "ENTSOG Transparency Platform",
            False,
        ),
        _src("src-gie", "GIE", ("agsi-storage", "alsi-lng"), "Gas Infrastructure Europe", True),
        _src(
            "src-eex",
            "EEX",
            ("power-futures", "gas-futures", "spot"),
            "European Energy Exchange",
            True,
        ),
        _src("src-trayport", "Trayport", ("market-data",), "Trayport market data", True),
        _src(
            "src-ice-ocm",
            "ICE_OCM",
            ("within-day", "day-ahead"),
            "ICE Endex OCM",
            True,
        ),
        _src(
            "src-weather",
            "Weather",
            ("temperature", "hdd", "cdd", "forecast"),
            "Weather and HDD/CDD data",
            True,
        ),
    ]


def _src(
    source_id: str,
    system: str,
    datasets: tuple[str, ...],
    description: str,
    entitled: bool,
) -> dict:
    return {
        "source_id": source_id,
        "source_system": system,
        "datasets": list(datasets),
        "status": "registered",
        "live_record_count": 0,
        "entitlement_scope": "licensed" if entitled else "public",
        "freshness_expectation_minutes": 60,
        "description": description,
        "credential_requirements": ["api_key"] if entitled else [],
        "export_restrictions": ["license-controlled"] if entitled else [],
    }


def _sources_with_runtime_status() -> list[dict]:
    sources = _registered_sources()
    counts = _runtime_source_counts()
    for source in sources:
        count = counts.get(source["source_system"], 0)
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
            CapacityObservationRecord,
            FlowObservationRecord,
            FxObservationRecord,
            LngObservationRecord,
            MarketObservationRecord,
            ReferenceNode,
            ReferenceTsoAccessPoint,
            StorageObservationRecord,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return {
                "ECB": session.query(MarketObservationRecord)
                .filter(MarketObservationRecord.source_system == "ECB")
                .count()
                + session.query(FxObservationRecord)
                .filter(FxObservationRecord.source_system == "ECB")
                .count(),
                "ENTSOG": session.query(FlowObservationRecord)
                .filter(FlowObservationRecord.source_system == "ENTSOG")
                .count()
                + session.query(ReferenceNode)
                .filter(ReferenceNode.id.like("entsog-%"))
                .count()
                + session.query(ReferenceTsoAccessPoint)
                .filter(ReferenceTsoAccessPoint.source_system == "ENTSOG")
                .count()
                + session.query(CapacityObservationRecord)
                .filter(CapacityObservationRecord.source_system == "ENTSOG")
                .count(),
                "GIE": session.query(StorageObservationRecord)
                .filter(StorageObservationRecord.source_system == "GIE")
                .count()
                + session.query(LngObservationRecord)
                .filter(LngObservationRecord.source_system == "GIE")
                .count(),
            }
    except sqlalchemy_error:
        return {}


def _db_ingestion_runs() -> list[dict]:
    if not _db_is_configured():
        return []

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import IngestionRunRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(IngestionRunRecord).order_by(
                IngestionRunRecord.started_at_utc.desc()
            )
            return [_ingestion_run_payload(row) for row in rows.all()]
    except sqlalchemy_error:
        return []


def _ingestion_run_payload(row) -> dict:
    source_id = {
        "ECB": "src-ecb",
        "ENTSOG": "src-entsog",
        "GIE-AGSI": "src-gie",
        "GIE-ALSI": "src-gie",
    }.get(row.source_name, row.source_name.lower())
    return {
        "run_id": row.run_id,
        "source_id": source_id,
        "source_name": row.source_name,
        "status": row.status,
        "started_at_utc": row.started_at_utc.isoformat(),
        "finished_at_utc": row.finished_at_utc.isoformat() if row.finished_at_utc else None,
        "records_ingested": _records_from_notes(row.notes),
        "records_failed": 0,
        "normalization": "normalized",
        "error_message": None if row.status == "succeeded" else row.notes,
        "source_reference": row.notes,
    }


def _records_from_notes(notes: str | None) -> int:
    if not notes:
        return 0
    match = re.match(r"(\d+)", notes)
    return int(match.group(1)) if match else 0


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _source_label() -> str:
    return "runtime-postgresql" if _db_is_configured() else "source-registry"


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError
