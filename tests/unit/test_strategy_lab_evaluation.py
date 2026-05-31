"""Strategy-lab evaluation tests."""

from __future__ import annotations

from datetime import UTC, datetime

from eurogas_nexus.domain.strategy_lab.evaluation import (
    StrategyComponent,
    StrategyComponentType,
    StrategyLabScenario,
    StrategyPriceObservation,
    StrategyResourceContext,
    StrategyRiskControl,
    StrategyRunMode,
    evaluate_strategy_lab,
)


def _obs(price_name: str, price: float, hour: int, minute: int = 0) -> StrategyPriceObservation:
    return StrategyPriceObservation(
        observation_id=f"{price_name}-{hour}-{minute}",
        source_system="operator-fixture",
        venue="ICE OCM" if price_name == "ICE_OCM" else "price-assessment",
        hub="NBP",
        product="within-day" if price_name == "ICE_OCM" else "day-ahead",
        price_name=price_name,
        price_gbp_mwh=price,
        observed_at_utc=datetime(2026, 1, 15, hour, minute, tzinfo=UTC),
        delivery_start_utc=datetime(2026, 1, 16, tzinfo=UTC),
        delivery_end_utc=datetime(2026, 1, 17, tzinfo=UTC),
        bar_minutes=5,
        source_reference=f"fixture:{price_name}",
    )


def _resource(**kwargs) -> StrategyResourceContext:
    base = {
        "resource_id": "easington-year",
        "resource_name": "Easington gas year contract",
        "available_quantity_mwh_per_day": 10000,
        "all_in_cost_gbp_mwh": 24.0,
        "booked_entry_capacity_mwh_per_day": 10000,
        "required_tso_access": ["National Gas NTS"],
        "company_accessible_tsos": ["National Gas NTS"],
    }
    base.update(kwargs)
    return StrategyResourceContext(**base)


def _scenario(**kwargs) -> StrategyLabScenario:
    base = {
        "strategy_id": "sap-icis-ocm",
        "strategy_name": "SAP and ICIS day-ahead versus ICE OCM",
        "run_mode": StrategyRunMode.SHADOW_RUN,
        "resource_contexts": [_resource()],
        "price_observations": [
            _obs("SAP", 27.0, 16, 0),
            _obs("ICIS_HEREN_DAY_AHEAD", 27.2, 16, 30),
            _obs("ICE_OCM", 29.0, 15, 5),
            _obs("ICE_OCM", 29.4, 16, 45),
            _obs("ICE_OCM", 25.0, 12, 0),
        ],
        "components": [
            StrategyComponent(
                component_id="ocm-vs-da-1500-1700",
                component_type=StrategyComponentType.OCM_VS_DAY_AHEAD,
                time_window_start="15:00",
                time_window_end="17:00",
                target_bar_minutes=5,
                positive_spread_threshold_gbp_mwh=0.2,
            )
        ],
        "risk_control": StrategyRiskControl(
            max_ocm_allocation_pct=70,
            min_day_ahead_allocation_pct=20,
            max_single_market_volume_mwh_per_day=6000,
        ),
    }
    base.update(kwargs)
    return StrategyLabScenario(**base)


def test_strategy_lab_prefers_ocm_when_intraday_outperforms_day_ahead_window() -> None:
    result = evaluate_strategy_lab(_scenario())

    assert result.status == "SUCCESS"
    assert result.day_ahead_average_gbp_mwh == 27.1
    assert result.intraday_average_gbp_mwh == 29.2
    assert result.intraday_vs_day_ahead_spread_gbp_mwh == 2.1
    assert result.candidate_action_for_review == "REVIEW_HIGHER_OCM_ALLOCATION"
    ocm_target = next(
        target for target in result.allocation_targets if target.market_bucket == "ICE_OCM"
    )
    assert ocm_target.target_quantity_mwh_per_day == 6000
    assert "MAX_SINGLE_MARKET_VOLUME_CLAMP_REQUIRED" in result.warnings
    assert result.research_only is True
    assert result.human_review_required is True


def test_strategy_lab_blocks_when_required_tso_access_is_missing() -> None:
    result = evaluate_strategy_lab(
        _scenario(
            resource_contexts=[
                _resource(company_accessible_tsos=["Other TSO"]),
            ]
        )
    )

    assert result.status == "PARTIAL"
    assert "TSO_ACCESS_MISSING:easington-year:National Gas NTS" in result.missing_inputs
    assert result.candidate_action_for_review == "REVIEW_HIGHER_OCM_ALLOCATION"


def test_strategy_lab_blocks_shadow_run_when_stop_loss_is_triggered() -> None:
    result = evaluate_strategy_lab(
        _scenario(
            risk_control=StrategyRiskControl(stop_shadow_run_loss_gbp=1000),
            existing_shadow_pnl_gbp=-1500,
        )
    )

    assert result.status == "BLOCKED"
    assert "SHADOW_RUN_STOP_LOSS_TRIGGERED" in result.warnings
    assert result.candidate_action_for_review == "REVIEW_BLOCKED_STRATEGY"


def test_strategy_lab_blocks_without_prices_or_resources() -> None:
    result = evaluate_strategy_lab(
        _scenario(
            resource_contexts=[],
            price_observations=[],
        )
    )

    assert result.status == "BLOCKED"
    assert "RESOURCE_CONTEXTS_MISSING" in result.missing_inputs
    assert "PRICE_OBSERVATIONS_MISSING" in result.missing_inputs
    assert "DAY_AHEAD_REFERENCE_PRICE_MISSING" in result.missing_inputs
    assert "INTRADAY_REFERENCE_PRICE_MISSING" in result.missing_inputs
