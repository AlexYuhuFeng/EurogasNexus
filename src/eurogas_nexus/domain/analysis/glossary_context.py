"""Glossary term context assembly (main entry + snapshot reads).

把"画像"（glossary_profile）与"实体"（glossary_entities）两层结果组装为
最终的 GlossaryContext 载荷：容量、使用量、价格、实时标记、路线、合约、
指标、数据质量与展示章节一次成型；任何关键上下文缺失都显式告警。
"""

from __future__ import annotations

from datetime import UTC, datetime

from eurogas_nexus.domain.analysis._common import (
    _contains_any,
    _parse_datetime,
    _row_matches_duration,
    _unique,
)
from eurogas_nexus.domain.analysis.contracts import AnalysisSnapshot, GlossaryContext
from eurogas_nexus.domain.analysis.glossary_entities import (
    _context_data_quality,
    _context_metrics,
    _context_sections,
    _entity_summary,
    _matched_entities,
    _sources_from_matched_entities,
)
from eurogas_nexus.domain.analysis.glossary_profile import _resolved_glossary_context_profile


def build_glossary_context(
    term: str,
    snapshot: AnalysisSnapshot,
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
    lang: str = "en",
) -> GlossaryContext:
    """Build the enriched glossary context for one term.

    组装术语的富上下文：匹配实体、容量/使用量、价格/实时标记、路线、
    合约、指标、数据质量与展示章节；按请求语言选择描述文本。

    Args:
        term: The queried term.
        snapshot: Backend-data snapshot.
        duration_start_utc: Window start filter, or None.
        duration_end_utc: Window end filter, or None.
        lang: Output language (``en`` or ``zh``/``zh-CN``).

    Returns:
        A GlossaryContext with matched runtime context and warnings;
        missing context is reported, never fabricated.

    Raises:
        No exceptions; all gaps surface as warnings.
    """

    profile = _resolved_glossary_context_profile(term, snapshot)
    duration = _duration_payload(duration_start_utc, duration_end_utc)
    point_keys = profile["point_keys"]
    price_keys = profile["price_keys"]
    route_keys = profile["route_keys"]
    matched_entities = _matched_entities(
        snapshot,
        point_keys=point_keys,
        price_keys=price_keys,
        route_keys=route_keys,
        contract_keys=[*point_keys, *route_keys],
    )

    capacity = _first_capacity(
        snapshot,
        point_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )
    capacity_usage = _capacity_usage(
        snapshot,
        point_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )
    prices = _related_prices(
        snapshot,
        price_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )
    live_marks = _related_live_marks(
        snapshot,
        price_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    )
    routes = _related_routes(snapshot, route_keys)
    contracts = _related_contracts(snapshot, [*point_keys, *route_keys])
    warnings = _context_warnings(snapshot)
    warnings.extend(profile["warnings"])
    if profile["context_type"] in {"entry_point", "exit_point", "capacity"} and capacity is None:
        warnings.append("CAPACITY_CONTEXT_MISSING")
    if (
        profile["context_type"] in {"entry_point", "exit_point", "capacity"}
        and capacity_usage is None
    ):
        warnings.append("CAPACITY_USAGE_CONTEXT_MISSING")
    if (
        profile["context_type"] in {"price_assessment", "hub", "venue"}
        and not prices
        and not live_marks
    ):
        warnings.append("PRICE_CONTEXT_MISSING")

    description_en = profile["description_en"]
    description_zh_cn = profile["description_zh_cn"]
    entity_summary = _entity_summary(
        term=term,
        profile=profile,
        capacity=capacity,
        capacity_usage=capacity_usage,
        prices=prices,
        live_marks=live_marks,
        routes=routes,
        contracts=contracts,
        matched_entities=matched_entities,
    )
    metrics = _context_metrics(capacity, capacity_usage, prices, live_marks, contracts)
    data_quality = _context_data_quality(
        snapshot,
        prices,
        live_marks,
        capacity,
        capacity_usage,
        matched_entities,
    )
    return GlossaryContext(
        term=term,
        context_type=profile["context_type"],
        description=description_zh_cn if lang in {"zh", "zh-CN"} else description_en,
        description_en=description_en,
        description_zh_cn=description_zh_cn,
        requested_duration=duration,
        entity_summary=entity_summary,
        matched_entities=matched_entities,
        capacity=capacity,
        capacity_usage=capacity_usage,
        metrics=metrics,
        related_prices=prices,
        related_routes=routes,
        related_contracts=contracts,
        live_market_marks=live_marks,
        context_sections=_context_sections(
            entity_summary=entity_summary,
            capacity=capacity,
            capacity_usage=capacity_usage,
            metrics=metrics,
            prices=prices,
            live_marks=live_marks,
            routes=routes,
            contracts=contracts,
            data_quality=data_quality,
            warnings=warnings,
        ),
        related_sources=profile["related_sources"] or _sources_from_matched_entities(
            matched_entities,
            snapshot,
        ),
        data_quality=data_quality,
        warnings=_unique(warnings),
    )


def _duration_payload(
    duration_start_utc: datetime | None,
    duration_end_utc: datetime | None,
) -> dict | None:
    """Normalize the requested duration to ISO strings, or None when empty.

    请求时间窗归一化：两端都缺时返回 None；否则输出 ISO 字符串载荷。
    """

    if duration_start_utc is None and duration_end_utc is None:
        return None
    return {
        "duration_start_utc": duration_start_utc.isoformat() if duration_start_utc else None,
        "duration_end_utc": duration_end_utc.isoformat() if duration_end_utc else None,
    }


def _first_capacity(
    snapshot: AnalysisSnapshot,
    point_keys: list[str],
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> dict | None:
    """Return the first capacity row matching point keys and the duration.

    取第一条匹配点位与时间窗的容量记录（保持快照顺序，不排序）。
    """

    for row in snapshot.capacity_context:
        if _contains_any(row, point_keys) and _row_matches_duration(
            row,
            duration_start_utc=duration_start_utc,
            duration_end_utc=duration_end_utc,
            start_fields=("valid_from_utc", "period_start_utc"),
            end_fields=("valid_to_utc", "period_end_utc"),
        ):
            return row
    return None


def _capacity_usage(
    snapshot: AnalysisSnapshot,
    point_keys: list[str],
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> dict | None:
    """Aggregate matching flow rows into a capacity-usage payload.

    容量使用量聚合：按点位与时间窗匹配流量观测，做 mcm→MWh 换算
    （缺容量侧 MWh 时用 1 mcm = 10,550 MWh 的显式假设并附注），
    计算均值/峰值与利用率。

    Args:
        snapshot: Backend-data snapshot.
        point_keys: Point keys to match.
        duration_start_utc: Window start filter, or None.
        duration_end_utc: Window end filter, or None.

    Returns:
        Usage payload with used/capacity, averages, peaks, usage
        percentages and a conversion assumption when applied; None when
        no flow row matches.
    """

    matching_rows = [
        row
        for row in snapshot.flow_observations
        if _contains_any(row, point_keys)
        and _row_matches_duration(
            row,
            duration_start_utc=duration_start_utc,
            duration_end_utc=duration_end_utc,
            start_fields=("period_start_utc",),
            end_fields=("period_end_utc",),
        )
    ]
    if not matching_rows:
        return None

    capacity = _first_capacity(
        snapshot,
        point_keys,
        duration_start_utc=duration_start_utc,
        duration_end_utc=duration_end_utc,
    ) or {}
    capacity_mwh = capacity.get("capacity_mwh_per_day")
    capacity_mcm = capacity.get("capacity_mcm_d")
    converted_rows: list[dict] = []
    conversion_assumptions: list[str] = []
    for row in matching_rows:
        flow_mwh = row.get("flow_mwh_per_day")
        flow_mcm = row.get("flow_mcm_d")
        conversion_assumption = None
        if flow_mwh is None and flow_mcm is not None and capacity_mwh is not None:
            # 只有 mcm 侧数据而容量以 MWh 表达：按标准热值换算并显式附注
            #（生产环境应替换为按热值（CV）的精确换算）。
            flow_mwh = round(float(flow_mcm) * 10550, 4)
            conversion_assumption = (
                "1 mcm = 10,550 MWh; replace with CV-specific conversion in production."
            )
            conversion_assumptions.append(conversion_assumption)
        converted_rows.append(
            {
                **row,
                "flow_mwh_per_day": flow_mwh,
                "flow_mcm_d": flow_mcm,
                "conversion_assumption": conversion_assumption,
            }
        )

    used_mwh_values = [
        float(row["flow_mwh_per_day"])
        for row in converted_rows
        if row.get("flow_mwh_per_day") is not None
    ]
    used_mcm_values = [
        float(row["flow_mcm_d"]) for row in converted_rows if row.get("flow_mcm_d") is not None
    ]
    average_mwh = round(sum(used_mwh_values) / len(used_mwh_values), 4) if used_mwh_values else None
    average_mcm = round(sum(used_mcm_values) / len(used_mcm_values), 4) if used_mcm_values else None
    peak_mwh = round(max(used_mwh_values), 4) if used_mwh_values else None
    peak_mcm = round(max(used_mcm_values), 4) if used_mcm_values else None
    capacity_value = capacity_mwh or capacity_mcm
    used_value = average_mwh if average_mwh is not None else average_mcm
    usage_pct = (
        round(float(used_value) / float(capacity_value) * 100, 2)
        if capacity_value and used_value
        else None
    )
    peak_used_value = peak_mwh if peak_mwh is not None else peak_mcm
    peak_usage_pct = (
        round(float(peak_used_value) / float(capacity_value) * 100, 2)
        if capacity_value and peak_used_value
        else None
    )
    period_starts = [
        parsed
        for row in converted_rows
        if (parsed := _parse_datetime(row.get("period_start_utc"))) is not None
    ]
    period_ends = [
        parsed
        for row in converted_rows
        if (parsed := _parse_datetime(row.get("period_end_utc"))) is not None
    ]
    latest_row = max(
        converted_rows,
        key=lambda row: _parse_datetime(row.get("period_end_utc"))
        or datetime.min.replace(tzinfo=UTC),
    )
    return {
        "period_start_utc": min(period_starts).isoformat() if period_starts else None,
        "period_end_utc": max(period_ends).isoformat() if period_ends else None,
        "used": used_value,
        "capacity": capacity_value,
        "used_mwh_per_day": average_mwh,
        "capacity_mwh_per_day": capacity_mwh,
        "used_mcm_d": average_mcm,
        "capacity_mcm_d": capacity_mcm,
        "peak_used_mwh_per_day": peak_mwh,
        "peak_used_mcm_d": peak_mcm,
        "usage_pct": usage_pct,
        "peak_usage_pct": peak_usage_pct,
        "observations_count": len(converted_rows),
        "direction": latest_row.get("direction"),
        "unit": "MWh/d" if capacity_mwh or average_mwh else "mcm/d",
        "source_reference": latest_row.get("source_reference"),
        "source_references": _unique(
            [
                str(row.get("source_reference"))
                for row in converted_rows
                if row.get("source_reference")
            ]
        ),
        "conversion_assumption": conversion_assumptions[0] if conversion_assumptions else None,
    }


def _related_prices(
    snapshot: AnalysisSnapshot,
    keys: list[str],
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> list[dict]:
    """Return matching market observation rows (capped at 10).

    相关价格：按 venue/product/price_name/来源字段匹配并过滤时间窗。
    """

    normalized = [key.lower() for key in keys]
    prices: list[dict] = []
    for row in snapshot.market_observations:
        if _contains_any(
            row,
            normalized,
            fields=("market_venue", "product", "price_name", "source_system", "source_reference"),
        ) and _row_matches_duration(
            row,
            duration_start_utc=duration_start_utc,
            duration_end_utc=duration_end_utc,
            start_fields=("period_start_utc", "observed_at_utc"),
            end_fields=("period_end_utc", "observed_at_utc"),
        ):
            prices.append(row)
    return prices[:10]


def _related_live_marks(
    snapshot: AnalysisSnapshot,
    keys: list[str],
    *,
    duration_start_utc: datetime | None = None,
    duration_end_utc: datetime | None = None,
) -> list[dict]:
    """Return matching live mark rows (capped at 10).

    相关实时标记：按 venue/hub/product/来源字段匹配并过滤时间窗。
    """

    marks: list[dict] = []
    for row in snapshot.live_market_marks:
        if _contains_any(
            row,
            keys,
            fields=("venue", "hub", "product", "source_system", "source_reference"),
        ) and _row_matches_duration(
            row,
            duration_start_utc=duration_start_utc,
            duration_end_utc=duration_end_utc,
            start_fields=("mark_time_utc",),
            end_fields=("mark_time_utc",),
        ):
            marks.append(row)
    return marks[:10]


def _related_routes(snapshot: AnalysisSnapshot, keys: list[str]) -> list[dict]:
    """Return matching route candidate rows (capped at 10)."""

    routes: list[dict] = []
    for row in snapshot.route_candidates:
        if _contains_any(row, keys):
            routes.append(row)
    return routes[:10]


def _related_contracts(snapshot: AnalysisSnapshot, keys: list[str]) -> list[dict]:
    """Return matching portfolio/contract rows (capped at 10)."""

    contracts: list[dict] = []
    for row in snapshot.portfolio_context:
        if _contains_any(row, keys):
            contracts.append(row)
    return contracts[:10]


def _context_warnings(snapshot: AnalysisSnapshot) -> list[str]:
    """Snapshot-level warnings plus the non-runtime-DB warning.

    快照告警汇总：非运行库来源必须追加 RUNTIME_DB_CONTEXT_NOT_AVAILABLE，
    提示上下文可信度受限（fail-closed 的展示侧纪律）。
    """

    warnings = list(snapshot.warnings)
    if snapshot.source != "runtime-postgresql":
        warnings.append("RUNTIME_DB_CONTEXT_NOT_AVAILABLE")
    return _unique(warnings)
