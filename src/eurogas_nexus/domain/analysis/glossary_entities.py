"""Entity matching, summaries, metrics, quality and display sections.

术语上下文的"实体层"：跨快照各集合做实体匹配与去重，生成实体摘要、
指标列表、数据质量与展示章节。所有集合都有数量上限，避免上下文爆炸。
"""

from __future__ import annotations

from eurogas_nexus.domain.analysis._common import _contains_any, _unique
from eurogas_nexus.domain.analysis.builders import _snapshot_citations
from eurogas_nexus.domain.analysis.contracts import AnalysisSnapshot


def _matched_entities(
    snapshot: AnalysisSnapshot,
    *,
    point_keys: list[str],
    price_keys: list[str],
    route_keys: list[str],
    contract_keys: list[str],
) -> list[dict]:
    """Match entities across every snapshot collection, deduplicated, capped.

    跨集合实体匹配：术语表、容量、流量、市场价格、实时标记、路线、
    上游合约逐类命中并打标；结果去重并截断到 30 条。

    Args:
        snapshot: Backend-data snapshot.
        point_keys: Keys for capacity/flow point matching.
        price_keys: Keys for market price/live mark matching.
        route_keys: Keys for route candidate matching.
        contract_keys: Keys for upstream contract matching.

    Returns:
        Deduplicated entity payloads (max 30).
    """

    entities: list[dict] = []
    for row in snapshot.glossary_terms:
        if _contains_any(
            row,
            [*point_keys, *price_keys],
            fields=("term", "term_id", "category", "definition_en", "aliases", "related_terms"),
        ):
            entities.append(
                _entity_payload(
                    "glossary_term",
                    str(row.get("term") or row.get("term_id")),
                    row,
                    category=row.get("category"),
                )
            )
    for row in snapshot.capacity_context:
        if _contains_any(row, point_keys, fields=("point_name", "direction", "source_reference")):
            entities.append(
                _entity_payload(
                    "capacity_point",
                    str(row.get("point_name")),
                    row,
                    direction=row.get("direction"),
                )
            )
    for row in snapshot.flow_observations:
        if _contains_any(row, point_keys, fields=("point_name", "direction", "source_reference")):
            entities.append(
                _entity_payload(
                    "flow_point",
                    str(row.get("point_name")),
                    row,
                    direction=row.get("direction"),
                )
            )
    for row in snapshot.market_observations:
        if _contains_any(
            row,
            price_keys,
            fields=("market_venue", "product", "source_system", "source_reference"),
        ):
            entities.append(
                _entity_payload(
                    "market_price",
                    f"{row.get('market_venue')} {row.get('product')}".strip(),
                    row,
                )
            )
    for row in snapshot.live_market_marks:
        if _contains_any(
            row,
            price_keys,
            fields=("venue", "hub", "product", "source_system", "source_reference"),
        ):
            entities.append(
                _entity_payload(
                    "live_market_mark",
                    f"{row.get('venue')} {row.get('hub')} {row.get('product')}".strip(),
                    row,
                )
            )
    for row in snapshot.route_candidates:
        if _contains_any(row, route_keys):
            entities.append(
                _entity_payload(
                    "route_candidate",
                    str(row.get("route_name") or row.get("route_id")),
                    row,
                )
            )
    for row in snapshot.portfolio_context:
        if _contains_any(row, contract_keys):
            entities.append(
                _entity_payload(
                    "upstream_contract",
                    str(row.get("contract_name") or row.get("contract_id")),
                    row,
                )
            )
    return _unique_entities(entities)[:30]


def _entity_payload(
    entity_type: str,
    label: str,
    row: dict,
    **extra: object,
) -> dict:
    """Build one normalized entity payload with provenance.

    组装实体载荷：类型、标签与来源引用；额外字段（direction/category）
    仅在非空时保留，避免载荷携带无意义空值。
    """

    return {
        "entity_type": entity_type,
        "label": label,
        "source_reference": row.get("source_reference")
        or row.get("source_system")
        or row.get("source_refs"),
        **{key: value for key, value in extra.items() if value is not None},
    }


def _unique_entities(entities: list[dict]) -> list[dict]:
    """Deduplicate entities by (entity_type, normalized label), keep first."""

    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        key = (str(entity.get("entity_type")), str(entity.get("label")).lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(entity)
    return unique


def _sources_from_matched_entities(
    matched_entities: list[dict],
    snapshot: AnalysisSnapshot,
) -> list[str]:
    """Derive source references from matched entities (fallback: citations).

    从实体载荷提取来源引用；实体无引用时回退到快照级引用清单。
    """

    sources = [
        str(entity.get("source_reference"))
        for entity in matched_entities
        if entity.get("source_reference")
    ]
    return _unique(sources) or _snapshot_citations(snapshot)


def _entity_summary(
    *,
    term: str,
    profile: dict,
    capacity: dict | None,
    capacity_usage: dict | None,
    prices: list[dict],
    live_marks: list[dict],
    routes: list[dict],
    contracts: list[dict],
    matched_entities: list[dict],
) -> dict:
    """Build the compact entity summary for the overview section.

    概览摘要：术语、上下文类型、各集合是否存在/数量、匹配实体类型与
    主要来源——给 UI 一行可读的"有什么"。
    """

    return {
        "term": term,
        "context_type": profile["context_type"],
        "has_capacity": capacity is not None,
        "has_capacity_usage": capacity_usage is not None,
        "price_count": len(prices),
        "live_mark_count": len(live_marks),
        "route_count": len(routes),
        "contract_count": len(contracts),
        "matched_entity_count": len(matched_entities),
        "matched_entity_types": _unique(
            [str(entity.get("entity_type")) for entity in matched_entities]
        ),
        "primary_sources": profile["related_sources"],
    }


def _context_metrics(
    capacity: dict | None,
    capacity_usage: dict | None,
    prices: list[dict],
    live_marks: list[dict],
    contracts: list[dict],
) -> list[dict]:
    """Extract a flat metric list for display (capacity/prices/marks/contracts).

    指标扁平化：容量与利用率、前 4 条价格、前 3 条实时标记、关联合约
    计数，每条都带 metric_id/标签/值/单位/来源引用。
    """

    metrics: list[dict] = []
    if capacity:
        value = capacity.get("capacity_mwh_per_day") or capacity.get("capacity_mcm_d")
        metrics.append(
            {
                "metric_id": "capacity",
                "label": "Capacity",
                "value": value,
                "unit": "MWh/d" if capacity.get("capacity_mwh_per_day") else "mcm/d",
                "source_reference": capacity.get("source_reference"),
            }
        )
    if capacity_usage:
        metrics.extend(
            [
                {
                    "metric_id": "capacity_used",
                    "label": "Capacity in use",
                    "value": capacity_usage.get("used"),
                    "unit": capacity_usage.get("unit"),
                    "source_reference": capacity_usage.get("source_reference"),
                },
                {
                    "metric_id": "capacity_usage_pct",
                    "label": "Capacity utilization",
                    "value": capacity_usage.get("usage_pct"),
                    "unit": "%",
                    "source_reference": capacity_usage.get("source_reference"),
                },
            ]
        )
    for index, price in enumerate(prices[:4]):
        metrics.append(
            {
                "metric_id": f"price_{index}",
                "label": (
                    f"{price.get('market_venue', price.get('source_system', 'Price'))} "
                    f"{price.get('product', '')}"
                ).strip(),
                "value": price.get("price"),
                "unit": price.get("unit") or price.get("currency"),
                "source_reference": price.get("source_reference"),
            }
        )
    for index, mark in enumerate(live_marks[:3]):
        metrics.append(
            {
                "metric_id": f"live_mark_{index}",
                "label": f"{mark.get('venue', 'Live mark')} {mark.get('product', '')}".strip(),
                "value": (
                    mark.get("last_gbp_mwh")
                    or mark.get("bid_gbp_mwh")
                    or mark.get("ask_gbp_mwh")
                ),
                "unit": "GBP/MWh",
                "source_reference": mark.get("source_reference"),
            }
        )
    if contracts:
        metrics.append(
            {
                "metric_id": "linked_contracts",
                "label": "Linked contracts",
                "value": len(contracts),
                "unit": "count",
                "source_reference": "runtime-postgresql" if contracts else None,
            }
        )
    return metrics


def _context_data_quality(
    snapshot: AnalysisSnapshot,
    prices: list[dict],
    live_marks: list[dict],
    capacity: dict | None,
    capacity_usage: dict | None,
    matched_entities: list[dict],
) -> dict:
    """Summarize snapshot data quality for the context payload.

    数据质量摘要：快照来源与是否运行库、各集合观测数、匹配实体数、
    快照告警数——用于 UI 判断上下文可信度。
    """

    return {
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_source": snapshot.source,
        "runtime_db": snapshot.source == "runtime-postgresql",
        "market_observation_count": len(prices),
        "live_mark_count": len(live_marks),
        "has_capacity": capacity is not None,
        "has_capacity_usage": capacity_usage is not None,
        "matched_entity_count": len(matched_entities),
        "warning_count": len(snapshot.warnings),
    }


def _context_sections(
    *,
    entity_summary: dict,
    capacity: dict | None,
    capacity_usage: dict | None,
    metrics: list[dict],
    prices: list[dict],
    live_marks: list[dict],
    routes: list[dict],
    contracts: list[dict],
    data_quality: dict,
    warnings: list[str],
) -> list[dict]:
    """Build structured display sections (overview/capacity/prices/routes/...).

    展示章节组装：每个章节携带 items/metrics/warnings 子集，按 metric_id
    前缀与告警编码分流，供前端分区渲染。
    """

    return [
        {
            "section_id": "overview",
            "title": "Overview",
            "items": [entity_summary],
            "warnings": [],
        },
        {
            "section_id": "capacity",
            "title": "Capacity and utilization",
            "items": [item for item in [capacity, capacity_usage] if item],
            "metrics": [
                metric
                for metric in metrics
                if str(metric.get("metric_id", "")).startswith("capacity")
            ],
            "warnings": [
                warning
                for warning in warnings
                if warning in {"CAPACITY_CONTEXT_MISSING", "CAPACITY_USAGE_CONTEXT_MISSING"}
            ],
        },
        {
            "section_id": "prices",
            "title": "Prices and live marks",
            "items": [*prices, *live_marks],
            "metrics": [
                metric
                for metric in metrics
                if str(metric.get("metric_id", "")).startswith(("price", "live_mark"))
            ],
            "warnings": [warning for warning in warnings if warning == "PRICE_CONTEXT_MISSING"],
        },
        {
            "section_id": "routes",
            "title": "Route options",
            "items": routes,
            "warnings": [],
        },
        {
            "section_id": "contracts",
            "title": "Linked contracts",
            "items": contracts,
            "metrics": [
                metric for metric in metrics if metric.get("metric_id") == "linked_contracts"
            ],
            "warnings": [],
        },
        {
            "section_id": "data_quality",
            "title": "Data quality",
            "items": [data_quality],
            "warnings": _unique(warnings),
        },
    ]
