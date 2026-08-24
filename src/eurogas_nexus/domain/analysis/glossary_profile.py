"""Glossary term -> context profile resolution (static rules + glossary rows).

术语上下文的"画像"解析：先从内置规则表（ICIS/NBP/TTF/OCM/容量）取基础
画像，再用快照中的术语表行与实体匹配增强键集合与描述，最后推断上下文
类型。规则表是静态数据，新增术语只需扩展 ``_glossary_context_profile``。
"""

from __future__ import annotations

from eurogas_nexus.domain.analysis._common import _unique
from eurogas_nexus.domain.analysis.contracts import AnalysisSnapshot
from eurogas_nexus.domain.analysis.glossary_entities import _matched_entities


def _resolved_glossary_context_profile(term: str, snapshot: AnalysisSnapshot) -> dict:
    """Resolve the full context profile for one term.

    解析术语的完整上下文画像：基础规则 + 术语表匹配 + 实体匹配，合并
    点/价/路由键集合、双语描述、来源与告警。

    Args:
        term: The queried term (raw casing).
        snapshot: Backend-data snapshot.

    Returns:
        A profile dict with ``context_type``, ``point_keys``, ``price_keys``,
        ``route_keys``, ``description_en``, ``description_zh_cn``,
        ``related_sources`` and ``warnings`` (plus base fields).
    """

    key = term.strip().lower()
    profile = _glossary_context_profile(key)
    glossary_rows = _matching_glossary_rows(term, snapshot)
    point_keys = _unique(
        [
            *profile["point_keys"],
            term,
            *_term_operational_keys(term),
            *[
                value
                for row in glossary_rows
                for value in [row.get("term"), *row.get("aliases", [])]
            ],
        ]
    )
    related_terms = _unique(
        [
            value
            for row in glossary_rows
            for value in [*row.get("related_terms", []), *row.get("source_refs", [])]
        ]
    )
    price_keys = _unique(
        [
            *profile["price_keys"],
            term,
            *_term_operational_keys(term),
            *related_terms,
        ]
    )
    route_keys = _unique([*profile["route_keys"], *point_keys, *related_terms])
    matched = _matched_entities(
        snapshot,
        point_keys=point_keys,
        price_keys=price_keys,
        route_keys=route_keys,
        contract_keys=[*point_keys, *route_keys],
    )
    context_type = _infer_context_type(profile["context_type"], term, glossary_rows, matched)
    description_en, description_zh_cn = _context_description(
        term,
        profile=profile,
        glossary_rows=glossary_rows,
        context_type=context_type,
    )
    warnings = list(profile["warnings"])
    if profile["context_type"] == "generic" and matched:
        # 通用术语但实体已匹配：撤回"映射不完整"告警（实体证据足够）。
        warnings = [warning for warning in warnings if warning != "TERM_CONTEXT_MAPPING_PARTIAL"]
    related_sources = _unique([*profile["related_sources"], *related_terms])
    return {
        **profile,
        "context_type": context_type,
        "point_keys": point_keys,
        "price_keys": price_keys,
        "route_keys": route_keys,
        "description_en": description_en,
        "description_zh_cn": description_zh_cn,
        "related_sources": related_sources,
        "warnings": warnings,
    }


def _matching_glossary_rows(term: str, snapshot: AnalysisSnapshot) -> list[dict]:
    """Return glossary rows matching the term (exact or substring, normalized).

    术语表匹配：按 term/term_id/aliases 归一化后精确或子串命中；
    子串匹配用于"nbp 入口点"这类组合术语。
    """

    key = term.strip().lower()
    matches: list[dict] = []
    for row in snapshot.glossary_terms:
        candidates = [
            row.get("term"),
            row.get("term_id"),
            *row.get("aliases", []),
        ]
        normalized = [str(value).strip().lower() for value in candidates if value]
        if key in normalized or any(candidate and candidate in key for candidate in normalized):
            matches.append(row)
    return matches


def _term_operational_keys(term: str) -> list[str]:
    """Derive operational search keys from a term (suffix strips + bigram).

    由术语派生操作键：去掉常见后缀（entry point、assessment 等）得到
    主干，并把连字符化的前两个词作为组合键，扩大匹配面。
    """

    key = term.strip()
    lower_key = key.lower()
    variants = [key]
    suffixes = (
        " entry point",
        " exit point",
        " beach terminal",
        " terminal",
        " assessment",
        " price",
    )
    for suffix in suffixes:
        if lower_key.endswith(suffix):
            variants.append(key[: -len(suffix)].strip())
    tokens = [token for token in key.replace("-", " ").split() if len(token) >= 3]
    if len(tokens) >= 2:
        variants.append(" ".join(tokens[:2]))
    return _unique([value for value in variants if value])


def _infer_context_type(
    base_context_type: str,
    term: str,
    glossary_rows: list[dict],
    matched_entities: list[dict],
) -> str:
    """Infer the context type when the base profile is generic.

    通用画像下按优先级推断：术语关键词（entry/exit point）→ 术语表
    分类（hub/venue/price）→ 实体类型与方向（容量/流量点、价格标记）。
    """

    if base_context_type != "generic":
        return base_context_type
    key = term.strip().lower()
    categories = {str(row.get("category", "")).lower() for row in glossary_rows}
    if "entry point" in key:
        return "entry_point"
    if "exit point" in key:
        return "exit_point"
    if "hub" in categories:
        return "hub"
    if "venue" in categories:
        return "venue"
    if "price" in categories:
        return "price_assessment"
    if any(
        entity["entity_type"] in {"capacity_point", "flow_point"}
        for entity in matched_entities
    ):
        directions = {str(entity.get("direction", "")).lower() for entity in matched_entities}
        if "entry" in directions:
            return "entry_point"
        if "exit" in directions:
            return "exit_point"
        return "capacity"
    if any(
        entity["entity_type"] in {"market_price", "live_market_mark"}
        for entity in matched_entities
    ):
        return "price_assessment"
    return base_context_type


def _context_description(
    term: str,
    *,
    profile: dict,
    glossary_rows: list[dict],
    context_type: str,
) -> tuple[str, str]:
    """Return the (en, zh) description for a term context.

    描述来源优先级：非通用画像用内置双语描述；通用画像优先取术语表
    定义；都没有则生成确定性兜底描述。
    """

    if profile["context_type"] != "generic":
        return profile["description_en"], profile["description_zh_cn"]
    if glossary_rows:
        row = glossary_rows[0]
        en = str(row.get("definition_en") or row.get("definition") or "").strip()
        zh = str(row.get("definition_zh_cn") or en).strip()
        if en:
            return en, zh
    en = (
        f"{term} is resolved from matching runtime records. Context type is "
        f"{context_type}; available capacity, usage, prices, live marks, routes, "
        "and contracts are shown when present in PostgreSQL."
    )
    zh = (
        f"{term} 由运行库中的匹配记录解析。上下文类型为 {context_type}；"
        "当 PostgreSQL 中存在容量、使用量、价格、实时标记、路线和合同记录时会一并展示。"
    )
    return en, zh


def _glossary_context_profile(key: str) -> dict:
    """Static context profile for known terms (ICIS/NBP/TTF/OCM/capacity).

    内置术语画像表：按关键词返回 context_type、点/价/路由键、双语描述、
    相关来源与告警。未知术语返回 generic 画像（带映射不完整告警）。
    """

    if "icis" in key or "heren" in key:
        return {
            "context_type": "price_assessment",
            "point_keys": ["nbp"],
            "price_keys": ["icis", "heren", "nbp", "day-ahead"],
            "route_keys": ["nbp", "iuk", "bbl"],
            "description_en": (
                "ICIS Heren is a licensed price-assessment reference. Eurogas Nexus "
                "can display and compare customer-licensed or operator-entered ICIS "
                "records against screen marks, but the repository must not contain "
                "raw licensed assessment data."
            ),
            "description_zh_cn": (
                "ICIS Heren 是需授权的价格评估来源。Eurogas Nexus 可以展示并比较客户授权"
                "或操作员录入的 ICIS 价格与屏幕价格，但代码仓库不得包含原始授权评估数据。"
            ),
            "related_sources": ["ICIS Heren", "licensed customer data", "operator-entered records"],
            "warnings": ["ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA"],
        }
    if key in {"nbp", "national balancing point"} or "national balancing point" in key:
        return {
            "context_type": "hub",
            "point_keys": ["nbp"],
            "price_keys": ["nbp", "ice ocm", "icis", "eex"],
            "route_keys": ["nbp", "iuk", "bbl"],
            "description_en": (
                "NBP is the UK virtual gas hub. Context links the hub to UK route "
                "options, screen marks, day-ahead assessments, and physical entry "
                "points that can monetize upstream resources."
            ),
            "description_zh_cn": (
                "NBP 是英国虚拟天然气交易枢纽。上下文会关联英国路线、屏幕价格、日前评估价"
                "以及可用于变现上游资源的物理入口点。"
            ),
            "related_sources": ["ICE OCM", "EEX", "ICIS Heren", "National Gas NTS"],
            "warnings": [],
        }
    if key in {"ttf", "title transfer facility"} or "title transfer facility" in key:
        return {
            "context_type": "hub",
            "point_keys": ["ttf"],
            "price_keys": ["ttf", "eex", "ice"],
            "route_keys": ["ttf", "the", "ncg"],
            "description_en": (
                "TTF is the Dutch virtual gas hub and a continental European benchmark. "
                "Context focuses on related marks, route candidates, and FX where "
                "available."
            ),
            "description_zh_cn": (
                "TTF 是荷兰虚拟天然气枢纽和欧洲大陆基准价。"
                "上下文重点展示相关价格、路线和可用汇率。"
            ),
            "related_sources": ["EEX", "ICE", "ECB"],
            "warnings": [],
        }
    if "ice ocm" in key or key == "ocm":
        return {
            "context_type": "venue",
            "point_keys": ["nbp"],
            "price_keys": ["ice ocm", "ocm", "nbp", "within-day"],
            "route_keys": ["nbp", "iuk", "bbl"],
            "description_en": (
                "ICE OCM is the UK within-day gas market. Context emphasizes bid, ask, "
                "last marks and the resource routes whose PnL can be marked against "
                "those executable screen prices."
            ),
            "description_zh_cn": (
                "ICE OCM 是英国日内天然气市场。上下文重点展示买价、卖价、"
                "最新价以及可按这些屏幕价盯市的资源路线。"
            ),
            "related_sources": ["ICE OCM", "National Gas NTS"],
            "warnings": [],
        }
    if "entry capacity" in key or "exit capacity" in key:
        direction = "entry" if "entry" in key else "exit"
        return {
            "context_type": "capacity",
            "point_keys": [direction],
            "price_keys": ["capacity", "tariff", "nts"],
            "route_keys": [direction, "national gas"],
            "description_en": (
                f"{direction.title()} capacity is the contractual or tariffed right "
                "to flow gas through a system point. Context shows matching capacity "
                "profiles, usage observations, tariffs or routes when present."
            ),
            "description_zh_cn": (
                f"{direction.title()} capacity 表示在系统点进行天然气流动所需的合同或收费容量权利。"
                "上下文会展示匹配的容量、使用量、费率或路线。"
            ),
            "related_sources": ["TSO tariff", "ENTSOG", "capacity profile"],
            "warnings": [],
        }
    return {
        "context_type": "generic",
        "point_keys": [key],
        "price_keys": [key],
        "route_keys": [key],
        "description_en": "No dedicated operational context mapping exists yet for this term.",
        "description_zh_cn": "该术语暂未配置专用运行上下文映射。",
        "related_sources": [],
        "warnings": ["TERM_CONTEXT_MAPPING_PARTIAL"],
    }
