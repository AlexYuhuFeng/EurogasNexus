"""SDK ↔ backend contract parity tests (drift prevention).

The unversioned /api contract is the product's public surface. These tests pin
the SDK DTOs to the backend payloads so a backend change without an SDK update
fails loudly instead of drifting silently.
"""

from __future__ import annotations

from eurogas_nexus_sdk.strategy_lab import (
    StrategyLabResult as SdkStrategyResult,
)
from eurogas_nexus_sdk.strategy_lab import (
    StrategyRunDTO,
    StrategySummaryDTO,
)

from eurogas_nexus.domain.strategy_lab.evaluation import (
    StrategyLabResult as DomainStrategyResult,
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


def test_sdk_optimization_route_dto_matches_backend_result() -> None:
    from dataclasses import fields

    from eurogas_nexus_sdk.optimization import RouteResultDTO

    from eurogas_nexus.optimization.models import RouteResult

    backend_keys = {item.name for item in fields(RouteResult)}
    sdk_fields = set(RouteResultDTO.model_fields)
    assert sdk_fields <= backend_keys, f"SDK drift: {sdk_fields - backend_keys}"


def test_sdk_optimization_pool_dto_matches_backend_result() -> None:
    from dataclasses import fields

    from eurogas_nexus_sdk.optimization import ResourcePoolResultDTO

    from eurogas_nexus.optimization.models import OptimizationResult

    backend_keys = {item.name for item in fields(OptimizationResult)}
    sdk_fields = set(ResourcePoolResultDTO.model_fields)
    assert sdk_fields <= backend_keys, f"SDK drift: {sdk_fields - backend_keys}"


def test_sdk_portfolio_network_dto_matches_backend_result() -> None:
    from dataclasses import fields

    from eurogas_nexus_sdk.optimization import PortfolioNetworkResultDTO

    from eurogas_nexus.domain.route_cost.portfolio_network import (
        PortfolioNetworkOptimizationResult,
    )

    backend_keys = {item.name for item in fields(PortfolioNetworkOptimizationResult)}
    sdk_fields = set(PortfolioNetworkResultDTO.model_fields)
    assert sdk_fields <= backend_keys, f"SDK drift: {sdk_fields - backend_keys}"
    assert backend_keys <= sdk_fields, f"SDK missing fields: {backend_keys - sdk_fields}"


def test_sdk_storage_nomination_dtos_match_backend_results() -> None:
    from dataclasses import fields

    from eurogas_nexus_sdk.optimization import (
        NominationWindowResultDTO,
        StorageDispatchResultDTO,
    )

    from eurogas_nexus.optimization.nomination import NominationScheduleResult
    from eurogas_nexus.optimization.storage import StorageDispatchResult

    storage_keys = {item.name for item in fields(StorageDispatchResult)}
    nomination_keys = {item.name for item in fields(NominationScheduleResult)}
    assert set(StorageDispatchResultDTO.model_fields) <= storage_keys
    assert set(NominationWindowResultDTO.model_fields) <= nomination_keys


def test_sdk_optimization_capacity_dto_matches_backend_result() -> None:
    from dataclasses import fields

    from eurogas_nexus_sdk.optimization import CapacityResultDTO

    from eurogas_nexus.optimization.models import CapacityBookingResult

    backend_keys = {item.name for item in fields(CapacityBookingResult)}
    sdk_fields = set(CapacityResultDTO.model_fields)
    assert sdk_fields <= backend_keys, f"SDK drift: {sdk_fields - backend_keys}"


def test_sdk_optimization_run_dto_matches_evidence_payload() -> None:
    from eurogas_nexus_sdk.optimization import OptimizationRunDTO

    # The evidence endpoint serializes the OptimizationRunRecord columns.
    record_columns = {
        "run_id",
        "optimization_type",
        "decision_context",
        "status",
        "input_snapshot",
        "output_snapshot",
        "source_refs",
        "warnings",
        "created_at_utc",
        "research_only",
        "human_review_required",
    }
    sdk_fields = set(OptimizationRunDTO.model_fields)
    assert sdk_fields <= record_columns, f"SDK drift: {sdk_fields - record_columns}"


def test_sdk_review_decision_dto_matches_repository_payload() -> None:
    from eurogas_nexus_sdk.review import ReviewDecisionDTO

    repository_keys = {
        "decision_id",
        "entity_type",
        "entity_id",
        "actor",
        "decision",
        "note",
        "created_at_utc",
    }
    sdk_fields = set(ReviewDecisionDTO.model_fields)
    assert sdk_fields <= repository_keys, f"SDK drift: {sdk_fields - repository_keys}"


def test_sdk_credential_provider_dto_matches_provider_status_payload() -> None:
    from eurogas_nexus_sdk.credentials import CredentialProviderDTO

    payload_keys = {
        "provider_id",
        "display_name",
        "credential_required",
        "default_model",
        "configured",
        "status",
        "label",
        "redacted_preview",
        "last_tested_at_utc",
        "last_test_status",
    }
    sdk_fields = set(CredentialProviderDTO.model_fields)
    assert sdk_fields <= payload_keys, f"SDK drift: {sdk_fields - payload_keys}"
