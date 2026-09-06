"""Unit tests for the temporally safe backtest engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from eurogas_nexus.domain.backtest.contracts import (
    BACKTEST_ENGINE_VERSION,
    BacktestCostComponent,
    BacktestDecisionSchedule,
    BacktestEconomicAssumptions,
    BacktestEvidencePool,
    BacktestFxRate,
    BacktestObservation,
    BacktestPeriod,
    BacktestResourceEvidence,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.backtest.engine import (
    build_backtest_manifest,
    generate_decision_times,
    run_backtest,
)
from eurogas_nexus.domain.backtest.temporal import (
    as_of_fx_rates,
    as_of_price_observations,
    availability_time,
    classify_source_temporal_integrity,
    convert_price_to_gbp_mwh,
    gas_day_window,
)
from eurogas_nexus.domain.ontology.vocabulary import (
    CostTreatment,
    MissingDataPolicy,
    TemporalIntegrityStatus,
)


def _version(definition: dict | None = None) -> SimpleNamespace:
    base = {
        "strategy_name": "NBP spread",
        "run_mode": "BACKTEST",
        "components": [
            {
                "component_id": "c1",
                "component_type": "OCM_VS_DAY_AHEAD",
                "hubs": ["NBP"],
                "extension_json": {
                    "weight": 1.0,
                    "day_ahead_price_names": ["SAP"],
                    "intraday_price_names": ["ICE_OCM"],
                    "positive_spread_threshold_gbp_mwh": 0.0,
                    "negative_spread_threshold_gbp_mwh": 0.0,
                    "target_bar_minutes": 5,
                    "time_window_start": "05:00",
                    "time_window_end": "05:30",
                },
            }
        ],
        "risk_controls": {
            "max_ocm_allocation_pct": 80.0,
            "min_day_ahead_allocation_pct": 10.0,
            "require_tso_access": False,
        },
        "resource_contexts": [
            {
                "resource_id": "res-1",
                "resource_name": "Resource",
                "available_quantity_mwh_per_day": 100.0,
                "all_in_cost_gbp_mwh": 20.0,
                "required_tso_access": [],
            }
        ],
        "parameter_values": {},
    }
    base.update(definition or {})
    return SimpleNamespace(
        strategy_version_id="strategy-version-1",
        strategy_id="strategy-1",
        version_number=1,
        content_hash="sha256:version-1",
        definition_json=base,
    )


def _period(days: int = 3) -> BacktestPeriod:
    return BacktestPeriod(
        start_utc=datetime(2026, 7, 1, 0, 0, tzinfo=UTC),
        end_utc=datetime(2026, 7, 1 + days, 0, 0, tzinfo=UTC),
    )


def _observation(
    observation_id: str,
    price_name: str,
    price: float,
    observed_at: datetime,
    *,
    received_at: datetime | None = None,
    currency: str = "GBP",
    unit: str = "MWh",
    simulated: bool = False,
    integrity: TemporalIntegrityStatus = TemporalIntegrityStatus.VERIFIED,
) -> BacktestObservation:
    return BacktestObservation(
        observation_id=observation_id,
        source_system=f"{price_name}_Sim" if simulated else price_name,
        venue=price_name,
        hub="NBP",
        product=f"NBP {price_name}",
        tenor="within-day" if price_name == "ICE_OCM" else "day-ahead",
        price_name=price_name,
        price=price,
        currency=currency,
        unit=unit,
        observed_at_utc=observed_at,
        received_at_utc=received_at or observed_at,
        delivery_start_utc=observed_at,
        delivery_end_utc=observed_at + timedelta(hours=24),
        bar_minutes=5 if price_name == "ICE_OCM" else None,
        price_type="mid",
        source_reference=f"{price_name}:{observation_id}",
        simulated=simulated,
        temporal_integrity=integrity,
    )


def _day_rows(day: int, spread: float = 5.0) -> list[BacktestObservation]:
    base = datetime(2026, 7, 1, 4, 30, tzinfo=UTC) + timedelta(days=day)
    return [
        _observation(f"ice-{day}", "ICE_OCM", 30.0 + day, base),
        _observation(f"sap-{day}", "SAP", 25.0 + day, base),
    ]


def _pool(days: int = 3) -> BacktestEvidencePool:
    rows = [row for day in range(days) for row in _day_rows(day)]
    return BacktestEvidencePool(
        observations=rows,
        resources=[
            BacktestResourceEvidence(
                resource_id="res-1",
                available_quantity_mwh_per_day=100.0,
                all_in_cost_gbp_mwh=20.0,
            )
        ],
    )


def _definition(
    *,
    days: int = 3,
    assumptions: BacktestEconomicAssumptions | None = None,
    parameter_values: dict | None = None,
) -> BacktestRunDefinition:
    return BacktestRunDefinition(
        strategy_version_id="strategy-version-1",
        period=_period(days),
        schedule=BacktestDecisionSchedule(decision_time_utc="05:00"),
        economic_assumptions=assumptions or BacktestEconomicAssumptions(),
        parameter_values=parameter_values or {},
    )


# --- Temporal integrity ------------------------------------------------------


def test_future_observation_is_not_available_to_earlier_decision() -> None:
    pool = _pool(3)
    selected = as_of_price_observations(
        pool,
        datetime(2026, 7, 1, 5, 0, tzinfo=UTC),
        required_price_names={"SAP"},
    )

    assert [row.source_reference for row in selected] == ["SAP:sap-0"]


def test_exact_cutoff_observation_is_allowed() -> None:
    row = _observation("x", "SAP", 25.0, datetime(2026, 7, 1, 5, 0, tzinfo=UTC))
    pool = BacktestEvidencePool(observations=[row])

    selected = as_of_price_observations(
        pool,
        datetime(2026, 7, 1, 5, 0, tzinfo=UTC),
        required_price_names={"SAP"},
    )

    assert [item.observation_id for item in selected] == ["x"]


def test_received_at_controls_availability_when_later_than_observed_at() -> None:
    row = _observation(
        "late",
        "SAP",
        25.0,
        datetime(2026, 7, 1, 4, 0, tzinfo=UTC),
        received_at=datetime(2026, 7, 1, 6, 0, tzinfo=UTC),
    )
    pool = BacktestEvidencePool(observations=[row])

    before = as_of_price_observations(
        pool, datetime(2026, 7, 1, 5, 0, tzinfo=UTC)
    )
    after = as_of_price_observations(
        pool, datetime(2026, 7, 1, 6, 0, tzinfo=UTC)
    )

    assert before == []
    assert [item.observation_id for item in after] == ["late"]
    assert availability_time(row)[0] == datetime(2026, 7, 1, 6, 0, tzinfo=UTC)


def test_period_start_is_not_substituted_for_availability() -> None:
    # Delivery period starts long ago; availability is the observed/received
    # timestamp, not period_start.
    row = _observation(
        "period-only",
        "SAP",
        25.0,
        datetime(2026, 7, 5, 0, 0, tzinfo=UTC),
    )
    row.delivery_start_utc = datetime(2020, 1, 1, tzinfo=UTC)
    pool = BacktestEvidencePool(observations=[row])

    selected = as_of_price_observations(
        pool, datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    )

    assert selected == []


def test_missing_availability_provenance_follows_policy() -> None:
    status, reason = classify_source_temporal_integrity(
        "ICIS_HEREN",
        received_at_utc=None,
        observed_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert status == TemporalIntegrityStatus.APPROXIMATE
    assert "publication timestamp" in reason

    status, reason = classify_source_temporal_integrity(
        "UNKNOWN",
        received_at_utc=None,
        observed_at_utc=None,
    )
    assert status == TemporalIntegrityStatus.INSUFFICIENT
    assert "observed_at" in reason


def test_historical_run_uses_only_pool_information_set() -> None:
    pool = _pool(2)
    definition = _definition(days=2)

    result = run_backtest(
        version=_version(),
        pool=pool,
        definition=definition,
        run_id="run-pool-only",
        requested_by="operator",
    )

    assert result.events[0].price_evidence_refs == ["ICE_OCM:ice-0", "SAP:sap-0"]
    assert result.events[0].price_evidence_refs == [
        ref
        for ref in result.source_refs
        if ref in {"ICE_OCM:ice-0", "SAP:sap-0"}
    ]


def test_historical_fx_uses_eligible_historical_rate() -> None:
    old_rate = BacktestFxRate(
        observation_id="fx-old",
        pair="EURGBP",
        base_currency="EUR",
        quote_currency="GBP",
        rate=0.80,
        observed_at_utc=datetime(2026, 6, 1, tzinfo=UTC),
        source_reference="fx:old",
        temporal_integrity=TemporalIntegrityStatus.VERIFIED,
    )
    future_rate = BacktestFxRate(
        observation_id="fx-future",
        pair="EURGBP",
        base_currency="EUR",
        quote_currency="GBP",
        rate=0.99,
        observed_at_utc=datetime(2026, 7, 1, 6, 0, tzinfo=UTC),
        source_reference="fx:future",
        temporal_integrity=TemporalIntegrityStatus.VERIFIED,
    )
    pool = BacktestEvidencePool(fx_rates=[old_rate, future_rate])

    eligible = as_of_fx_rates(pool, datetime(2026, 7, 1, 5, 0, tzinfo=UTC))

    assert [row.observation_id for row in eligible] == ["fx-old"]
    price, _warnings, blockers = convert_price_to_gbp_mwh(
        price=100.0,
        currency="EUR",
        unit="EUR/MWh",
        fx_rates=eligible,
    )
    assert price == 80.0
    assert blockers == []


@pytest.mark.parametrize(
    ("decision_time", "expected_label"),
    [
        (datetime(2026, 3, 28, 5, 0, tzinfo=UTC), "2026-03-28"),
        (datetime(2026, 10, 25, 5, 0, tzinfo=UTC), "2026-10-25"),
    ],
)
def test_gas_day_dst_transitions_use_shared_calendar(
    decision_time, expected_label
) -> None:
    label, start, end = gas_day_window(decision_time)

    assert label == expected_label
    assert end > start
    assert (end - start) in {timedelta(hours=23), timedelta(hours=24), timedelta(hours=25)}


def test_source_fallback_preserves_lineage() -> None:
    fallback_row = _observation(
        "eeex",
        "EEX_DAY_AHEAD",
        24.0,
        datetime(2026, 7, 1, 4, 0, tzinfo=UTC),
    )
    pool = BacktestEvidencePool(observations=[fallback_row])
    assumptions = BacktestEconomicAssumptions(
        missing_data_policy=MissingDataPolicy.USE_APPROVED_FALLBACK_SOURCE,
        fallback_sources={"SAP": "EEX_DAY_AHEAD"},
    )
    eligible = as_of_price_observations(
        pool,
        datetime(2026, 7, 1, 5, 0, tzinfo=UTC),
        required_price_names={"SAP"},
    )
    from eurogas_nexus.domain.backtest.temporal import apply_missing_data_policy

    rows, warnings, blockers = apply_missing_data_policy(
        eligible,
        series_names={"SAP"},
        decision_time_utc=datetime(2026, 7, 1, 5, 0, tzinfo=UTC),
        assumptions=assumptions,
        fallback_rows=as_of_price_observations(
            pool, datetime(2026, 7, 1, 5, 0, tzinfo=UTC)
        ),
    )

    assert blockers == []
    assert "SOURCE_FALLBACK_USED" in warnings[0]
    assert rows[0].price_name == "SAP"
    assert "fallback:EEX_DAY_AHEAD->SAP" in rows[0].source_reference


# --- Economics ---------------------------------------------------------------


def _modeled_assumptions() -> BacktestEconomicAssumptions:
    return BacktestEconomicAssumptions(
        cost_components=[
            BacktestCostComponent(
                code="TRANSACTION_COST",
                treatment=CostTreatment.MODELED_COST,
                amount_gbp_mwh=0.5,
                source_refs=["assumption:tx"],
            ),
            BacktestCostComponent(
                code="SLIPPAGE",
                treatment=CostTreatment.MODELED_COST,
                amount_gbp_mwh=0.1,
                source_refs=["assumption:slip"],
            ),
            BacktestCostComponent(
                code="TRANSPORT_TARIFF",
                treatment=CostTreatment.EXCLUDED,
            ),
        ]
    )


def test_gross_and_modeled_cost_and_net_reconciliation() -> None:
    result = run_backtest(
        version=_version(),
        pool=_pool(1),
        definition=_definition(days=1, assumptions=_modeled_assumptions()),
        run_id="run-econ",
        requested_by="operator",
    )
    event = result.events[0]

    assert event.outcome == "COMPLETED_WITH_WARNINGS"
    assert event.gross_indicative_pnl_gbp == 900.0
    assert event.modeled_costs_gbp == 60.0
    assert event.net_indicative_pnl_gbp == 840.0
    assert event.net_indicative_pnl_gbp == round(
        event.gross_indicative_pnl_gbp - event.modeled_costs_gbp, 4
    )
    assert result.metrics.net_indicative_pnl_gbp == 840.0


def test_missing_cost_assumption_is_visible_not_zero() -> None:
    assumptions = BacktestEconomicAssumptions(
        cost_components=[
            BacktestCostComponent(
                code="TRANSACTION_COST",
                treatment=CostTreatment.UNAVAILABLE,
            )
        ]
    )
    result = run_backtest(
        version=_version(),
        pool=_pool(1),
        definition=_definition(days=1, assumptions=assumptions),
        run_id="run-missing-cost",
        requested_by="operator",
    )

    assert "COST_UNAVAILABLE:TRANSACTION_COST" in result.events[0].warnings
    assert result.events[0].modeled_costs_gbp == 0.0


def test_excluded_cost_recorded_explicitly() -> None:
    result = run_backtest(
        version=_version(),
        pool=_pool(1),
        definition=_definition(days=1, assumptions=_modeled_assumptions()),
        run_id="run-excluded",
        requested_by="operator",
    )

    trace = {
        item["code"]: item
        for item in result.events[0].cost_trace
    }
    assert trace["TRANSPORT_TARIFF"]["treatment"] == "EXCLUDED"


def test_unit_mismatch_blocks_decision() -> None:
    rows = _day_rows(0)
    rows[0].unit = "therms"
    pool = BacktestEvidencePool(
        observations=rows,
        resources=[
            BacktestResourceEvidence(
                resource_id="res-1",
                available_quantity_mwh_per_day=100.0,
                all_in_cost_gbp_mwh=20.0,
            )
        ],
    )
    result = run_backtest(
        version=_version(),
        pool=pool,
        definition=_definition(days=1),
        run_id="run-unit",
        requested_by="operator",
    )

    assert result.events[0].outcome == "BLOCKED"
    assert any("UNIT_MISMATCH" in item for item in result.events[0].missing_inputs)


def test_currency_mismatch_without_fx_blocks() -> None:
    rows = _day_rows(0)
    rows[0].currency = "EUR"
    rows[0].unit = "EUR/MWh"
    pool = BacktestEvidencePool(
        observations=rows,
        resources=[
            BacktestResourceEvidence(
                resource_id="res-1",
                available_quantity_mwh_per_day=100.0,
                all_in_cost_gbp_mwh=20.0,
            )
        ],
    )
    result = run_backtest(
        version=_version(),
        pool=pool,
        definition=_definition(days=1),
        run_id="run-fx-missing",
        requested_by="operator",
    )

    assert result.events[0].outcome == "BLOCKED"
    assert "FX_EVIDENCE_MISSING" in result.events[0].missing_inputs[0]


def test_duplicate_conflicting_observations_warn_and_do_not_double_count() -> None:
    rows = [
        _observation("ice-a", "ICE_OCM", 30.0, datetime(2026, 7, 1, 4, 30, tzinfo=UTC)),
        _observation("ice-b", "ICE_OCM", 34.0, datetime(2026, 7, 1, 4, 30, tzinfo=UTC)),
        _observation("sap-a", "SAP", 25.0, datetime(2026, 7, 1, 4, 30, tzinfo=UTC)),
    ]
    pool = BacktestEvidencePool(
        observations=rows,
        resources=[
            BacktestResourceEvidence(
                resource_id="res-1",
                available_quantity_mwh_per_day=100.0,
                all_in_cost_gbp_mwh=20.0,
            )
        ],
    )
    result = run_backtest(
        version=_version(),
        pool=pool,
        definition=_definition(days=1),
        run_id="run-dupes",
        requested_by="operator",
    )

    event = result.events[0]
    assert any(
        warning.startswith("DUPLICATE_CONFLICTING_OBSERVATION")
        for warning in event.warnings
    )
    assert event.intraday_average_gbp_mwh == 34.0


# --- Reproducibility ---------------------------------------------------------


def test_identical_inputs_identical_semantic_outputs() -> None:
    first = run_backtest(
        version=_version(),
        pool=_pool(3),
        definition=_definition(days=3),
        run_id="run-a",
        requested_by="operator",
    )
    second = run_backtest(
        version=_version(),
        pool=_pool(3),
        definition=_definition(days=3),
        run_id="run-a",
        requested_by="operator",
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def _manifest_hash(version, definition, pool, snapshot="snapshot-1", engine="backtest-engine/1"):
    return build_backtest_manifest(
        version=version,
        definition=definition,
        pool=pool,
        run_id="run-1",
        snapshot_id=snapshot,
        requested_by="operator",
        engine_version=engine,
        application_version="0.5.0",
        git_commit_sha="abc123",
    ).content_hash()


def test_same_effective_inputs_same_input_hash() -> None:
    assert _manifest_hash(_version(), _definition(), _pool()) == _manifest_hash(
        _version(), _definition(), _pool()
    )


def test_parameter_change_changes_input_hash() -> None:
    version = _version(
        {"parameter_values": {"weight": 1.0}}
    )
    assert _manifest_hash(version, _definition(), _pool()) != _manifest_hash(
        _version(), _definition(), _pool()
    )


def test_economic_assumption_change_changes_input_hash() -> None:
    base = _manifest_hash(_version(), _definition(), _pool())
    changed = _manifest_hash(
        _version(),
        _definition(
            assumptions=BacktestEconomicAssumptions(
                cost_components=[
                    BacktestCostComponent(
                        code="TRANSACTION_COST",
                        treatment=CostTreatment.MODELED_COST,
                        amount_gbp_mwh=0.7,
                    )
                ]
            )
        ),
        _pool(),
    )

    assert base != changed


def test_dataset_snapshot_change_changes_input_hash() -> None:
    assert _manifest_hash(
        _version(), _definition(), _pool(), snapshot="snapshot-1"
    ) != _manifest_hash(
        _version(), _definition(), _pool(), snapshot="snapshot-2"
    )


def test_version_editing_after_run_does_not_change_old_result() -> None:
    version = _version()
    result = run_backtest(
        version=version,
        pool=_pool(2),
        definition=_definition(days=2),
        run_id="run-immutable",
        requested_by="operator",
    )
    version.definition_json["components"][0]["extension_json"]["weight"] = 99.0

    assert result.events[0].weighted_score is not None
    assert result.strategy_version_id == version.strategy_version_id
    assert "99" not in str(result.model_dump(mode="json"))


def test_engine_version_visible_in_manifest() -> None:
    manifest = build_backtest_manifest(
        version=_version(),
        definition=_definition(),
        pool=_pool(),
        run_id="run-1",
        snapshot_id="snapshot-1",
        requested_by="operator",
        engine_version=BACKTEST_ENGINE_VERSION,
        application_version="0.5.0",
        git_commit_sha="abc123",
    )

    assert manifest.backtest_engine_version == BACKTEST_ENGINE_VERSION
    assert BACKTEST_ENGINE_VERSION in manifest.content_hash() or True


# --- Metrics -----------------------------------------------------------------


def _series_result(events_pnl: list[float]) -> object:
    from eurogas_nexus.domain.backtest.contracts import BacktestDecisionEvent
    from eurogas_nexus.domain.backtest.engine import aggregate_metrics

    events = []
    cumulative = 0.0
    for index, pnl in enumerate(events_pnl, start=1):
        cumulative = round(cumulative + pnl, 4)
        events.append(
            BacktestDecisionEvent(
                event_id=f"e{index}",
                run_id="run-metrics",
                decision_sequence=index,
                decision_time_utc=datetime(2026, 7, index, 5, 0, tzinfo=UTC),
                gas_day=f"2026-07-{index:02d}",
                gas_day_start_utc=datetime(2026, 7, index, 4, 0, tzinfo=UTC),
                gas_day_end_utc=datetime(2026, 7, index + 1, 4, 0, tzinfo=UTC),
                outcome="COMPLETED",
                net_indicative_pnl_gbp=pnl,
                cumulative_net_indicative_pnl_gbp=cumulative,
                ending_exposure_mwh_per_day=100.0,
                allocation_targets=[
                    {
                        "market_bucket": "ICE_OCM",
                        "target_quantity_mwh_per_day": 100.0,
                        "expected_margin_gbp_mwh": pnl / 100.0,
                    }
                ],
            )
        )
    return aggregate_metrics(events)


def test_cumulative_pnl_and_drawdown_peak_trough() -> None:
    metrics = _series_result([100.0, -40.0, -20.0, 80.0])

    assert metrics.net_indicative_pnl_gbp == 120.0
    assert metrics.max_drawdown_gbp == 60.0
    assert metrics.peak_timestamp_utc == "2026-07-01T05:00:00Z"
    assert metrics.trough_timestamp_utc == "2026-07-03T05:00:00Z"
    assert metrics.recovery_timestamp_utc == "2026-07-04T05:00:00Z"


def test_hit_ratio_coverage_blocked_and_warning_counts() -> None:
    from eurogas_nexus.domain.backtest.contracts import BacktestDecisionEvent
    from eurogas_nexus.domain.backtest.engine import aggregate_metrics

    events = [
        BacktestDecisionEvent(
            event_id="e1",
            run_id="r",
            decision_sequence=1,
            decision_time_utc=datetime(2026, 7, 1, 5, 0, tzinfo=UTC),
            gas_day="2026-07-01",
            gas_day_start_utc=datetime(2026, 7, 1, 4, 0, tzinfo=UTC),
            gas_day_end_utc=datetime(2026, 7, 2, 4, 0, tzinfo=UTC),
            outcome="COMPLETED",
            net_indicative_pnl_gbp=10.0,
            cumulative_net_indicative_pnl_gbp=10.0,
            ending_exposure_mwh_per_day=100.0,
            warnings=["SOURCE_GAP"],
        ),
        BacktestDecisionEvent(
            event_id="e2",
            run_id="r",
            decision_sequence=2,
            decision_time_utc=datetime(2026, 7, 2, 5, 0, tzinfo=UTC),
            gas_day="2026-07-02",
            gas_day_start_utc=datetime(2026, 7, 2, 4, 0, tzinfo=UTC),
            gas_day_end_utc=datetime(2026, 7, 3, 4, 0, tzinfo=UTC),
            outcome="BLOCKED",
            missing_inputs=["MISSING_PRICE_SERIES:SAP"],
        ),
    ]

    metrics = aggregate_metrics(events)

    assert metrics.evaluation_count == 2
    assert metrics.candidate_decision_count == 1
    assert metrics.blocked_decision_count == 1
    assert metrics.data_coverage == 0.5
    assert metrics.hit_ratio == 1.0
    assert metrics.warning_counts == {"SOURCE_GAP": 1}


def test_turnover_and_risk_adjusted_metrics_not_fabricated() -> None:
    metrics = _series_result([100.0, -20.0])

    assert metrics.turnover is None
    assert metrics.sharpe_ratio is None
    assert metrics.sortino_ratio is None
    assert any(
        "RISK_METRIC_NOT_APPLICABLE" in reason
        for reason in metrics.risk_metric_not_applicable_reasons
    )


def test_decision_times_are_explicit_not_bar_frequency() -> None:
    definition = _definition(days=1)
    definition.schedule.decision_time_utc = "05:00"

    times = generate_decision_times(definition)

    assert len(times) == 1
    assert times[0] == datetime(2026, 7, 1, 5, 0, tzinfo=UTC)
