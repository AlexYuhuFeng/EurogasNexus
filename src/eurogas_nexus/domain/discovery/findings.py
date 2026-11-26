"""Typed findings, the relevance table per job function, ranking and template phrasing.

A finding is computed elsewhere (an opportunity evaluator, a limit calculation); here it is
only ranked and phrased. The relevance table and the first sentences follow
``docs/product/ROLE_FIRST_REDESIGN.md`` section 9.1. The template sentence is always
available; a model may rephrase it only from the same facts and evidence (not done here).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.valuation.quality import InputClass

#: Audiences the relevance table knows; a job function maps to one of them.
AUDIENCES = ("trader", "risk", "operations", "analyst", "finance", "compliance", "management")

#: Job function (``security.capabilities.FunctionalAssignment``) -> audience.
FUNCTION_AUDIENCE: dict[str, str] = {
    "TRADER": "trader",
    "ORIGINATOR": "trader",
    "RISK_MANAGER": "risk",
    "OPERATIONS": "operations",
    "HQ_BUSINESS_ANALYST": "analyst",
    "QUANT_RESEARCHER": "analyst",
    "FINANCE_SETTLEMENT": "finance",
    "LEGAL_COMPLIANCE": "compliance",
    "MANAGEMENT": "management",
    "REVIEWER_MANAGEMENT": "management",
}

#: kind -> audience -> weight (0..1). A kind absent for an audience ranks at 0.1.
RELEVANCE: dict[str, dict[str, float]] = {
    # The market lane (no position): first for the people who trade it (an originator is in
    # the trader audience, FUNCTION_AUDIENCE); risk does not see it by default (weight 0 is
    # "hidden", not "last").
    "market.locational": {"trader": 1.0, "management": 0.3, "risk": 0.0},
    "market.prompt_arbitrage": {"trader": 1.0, "management": 0.3, "risk": 0.0},
    "market.time_spread": {"trader": 0.9, "management": 0.3, "risk": 0.0},
    "opportunity.locational": {"trader": 1.0, "management": 0.5, "risk": 0.2},
    "opportunity.unused_capacity": {"trader": 1.0, "operations": 0.5, "management": 0.5},
    "opportunity.time_spread": {"trader": 0.9, "management": 0.4},
    "opportunity.reroute": {"trader": 0.9, "operations": 0.4, "management": 0.4},
    "opportunity.sell_down": {"trader": 0.9, "operations": 0.9},
    "opportunity.event_exposure": {
        "operations": 1.0,
        "trader": 0.9,
        "risk": 0.8,
        "finance": 0.6,
        "management": 0.8,
    },
    "opportunity.hedge_gap": {"risk": 1.0, "compliance": 0.8, "trader": 0.6, "management": 0.7},
    "credit.breach": {
        "risk": 1.0,
        "compliance": 0.9,
        "management": 0.9,
        "finance": 0.8,
        "trader": 0.3,
    },
    "credit.projected": {"risk": 0.95, "finance": 0.7, "management": 0.7, "trader": 0.2},
    # A tracked strategy (paper) whose signal changed: the owner's own research.
    "strategy.signal": {"trader": 0.9, "analyst": 0.9, "risk": 0.3, "management": 0.2},
    "strategy.close": {"trader": 0.8, "analyst": 0.8, "risk": 0.3, "management": 0.2},
    "mandate.breach": {"compliance": 1.0, "risk": 0.9, "management": 0.8, "trader": 0.5},
}

#: Severity: 3 obligation or breach, 2 actionable or projected, 1 watch.
SEVERITY_WORD = {3: "must act", 2: "could act", 1: "watch"}


@dataclass(frozen=True)
class Finding:
    """One thing the data says, with its evidence and where to act on it."""

    finding_id: str
    kind: str
    severity: int
    facts: Mapping[str, str]
    input_class: InputClass
    simulated: bool
    value: Decimal | None = None
    value_unit: str = ""
    size: Decimal = Decimal(0)
    evidence: tuple[Mapping[str, Any], ...] = ()
    book_ids: tuple[str, ...] = ()
    link: Mapping[str, str] = field(default_factory=dict)
    due_utc: datetime | None = None
    method: str = ""


def audience_of(function: str | None) -> str:
    """The audience of a job function (``management`` when unknown)."""

    return FUNCTION_AUDIENCE.get(str(function or "").upper(), "management")


def weight(kind: str, audience: str) -> float:
    """How much a kind matters to an audience."""

    return RELEVANCE.get(kind, {}).get(audience, 0.1)


def rank(findings: Iterable[Finding], audience: str) -> list[Finding]:
    """Most relevant first: weight x severity, then size, then the earliest due."""

    far = datetime.max
    return sorted(
        # A weight of zero hides the kind from the audience (the market lane for risk).
        (item for item in findings if RELEVANCE.get(item.kind, {}).get(audience, 1.0) > 0),
        key=lambda item: (
            -(weight(item.kind, audience) * item.severity),
            -abs(item.size),
            (item.due_utc.replace(tzinfo=None) if item.due_utc else far),
            item.finding_id,
        ),
    )


# ------------------------------------------------------------------------- templates

_QUALIFIER = {
    "en": {
        InputClass.SIMULATED: " (on simulated prices)",
        InputClass.INDICATIVE: " (on indicative marks)",
        InputClass.FIRM_MARK: " (on the firm's marks)",
        InputClass.ASSUMPTION: " (on the firm's assumptions)",
    },
    "zh": {
        InputClass.SIMULATED: "（基于模拟价格）",
        InputClass.INDICATIVE: "（基于参考价格）",
        InputClass.FIRM_MARK: "（基于公司自定价格）",
        InputClass.ASSUMPTION: "（基于公司假设）",
    },
}

#: (kind, audience or "*") -> {language: template}. Fields come from ``Finding.facts``.
TEMPLATES: dict[tuple[str, str], dict[str, str]] = {
    ("strategy.close", "*"): {
        "en": "{name}: the rule closed its paper position; spread bid {bid} / offer {offer} "
        "{unit}; valid until {expires}. Not an instruction{q}.",
        "zh": "{name}：规则已平掉纸面头寸；价差买价 {bid} / 卖价 {offer} {unit}；有效至 {expires}。"
        "并非交易指令{q}。",
    },
    ("strategy.signal", "*"): {
        "en": "{name}: paper signal {signal_en} at {entry}; spread bid {bid} / offer {offer} "
        "{unit}, edge after crossing {edge}; valid until {expires}. Not an instruction{q}.",
        "zh": "{name}：纸面信号{signal_zh}，价位 {entry}；价差买价 {bid} / 卖价 {offer} {unit}，"
        "扣除买卖价差后优势 {edge}；有效至 {expires}。并非交易指令{q}。",
    },
    ("credit.breach", "*"): {
        "en": "{counterparty} is over its credit line: exposure {exposure} against a limit "
        "of {limit}{q}.",
        "zh": "{counterparty} 超出信用额度：敞口 {exposure}，额度 {limit}{q}。",
    },
    ("credit.breach", "finance"): {
        "en": "Credit exposure to {counterparty} is {exposure}, above the {limit} line{q}.",
        "zh": "对 {counterparty} 的信用敞口为 {exposure}，高于 {limit} 的额度{q}。",
    },
    ("credit.projected", "*"): {
        "en": "{counterparty} reaches its {limit} credit line if {hub} moves {move_pct} "
        "({move_price}); at {shock} the line is crossed in {tenor}{q}.",
        "zh": "若 {hub} 变动 {move_pct}（{move_price}），{counterparty} 将触及 {limit} 的信用"
        "额度；在 {shock} 情形下于 {tenor} 超限{q}。",
    },
    ("mandate.breach", "*"): {
        "en": "{mandate} is outside its mandate: {detail}.",
        "zh": "{mandate} 超出授权：{detail}。",
    },
    # Opportunity claims are rendered in English by the claim templates; the Chinese line is
    # built from the same structured figures.
    ("opportunity", "trader"): {
        "en": "{claim}",
        "zh": "{type_label}（{period}）：{headline}，金额 {value}{q}。",
    },
    ("opportunity", "*"): {
        "en": "{type_label}: {claim}",
        "zh": "{type_label}（{period}）：{headline}，金额 {value}{q}。",
    },
    ("opportunity.event_exposure", "operations"): {
        "en": "Supply cut: {claim}",
        "zh": "供应中断（{period}）：{headline}，补足成本 {value}{q}。",
    },
    ("opportunity.event_exposure", "risk"): {
        "en": "Exposure to an outage: {claim}",
        "zh": "停运敞口（{period}）：{headline}，补足成本 {value}{q}。",
    },
    ("opportunity.hedge_gap", "*"): {
        "en": "{type_label}: {claim}",
        "zh": "对冲比例超出批准区间（{period}）：缺口 {headline}{q}。",
    },
    ("opportunity.hedge_gap", "risk"): {
        "en": "Hedge outside its approved band: {claim}",
        "zh": "对冲比例超出批准区间（{period}）：缺口 {headline}{q}。",
    },
}

TYPE_LABEL = {
    "en": {
        "locational": "Location spread",
        "unused_capacity": "Held capacity",
        "time_spread": "Storage spread",
        "reroute": "Re-route",
        "sell_down": "Open balance",
        "hedge_gap": "Hedge band",
        "event_exposure": "Outage exposure",
    },
    "zh": {
        "locational": "地点价差",
        "unused_capacity": "已持有容量",
        "time_spread": "储气价差",
        "reroute": "改道",
        "sell_down": "未平衡头寸",
        "hedge_gap": "对冲区间",
        "event_exposure": "停运敞口",
    },
}


def phrase(finding: Finding, audience: str, language: str = "en") -> str:
    """The first sentence for one audience, in ``en`` or ``zh``, from the finding's facts."""

    lang = "zh" if str(language).lower().startswith("zh") else "en"
    family = finding.kind.split(".")[0]
    template = None
    for key in ((finding.kind, audience), (finding.kind, "*"), (family, audience), (family, "*")):
        if key in TEMPLATES:
            template = TEMPLATES[key][lang]
            break
    if template is None:
        template = "{claim}"
    facts = dict(finding.facts)
    facts.setdefault("q", _QUALIFIER[lang].get(finding.input_class, ""))
    kind = finding.kind.split(".", 1)[-1]
    facts.setdefault("type_label", TYPE_LABEL[lang].get(kind, kind))
    return template.format(**facts)
