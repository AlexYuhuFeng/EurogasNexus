"""Registered source systems — static data, import-safe.

The source registry is pure data used by the Source Center API
(``api/routes/public/sources.py``) and by operators to reason about the
registered feed surface. It must stay free of web-framework and database
imports (enforced by the import-boundary contract tests).

本模块是数据源登记表的唯一静态事实来源：24 个注册来源的分类、授权、
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
    """Return the full static registry of 24 source systems.

    返回全部注册来源的静态登记记录列表。

    Returns:
        List of source records; each carries identity, category, datasets,
        entitlement scope, freshness expectation, credential requirements
        and certification state. Runtime fields (record counts, last
        success/failure) are initialised empty here and overlaid by the
        Source Center API from the runtime store.
    """

    return [
        _source_row(
            "src-ecb",
            "ECB",
            "fx",
            ("eurofxref-daily", "fx-reference-rates"),
            "European Central Bank FX reference rates.",
            False,
            freshness_minutes=1440,
        ),
        _source_row(
            "src-entsog",
            "ENTSOG",
            "infrastructure",
            ("connection-points", "operator-directions", "flows", "capacity", "outages", "ip"),
            "ENTSOG Transparency Platform infrastructure, flows, capacities, IPs, and outages.",
            False,
            freshness_minutes=60,
        ),
        _source_row(
            "src-gie",
            "GIE",
            "infrastructure",
            ("agsi-storage", "alsi-lng"),
            "Gas Infrastructure Europe AGSI storage and ALSI LNG data.",
            True,
            freshness_minutes=360,
        ),
        _source_row(
            "src-national-gas-nts",
            "NationalGasNTS",
            "tariff",
            ("transportation-statement", "entry-tariffs", "exit-tariffs", "commodity-charges"),
            "National Gas NTS transportation tariff references for explicit-leg route costing.",
            False,
            freshness_minutes=43200,
        ),
        _source_row(
            "src-bbl",
            "BBL",
            "tariff",
            ("interconnector-tariffs", "forward-flow", "reverse-flow"),
            "BBL Company public interconnector capacity tariff references.",
            False,
            freshness_minutes=43200,
        ),
        _source_row(
            "src-iuk",
            "IUK",
            "tariff",
            ("interconnector-tariffs", "bacton", "zeebrugge"),
            "Interconnector UK public charging statement and capacity tariff references.",
            False,
            freshness_minutes=43200,
        ),
        _source_row(
            "src-gts",
            "GTS",
            "tariff",
            ("netherlands-transmission-tariffs", "entry-exit"),
            "Gasunie Transport Services Dutch transmission tariff references.",
            False,
            freshness_minutes=43200,
        ),
        _source_row(
            "src-natran",
            "NaTran",
            "tariff",
            ("france-transmission-tariffs", "entry-exit", "peg"),
            "French transmission tariff references for NaTran/GRTgaz/Terega context.",
            False,
            freshness_minutes=43200,
        ),
        _source_row(
            "src-german-tso",
            "GermanTSO",
            "tariff",
            ("germany-transmission-tariffs", "the-market-area", "entry-exit"),
            "German gas transmission tariff references for THE market-area routing.",
            False,
            freshness_minutes=43200,
        ),
        _source_row(
            "src-fluxys-belgium",
            "FluxysBelgium",
            "tariff",
            ("belgium-transmission-tariffs", "ztp", "interconnection"),
            "Fluxys Belgium transmission tariff references for ZTP and border routing.",
            False,
            freshness_minutes=43200,
        ),
        _source_row(
            "src-cnmc-enagas",
            "CNMCEnagas",
            "tariff",
            ("spain-access-tolls", "transmission", "regasification"),
            "Spanish CNMC/Enagas gas access toll and tariff references.",
            False,
            freshness_minutes=43200,
        ),
        _source_row(
            "src-eex",
            "EEX",
            "price",
            ("gas-futures", "gas-spot", "screen-trades", "settlements"),
            "European Energy Exchange gas market prices and screen observations.",
            True,
            freshness_minutes=1,
        ),
        _source_row(
            "src-eex-sim",
            "EEX_Sim",
            "price",
            ("gas-spot", "day-ahead", "weekend", "month-ahead", "simulated"),
            (
                "EEX-shaped simulated gas market prices injected into the runtime DB "
                "at a continuous worker cadence for decision-support testing."
            ),
            False,
            freshness_minutes=1,
        ),
        _source_row(
            "src-ice-ocm",
            "ICE_OCM",
            "price",
            ("within-day", "day-ahead", "screen-orders", "live-marks"),
            "ICE OCM live within-day and day-ahead market observations.",
            True,
            freshness_minutes=1,
        ),
        _source_row(
            "src-ice-ocm-sim",
            "ICE_OCM_Sim",
            "price",
            ("within-day", "day-ahead", "screen-marks", "simulated"),
            (
                "ICE OCM-shaped simulated within-day and day-ahead marks injected "
                "through the runtime DB path at a high-frequency worker cadence."
            ),
            False,
            freshness_minutes=1,
        ),
        _source_row(
            "src-trayport",
            "Trayport",
            "price",
            ("broker-screens", "market-data", "screen-orders"),
            "Trayport screen and broker market data.",
            True,
            freshness_minutes=1,
        ),
        _source_row(
            "src-trayport-sim",
            "Trayport_Sim",
            "price",
            ("broker-screens", "within-day", "day-ahead", "simulated"),
            (
                "Trayport-shaped simulated broker-screen marks injected through "
                "the canonical runtime DB path at a realtime worker cadence."
            ),
            False,
            freshness_minutes=1,
        ),
        _source_row(
            "src-platts",
            "Platts",
            "price",
            ("assessments", "forward-curves", "indices"),
            "Platts licensed gas price assessments and curves.",
            True,
            freshness_minutes=1440,
        ),
        _source_row(
            "src-icis",
            "ICIS",
            "price",
            ("heren-assessments", "day-ahead", "indices", "curves"),
            "ICIS Heren licensed gas assessments and reference prices.",
            True,
            freshness_minutes=1440,
        ),
        _source_row(
            "src-icis-sim",
            "ICIS_Sim",
            "price",
            ("heren-assessments", "day-ahead", "daily-assessment", "simulated"),
            "ICIS Heren-shaped simulated daily assessment rows injected into market observations.",
            False,
            freshness_minutes=1440,
        ),
        _source_row(
            "src-argus",
            "Argus",
            "price",
            ("assessments", "indices", "curves"),
            "Argus licensed gas assessments and market references.",
            True,
            freshness_minutes=1440,
        ),
        _source_row(
            "src-kpler",
            "Kpler",
            "price",
            ("lng-flows", "cargo-tracking", "market-data"),
            "Kpler licensed LNG and market intelligence feeds.",
            True,
            freshness_minutes=60,
        ),
        _source_row(
            "src-weather",
            "Weather",
            "weather",
            ("temperature", "hdd", "cdd", "forecast"),
            "Weather observations and forecast signals for HDD/CDD modelling.",
            True,
            freshness_minutes=180,
        ),
        _source_row(
            "src-deepseek",
            "DEEPSEEK",
            "ai",
            ("analysis", "reporting", "qa"),
            "DeepSeek LLM analysis provider for operator-reviewed reports.",
            True,
            freshness_minutes=0,
        ),
    ]
