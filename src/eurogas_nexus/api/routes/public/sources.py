"""Read-only /api source registry and ingestion status routes."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.domain.dataops.contracts import IngestionRunStatus
from eurogas_nexus.domain.dataops.run_status import (
    FAILURE_RUN_STATUSES,
    SUCCESS_RUN_STATUSES,
    canonical_run_status,
    stored_statuses_for,
)
from eurogas_nexus.domain.ingestion.certification import certification_gate
from eurogas_nexus.domain.ingestion.source_registry import (
    CATEGORY_LABELS,
    registered_sources,
)

router = APIRouter(tags=["sources"])
logger = logging.getLogger(__name__)

#: Shown when the runtime database is configured but the count read failed: every source's
#: ``live_record_count`` is then null (unknown), never 0, which would read as "no data".
COUNTS_UNAVAILABLE_WARNING = (
    "Source row counts are unavailable: the runtime database read failed. Counts show as "
    "unknown, not zero; see the server log for the error class."
)
LATEST_OBSERVED_UNAVAILABLE_WARNING = (
    "Newest-observation times are unavailable: the runtime database read failed, so "
    "freshness is unknown."
)

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
    "ECMWF_OPEN_DATA": "src-ecmwf-open-data",
    "EEX": "src-eex",
    "EEX-NGP": "src-eex",
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

    sources, warnings = _sources_with_runtime_status()
    return _envelope(
        sources,
        request,
        source=_source_label(),
        source_posture_summary=_source_posture_summary(sources),
        warnings=warnings,
    )


@router.get("/api/sources/{source_id}")
def get_source(source_id: str, request: Request) -> dict:
    """Get a single registered source by ID."""

    sources, warnings = _sources_with_runtime_status()
    for source in sources:
        if source["source_id"] == source_id:
            return _envelope(source, request, source=_source_label(), warnings=warnings)
    raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found.")


@router.get("/api/ingestion-runs")
def list_ingestion_runs(
    request: Request,
    source_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    """List persisted ingestion runs from the runtime DB (bounded by limit).

    The source filter and the page limit are applied by the database; the
    previous shape materialized every persisted run and sliced in Python, so
    the read grew with total ingestion history instead of with the page size.
    """

    runs = _db_ingestion_runs(source_id=source_id, limit=limit)
    return _envelope(runs, request, source=_source_label())


def _envelope(
    data: object,
    request: Request,
    *,
    source: str,
    source_posture_summary: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict:
    _ = request
    warnings = list(warnings or [])
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


def _sources_with_runtime_status() -> tuple[list[dict], list[str]]:
    """Registered sources with runtime status, and warnings for reads that failed."""

    sources = registered_sources()
    counts = _runtime_source_counts()
    latest_observed = _runtime_source_latest_observed()
    warnings: list[str] = []
    if counts is None:
        warnings.append(COUNTS_UNAVAILABLE_WARNING)
    if latest_observed is None:
        warnings.append(LATEST_OBSERVED_UNAVAILABLE_WARNING)
        latest_observed = {}
    ingestion_status = _latest_ingestion_status_by_source()
    credential_status = _credential_status_by_provider()
    certifications = _certification_by_source_system()
    runtime_states = _source_runtime_states_by_source_id()
    for source in sources:
        # None: the count read failed, so the number is unknown (not zero).
        count = None if counts is None else counts.get(source["source_system"], 0)
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
        source["certification_stage"] = certification["stage"] if certification else "unverified"
        runtime_state = runtime_states.get(source["source_id"])
        if runtime_state is not None:
            source["runtime_state"] = runtime_state
            source["scheduler_enabled"] = runtime_state.get("enabled", False)
            source["circuit_state"] = runtime_state.get("circuit_state")
            source["next_run_at_utc"] = runtime_state.get("next_run_at_utc")
            source["consecutive_failures"] = runtime_state.get("consecutive_failures", 0)
            source["freshness_state"] = runtime_state.get("freshness_state")
            source["source_age_seconds"] = runtime_state.get("source_age_seconds")
            source["certification_state"] = runtime_state.get("certification_state")
            source["entitlement_state"] = runtime_state.get("entitlement_state")
            source["adapter_version"] = runtime_state.get("adapter_version")
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
        if source["category"] == "ai":
            source["model_service"] = _model_service_endpoint()
        connectivity_status = _connectivity_status(source, count, credential_state, latest_run)
        source["connectivity_status"] = connectivity_status
        source["status"] = connectivity_status
        source["diagnostics"] = _diagnostics(
            source,
            count,
            credential_state,
            latest_run,
            last_success_with_warnings=(
                canonical_run_status(source_ingestion.get("last_success_status"))
                is IngestionRunStatus.SUCCEEDED_WITH_WARNINGS
            ),
        )
    _attach_preview_substitute_status(sources)
    _attach_operational_status(sources)
    return sources, warnings


def _record_total(sources: list[dict]) -> int | None:
    """Sum of the sources' counts, or None when any count is unknown."""

    counts = [source["live_record_count"] for source in sources]
    return None if any(count is None for count in counts) else sum(int(c) for c in counts)


def _source_runtime_states_by_source_id() -> dict[str, dict[str, Any]]:
    if not _db_is_configured():
        return {}

    try:
        from eurogas_nexus.db.models import SourceRuntimeStateRecord
        from eurogas_nexus.db.repositories.dataops import source_runtime_payload
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(SourceRuntimeStateRecord).all()
            return {row.source_id: source_runtime_payload(row) for row in rows}
    except Exception:
        return {}


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
            "workflow_ready_sources": sum(1 for source in sources if source["workflow_ready"]),
            "sources_needing_attention": sum(
                1 for source in sources if _source_needs_attention(source)
            ),
            "missing_credentials": sum(
                1 for source in sources if source["credential_state"] == "missing"
            ),
            "preview_substitutes_active": sum(
                1 for source in sources if source["preview_substitute_status"] == "active"
            ),
            "uncertified_active_sources": sum(
                1 for source in sources if source["operational_status"] == "active_uncertified"
            ),
            "runtime_records": _record_total(sources),
        },
        "categories": categories,
    }


def _category_posture(category: str, label: str, sources: list[dict]) -> dict[str, Any]:
    missing_credentials = sum(1 for source in sources if source["credential_state"] == "missing")
    failed_sources = sum(1 for source in sources if source["connectivity_status"] == "failed")
    active_sources = sum(1 for source in sources if source["connectivity_status"] == "active")
    workflow_ready_sources = sum(1 for source in sources if source["workflow_ready"])
    runtime_records = _record_total(sources)
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
        "counts_unavailable",
    }


def _category_next_action(
    *,
    missing_credentials: int,
    failed_sources: int,
    workflow_ready_sources: int,
    runtime_records: int | None,
) -> str:
    if missing_credentials > 0 and workflow_ready_sources == 0:
        return "add_credentials"
    if failed_sources > 0:
        return "inspect_failure"
    if runtime_records is None:
        return "inspect_failure"  # the count read failed: not a reason to ingest again
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
        if (
            substitute_status == "active"
            and "preview_substitute_active" not in source["diagnostics"]
        ):
            source["diagnostics"].append("preview_substitute_active")


def _attach_operational_status(sources: list[dict]) -> None:
    by_system = {source["source_system"]: source for source in sources}
    for source in sources:
        certification_required = bool(source["credential_requirements"])
        native_active = (
            source["connectivity_status"] == "active"
            and (source["live_record_count"] or 0) > 0
            and (not certification_required or source["certification_allows_live"])
        )
        substitute = by_system.get(source["preview_substitute_source_system"])
        substitute_active = bool(
            substitute
            and substitute["connectivity_status"] == "active"
            and (substitute["live_record_count"] or 0) > 0
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


def _model_service_endpoint() -> dict[str, str] | None:
    """The configured model endpoint, so the UI names what is configured (#33).

    Provider, model and host only: the key never leaves the backend, and a path or query
    on the base URL is not shown.
    """
    from urllib.parse import urlsplit

    from eurogas_nexus.llm.provider import LlmEndpointError, configured_endpoint

    try:
        endpoint = configured_endpoint()
    except LlmEndpointError:
        return None
    return {
        "provider_name": endpoint.provider_name,
        "model": endpoint.model,
        "host": urlsplit(endpoint.base_url).hostname or "",
    }


def _credential_state(source: dict, credential: dict[str, Any] | None) -> str:
    if not source["credential_requirements"]:
        return "not_required"
    if credential is None:
        # The GIE key can live outside the encrypted credential store (external
        # file / env path). Resolve that through the shared transport resolver so
        # the source status does not keep claiming "key missing" when an external
        # owner-managed key is configured.
        if _external_credential_configured(str(source.get("credential_provider_id") or "")):
            return "configured"
        return "missing"
    if credential.get("status") == "disabled":
        return "disabled"
    if credential.get("configured"):
        return "configured"
    if _external_credential_configured(str(source.get("credential_provider_id") or "")):
        return "configured"
    return "missing"


def _external_credential_configured(provider_id: str) -> bool:
    """Whether a provider credential is configured outside the encrypted store.

    Only the GIE external owner-managed env/file path is supported today. The
    same runtime resolver the fetch path and credential API use decides the
    answer, so an operator-disabled stored credential or an explicitly disabled
    source operation still blocks the registry status instead of being re-enabled
    by environment/file precedence, and an unreadable operator state is never
    reported as configured.
    """

    if provider_id != "GIE":
        return False
    try:
        from eurogas_nexus.ingestion.gie_transport import (
            resolve_gie_runtime_credential_status,
        )

        status = resolve_gie_runtime_credential_status()
    except Exception:  # noqa: BLE001 - a status read must never fail the registry
        return False
    return status.configured


def _connectivity_status(
    source: dict,
    live_record_count: int | None,
    credential_state: str,
    latest_run: dict[str, Any] | None,
) -> str:
    if credential_state == "missing":
        return "needs_credential"
    if credential_state == "disabled":
        return "credential_disabled"
    if latest_run and canonical_run_status(latest_run.get("status")) in FAILURE_RUN_STATUSES:
        return "failed"
    if live_record_count is None:
        return "counts_unavailable"
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
    live_record_count: int | None,
    credential_state: str,
    latest_run: dict[str, Any] | None,
    *,
    last_success_with_warnings: bool = False,
) -> list[str]:
    if credential_state == "missing":
        return ["credential_missing"]
    diagnostics: list[str] = []
    if credential_state == "disabled":
        diagnostics.append("credential_disabled")
    latest_status = canonical_run_status(latest_run.get("status")) if latest_run else None
    if latest_status is IngestionRunStatus.FAILED:
        diagnostics.append("last_ingestion_failed")
    elif latest_status in (IngestionRunStatus.QUEUED, IngestionRunStatus.RUNNING):
        # A pending run is neither success nor failure; say so instead of
        # letting the previous outcome imply the run already finished.
        diagnostics.append("last_ingestion_pending")
    elif latest_status is IngestionRunStatus.CANCELLED:
        diagnostics.append("last_ingestion_cancelled")
    elif latest_status is IngestionRunStatus.SUCCEEDED_WITH_WARNINGS:
        diagnostics.append("last_ingestion_succeeded_with_warnings")
    elif latest_run is not None and latest_status is None:
        diagnostics.append("last_ingestion_status_unknown")
    if last_success_with_warnings and "last_ingestion_succeeded_with_warnings" not in diagnostics:
        # The exposed last_success_at_utc came from a warnings run; keep that
        # success visibly qualified even when a newer failed/pending run exists.
        diagnostics.append("last_ingestion_succeeded_with_warnings")
    if live_record_count is None:
        diagnostics.append("record_count_unavailable")
    elif live_record_count > 0:
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


#: Rate fixings are stored under their administrator (ECB also publishes FX), so they are
#: attributed to a registered source by benchmark.
_RATE_SOURCE_BY_BENCHMARK = {"SONIA": "BOE", "ESTR": "ECB_ESTR", "SOFR": "NYFED"}


def _observation_counts_by_source_system(session: Any) -> dict[str, int]:
    """Rows per ``source_system`` over every observation table, in one statement.

    A connector that writes one of these tables under its registered ``source_system``
    is counted without a change here (National Gas storage/LNG, Elexon and ENTSO-E
    power, EIA prices, REMIT messages). Screen orders are counted separately because a
    venue row can also name its provider.
    """

    from sqlalchemy import func, select, union_all

    from eurogas_nexus.db.models import (
        CapacityObservationRecord,
        FlowObservationRecord,
        FxObservationRecord,
        InterestRateObservationRecord,
        LngObservationRecord,
        MarketObservationRecord,
        PowerObservationRecord,
        RemitUmmRecord,
        StorageObservationRecord,
    )

    parts = [
        select(model.source_system.label("system"), func.count().label("rows")).group_by(
            model.source_system
        )
        for model in (
            MarketObservationRecord,
            FxObservationRecord,
            FlowObservationRecord,
            CapacityObservationRecord,
            StorageObservationRecord,
            LngObservationRecord,
            PowerObservationRecord,
            RemitUmmRecord,
        )
    ]
    counts: dict[str, int] = {}
    for system, rows in session.execute(union_all(*parts)):
        if system is not None:
            counts[str(system)] = counts.get(str(system), 0) + int(rows)
    rates = InterestRateObservationRecord
    for benchmark, administrator, rows in session.execute(
        select(rates.benchmark_id, rates.source_system, func.count()).group_by(
            rates.benchmark_id, rates.source_system
        )
    ):
        system = _RATE_SOURCE_BY_BENCHMARK.get(str(benchmark), str(administrator))
        counts[system] = counts.get(system, 0) + int(rows)
    return counts


def _runtime_source_counts() -> dict[str, int] | None:
    """Row counts per source system; None when the read failed (logged), {} without a DB.

    A failed read used to return {} and every source showed 0 rows: a broken query looked
    like an empty store.
    """

    if not _db_is_configured():
        return {}

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from sqlalchemy import or_

        from eurogas_nexus.db.models import (
            ReferenceNode,
            ReferenceTsoAccessPoint,
            ScreenOrderObservationRecord,
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
            # One grouped statement over the observation tables; the previous shape
            # re-scanned the market history once per registered system and named each
            # source's tables by hand, so new connectors read 0 rows.
            observation_counts = _observation_counts_by_source_system(session)
            counts = dict(observation_counts)
            for system in price_systems:
                counts.setdefault(system, 0)
            screen_order_counts = _row_counts_by_source_system(
                session,
                ScreenOrderObservationRecord,
                ScreenOrderObservationRecord.source_system,
                ScreenOrderObservationRecord.provider_id,
            )
            for system in ("ICE_OCM", "ICE_OCM_Sim", "Trayport", "Trayport_Sim"):
                counts[system] = counts.get(system, 0) + sum(
                    row_count
                    for (source_system, provider_id), row_count in screen_order_counts.items()
                    if system in (source_system, provider_id)
                )
            return {
                **counts,
                "ECB": observation_counts.get("ECB", 0),  # market and FX rows
                "ENTSOG": observation_counts.get("ENTSOG", 0)  # flows and capacity
                + session.query(ReferenceNode).filter(ReferenceNode.id.like("entsog-%")).count()
                + session.query(ReferenceTsoAccessPoint)
                .filter(ReferenceTsoAccessPoint.source_system == "ENTSOG")
                .count(),
                "GIE": observation_counts.get("GIE", 0),
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
                "Weather": observation_counts.get("Weather", 0),
                "DEEPSEEK": 0,
            }
    except sqlalchemy_error as exc:
        logger.warning(
            "source row counts unavailable: %s", type(exc).__name__,
            extra={"error_class": type(exc).__name__},
        )
        return None


def _row_counts_by_source_system(session: Any, model: Any, *dimensions: Any) -> dict[Any, int]:
    """Return one grouped ``COUNT(*)`` read keyed by the given columns.

    Replaces the per-registered-system ``COUNT(*)`` fan-out that scanned the
    same table once per source system. With one dimension the key is the
    column value; with several it is the value tuple.
    """

    from sqlalchemy import func

    group_columns = dimensions or (model.source_system,)
    counts: dict[Any, int] = {}
    for row in (
        session.query(*group_columns, func.count()).select_from(model).group_by(*group_columns)
    ):
        values = tuple(row)
        key = values[0] if len(group_columns) == 1 else values[:-1]
        counts[key] = int(values[-1])
    return counts


def _runtime_source_latest_observed() -> dict[str, str] | None:
    """Return the newest observation timestamp per source system (ISO UTC).

    Drives the read-side freshness evaluation (audit item 3): a source is
    only ``active`` while its newest row satisfies the freshness expectation.
    None when the read failed (logged), so the caller can say freshness is unknown.
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
            PowerObservationRecord,
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
            for row in session.query(
                MarketObservationRecord.source_system,
                func.max(MarketObservationRecord.observed_at_utc),
            ).group_by(MarketObservationRecord.source_system):
                track(str(row[0]), row[1])
            for row in session.query(
                FlowObservationRecord.source_system,
                func.max(FlowObservationRecord.observed_at_utc),
            ).group_by(FlowObservationRecord.source_system):
                track(str(row[0]), row[1])
            for row in session.query(
                StorageObservationRecord.source_system,
                func.max(StorageObservationRecord.observed_at_utc),
            ).group_by(StorageObservationRecord.source_system):
                track(str(row[0]), row[1])
            for row in session.query(
                LngObservationRecord.source_system,
                func.max(LngObservationRecord.observed_at_utc),
            ).group_by(LngObservationRecord.source_system):
                track(str(row[0]), row[1])
            for row in session.query(
                FxObservationRecord.source_system,
                func.max(FxObservationRecord.observed_at_utc),
            ).group_by(FxObservationRecord.source_system):
                track(str(row[0]), row[1])
            for row in session.query(
                ScreenOrderObservationRecord.source_system,
                func.max(ScreenOrderObservationRecord.observed_at_utc),
            ).group_by(ScreenOrderObservationRecord.source_system):
                track(str(row[0]), row[1])
            # Power rows (ENTSO-E, Elexon) carry no observed_at; ingestion time is used,
            # as the DataOps freshness read does.
            for row in session.query(
                PowerObservationRecord.source_system,
                func.max(PowerObservationRecord.ingested_at_utc),
            ).group_by(PowerObservationRecord.source_system):
                track(str(row[0]), row[1])
        return {
            system: value.isoformat()
            for system, value in latest.items()
            if hasattr(value, "isoformat")
        }
    except Exception as exc:  # noqa: BLE001 - freshness must not fail the registry
        # Freshness annotation is best-effort: sources evaluate as UNKNOWN rather than
        # failing the registry, but the failure is logged and reported, not silent.
        logger.warning(
            "source newest-observation times unavailable: %s", type(exc).__name__,
            extra={"error_class": type(exc).__name__},
        )
        return None


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
    """Return per-source latest / latest-succeeded / latest-failed runs.

    The Source Center needs one run per source for each of those three roles.
    The previous shape loaded every persisted ingestion run through the ORM and
    kept the first match per source in Python, so the read grew without bound
    with ingestion history. The grouped reads below return at most one row per
    source from the database and serialize them with the repository payload.

    Status vocabulary: canonical ``IngestionRunStatus`` values plus the one
    explicit legacy mapping owned by ``domain/dataops/run_status.py`` and shared
    with the monitoring, pipeline-health and metrics consumers.
    ``SUCCEEDED_WITH_WARNINGS`` counts as a success (with the stored status and
    an explicit warning diagnostic preserved on the read model); pending,
    cancelled and unknown stored values are neither successes nor failures. The
    newest success/failure is selected by completion instant, matching the
    ``last_*_at_utc`` values the read model exposes. Rows with no run still
    produce no bucket (missing stays missing).
    """

    if not _db_is_configured():
        return {}

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import IngestionRunRecord
        from eurogas_nexus.db.repositories.dataops import ingestion_run_payload
        from eurogas_nexus.db.session import get_session_factory

        status: dict[str, dict[str, Any]] = {}
        with get_session_factory()() as session:
            latest_rows = _latest_run_per_source(session, IngestionRunRecord)
            success_rows = _latest_run_per_source(
                session,
                IngestionRunRecord,
                statuses=stored_statuses_for(*SUCCESS_RUN_STATUSES),
            )
            failure_rows = _latest_run_per_source(
                session,
                IngestionRunRecord,
                statuses=stored_statuses_for(*FAILURE_RUN_STATUSES),
            )
            for row in latest_rows:
                status[row.source_id] = {"latest": ingestion_run_payload(row)}
            for row in success_rows:
                payload = ingestion_run_payload(row)
                bucket = status.setdefault(row.source_id, {})
                bucket["last_success_at_utc"] = (
                    payload["finished_at_utc"] or payload["started_at_utc"]
                )
                if payload["status"] == IngestionRunStatus.SUCCEEDED_WITH_WARNINGS.value:
                    # Raw stored status of the run behind last_success_at_utc.
                    # Only a warning-qualified success sets it, so plain
                    # successes keep the previous bucket shape while the
                    # warning case stays traceable for the diagnostics below.
                    bucket["last_success_status"] = payload["status"]
            for row in failure_rows:
                payload = ingestion_run_payload(row)
                bucket = status.setdefault(row.source_id, {})
                bucket["last_failure_at_utc"] = (
                    payload["finished_at_utc"] or payload["started_at_utc"]
                )
        return status
    except sqlalchemy_error:
        return {}


def _latest_run_per_source(
    session: Any,
    model: Any,
    *,
    statuses: tuple[str, ...] | None = None,
):
    """Return the newest run per ``source_id`` in one bounded query.

    ``row_number()`` ranks each source's runs and only rank 1 is hydrated, so
    callers materialize at most one row per source instead of the whole
    persisted history. The unscoped role ranks by ``started_at_utc`` (newest
    requested run). ``statuses`` narrows the ranking to the stored spellings of
    one canonical role and ranks by the completion instant
    (``finished_at_utc`` with ``started_at_utc`` as the fallback for rows that
    never finished), because that is the timestamp the read model exposes as
    ``last_success_at_utc`` / ``last_failure_at_utc``. ``started_at_utc`` then
    ``run_id`` break ties deterministically.
    """

    from sqlalchemy import func

    if statuses is None:
        order_by = (model.started_at_utc.desc(), model.run_id.desc())
    else:
        completion = func.coalesce(model.finished_at_utc, model.started_at_utc)
        order_by = (
            completion.desc(),
            model.started_at_utc.desc(),
            model.run_id.desc(),
        )
    ranked = session.query(
        model.run_id.label("run_id"),
        func.row_number()
        .over(
            partition_by=model.source_id,
            order_by=order_by,
        )
        .label("source_rank"),
    ).select_from(model)
    if statuses is not None:
        ranked = ranked.filter(model.status.in_(statuses))
    ranked_rows = ranked.subquery()
    return (
        session.query(model)
        .join(ranked_rows, ranked_rows.c.run_id == model.run_id)
        .filter(ranked_rows.c.source_rank == 1)
        .all()
    )


def _db_ingestion_runs(
    *,
    source_id: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Read persisted ingestion runs newest first, bounded by the caller.

    ``source_id`` filters on the persisted run column (the same value the
    serialized payload exposes; an empty string keeps the legacy unfiltered
    behaviour) and ``limit`` pages in the database, so the read no longer
    materializes the full run history to return one page.
    """

    if not _db_is_configured():
        return []

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import IngestionRunRecord
        from eurogas_nexus.db.repositories.dataops import ingestion_run_payload
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            query = session.query(IngestionRunRecord).order_by(
                IngestionRunRecord.started_at_utc.desc(),
                IngestionRunRecord.run_id.desc(),
            )
            if source_id:
                query = query.filter(IngestionRunRecord.source_id == source_id)
            if limit is not None:
                query = query.limit(limit)
            return [ingestion_run_payload(row) for row in query.all()]
    except sqlalchemy_error:
        return []


def _ingestion_run_payload(row) -> dict:
    source_id = _source_id_for_source_name(row.source_name)
    canonical_status = canonical_run_status(row.status)
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
        "error_message": (None if canonical_status in SUCCESS_RUN_STATUSES else row.notes),
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
