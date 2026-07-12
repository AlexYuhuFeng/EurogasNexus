"""SDK client for /api/sources and /api/ingestion-runs."""

from pydantic import BaseModel, Field

from eurogas_nexus.sdk._transport import SdkResult, api_url, get_envelope


class SourceSystem(BaseModel):
    source_id: str
    source_system: str
    datasets: list[str] = Field(default_factory=list)
    status: str = "registered"
    description: str = ""
    category: str = "other"
    category_label: str = "Other"
    connectivity_status: str = "runtime_unconfigured"
    operational_status: str = "runtime_unconfigured"
    workflow_ready: bool = False
    effective_source_system: str = ""
    effective_record_count: int = 0
    effective_last_success_at_utc: str | None = None
    entitlement_scope: str = "public"
    freshness_expectation_minutes: int = 0
    credential_requirements: list[str] = Field(default_factory=list)
    credential_provider_id: str | None = None
    credential_state: str = "not_required"
    live_record_count: int = 0
    diagnostics: list[str] = Field(default_factory=list)
    export_restrictions: list[str] = Field(default_factory=list)


class IngestionRun(BaseModel):
    run_id: str
    source_id: str
    status: str
    records_ingested: int = 0
    records_failed: int = 0
    normalization: str = "unknown"
    error_message: str | None = None


def fetch_sources(base_url: str) -> list[SourceSystem]:
    return fetch_sources_result(base_url).data


def fetch_sources_result(base_url: str) -> SdkResult[list[SourceSystem]]:
    data, meta = get_envelope(api_url(base_url, "sources"))
    return SdkResult([SourceSystem.model_validate(row) for row in data], meta)


def fetch_source(base_url: str, source_id: str) -> SourceSystem:
    return fetch_source_result(base_url, source_id).data


def fetch_source_result(base_url: str, source_id: str) -> SdkResult[SourceSystem]:
    data, meta = get_envelope(api_url(base_url, f"sources/{source_id}"))
    return SdkResult(SourceSystem.model_validate(data), meta)


def fetch_ingestion_runs(base_url: str, *, source_id: str | None = None) -> list[IngestionRun]:
    return fetch_ingestion_runs_result(base_url, source_id=source_id).data


def fetch_ingestion_runs_result(
    base_url: str,
    *,
    source_id: str | None = None,
) -> SdkResult[list[IngestionRun]]:
    params = {"source_id": source_id} if source_id is not None else None
    data, meta = get_envelope(api_url(base_url, "ingestion-runs"), params=params)
    return SdkResult([IngestionRun.model_validate(row) for row in data], meta)
