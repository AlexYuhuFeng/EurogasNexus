"""Typed concept definitions — the L1 declarative ontology.

Each concept is a frozen record with a stable id, bilingual definition, and a
tuple of typed slots. Slot types reference the controlled vocabulary enums or
built-in types, so a concept's shape is machine-checkable rather than prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from eurogas_nexus.domain.ontology.vocabulary import (
    CapacityProduct,
    CapacityScope,
    Currency,
    DeliveryMode,
    EdgeType,
    FacilityType,
    Firmness,
    FlowKind,
    MarketHub,
    NodeType,
    PriceType,
    ProductKind,
    ProductTenor,
    StrategyRunMode,
    TariffDirection,
)


@dataclass(frozen=True)
class Slot:
    """A typed attribute of a concept."""

    name: str
    type: Any  # a built-in type, enum class, or nested concept id (str)
    cardinality: str = "1"  # "1", "0..1", "0..n"


@dataclass(frozen=True)
class Concept:
    """A typed concept in the European natural-gas ontology."""

    concept_id: str
    name: str
    definition_en: str
    definition_zh_cn: str
    slots: tuple[Slot, ...] = ()
    supertype: str | None = None


CONCEPTS: tuple[Concept, ...] = (
    Concept(
        "UpstreamResourceContract",
        "Upstream Resource Contract",
        "A contract sourcing physical gas, virtual hub position, LNG offtake, or screen purchase.",
        "获取物理气、虚拟枢纽头寸、LNG 上游或屏幕采购的上游资源合同。",
        (
            Slot("delivery_point", str),
            Slot("gas_year", str),
            Slot("available_quantity_mwh_per_day", float),
            Slot("all_in_cost_gbp_mwh", float),
            Slot("settlement_frequency", str),
            Slot("delivery_mode", DeliveryMode, "0..1"),
        ),
    ),
    Concept(
        "ResourcePool",
        "Resource Pool",
        "The aggregation of available upstream resources that is the optimization input.",
        "所有可用上游资源汇聚成的组合，是优化的输入。",
        (
            Slot("resources", "UpstreamResourceContract", "0..n"),
            Slot("total_quantity_mwh_per_day", float),
        ),
    ),
    Concept(
        "VirtualHub",
        "Virtual Trading Hub",
        "A notional trading point inside a market area carrying that area's balancing price.",
        "市场区内的记账式交易点，承载该区的平衡价格。",
        (
            Slot("hub", MarketHub),
            Slot("market_area", "MarketArea"),
        ),
    ),
    Concept(
        "MarketArea",
        "Market Area / Balancing Zone",
        "The geographic and settlement region whose net flows settle at one virtual hub.",
        "净流量归结到单一虚拟枢纽结算的地理与结算区域。",
        (
            Slot("country", str),
            Slot("hub", MarketHub),
            Slot("nodes", "ReferenceNode", "0..n"),
        ),
    ),
    Concept(
        "ReferenceNode",
        "Reference Node",
        "A topological anchor: hub, interconnection, LNG terminal, storage, or point.",
        "拓扑锚点：枢纽、互联点、LNG 终端、储气库或点位。",
        (
            Slot("node_type", NodeType),
            Slot("country", str),
            Slot("lat", float),
            Slot("lon", float),
        ),
    ),
    Concept(
        "ReferenceEdge",
        "Reference Edge",
        "A directional connection between two reference nodes.",
        "两个参考节点之间的有向连接。",
        (
            Slot("from_node", "ReferenceNode"),
            Slot("to_node", "ReferenceNode"),
            Slot("edge_type", EdgeType),
        ),
    ),
    Concept(
        "ReferenceFacility",
        "Reference Facility",
        "A physical/commercial facility on the network (LNG terminal, storage, ...).",
        "网络上的物理/商业设施（LNG 接收站、储气库等）。",
        (
            Slot("facility_type", FacilityType),
            Slot("country", str),
        ),
    ),
    Concept(
        "FlowObservation",
        "Flow Observation",
        "A physical flow at a point, tagged with its nature (actual/nomination/...).",
        "某点的物理流量，并标记其性质（实际/提名/分配/预测）。",
        (
            Slot("point", "ReferenceNode"),
            Slot("kind", FlowKind),
            Slot("flow_mcm_d", float),
        ),
    ),
    Concept(
        "InterconnectionPoint",
        "Interconnection Point",
        "A point linking two market areas where cross-border capacity is measured.",
        "连接两个市场区、计量跨境容量的点。",
        (
            Slot("node", "ReferenceNode"),
            Slot("adjacent_zone_a", "MarketArea"),
            Slot("adjacent_zone_b", "MarketArea"),
        ),
    ),
    Concept(
        "CapacityProfile",
        "Capacity Profile",
        "A quantity of directional capacity valid over a time interval.",
        "在有效区间内可用的方向性容量数量。",
        (
            Slot("direction", TariffDirection),
            Slot("firmness", Firmness),
            Slot("product", CapacityProduct),
            Slot("scope", CapacityScope),
            Slot("quantity_mwh_per_day", float),
            Slot("valid_from", datetime),
            Slot("valid_to", datetime),
        ),
    ),
    Concept(
        "TsoTariff",
        "TSO Tariff",
        "A tariff charged by a TSO for capacity or commodity at a point and direction.",
        "TSO 在某点、某方向对容量或商品收取的费率。",
        (
            Slot("point", "ReferenceNode"),
            Slot("direction", TariffDirection),
            Slot("charge_type", str),  # "capacity" | "commodity"
            Slot("value", float),
            Slot("currency", Currency),
        ),
    ),
    Concept(
        "CompanyTsoAccess",
        "Company TSO Access",
        "The company's entitlement to use a specific TSO / point.",
        "公司对特定 TSO/点的准入权利。",
        (
            Slot("tso", str),
            Slot("point", "ReferenceNode", "0..1"),
        ),
    ),
    Concept(
        "RouteCandidate",
        "Route Candidate",
        "A feasible route/sale-market option with cost, capacity, and access inputs.",
        "具备成本、容量与准入输入的可行路线/销售选项。",
        (
            Slot("source_point", "ReferenceNode"),
            Slot("destination_market", MarketHub, "0..1"),
            Slot("required_tso_access", str, "0..n"),
        ),
    ),
    Concept(
        "MarketObservation",
        "Market Observation",
        "An assessment, index, settlement, or derived price (not an executable mark).",
        "评估、指数、结算或衍生价格（非可成交 mark）。",
        (
            Slot("hub", MarketHub),
            Slot("product_tenor", ProductTenor),
            Slot("product_kind", ProductKind),
            Slot("price_type", PriceType),
            Slot("price", float),
            Slot("currency", Currency),
        ),
    ),
    Concept(
        "LiveMarketMark",
        "Live Market Mark",
        "An executable screen mark from ICE OCM, EEX, Trayport, or a broker.",
        "来自 ICE OCM、EEX、Trayport 或经纪商的可成交屏幕 mark。",
        (
            Slot("venue", str),
            Slot("hub", MarketHub),
            Slot("product_tenor", ProductTenor),
            Slot("bid_gbp_mwh", float, "0..1"),
            Slot("ask_gbp_mwh", float, "0..1"),
            Slot("last_gbp_mwh", float, "0..1"),
        ),
    ),
    Concept(
        "MarketQuote",
        "Market Quote",
        "A normalized L1 quote (bid/ask/size) driving intraday opportunity scans.",
        "驱动日内机会扫描的规范化 L1 报价（bid/ask/量）。",
        (
            Slot("bid", float, "0..1"),
            Slot("ask", float, "0..1"),
            Slot("size_mwh", float, "0..1"),
        ),
    ),
    Concept(
        "FxObservation",
        "FX Observation",
        "A reference FX rate used for cross-currency conversion.",
        "用于跨币种换算的参考汇率。",
        (
            Slot("pair", str),
            Slot("rate", float),
            Slot("value_date", datetime),
        ),
    ),
    Concept(
        "LngRegasScenario",
        "LNG Regas Scenario",
        "An LNG cargo regasification and delivery option.",
        "LNG 船货再气化与交付选项。",
        (
            Slot("terminal", "ReferenceFacility"),
            Slot("cargo_size_mwh", float),
            Slot("delivery_mode", DeliveryMode),
        ),
    ),
    Concept(
        "StorageFacility",
        "Storage Facility",
        "An underground storage with injection/withdrawal capability.",
        "具备注采能力的地下储气库。",
        (
            Slot("facility", "ReferenceFacility"),
            Slot("injection_mwh_per_day", float, "0..1"),
            Slot("withdrawal_mwh_per_day", float, "0..1"),
        ),
    ),
    Concept(
        "Nomination",
        "Nomination",
        "A scheduled flow instruction submitted to a TSO (assessment only here).",
        "提交给 TSO 的流量计划（本域仅评估，不提交）。",
        (
            Slot("point", "ReferenceNode"),
            Slot("quantity_mwh_per_day", float),
            Slot("tolerance_pct", float, "0..1"),
        ),
    ),
    Concept(
        "StrategyDefinition",
        "Strategy Definition",
        "A configured paper strategy with components and risk controls.",
        "带有组件与风控的已配置纸面策略。",
        (
            Slot("components", str, "0..n"),
            Slot("risk_control", str, "0..1"),
        ),
    ),
    Concept(
        "StrategyRun",
        "Strategy Run",
        "A persisted backtest, shadow-run, or live-monitor evaluation snapshot.",
        "已持久化的 backtest / shadow-run / live-monitor 评估快照。",
        (
            Slot("strategy", "StrategyDefinition"),
            Slot("mode", StrategyRunMode),
            Slot("paper_pnl_gbp", float),
            Slot("status", str),
        ),
    ),
    Concept(
        "StrategyAllocationTarget",
        "Strategy Allocation Target",
        "A paper allocation target produced by a strategy run.",
        "策略运行产生的纸面分配目标。",
        (
            Slot("market_bucket", str),
            Slot("target_allocation_pct", float),
            Slot("target_quantity_mwh_per_day", float),
        ),
    ),
    Concept(
        "EntitlementDecision",
        "Entitlement Decision",
        "A fail-closed decision on whether commercial data may be used or exported.",
        "关于商业数据是否可用/可导出的 fail-closed 决策。",
        (
            Slot("scope", str),
            Slot("allowed", bool),
            Slot("reason", str, "0..1"),
        ),
    ),
    Concept(
        "WeatherObservation",
        "Weather Observation",
        "HDD/CDD weather-derived demand signal.",
        "HDD/CDD 由天气驱动的需求信号。",
        (
            Slot("kind", str),  # "HDD" | "CDD"
            Slot("value", float),
            Slot("observed_at", datetime),
        ),
    ),
    Concept(
        "GlossaryTerm",
        "Glossary Term",
        "A human-readable bilingual annotation; not the correctness backbone.",
        "人读的双语注释，不是正确性骨干。",
        (
            Slot("term", str),
            Slot("category", str),
            Slot("definition_en", str),
            Slot("definition_zh_cn", str),
        ),
    ),
    Concept(
        "GeneratedReport",
        "Generated Report",
        "A persisted analysis or portfolio report citing source snapshots.",
        "引用来源快照的已持久化分析或组合报告。",
        (
            Slot("report_id", str),
            Slot("title", str),
        ),
    ),
)
