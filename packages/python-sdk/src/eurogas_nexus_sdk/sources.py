"""SDK client for /api/sources and /api/ingestion-runs."""

from pydantic import BaseModel, Field

from eurogas_nexus_sdk._transport import SdkResult, api_url, get_envelope


class SourceSystem(BaseModel):
    """One registered data source and its operational posture.

    Attributes:
        source_id: Stable identifier of the source.
        source_system: System that provides the data (e.g. ``GIE``, ``ENTSOG``).
        datasets: Datasets this source publishes.
        status: Registration lifecycle status.
        description: Human-readable description of the source.
        category: Machine category key (``other`` when unknown).
        category_label: Display label for ``category``.
        connectivity_status: Runtime connectivity posture; defaults to
            ``runtime_unconfigured`` until the runtime store holds a record.
        operational_status: Runtime operational posture; same default rationale.
        workflow_ready: Whether workflow routing considers this source usable.
        effective_source_system: Final source system after runtime overrides;
            empty string when no override is active.
        effective_record_count: Record count from the latest successful ingest.
        effective_last_success_at_utc: UTC timestamp of the last successful
            ingest; None when the source never succeeded at runtime.
        entitlement_scope: Access scope (``public`` or an entitlement name).
        freshness_expectation_minutes: Expected freshness window in minutes;
            non-positive means no expectation declared (unknown).
        credential_requirements: Credential keys the connector needs.
        credential_provider_id: Provider backing the required credential;
            None when no credential is required.
        credential_state: Runtime credential posture (e.g. ``not_required``).
        live_record_count: Record count visible through the live API.
        diagnostics: Non-fatal diagnostic messages from recent checks.
        export_restrictions: Export-control restrictions applying to this source.
    """

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
    # effective_* 是叠加运行时覆盖后的最终口径；last_success 为 None 表示
    # 该来源从未在运行时成功入库，展示层应据此标记"未激活"而非"无数据"。
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
    """One ingestion run attempt for a source.

    Attributes:
        run_id: Unique identifier of the run.
        source_id: Source the run ingested from.
        status: Run status (e.g. ``completed``, ``failed``).
        records_ingested: Number of rows successfully ingested.
        records_failed: Number of rows rejected during validation or import.
        normalization: Normalization mode applied during the run.
        error_message: Failure detail; None when the run did not fail.
    """

    run_id: str
    source_id: str
    status: str
    records_ingested: int = 0
    records_failed: int = 0
    normalization: str = "unknown"
    # 只有失败运行才回填错误信息，成功/进行中的运行保持 None，
    # 调用方不能把 None 当作"没有错误"之外的其他含义。
    error_message: str | None = None


def fetch_sources(base_url: str) -> list[SourceSystem]:
    """Return all registered sources, dropping envelope metadata.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        All registered sources; use :func:`fetch_sources_result` when lineage
        metadata (``meta``) is needed.
    """
    return fetch_sources_result(base_url).data


def fetch_sources_result(base_url: str) -> SdkResult[list[SourceSystem]]:
    """Return all registered sources plus backend envelope metadata.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        The sources together with the backend ``meta`` envelope (source
        references, warnings, research-only flags) preserved for auditability.
    """
    # data 与 meta 同返：meta 携带来源引用/告警等血缘信息，供审计与展示层使用；
    # 不需要血缘的调用方直接用 fetch_sources() 取 data 即可。
    data, meta = get_envelope(api_url(base_url, "sources"))
    return SdkResult([SourceSystem.model_validate(row) for row in data], meta)


def fetch_source(base_url: str, source_id: str) -> SourceSystem:
    """Return one source by id, dropping envelope metadata.

    Args:
        base_url: Base URL of the backend server.
        source_id: Identifier of the source to fetch.

    Returns:
        The matching source; unknown ids surface as an HTTP error from the
        transport layer.
    """
    return fetch_source_result(base_url, source_id).data


def fetch_source_result(base_url: str, source_id: str) -> SdkResult[SourceSystem]:
    """Return one source plus backend envelope metadata.

    Args:
        base_url: Base URL of the backend server.
        source_id: Identifier of the source to fetch.

    Returns:
        The source together with the backend ``meta`` envelope.
    """
    data, meta = get_envelope(api_url(base_url, f"sources/{source_id}"))
    return SdkResult(SourceSystem.model_validate(data), meta)


def fetch_ingestion_runs(base_url: str, *, source_id: str | None = None) -> list[IngestionRun]:
    """Return ingestion runs, optionally filtered by source.

    Args:
        base_url: Base URL of the backend server.
        source_id: When given, only runs for this source are returned.

    Returns:
        Ingestion runs; use :func:`fetch_ingestion_runs_result` when the
        backend ``meta`` envelope is needed.
    """
    return fetch_ingestion_runs_result(base_url, source_id=source_id).data


def fetch_ingestion_runs_result(
    base_url: str,
    *,
    source_id: str | None = None,
) -> SdkResult[list[IngestionRun]]:
    """Return ingestion runs plus backend envelope metadata.

    Args:
        base_url: Base URL of the backend server.
        source_id: When given, only runs for this source are returned.

    Returns:
        The runs together with the backend ``meta`` envelope.
    """
    # 未指定 source_id 时不带过滤参数：显式传空串会被后端当作字面值过滤，
    # 结果变成"空"而不是"全部"。
    params = {"source_id": source_id} if source_id is not None else None
    data, meta = get_envelope(api_url(base_url, "ingestion-runs"), params=params)
    return SdkResult([IngestionRun.model_validate(row) for row in data], meta)
