"""Action taxonomy — the first-class action vocabulary.

Every decision-support action is enumerable and, by product boundary, requires
human review. The forbidden set encodes the hard no-execution boundary.
Actions are classified into governance categories so approval/audit rules can
treat System, Analytical, Decision Candidate, and External actions
differently (audit: "数据导入、查询、分析、人工决策、外部执行混在一个 ActionKind").
"""

from __future__ import annotations

from enum import StrEnum

from eurogas_nexus.domain.ontology.vocabulary import ActionKindCategory


class ActionKind(StrEnum):
    """Allowed paper / decision-support actions (human review required)."""

    CAPTURE_RESOURCE_TERM = "capture_resource_term"
    REVIEW_RESOURCE_ASSUMPTION = "review_resource_assumption"
    IMPORT_SCREEN_OBSERVATION = "import_screen_observation"
    MARK_AT_HUB = "mark_at_hub"
    TRANSFER_BETWEEN_ZONES = "transfer_between_zones"
    MATERIALIZE_TOPOLOGY = "materialize_topology"
    QUERY_ROUTE = "query_route"
    ALLOCATE_CAPACITY = "allocate_capacity"
    VALIDATE_ACCESS = "validate_access"
    ESTIMATE_ROUTE_COST = "estimate_route_cost"
    OBSERVE_PRICE = "observe_price"
    MARK_TO_MARKET = "mark_to_market"
    EVALUATE_SPREAD = "evaluate_spread"
    ASSESS_REGAS_READINESS = "assess_regas_readiness"
    ASSESS_STORAGE_DISPATCH = "assess_storage_dispatch"
    ASSESS_NOMINATION_WINDOW = "assess_nomination_window"
    MONITOR_IMBALANCE = "monitor_imbalance"
    RECONCILE_PNL = "reconcile_pnl"
    COMPUTE_CASH_FLOW = "compute_cash_flow"
    ENFORCE_ENTITLEMENT = "enforce_entitlement"
    AUDIT_ACTION = "audit_action"
    BACKTEST = "backtest"
    SHADOW_RUN = "shadow_run"
    LIVE_MONITOR = "live_monitor"
    REVIEW_STRATEGY_OUTPUT = "review_strategy_output"


class ForbiddenAction(StrEnum):
    """Actions Eurogas Nexus must never perform (hard product boundary)."""

    PLACE_ORDER = "place_order"
    ROUTE_ORDER = "route_order"
    AMEND_ORDER = "amend_order"
    CANCEL_ORDER = "cancel_order"
    TRADE_CAPTURE = "trade_capture"
    SUBMIT_NOMINATION = "submit_nomination"
    OFFICIAL_APPROVAL = "official_approval"
    AUTO_TRADE = "auto_trade"
    LEGAL_ADVICE = "legal_advice"
    ETRM_REPLACEMENT = "etrm_replacement"


ACTION_KIND_CATEGORIES: dict[ActionKind, ActionKindCategory] = {
    # System: import, topology materialization, governance plumbing.
    ActionKind.IMPORT_SCREEN_OBSERVATION: ActionKindCategory.SYSTEM,
    ActionKind.MATERIALIZE_TOPOLOGY: ActionKindCategory.SYSTEM,
    ActionKind.ENFORCE_ENTITLEMENT: ActionKindCategory.SYSTEM,
    ActionKind.AUDIT_ACTION: ActionKindCategory.SYSTEM,
    # Analytical: research outputs that change no state.
    ActionKind.QUERY_ROUTE: ActionKindCategory.ANALYTICAL,
    ActionKind.ESTIMATE_ROUTE_COST: ActionKindCategory.ANALYTICAL,
    ActionKind.OBSERVE_PRICE: ActionKindCategory.ANALYTICAL,
    ActionKind.MARK_TO_MARKET: ActionKindCategory.ANALYTICAL,
    ActionKind.EVALUATE_SPREAD: ActionKindCategory.ANALYTICAL,
    ActionKind.ASSESS_REGAS_READINESS: ActionKindCategory.ANALYTICAL,
    ActionKind.ASSESS_STORAGE_DISPATCH: ActionKindCategory.ANALYTICAL,
    ActionKind.ASSESS_NOMINATION_WINDOW: ActionKindCategory.ANALYTICAL,
    ActionKind.MONITOR_IMBALANCE: ActionKindCategory.ANALYTICAL,
    ActionKind.RECONCILE_PNL: ActionKindCategory.ANALYTICAL,
    ActionKind.COMPUTE_CASH_FLOW: ActionKindCategory.ANALYTICAL,
    ActionKind.BACKTEST: ActionKindCategory.ANALYTICAL,
    ActionKind.LIVE_MONITOR: ActionKindCategory.ANALYTICAL,
    # Decision candidate: outputs that require human review before use.
    ActionKind.CAPTURE_RESOURCE_TERM: ActionKindCategory.DECISION_CANDIDATE,
    ActionKind.REVIEW_RESOURCE_ASSUMPTION: ActionKindCategory.DECISION_CANDIDATE,
    ActionKind.MARK_AT_HUB: ActionKindCategory.DECISION_CANDIDATE,
    ActionKind.TRANSFER_BETWEEN_ZONES: ActionKindCategory.DECISION_CANDIDATE,
    ActionKind.ALLOCATE_CAPACITY: ActionKindCategory.DECISION_CANDIDATE,
    ActionKind.VALIDATE_ACCESS: ActionKindCategory.DECISION_CANDIDATE,
    ActionKind.SHADOW_RUN: ActionKindCategory.DECISION_CANDIDATE,
    ActionKind.REVIEW_STRATEGY_OUTPUT: ActionKindCategory.DECISION_CANDIDATE,
}

FORBIDDEN_ACTION_CATEGORY = ActionKindCategory.EXTERNAL_ACTION


def action_category(action: ActionKind | ForbiddenAction) -> ActionKindCategory:
    """Return the governance category for an action.

    返回动作的治理分类（审批/审计规则按分类差异化处理）。

    Forbidden actions are always EXTERNAL_ACTION (never performed); allowed
    actions must be classified explicitly so a missing classification fails
    closed as DECISION_CANDIDATE (human review required).

    Args:
        action: An allowed or forbidden action kind.

    Returns:
        The governance category; missing classifications default to
        DECISION_CANDIDATE (fail-closed toward human review).
    """

    if isinstance(action, ForbiddenAction):
        return FORBIDDEN_ACTION_CATEGORY
    # 未登记的动作按 DECISION_CANDIDATE 处理：宁严勿松，强制人工复核。
    return ACTION_KIND_CATEGORIES.get(action, ActionKindCategory.DECISION_CANDIDATE)
