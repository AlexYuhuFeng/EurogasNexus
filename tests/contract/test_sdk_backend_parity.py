"""SDK ↔ backend contract parity tests (drift prevention).

The unversioned /api contract is the product's public surface. These tests pin
the SDK DTOs to the backend payloads so a backend change without an SDK update
fails loudly instead of drifting silently.
"""

from __future__ import annotations

from eurogas_nexus.domain.strategy_lab.evaluation import (
    StrategyLabResult as DomainStrategyResult,
)
from eurogas_nexus.sdk.strategy_lab import (
    StrategyLabResult as SdkStrategyResult,
)
from eurogas_nexus.sdk.strategy_lab import (
    StrategyRunDTO,
    StrategySummaryDTO,
)

# The strategy-run payload contract produced by
# `eurogas_nexus.db.repositories.strategy.strategy_run_payload`.
STRATEGY_RUN_PAYLOAD_KEYS = {
    "run_id",
    "strategy_id",
    "run_mode",
    "status",
    "started_at_utc",
    "finished_at_utc",
    "paper_pnl_gbp",
    "cumulative_pnl_gbp",
    "hit",
    "weighted_score",
    "allocation_targets",
    "missing_inputs",
    "warnings",
    "source_refs",
    "research_only",
    "human_review_required",
}

# The summary contract produced by
# `eurogas_nexus.db.repositories.strategy.strategy_summary`.
STRATEGY_SUMMARY_KEYS = {
    "strategy_id",
    "run_mode",
    "run_count",
    "total_paper_pnl_gbp",
    "cumulative_pnl_gbp",
    "hit_rate",
    "max_drawdown_gbp",
    "first_started_at_utc",
    "last_started_at_utc",
    "latest_status",
}


def test_sdk_strategy_result_fields_exist_in_backend_result() -> None:
    backend_fields = set(DomainStrategyResult.model_fields) | {"run_id"}
    sdk_fields = set(SdkStrategyResult.model_fields)
    assert sdk_fields <= backend_fields, f"SDK drift: {sdk_fields - backend_fields}"


def test_sdk_strategy_run_dto_matches_repository_payload() -> None:
    sdk_fields = set(StrategyRunDTO.model_fields)
    assert sdk_fields <= STRATEGY_RUN_PAYLOAD_KEYS, (
        f"SDK drift: {sdk_fields - STRATEGY_RUN_PAYLOAD_KEYS}"
    )


def test_sdk_strategy_summary_matches_summary_contract() -> None:
    sdk_fields = set(StrategySummaryDTO.model_fields)
    assert sdk_fields <= STRATEGY_SUMMARY_KEYS, (
        f"SDK drift: {sdk_fields - STRATEGY_SUMMARY_KEYS}"
    )


def test_sdk_strategy_summary_covers_all_summary_contract_keys() -> None:
    sdk_fields = set(StrategySummaryDTO.model_fields)
    assert STRATEGY_SUMMARY_KEYS <= sdk_fields, (
        f"SDK missing summary keys: {STRATEGY_SUMMARY_KEYS - sdk_fields}"
    )
