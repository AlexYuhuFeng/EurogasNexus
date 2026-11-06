"""Registered source systems — static data, import-safe.

The source registry is pure data used by the Source Center API
(``api/routes/public/sources.py``) and by operators to reason about the
registered feed surface. It must stay free of web-framework and database
imports (enforced by the import-boundary contract tests).

本模块是数据源登记表的唯一静态事实来源：25 个注册来源的分类、授权、
新鲜度期望、凭据与认证要求都在此处声明；API 层只做展示与运行时状态
叠加，不得另行维护一份来源清单。
"""

# 来源分类的展示标签：键为稳定分类码，值用于 UI 与文档。
CATEGORY_LABELS = {
    "price": "Prices",
    "fx": "FX",
    "infrastructure": "Infrastructure",
    "tariff": "TSO Tariffs",
    "weather": "Weather",
    "power": "Power",
    "rates": "Interest rates",
    "ai": "LLM",
}


def _source_row(
    source_id: str,
    system: str,
    category: str,
    datasets: tuple[str, ...],
    description: str,
    entitled: bool,
    *,
    freshness_minutes: int,
    integration: str = "api",
) -> dict:
    """Build one registered-source record (static fields only).

    组装单条来源登记记录：entitled 来源需要 API 密钥、受许可管控、预览
    替换机制，且默认 certifi-cation 未验证（禁活）；公共来源则相反。
    """

    return {
        "source_id": source_id,
        "source_system": system,
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        # How the data arrives, apart from whether it is running (#33): "api" (a connector
        # fetches it), "file_import" (an operator imports the desk's own export; no
        # connection, no schedule), "template" (a placeholder for a vendor not chosen yet;
        # nothing reads it), "model_service" (a model endpoint, not a data feed).
        "integration": integration,
        "datasets": list(datasets),
        "status": "registered",
        "connectivity_status": "registered",
        "operational_status": "registered",
        "workflow_ready": False,
        "live_record_count": 0,
        "effective_source_system": system,
        "effective_record_count": 0,
        "effective_last_success_at_utc": None,
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
        # 认证未验证的来源禁止实时接入（fail-closed，见审计项 4）。
        "certification_stage": "unverified",
        "certification_allows_live": False,
        "preview_substitute_source_system": None,
        "preview_substitute_status": None,
        "preview_substitute_record_count": 0,
        "last_success_at_utc": None,
        "last_failure_at_utc": None,
        "last_ingestion_status": None,
        "last_ingestion_message": None,
        "diagnostics": [],
    }


def registered_sources() -> list[dict]:
    """Return the full static registry of source systems, one row per connector manifest.

    返回全部注册来源的静态登记记录列表（由连接器清单派生）。

    Returns:
        List of source records; each carries identity, category, datasets,
        entitlement scope, freshness expectation, credential requirements
        and certification state. Runtime fields (record counts, last
        success/failure) are initialised empty here and overlaid by the
        Source Center API from the runtime store. Each row is derived from the
        provider's connector manifest (``eurogas_nexus.domain.connectors``), the one
        place a provider is declared.
    """

    from eurogas_nexus.domain.connectors.registry import connector_manifests

    return [_row_from_manifest(manifest) for manifest in connector_manifests()]


def _row_from_manifest(manifest) -> dict:
    from eurogas_nexus.domain.connectors.plugins import plugin_enabled

    row = _source_row(
        manifest.source_id,
        manifest.system,
        manifest.category,
        tuple(manifest.datasets),
        manifest.description,
        manifest.entitled,
        freshness_minutes=manifest.freshness_minutes,
        integration=manifest.integration,
    )
    if manifest.licensed_import:
        # Licensed fixes the desk imports from its own export: served only to principals
        # holding the matching data scope, though no key is configured for them (#33).
        row["entitlement_scope"] = "licensed"
        row["export_restrictions"] = ["license-controlled"]
    if manifest.plugin:
        row["plugin"] = {"name": manifest.plugin, "enabled": plugin_enabled(manifest)}
    return row
