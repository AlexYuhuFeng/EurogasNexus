"""Action taxonomy — the first-class action vocabulary.

Every decision-support action is enumerable and, by product boundary, requires
human review. The forbidden set encodes the hard no-execution boundary.
"""

from __future__ import annotations

from enum import StrEnum


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
