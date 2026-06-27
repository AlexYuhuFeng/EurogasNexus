"""Read-only /api source registry and ingestion status routes."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["sources"])

CATEGORY_LABELS = {
    "price": "Prices",
    "fx": "FX",
    "infrastructure": "Infrastructure",
    "tariff": "TSO Tariffs",
    "weather": "Weather",
    "ai": "LLM",
}

SOURCE_ID_BY_NAME = {
    "ARGUS": "src-argus",
    "DEEPSEEK": "src-deepseek",
    "ECB": "src-ecb",
    "EEX": "src-eex",
    "ENTSOG": "src-entsog",
    "GIE": "src-gie",
    "GIE-AGSI": "src-gie",
    "GIE-ALSI": "src-gie",
    "ICE_OCM": "src-ice-ocm",
    "ICE OCM": "src-ice-ocm",
    "ICIS": "src-icis",
    "KPLER": "src-kpler",
    "NATIONALGASNTS": "src-national-gas-nts",
    "NATIONAL_GAS_NTS": "src-national-gas-nts",
    "NATIONAL GAS NTS": "src-national-gas-nts",
    "PLATTS": "src-platts",
    "TRAYPORT": "src-trayport",
    "WEATHER": "src-weather",
}


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
        _src(
            "src-ecb",
            "ECB",
            "fx",
            ("eurofxref-daily", "fx-reference-rates"),
            "European Central Bank FX reference rates.",
            False,
            freshness_minutes=1440,
        ),
        _src(
            "src-entsog",
            "ENTSOG",
            "infrastructure",
            ("connection-points", "operator-directions", "flows", "capacity", "outages", "ip"),
            "ENTSOG Transparency Platform infrastructure, flows, capacities, IPs, and outages.",
            False,
            freshness_minutes=60,
        ),
        _src(
            "src-gie",
            "GIE",
            "infrastructure",
            ("agsi-storage", "alsi-lng"),
            "Gas Infrastructure Europe AGSI storage and ALSI LNG data.",
            True,
            freshness_minutes=360,
        ),
        _src(
            "src-national-gas-nts",
            "NationalGasNTS",
            "tariff",
            ("transportation-statement", "entry-tariffs", "exit-tariffs", "commodity-charges"),
            "National Gas NTS transportation tariff references for UK route-cost calculation.",
            False,
            freshness_minutes=43200,
        ),
        _src(
            "src-eex",
            "EEX",
            "price",
            ("gas-futures", "gas-spot", "screen-trades", "settlements"),
            "European Energy Exchange gas market prices and screen observations.",
            True,
            freshness_minutes=5,
        ),
        _src(
            "src-ice-ocm",
            "ICE_OCM",
            "price",
            ("within-day", "day-ahead", "screen-orders", "live-marks"),
            "ICE OCM live within-day and day-ahead market observations.",
            True,
            freshness_minutes=5,
        ),
        _src(
            "src-trayport",
            "Trayport",
            "price",
            ("broker-screens", "market-data", "screen-orders"),
            "Trayport screen and broker market data.",
            True,
            freshness_minutes=5,
        ),
        _src(
            "src-platts",
            "Platts",
            "price",
            ("assessments", "forward-curves", "indices"),
            "Platts licensed gas price assessments and curves.",
            True,
            freshness_minutes=1440,
        ),
        _src(
            "src-icis",
            "ICIS",
            "price",
            ("heren-assessments", "day-ahead", "indices", "curves"),
            "ICIS Heren licensed gas assessments and reference prices.",
            True,
            freshness_minutes=1440,
        ),
        _src(
            "src-argus",
            "Argus",
            "price",
            ("assessments", "indices", "curves"),
            "Argus licensed gas assessments and market references.",
            True,
            freshness_minutes=1440,
        ),
        _src(
            "src-kpler",
            "Kpler",
            "price",
            ("lng-flows", "cargo-tracking", "market-data"),
            "Kpler licensed LNG and market intelligence feeds.",
            True,
            freshness_minutes=60,
        ),
        _src(
            "src-weather",
            "Weather",
            "weather",
            ("temperature", "hdd", "cdd", "forecast"),
            "Weather observations and forecast signals for HDD/CDD modelling.",
            True,
            freshness_minutes=180,
        ),
        _src(
            "src-deepseek",
            "DEEPSEEK",
            "ai",
            ("analysis", "reporting", "qa"),
            "DeepSeek LLM analysis provider for operator-reviewed reports.",
            True,
            freshness_minutes=0,
        ),
    ]


def _src(
    source_id: str,
    system: str,
    category: str,
    datasets: tuple[str, ...],
    description: str,
    entitled: bool,
    *,
    freshness_minutes: int,
) -> dict:
    return {
        "source_id": source_id,
        "source_system": system,
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "datasets": list(datasets),
        "status": "registered",
        "connectivity_status": "registered",
        "live_record_count": 0,
        "entitlement_scope": "licensed" if entitled else "public",
        "freshness_expectation_minutes": freshness_minutes,
        "description": description,
        "credential_requirements": ["api_key"] if entitled else [],
        "credential_provider_id": system if entitled else None,
        "credential_state": "missing" if entitled else "not_required",
        "credential_status": None,
        "credential_last_tested_at_utc": None,
        "credential_last_test_status": None,
        "export_restrictions": ["license-controlled"] if entitled else [],
        "last_success_at_utc": None,
        "last_failure_at_utc": None,
        "last_ingestion_status": None,
        "last_ingestion_message": None,
        "diagnostics": [],
    }


def _sources_with_runtime_status() -> list[dict]:
    sources = _registered_sources()
    counts = _runtime_source_counts()
    ingestion_status = _latest_ingestion_status_by_source()
    credential_status = _credential_status_by_provider()
    for source in sources:
        count = counts.get(source["source_system"], 0)
        source["live_record_count"] = count
        source_id = source["source_id"]
        source_ingestion = ingestion_status.get(source_id, {})
        latest_run = source_ingestion.get("latest")
        credential = credential_status.get(str(source["credential_provider_id"]))
        credential_state = _credential_state(source, credential)
        source["credential_state"] = credential_state
        source["credential_status"] = credential.get("status") if credential else None
        source["credential_last_tested_at_utc"] = (
            credential.get("last_tested_at_utc") if credential else None
        )
        source["credential_last_test_status"] = (
            credential.get("last_test_status") if credential else None
        )
        source["last_success_at_utc"] = source_ingestion.get("last_success_at_utc")
        source["last_failure_at_utc"] = source_ingestion.get("last_failure_at_utc")
        source["last_ingestion_status"] = latest_run.get("status") if latest_run else None
        source["last_ingestion_message"] = (
            latest_run.get("error_message") or latest_run.get("source_reference")
            if latest_run
            else None
        )
        connectivity_status = _connectivity_status(source, count, credential_state, latest_run)
        source["connectivity_status"] = connectivity_status
        source["status"] = connectivity_status
        source["diagnostics"] = _diagnostics(source, count, credential_state, latest_run)
    return sources


def _credential_state(source: dict, credential: dict[str, Any] | None) -> str:
    if not source["credential_requirements"]:
        return "not_required"
    if credential is None:
        return "missing"
    if credential.get("status") == "disabled":
        return "disabled"
    return "configured" if credential.get("configured") else "missing"


def _connectivity_status(
    source: dict,
    live_record_count: int,
    credential_state: str,
    latest_run: dict[str, Any] | None,
) -> str:
    if credential_state == "missing":
        return "needs_credential"
    if credential_state == "disabled":
        return "credential_disabled"
    if latest_run and latest_run.get("status") == "failed":
        return "failed"
    if live_record_count > 0:
        return "active"
    if not _db_is_configured():
        return "runtime_unconfigured"
    if source["category"] == "ai":
        return "configured" if credential_state == "configured" else "needs_credential"
    return "no_records"


def _diagnostics(
    source: dict,
    live_record_count: int,
    credential_state: str,
    latest_run: dict[str, Any] | None,
) -> list[str]:
    if credential_state == "missing":
        return ["credential_missing"]
    diagnostics: list[str] = []
    if credential_state == "disabled":
        diagnostics.append("credential_disabled")
    if latest_run and latest_run.get("status") == "failed":
        diagnostics.append("last_ingestion_failed")
    if live_record_count > 0:
        diagnostics.append("live_records_available")
    elif not _db_is_configured():
        diagnostics.append("runtime_db_not_configured")
    elif source["category"] != "ai":
        diagnostics.append("no_records_in_runtime_db")
    if not diagnostics:
        diagnostics.append("ready")
    return diagnostics


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
            ScreenOrderObservationRecord,
            StorageObservationRecord,
            TsoTariffRecord,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            price_systems = [
                "Argus",
                "EEX",
                "ICE_OCM",
                "ICIS",
                "Kpler",
                "Platts",
                "Trayport",
            ]
            counts = {
                system: session.query(MarketObservationRecord)
                .filter(MarketObservationRecord.source_system == system)
                .count()
                for system in price_systems
            }
            for system in ("ICE_OCM", "Trayport"):
                counts[system] = counts.get(system, 0) + session.query(
                    ScreenOrderObservationRecord
                ).filter(
                    (ScreenOrderObservationRecord.source_system == system)
                    | (ScreenOrderObservationRecord.provider_id == system)
                ).count()
            weather_count = session.query(MarketObservationRecord).filter(
                MarketObservationRecord.source_system == "Weather"
            ).count()
            return {
                **counts,
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
                "NationalGasNTS": session.query(TsoTariffRecord).filter(
                    TsoTariffRecord.country == "GB"
                ).count(),
                "Weather": weather_count,
                "DEEPSEEK": 0,
            }
    except sqlalchemy_error:
        return {}


def _credential_status_by_provider() -> dict[str, dict[str, Any]]:
    if not _db_is_configured():
        return {}

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import ProviderCredentialRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(ProviderCredentialRecord).all()
            return {
                row.provider_id: {
                    "configured": row.status != "disabled",
                    "status": row.status,
                    "last_tested_at_utc": _iso(row.last_tested_at_utc),
                    "last_test_status": row.last_test_status,
                }
                for row in rows
            }
    except sqlalchemy_error:
        return {}


def _latest_ingestion_status_by_source() -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    for run in _db_ingestion_runs():
        bucket = status.setdefault(run["source_id"], {})
        bucket.setdefault("latest", run)
        if run["status"] == "succeeded" and "last_success_at_utc" not in bucket:
            bucket["last_success_at_utc"] = run["finished_at_utc"] or run["started_at_utc"]
        if run["status"] == "failed" and "last_failure_at_utc" not in bucket:
            bucket["last_failure_at_utc"] = run["finished_at_utc"] or run["started_at_utc"]
    return status


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
    source_id = _source_id_for_source_name(row.source_name)
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


def _source_id_for_source_name(source_name: str) -> str:
    normalized = source_name.strip().upper()
    compact = re.sub(r"[^A-Z0-9_]+", " ", normalized)
    return (
        SOURCE_ID_BY_NAME.get(normalized)
        or SOURCE_ID_BY_NAME.get(compact)
        or SOURCE_ID_BY_NAME.get(normalized.replace("_", " "))
        or f"src-{normalized.lower().replace('_', '-')}"
    )


def _records_from_notes(notes: str | None) -> int:
    if not notes:
        return 0
    match = re.match(r"(\d+)", notes)
    return int(match.group(1)) if match else 0


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _source_label() -> str:
    return "runtime-postgresql" if _db_is_configured() else "source-registry"


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError
