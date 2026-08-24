"""Read-only /api source registry and ingestion status routes."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.domain.ingestion.certification import certification_gate
from eurogas_nexus.domain.ingestion.source_registry import (
    CATEGORY_LABELS,
    registered_sources,
)

router = APIRouter(tags=["sources"])

PREVIEW_SUBSTITUTE_SOURCE_SYSTEM_BY_LICENSED_SOURCE = {
    "EEX": "EEX_Sim",
    "ICE_OCM": "ICE_OCM_Sim",
    "Trayport": "Trayport_Sim",
    "ICIS": "ICIS_Sim",
}

SOURCE_ID_BY_NAME = {
    "ARGUS": "src-argus",
    "DEEPSEEK": "src-deepseek",
    "ECB": "src-ecb",
    "EEX": "src-eex",
    "EEX_SIM": "src-eex-sim",
    "EEX SIM": "src-eex-sim",
    "ENTSOG": "src-entsog",
    "GIE": "src-gie",
    "GIE-AGSI": "src-gie",
    "GIE-ALSI": "src-gie",
    "ICE_OCM": "src-ice-ocm",
    "ICE OCM": "src-ice-ocm",
    "ICE_OCM_SIM": "src-ice-ocm-sim",
    "ICE OCM SIM": "src-ice-ocm-sim",
    "ICIS": "src-icis",
    "ICIS_SIM": "src-icis-sim",
    "ICIS SIM": "src-icis-sim",
    "KPLER": "src-kpler",
    "NATIONALGASNTS": "src-national-gas-nts",
    "NATIONAL_GAS_NTS": "src-national-gas-nts",
    "NATIONAL GAS NTS": "src-national-gas-nts",
    "BBL": "src-bbl",
    "BBL COMPANY": "src-bbl",
    "IUK": "src-iuk",
    "INTERCONNECTOR UK": "src-iuk",
    "GTS": "src-gts",
    "GASUNIE TRANSPORT SERVICES": "src-gts",
    "NATRAN": "src-natran",
    "GRTGAZ": "src-natran",
    "TEREGA": "src-natran",
    "GERMAN TSO": "src-german-tso",
    "GERMANY TSO": "src-german-tso",
    "FLUXYS BELGIUM": "src-fluxys-belgium",
    "CNMC ENAGAS": "src-cnmc-enagas",
    "PLATTS": "src-platts",
    "TRAYPORT": "src-trayport",
    "TRAYPORT_SIM": "src-trayport-sim",
    "TRAYPORT SIM": "src-trayport-sim",
    "WEATHER": "src-weather",
}


@router.get("/api/sources")
def list_sources(request: Request) -> dict:
    """List registered source systems with runtime DB counts when configured."""

    sources = _sources_with_runtime_status()
    return _envelope(
        sources,
        request,
        source=_source_label(),
        source_posture_summary=_source_posture_summary(sources),
    )


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
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    """List persisted ingestion runs from the runtime DB (bounded by limit)."""

    runs = _db_ingestion_runs()
    if source_id:
        runs = [run for run in runs if run["source_id"] == source_id]
    return _envelope(runs[:limit], request, source=_source_label())


def _envelope(
    data: object,
    request: Request,
    *,
    source: str,
    source_posture_summary: dict[str, Any] | None = None,
) -> dict:
    _ = request
    warnings: list[str] = []
    if source != "runtime-postgresql":
        warnings.append("Runtime database is not configured; live source counts are unavailable.")
    meta: dict[str, Any] = {
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
    }
    if source_posture_summary is not None:
        meta["source_posture_summary"] = source_posture_summary
    return {
        "data": data,
        "meta": meta,
    }


def _sources_with_runtime_status() -> list[dict]:
    sources = registered_sources()
    counts = _runtime_source_counts()
    latest_observed = _runtime_source_latest_observed()
    ingestion_status = _latest_ingestion_status_by_source()
    credential_status = _credential_status_by_provider()
    certifications = _certification_by_source_system()
    for source in sources:
        count = counts.get(source["source_system"], 0)
        source["live_record_count"] = count
        last_observed = latest_observed.get(source["source_system"])
        source["last_observed_at_utc"] = last_observed
        source["freshness_status"] = _source_freshness_status(source, last_observed)
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
        certification = certifications.get(source["source_system"])
        source["certification_stage"] = (
            certification["stage"] if certification else "unverified"
        )
        gate = certification_gate(
            source["source_system"],
            stage=source["certification_stage"],
            checks=certification.get("checks") if certification else None,
        )
        source["certification_allows_live"] = gate.allows_live
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
    _attach_preview_substitute_status(sources)
    _attach_operational_status(sources)
    return sources


def _source_freshness_status(source: dict, last_observed_at_utc: str | None) -> str:
    """Evaluate read-side freshness against the source expectation (audit item 3)."""

    from eurogas_nexus.domain.monitoring.freshness import evaluate_freshness

    observed = _parse_utc_datetime(last_observed_at_utc)
    expectation = int(source.get("freshness_expectation_minutes") or 0)
    return evaluate_freshness(expectation, observed).value


def _parse_utc_datetime(value: str | None):
    from datetime import UTC, datetime

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _source_posture_summary(sources: list[dict]) -> dict[str, Any]:
    categories = []
    for category, label in CATEGORY_LABELS.items():
        category_sources = [source for source in sources if source["category"] == category]
        if not category_sources:
            continue
        categories.append(_category_posture(category, label, category_sources))

    return {
        "totals": {
            "registered_sources": len(sources),
            "active_sources": sum(
                1 for source in sources if source["connectivity_status"] == "active"
            ),
            "workflow_ready_sources": sum(
                1 for source in sources if source["workflow_ready"]
            ),
            "sources_needing_attention": sum(
                1 for source in sources if _source_needs_attention(source)
            ),
            "missing_credentials": sum(
                1 for source in sources if source["credential_state"] == "missing"
            ),
            "preview_substitutes_active": sum(
                1
                for source in sources
                if source["preview_substitute_status"] == "active"
            ),
            "uncertified_active_sources": sum(
                1
                for source in sources
                if source["operational_status"] == "active_uncertified"
            ),
            "runtime_records": sum(int(source["live_record_count"]) for source in sources),
        },
        "categories": categories,
    }


def _category_posture(category: str, label: str, sources: list[dict]) -> dict[str, Any]:
    missing_credentials = sum(1 for source in sources if source["credential_state"] == "missing")
    failed_sources = sum(1 for source in sources if source["connectivity_status"] == "failed")
    active_sources = sum(1 for source in sources if source["connectivity_status"] == "active")
    workflow_ready_sources = sum(1 for source in sources if source["workflow_ready"])
    runtime_records = sum(int(source["live_record_count"]) for source in sources)
    preview_substitutes_active = sum(
        1 for source in sources if source["preview_substitute_status"] == "active"
    )
    return {
        "category": category,
        "category_label": label,
        "registered_sources": len(sources),
        "active_sources": active_sources,
        "workflow_ready_sources": workflow_ready_sources,
        "sources_needing_attention": sum(
            1 for source in sources if _source_needs_attention(source)
        ),
        "missing_credentials": missing_credentials,
        "preview_substitutes_active": preview_substitutes_active,
        "runtime_records": runtime_records,
        "next_action": _category_next_action(
            missing_credentials=missing_credentials,
            failed_sources=failed_sources,
            workflow_ready_sources=workflow_ready_sources,
            runtime_records=runtime_records,
        ),
    }


def _source_needs_attention(source: dict) -> bool:
    if source["workflow_ready"]:
        return False
    if source["operational_status"] == "active_uncertified":
        return True
    return source["connectivity_status"] in {
        "failed",
        "needs_credential",
        "credential_disabled",
        "runtime_unconfigured",
        "no_records",
    }


def _category_next_action(
    *,
    missing_credentials: int,
    failed_sources: int,
    workflow_ready_sources: int,
    runtime_records: int,
) -> str:
    if missing_credentials > 0 and workflow_ready_sources == 0:
        return "add_credentials"
    if failed_sources > 0:
        return "inspect_failure"
    if workflow_ready_sources == 0 or runtime_records == 0:
        return "run_ingestion"
    if missing_credentials > 0:
        return "configure_live_credentials"
    return "monitor"


def _attach_preview_substitute_status(sources: list[dict]) -> None:
    by_system = {source["source_system"]: source for source in sources}
    for source in sources:
        substitute_system = PREVIEW_SUBSTITUTE_SOURCE_SYSTEM_BY_LICENSED_SOURCE.get(
            source["source_system"]
        )
        if substitute_system is None:
            continue
        substitute = by_system.get(substitute_system)
        substitute_status = substitute["connectivity_status"] if substitute else "not_registered"
        substitute_record_count = substitute["live_record_count"] if substitute else 0
        source["preview_substitute_source_system"] = substitute_system
        source["preview_substitute_status"] = substitute_status
        source["preview_substitute_record_count"] = substitute_record_count
        if substitute_status == "active" and "preview_substitute_active" not in source[
            "diagnostics"
        ]:
            source["diagnostics"].append("preview_substitute_active")


def _attach_operational_status(sources: list[dict]) -> None:
    by_system = {source["source_system"]: source for source in sources}
    for source in sources:
        certification_required = bool(source["credential_requirements"])
        native_active = (
            source["connectivity_status"] == "active"
            and int(source["live_record_count"]) > 0
            and (not certification_required or source["certification_allows_live"])
        )
        substitute = by_system.get(source["preview_substitute_source_system"])
        substitute_active = bool(
            substitute
            and substitute["connectivity_status"] == "active"
            and int(substitute["live_record_count"]) > 0
        )
        if native_active:
            source["operational_status"] = "active"
            source["workflow_ready"] = True
            source["effective_source_system"] = source["source_system"]
            source["effective_record_count"] = source["live_record_count"]
            source["effective_last_success_at_utc"] = source["last_success_at_utc"]
        elif substitute_active and substitute is not None:
            source["operational_status"] = "active_simulated"
            source["workflow_ready"] = True
            source["effective_source_system"] = substitute["source_system"]
            source["effective_record_count"] = substitute["live_record_count"]
            source["effective_last_success_at_utc"] = substitute["last_success_at_utc"]
        elif (
            source["credential_requirements"]
            and source["connectivity_status"] == "active"
            and not source["certification_allows_live"]
        ):
            source["operational_status"] = "active_uncertified"
            source["workflow_ready"] = False
            source["effective_source_system"] = source["source_system"]
            source["effective_record_count"] = source["live_record_count"]
            source["effective_last_success_at_utc"] = source["last_success_at_utc"]
        else:
            source["operational_status"] = source["connectivity_status"]
            source["workflow_ready"] = False
            source["effective_source_system"] = source["source_system"]
            source["effective_record_count"] = source["live_record_count"]
            source["effective_last_success_at_utc"] = source["last_success_at_utc"]


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
        # Audit item 3: records alone do not make a source live. A source whose
        # newest observation is older than its freshness expectation is stale.
        if source.get("freshness_status") == "stale":
            return "stale"
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
        if source["credential_requirements"] and not source["certification_allows_live"]:
            diagnostics.append("certification_required")
        if source.get("freshness_status") == "stale":
            diagnostics.append("data_stale")
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
        from sqlalchemy import or_

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
                "EEX_Sim",
                "ICE_OCM",
                "ICE_OCM_Sim",
                "ICIS",
                "ICIS_Sim",
                "Kpler",
                "Platts",
                "Trayport",
                "Trayport_Sim",
            ]
            counts = {
                system: session.query(MarketObservationRecord)
                .filter(MarketObservationRecord.source_system == system)
                .count()
                for system in price_systems
            }
            for system in ("ICE_OCM", "ICE_OCM_Sim", "Trayport", "Trayport_Sim"):
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
                "NationalGasNTS": session.query(TsoTariffRecord)
                .filter(_national_gas_nts_tariff_filter(TsoTariffRecord, or_))
                .count(),
                "BBL": session.query(TsoTariffRecord)
                .filter(_bbl_tariff_filter(TsoTariffRecord, or_))
                .count(),
                "IUK": session.query(TsoTariffRecord)
                .filter(_iuk_tariff_filter(TsoTariffRecord, or_))
                .count(),
                "GTS": session.query(TsoTariffRecord)
                .filter(_gts_tariff_filter(TsoTariffRecord, or_))
                .count(),
                "NaTran": session.query(TsoTariffRecord)
                .filter(_france_tariff_filter(TsoTariffRecord, or_))
                .count(),
                "GermanTSO": session.query(TsoTariffRecord)
                .filter(_germany_tariff_filter(TsoTariffRecord, or_))
                .count(),
                "FluxysBelgium": session.query(TsoTariffRecord)
                .filter(_belgium_tariff_filter(TsoTariffRecord, or_))
                .count(),
                "CNMCEnagas": session.query(TsoTariffRecord)
                .filter(_spain_tariff_filter(TsoTariffRecord, or_))
                .count(),
                "Weather": weather_count,
                "DEEPSEEK": 0,
            }
    except sqlalchemy_error:
        return {}


def _runtime_source_latest_observed() -> dict[str, str]:
    """Return the newest observation timestamp per source system (ISO UTC).

    Drives the read-side freshness evaluation (audit item 3): a source is
    only ``active`` while its newest row satisfies the freshness expectation.
    """

    if not _db_is_configured():
        return {}

    try:
        from sqlalchemy import func

        from eurogas_nexus.db.models import (
            FlowObservationRecord,
            FxObservationRecord,
            LngObservationRecord,
            MarketObservationRecord,
            ScreenOrderObservationRecord,
            StorageObservationRecord,
        )
        from eurogas_nexus.db.session import get_session_factory

        latest: dict[str, datetime | None] = {}

        def track(system: str, value: datetime | None) -> None:
            if value is None:
                return
            if system not in latest or value > latest[system]:
                latest[system] = value

        with get_session_factory()() as session:
            for row in (
                session.query(
                    MarketObservationRecord.source_system,
                    func.max(MarketObservationRecord.observed_at_utc),
                ).group_by(MarketObservationRecord.source_system)
            ):
                track(str(row[0]), row[1])
            for row in (
                session.query(
                    FlowObservationRecord.source_system,
                    func.max(FlowObservationRecord.observed_at_utc),
                ).group_by(FlowObservationRecord.source_system)
            ):
                track(str(row[0]), row[1])
            for row in (
                session.query(
                    StorageObservationRecord.source_system,
                    func.max(StorageObservationRecord.observed_at_utc),
                ).group_by(StorageObservationRecord.source_system)
            ):
                track(str(row[0]), row[1])
            for row in (
                session.query(
                    LngObservationRecord.source_system,
                    func.max(LngObservationRecord.observed_at_utc),
                ).group_by(LngObservationRecord.source_system)
            ):
                track(str(row[0]), row[1])
            for row in (
                session.query(
                    FxObservationRecord.source_system,
                    func.max(FxObservationRecord.observed_at_utc),
                ).group_by(FxObservationRecord.source_system)
            ):
                track(str(row[0]), row[1])
            for row in (
                session.query(
                    ScreenOrderObservationRecord.source_system,
                    func.max(ScreenOrderObservationRecord.observed_at_utc),
                ).group_by(ScreenOrderObservationRecord.source_system)
            ):
                track(str(row[0]), row[1])
        return {
            system: value.isoformat()
            for system, value in latest.items()
            if hasattr(value, "isoformat")
        }
    except Exception:
        # Freshness annotation is best-effort: unavailability (including
        # monkeypatched test environments without a DSN) yields no timestamps
        # and sources evaluate as UNKNOWN rather than failing the registry.
        return {}


def _national_gas_nts_tariff_filter(tariff_model: Any, or_: Any) -> Any:
    """Return the UK NTS tariff predicate used for National Gas source health."""

    return or_(
        tariff_model.country.in_(("GB", "UK", "GBR")),
        tariff_model.market_area.ilike("%NTS%"),
        tariff_model.tso.ilike("%National Gas%"),
    )


def _bbl_tariff_filter(tariff_model: Any, or_: Any) -> Any:
    return or_(
        tariff_model.market_area.ilike("%BBL%"),
        tariff_model.tso.ilike("%BBL%"),
    )


def _iuk_tariff_filter(tariff_model: Any, or_: Any) -> Any:
    return or_(
        tariff_model.market_area.ilike("%IUK%"),
        tariff_model.tso.ilike("%Interconnector UK%"),
    )


def _gts_tariff_filter(tariff_model: Any, or_: Any) -> Any:
    return or_(
        tariff_model.tso.ilike("%Gasunie%"),
        tariff_model.tso.ilike("%GTS%"),
    )


def _france_tariff_filter(tariff_model: Any, or_: Any) -> Any:
    return or_(
        tariff_model.country == "FR",
        tariff_model.tso.ilike("%NaTran%"),
        tariff_model.tso.ilike("%GRTgaz%"),
        tariff_model.tso.ilike("%Terega%"),
        tariff_model.tso.ilike("%Teréga%"),
    )


def _germany_tariff_filter(tariff_model: Any, or_: Any) -> Any:
    return or_(
        tariff_model.country == "DE",
        tariff_model.market_area.ilike("%THE%"),
    )


def _belgium_tariff_filter(tariff_model: Any, or_: Any) -> Any:
    return or_(
        tariff_model.tso.ilike("%Fluxys%"),
        tariff_model.market_area.ilike("%ZTP%"),
    )


def _spain_tariff_filter(tariff_model: Any, or_: Any) -> Any:
    return or_(
        tariff_model.country == "ES",
        tariff_model.tso.ilike("%Enagas%"),
        tariff_model.tso.ilike("%Enagás%"),
        tariff_model.tso.ilike("%CNMC%"),
    )


def _certification_by_source_system() -> dict[str, dict[str, Any]]:
    if not _db_is_configured():
        return {}

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.certification import list_certifications
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = list_certifications(session)
        return {row["source_system"]: row for row in rows}
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
    match = re.search(r"(?:^|[;\s])records=(\d+)", notes) or re.match(r"(\d+)", notes)
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
