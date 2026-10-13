"""Target-aware (engine/2) evidence selection — CR-04 focused acceptance.

These tests pin the new product-aware selection rules directly at the domain
boundary:

* the valid control selects a matching future-delivery quote that was
  available before ``T``;
* a price observed after ``T``, the wrong hub/tenor/basis/role, an unknown
  evidence role/basis or a mismatched delivery interval is refused;
* the 365-decision regression proves a rolling gas-day target admits only the
  matching delivery day and does not reproduce engine/1's year of equal
  returns at 100% evaluation completion;
* 23/25-hour DST gas days, an expired fixed target and a reference validity
  window are resolved through the canonical calendar;
* carry-forward enforces the configured max age exactly, and fallback cannot
  bypass the declared product identity;
* the declared ``fill_price_policy`` is enforced for primary and fallback
  candidates, so a basis/policy conflict blocks instead of switching basis
  (``NEXT_ELIGIBLE`` stays permissive).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from eurogas_nexus.domain.backtest.contracts import (
    BacktestDecisionSchedule,
    BacktestEconomicAssumptions,
    BacktestEvidencePool,
    BacktestObservation,
    BacktestPeriod,
    BacktestResourceEvidence,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.backtest.engine import run_backtest, run_target_backtest
from eurogas_nexus.domain.backtest.target_selection import resolve_target_interval
from eurogas_nexus.domain.ontology.vocabulary import (
    FillPricePolicy,
    MissingDataPolicy,
    TemporalIntegrityStatus,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyEvidenceTarget,
    StrategyVersionDefinition,
)

DAY = 24 * 60 * 60
JUL1 = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
JUL2 = datetime(2026, 7, 2, 0, 0, tzinfo=UTC)
JUL3 = datetime(2026, 7, 3, 0, 0, tzinfo=UTC)


def _component(
    *,
    targets: list[dict],
    day_names: list[str] | None = ("SAP",),
    intraday_names: list[str] | None = ("ICE_OCM",),
) -> dict:
    extension: dict = {
        "weight": 1.0,
        "positive_spread_threshold_gbp_mwh": 0.0,
        "negative_spread_threshold_gbp_mwh": 0.0,
        "target_bar_minutes": 5,
        "time_window_start": "05:00",
        "time_window_end": "05:30",
    }
    if day_names is not None:
        extension["day_ahead_price_names"] = list(day_names)
    if intraday_names is not None:
        extension["intraday_price_names"] = list(intraday_names)
    return {
        "component_id": "ocm-da",
        "component_type": "OCM_VS_DAY_AHEAD",
        "hubs": ["NBP"],
        "extension_json": extension,
        "evidence_targets": targets,
    }


def _gas_day_target(
    leg_id: str,
    names: list[str],
    *,
    tenor: str,
    offset: int = 0,
    role: str = "DELIVERY_PRICE",
    basis: str = "MID",
    hub: str = "NBP",
) -> dict:
    return {
        "leg_id": leg_id,
        "price_names": names,
        "role": role,
        "hub": hub,
        "tenor": tenor,
        "price_basis": basis,
        "target_basis": "GAS_DAY",
        "calendar_id": "EU-CAM-UTC-2025",
        "gas_day_offset": offset,
    }


def _explicit_target(
    leg_id: str,
    names: list[str],
    *,
    tenor: str,
    start: str,
    end: str,
    role: str = "DELIVERY_PRICE",
    basis: str = "MID",
    hub: str = "NBP",
) -> dict:
    return {
        "leg_id": leg_id,
        "price_names": names,
        "role": role,
        "hub": hub,
        "tenor": tenor,
        "price_basis": basis,
        "target_basis": "EXPLICIT_INTERVAL",
        "delivery_start_utc": start,
        "delivery_end_utc": end,
    }


def _definition(component: dict) -> StrategyVersionDefinition:
    return StrategyVersionDefinition.model_validate(
        {
            "components": [component],
            "resource_contexts": [
                {
                    "resource_id": "r1",
                    "resource_name": "R",
                    "available_quantity_mwh_per_day": 100.0,
                    "all_in_cost_gbp_mwh": 20.0,
                    "required_tso_access": [],
                }
            ],
            "parameter_values": {},
        }
    )


def _version(definition: StrategyVersionDefinition) -> SimpleNamespace:
    return SimpleNamespace(
        strategy_version_id="strategy-version-target",
        strategy_id="strategy-target",
        version_number=1,
        content_hash="sha256:target",
        definition_json={
            "strategy_name": "Target",
            "components": definition.model_dump(mode="json")["components"],
            "resource_contexts": [
                {
                    "resource_id": "r1",
                    "resource_name": "R",
                    "available_quantity_mwh_per_day": 100.0,
                    "all_in_cost_gbp_mwh": 20.0,
                    "required_tso_access": [],
                }
            ],
            "parameter_values": {},
        },
    )


def _observation(
    observation_id: str,
    price_name: str,
    price: float,
    *,
    observed_at: datetime,
    delivery_start: datetime,
    delivery_end: datetime,
    tenor: str = "day-ahead",
    hub: str = "NBP",
    role: str | None = "DELIVERY_PRICE",
    basis: str | None = "MID",
    price_type: str = "mid",
    source_system: str | None = None,
    simulated: bool = False,
) -> BacktestObservation:
    return BacktestObservation(
        observation_id=observation_id,
        source_system=source_system or price_name,
        venue=price_name,
        hub=hub,
        product=price_name,
        tenor=tenor,
        price_name=price_name,
        price=price,
        currency="GBP",
        unit="MWh",
        observed_at_utc=observed_at,
        received_at_utc=observed_at,
        delivery_start_utc=delivery_start,
        delivery_end_utc=delivery_end,
        bar_minutes=5 if price_name == "ICE_OCM" else None,
        price_type=price_type,
        source_reference=f"{price_name}:{observation_id}",
        simulated=simulated,
        temporal_integrity=TemporalIntegrityStatus.VERIFIED,
        evidence_role=role,
        price_basis=basis,
    )


def _pool(rows: list[BacktestObservation]) -> BacktestEvidencePool:
    return BacktestEvidencePool(
        observations=rows,
        resources=[
            BacktestResourceEvidence(
                resource_id="r1",
                available_quantity_mwh_per_day=100.0,
                all_in_cost_gbp_mwh=20.0,
            )
        ],
    )


def _period(start: datetime, end: datetime) -> BacktestPeriod:
    return BacktestPeriod(start_utc=start, end_utc=end)


def _run_definition(
    start: datetime,
    end: datetime,
    *,
    policy: MissingDataPolicy = MissingDataPolicy.FAIL,
    max_age: int = DAY,
    decision_time_utc: str = "05:00",
    fill_price_policy: FillPricePolicy = FillPricePolicy.NEXT_ELIGIBLE,
    fallback_sources: dict[str, str] | None = None,
) -> BacktestRunDefinition:
    return BacktestRunDefinition(
        strategy_version_id="strategy-version-target",
        period=_period(start, end),
        schedule=BacktestDecisionSchedule(decision_time_utc=decision_time_utc),
        economic_assumptions=BacktestEconomicAssumptions(
            missing_data_policy=policy,
            carry_forward_max_age_seconds=max_age,
            fill_price_policy=fill_price_policy,
            fallback_sources=fallback_sources or {},
        ),
    )


def _run_target(definition: StrategyVersionDefinition, pool, run_definition):
    return run_target_backtest(
        version=_version(definition),
        pool=pool,
        definition=run_definition,
        run_id="run-target",
        requested_by="operator",
        target_definition=definition,
    )


# --- valid control -----------------------------------------------------------


def test_engine2_valid_control_selects_future_delivery_quote_available_before_t() -> None:
    # T = 2026-07-01T05:00Z. The next-gas-day target starts 2026-07-02T04:00Z,
    # i.e. delivery legitimately begins after T, but the quote was observed at
    # 2026-07-01T04:30Z, before T.
    component = _component(
        targets=[
            _gas_day_target("da", ["SAP"], tenor="day-ahead", offset=1),
            _gas_day_target("id", ["ICE_OCM"], tenor="within-day", offset=1),
        ]
    )
    definition = _definition(component)
    start = datetime(2026, 7, 2, 4, 0, tzinfo=UTC)
    end = datetime(2026, 7, 3, 4, 0, tzinfo=UTC)
    pool = _pool(
        [
            _observation(
                "sap-next",
                "SAP",
                25.0,
                observed_at=datetime(2026, 7, 1, 4, 30, tzinfo=UTC),
                delivery_start=start,
                delivery_end=end,
            ),
            _observation(
                "ice-next",
                "ICE_OCM",
                30.0,
                observed_at=datetime(2026, 7, 1, 4, 30, tzinfo=UTC),
                delivery_start=start,
                delivery_end=end,
                tenor="within-day",
            ),
        ]
    )
    result = _run_target(
        definition,
        pool,
        _run_definition(JUL1, JUL2),
    )

    assert result.backtest_engine_version == "backtest-engine/2"
    assert result.events[0].outcome == "COMPLETED_WITH_WARNINGS"
    assert result.events[0].price_evidence_refs == ["SAP:sap-next", "ICE_OCM:ice-next"]
    matched = {item["price_name"]: item for item in result.events[0].evidence_selection_trace}
    assert matched["SAP"]["outcome"] == "MATCHED"
    assert matched["SAP"]["resolved_start_utc"] == "2026-07-02T04:00:00Z"
    assert matched["SAP"]["evidence_role"] == "DELIVERY_PRICE"
    assert matched["SAP"]["price_basis"] == "MID"
    assert matched["SAP"]["simulated"] is False


def test_engine2_refuses_a_price_observed_after_the_decision() -> None:
    component = _component(
        targets=[
            _gas_day_target("da", ["SAP"], tenor="day-ahead", offset=0),
            _gas_day_target("id", ["ICE_OCM"], tenor="within-day", offset=0),
        ]
    )
    definition = _definition(component)
    start = datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
    end = datetime(2026, 7, 2, 4, 0, tzinfo=UTC)
    pool = _pool(
        [
            _observation(
                "sap-late",
                "SAP",
                25.0,
                observed_at=datetime(2026, 7, 1, 6, 0, tzinfo=UTC),
                delivery_start=start,
                delivery_end=end,
            ),
            _observation(
                "ice-ok",
                "ICE_OCM",
                30.0,
                observed_at=datetime(2026, 7, 1, 4, 30, tzinfo=UTC),
                delivery_start=start,
                delivery_end=end,
                tenor="within-day",
            ),
        ]
    )
    result = _run_target(
        definition,
        pool,
        _run_definition(JUL1, JUL2),
    )

    event = result.events[0]
    assert event.outcome == "BLOCKED"
    assert "MISSING_PRICE_SERIES:SAP" in event.missing_inputs
    trace = {item["price_name"]: item for item in event.evidence_selection_trace}
    assert trace["SAP"]["rejected_reasons"] == {"AVAILABILITY_AFTER_DECISION": 1}


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"hub": "TTF"}, "HUB_MISMATCH"),
        ({"tenor": "weekend"}, "TENOR_MISMATCH"),
        ({"basis": "BID"}, "PRICE_BASIS_MISMATCH"),
        ({"role": "REFERENCE_LEVEL"}, "EVIDENCE_ROLE_MISMATCH"),
        ({"role": None}, "EVIDENCE_ROLE_UNKNOWN"),
        ({"basis": None}, "PRICE_BASIS_UNKNOWN"),
    ],
)
def test_engine2_refuses_a_wrong_product_or_unknown_metadata(overrides, reason) -> None:
    component = _component(
        targets=[_gas_day_target("da", ["SAP"], tenor="day-ahead", offset=0)],
        intraday_names=None,
    )
    definition = _definition(component)
    start = datetime(2026, 7, 1, 4, 0, tzinfo=UTC)
    end = datetime(2026, 7, 2, 4, 0, tzinfo=UTC)
    pool = _pool(
        [
            _observation(
                "sap-wrong",
                "SAP",
                25.0,
                observed_at=datetime(2026, 7, 1, 4, 30, tzinfo=UTC),
                delivery_start=start,
                delivery_end=end,
                **overrides,
            )
        ]
    )
    result = _run_target(
        definition,
        pool,
        _run_definition(JUL1, JUL2),
    )

    trace = {item["price_name"]: item for item in result.events[0].evidence_selection_trace}
    assert reason in trace["SAP"]["rejected_reasons"]


def test_engine2_refuses_a_mismatched_delivery_interval() -> None:
    component = _component(
        targets=[_gas_day_target("da", ["SAP"], tenor="day-ahead", offset=0)],
        intraday_names=None,
    )
    definition = _definition(component)
    pool = _pool(
        [
            _observation(
                "sap-shifted",
                "SAP",
                25.0,
                observed_at=datetime(2026, 7, 1, 4, 30, tzinfo=UTC),
                # One hour later than the resolved gas day start.
                delivery_start=datetime(2026, 7, 1, 5, 0, tzinfo=UTC),
                delivery_end=datetime(2026, 7, 2, 5, 0, tzinfo=UTC),
            )
        ]
    )
    result = _run_target(
        definition,
        pool,
        _run_definition(JUL1, JUL2),
    )

    trace = {item["price_name"]: item for item in result.events[0].evidence_selection_trace}
    assert trace["SAP"]["rejected_reasons"] == {"DELIVERY_INTERVAL_MISMATCH": 1}


# --- 365-day regression ------------------------------------------------------


def test_engine2_rolling_gas_day_cannot_reuse_one_day_of_evidence_for_a_year() -> None:
    # One day of admissible evidence; a rolling current-gas-day target for 365
    # decisions must admit it exactly once. Engine/1 reuses it for every
    # decision because it only matched the series name.
    component = _component(
        targets=[
            _gas_day_target("da", ["SAP"], tenor="day-ahead", offset=0),
            _gas_day_target("id", ["ICE_OCM"], tenor="within-day", offset=0),
        ]
    )
    definition = _definition(component)
    start = datetime(2026, 1, 1, 5, 0, tzinfo=UTC)
    end = datetime(2026, 1, 2, 5, 0, tzinfo=UTC)
    pool = _pool(
        [
            _observation(
                "sap-day1",
                "SAP",
                25.0,
                observed_at=datetime(2026, 1, 1, 4, 30, tzinfo=UTC),
                delivery_start=start,
                delivery_end=end,
            ),
            _observation(
                "ice-day1",
                "ICE_OCM",
                30.0,
                observed_at=datetime(2026, 1, 1, 4, 30, tzinfo=UTC),
                delivery_start=start,
                delivery_end=end,
                tenor="within-day",
            ),
        ]
    )
    run_definition = _run_definition(
        datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        datetime(2027, 1, 1, 0, 0, tzinfo=UTC),
    )

    targeted = _run_target(definition, pool, run_definition)
    legacy = run_backtest(
        version=_version(definition),
        pool=pool,
        definition=run_definition,
        run_id="run-legacy",
        requested_by="operator",
    )

    assert targeted.metrics.evaluation_count == 365
    assert targeted.metrics.candidate_decision_count == 1
    assert targeted.metrics.data_coverage == pytest.approx(round(1 / 365, 4))
    assert targeted.metrics.distinct_admitted_price_refs == 2
    assert targeted.metrics.events_reusing_admitted_price_refs == 0
    # Engine/1 is the failure mode the amendment removes: 365 identical returns.
    assert legacy.metrics.evaluation_count == 365
    assert legacy.metrics.candidate_decision_count == 365
    assert legacy.metrics.data_coverage == 1.0
    legacy_nets = {event.net_indicative_pnl_gbp for event in legacy.events}
    assert len(legacy_nets) == 1
    assert legacy.metrics.distinct_admitted_price_refs == 2
    assert legacy.metrics.events_reusing_admitted_price_refs == 364


# --- DST / fixed targets -----------------------------------------------------


def test_engine2_gas_day_target_resolves_23_and_25_hour_dst_days() -> None:
    target = StrategyEvidenceTarget.model_validate(
        _gas_day_target("da", ["SAP"], tenor="day-ahead", offset=0)
    )
    spring = resolve_target_interval(target, datetime(2026, 3, 28, 12, 0, tzinfo=UTC))
    assert (spring.end_utc - spring.start_utc) == timedelta(hours=23)
    assert spring.start_utc == datetime(2026, 3, 28, 5, 0, tzinfo=UTC)
    assert spring.end_utc == datetime(2026, 3, 29, 4, 0, tzinfo=UTC)

    autumn = resolve_target_interval(target, datetime(2026, 10, 24, 12, 0, tzinfo=UTC))
    assert (autumn.end_utc - autumn.start_utc) == timedelta(hours=25)
    assert autumn.start_utc == datetime(2026, 10, 24, 4, 0, tzinfo=UTC)
    assert autumn.end_utc == datetime(2026, 10, 25, 5, 0, tzinfo=UTC)

    next_day = StrategyEvidenceTarget.model_validate(
        _gas_day_target("da", ["SAP"], tenor="day-ahead", offset=1)
    )
    offset_one = resolve_target_interval(next_day, datetime(2026, 3, 28, 12, 0, tzinfo=UTC))
    assert offset_one.start_utc == datetime(2026, 3, 29, 4, 0, tzinfo=UTC)
    assert offset_one.end_utc == datetime(2026, 3, 30, 4, 0, tzinfo=UTC)


def test_engine2_explicit_hour_intervals_distinguish_dst_repeats_by_utc() -> None:
    # On the fall-back night the local wall clock repeats; the UTC endpoints do
    # not. Each declared explicit hour admits exactly its own UTC window.
    first = _explicit_target(
        "da",
        ["SAP"],
        tenor="hour",
        start="2026-10-25T00:00:00Z",
        end="2026-10-25T01:00:00Z",
    )
    second = _explicit_target(
        "da",
        ["SAP"],
        tenor="hour",
        start="2026-10-25T01:00:00Z",
        end="2026-10-25T02:00:00Z",
    )
    row = _observation(
        "sap-hour",
        "SAP",
        25.0,
        observed_at=datetime(2026, 10, 24, 23, 30, tzinfo=UTC),
        delivery_start=datetime(2026, 10, 25, 1, 0, tzinfo=UTC),
        delivery_end=datetime(2026, 10, 25, 2, 0, tzinfo=UTC),
        tenor="hour",
    )
    definition = _definition(
        _component(targets=[second], intraday_names=None)
    )
    result = _run_target(
        definition,
        _pool([row]),
        _run_definition(
            datetime(2026, 10, 25, 0, 0, tzinfo=UTC),
            datetime(2026, 10, 25, 1, 0, tzinfo=UTC),
            decision_time_utc="00:30",
        ),
    )
    assert result.events[0].price_evidence_refs == ["SAP:sap-hour"]

    wrong = _definition(_component(targets=[first], intraday_names=None))
    refused = _run_target(
        wrong,
        _pool([row]),
        _run_definition(
            datetime(2026, 10, 25, 0, 0, tzinfo=UTC),
            datetime(2026, 10, 25, 1, 0, tzinfo=UTC),
            decision_time_utc="00:30",
        ),
    )
    trace = {item["price_name"]: item for item in refused.events[0].evidence_selection_trace}
    assert "DELIVERY_INTERVAL_MISMATCH" in trace["SAP"]["rejected_reasons"]


def test_engine2_refuses_an_expired_fixed_delivery_target() -> None:
    target = _explicit_target(
        "da",
        ["SAP"],
        tenor="day-ahead",
        start="2026-07-01T04:00:00Z",
        end="2026-07-02T04:00:00Z",
    )
    definition = _definition(_component(targets=[target], intraday_names=None))
    result = _run_target(
        definition,
        _pool([]),
        _run_definition(
            datetime(2026, 7, 3, 0, 0, tzinfo=UTC),
            datetime(2026, 7, 4, 0, 0, tzinfo=UTC),
        ),
    )
    assert "DELIVERY_TARGET_EXPIRED:SAP" in result.events[0].missing_inputs


def test_engine2_reference_level_validity_must_contain_the_decision() -> None:
    target = _explicit_target(
        "ref",
        ["SAP"],
        tenor="day-ahead",
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        role="REFERENCE_LEVEL",
    )
    definition = _definition(_component(targets=[target], intraday_names=None))
    result = _run_target(
        definition,
        _pool([]),
        _run_definition(
            datetime(2026, 7, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
        ),
    )
    assert (
        "REFERENCE_VALIDITY_NOT_CONTAINING_DECISION:SAP"
        in result.events[0].missing_inputs
    )


# --- policies ----------------------------------------------------------------


def _carry_pool(observed_at: datetime) -> BacktestEvidencePool:
    return _pool(
        [
            _observation(
                "sap-old",
                "SAP",
                25.0,
                observed_at=observed_at,
                delivery_start=datetime(2026, 7, 2, 4, 0, tzinfo=UTC),
                delivery_end=datetime(2026, 7, 3, 4, 0, tzinfo=UTC),
            )
        ]
    )


_CARRY_TARGET = _explicit_target(
    "da",
    ["SAP"],
    tenor="day-ahead",
    start="2026-07-02T04:00:00Z",
    end="2026-07-03T04:00:00Z",
)


def test_engine2_carry_forward_enforces_max_age_exactly() -> None:
    decision = datetime(2026, 7, 2, 5, 0, tzinfo=UTC)
    definition = _definition(_component(targets=[_CARRY_TARGET], intraday_names=None))
    run_definition = _run_definition(
        decision,
        decision + timedelta(days=1),
        policy=MissingDataPolicy.CARRY_FORWARD_WITH_MAX_AGE,
        max_age=DAY,
    )

    at_limit = _run_target(
        definition, _carry_pool(decision - timedelta(seconds=DAY)), run_definition
    )
    assert at_limit.events[0].price_evidence_refs == ["SAP:sap-old"]

    over_limit = _run_target(
        definition, _carry_pool(decision - timedelta(seconds=DAY + 1)), run_definition
    )
    assert (
        "CARRY_FORWARD_MAX_AGE_EXCEEDED:SAP:86401s" in over_limit.events[0].missing_inputs
    )


def test_engine2_carry_forward_rejects_one_microsecond_over_max_age() -> None:
    # The age must be compared exactly: truncating to whole seconds admitted an
    # age of max + 0.9s. One microsecond past the limit is already too old, and
    # the displayed age keeps the microsecond rather than rounding it away.
    decision = datetime(2026, 7, 2, 5, 0, tzinfo=UTC)
    definition = _definition(_component(targets=[_CARRY_TARGET], intraday_names=None))
    run_definition = _run_definition(
        decision,
        decision + timedelta(days=1),
        policy=MissingDataPolicy.CARRY_FORWARD_WITH_MAX_AGE,
        max_age=DAY,
    )

    over = _run_target(
        definition,
        _carry_pool(decision - timedelta(seconds=DAY) - timedelta(microseconds=1)),
        run_definition,
    )

    assert over.events[0].outcome == "BLOCKED"
    assert (
        "CARRY_FORWARD_MAX_AGE_EXCEEDED:SAP:86400.000001s"
        in over.events[0].missing_inputs
    )
    trace = over.events[0].evidence_selection_trace[0]
    assert trace["reason"] == "CARRY_FORWARD_MAX_AGE_EXCEEDED"
    assert trace["carry_forward_age_seconds"] == pytest.approx(86_400.000001)


def test_engine2_fallback_cannot_bypass_the_declared_product() -> None:
    target = _explicit_target(
        "da",
        ["SAP"],
        tenor="day-ahead",
        start="2026-07-02T04:00:00Z",
        end="2026-07-03T04:00:00Z",
    )
    definition = _definition(_component(targets=[target], intraday_names=None))
    run_definition = BacktestRunDefinition(
        strategy_version_id="strategy-version-target",
        period=_period(JUL2, JUL3),
        economic_assumptions=BacktestEconomicAssumptions(
            missing_data_policy=MissingDataPolicy.USE_APPROVED_FALLBACK_SOURCE,
            fallback_sources={"SAP": "EEX_DAY_AHEAD"},
        ),
    )

    # The configured fallback carries the wrong tenor: it must not be renamed
    # into SAP just because the source matches.
    wrong = _observation(
        "eex-wrong",
        "EEX_DAY_AHEAD",
        24.0,
        observed_at=datetime(2026, 7, 1, 4, 0, tzinfo=UTC),
        delivery_start=datetime(2026, 7, 2, 4, 0, tzinfo=UTC),
        delivery_end=datetime(2026, 7, 3, 4, 0, tzinfo=UTC),
        tenor="within-day",
        source_system="EEX",
    )
    refused = _run_target(definition, _pool([wrong]), run_definition)
    assert "FALLBACK_SOURCE_MISSING:SAP" in refused.events[0].missing_inputs

    right = _observation(
        "eex-ok",
        "EEX_DAY_AHEAD",
        24.0,
        observed_at=datetime(2026, 7, 1, 4, 0, tzinfo=UTC),
        delivery_start=datetime(2026, 7, 2, 4, 0, tzinfo=UTC),
        delivery_end=datetime(2026, 7, 3, 4, 0, tzinfo=UTC),
        tenor="day-ahead",
        source_system="EEX",
    )
    accepted = _run_target(definition, _pool([right]), run_definition)
    assert accepted.events[0].price_evidence_refs == [
        "fallback:EEX_DAY_AHEAD->SAP:EEX_DAY_AHEAD:eex-ok"
    ]
    assert "SOURCE_FALLBACK_USED:SAP" in accepted.events[0].warnings


# --- fill-price policy (engine/2 must not ignore the manifest claim) ---------

_FILL_TARGET_START = "2026-07-02T04:00:00Z"
_FILL_TARGET_END = "2026-07-03T04:00:00Z"
_FILL_OBSERVED = datetime(2026, 7, 1, 4, 0, tzinfo=UTC)


def _fill_target(*, basis: str) -> dict:
    return _explicit_target(
        "da",
        ["SAP"],
        tenor="day-ahead",
        start=_FILL_TARGET_START,
        end=_FILL_TARGET_END,
        basis=basis,
    )


def _fill_pool(
    *,
    basis: str,
    price_type: str,
    observation_id: str = "sap",
    price_name: str = "SAP",
    source_system: str | None = None,
) -> BacktestEvidencePool:
    return _pool(
        [
            _observation(
                observation_id,
                price_name,
                25.0,
                observed_at=_FILL_OBSERVED,
                delivery_start=datetime(2026, 7, 2, 4, 0, tzinfo=UTC),
                delivery_end=datetime(2026, 7, 3, 4, 0, tzinfo=UTC),
                basis=basis,
                price_type=price_type,
                source_system=source_system,
            )
        ]
    )


@pytest.mark.parametrize(
    ("policy", "basis", "price_type"),
    [
        # MID is the legacy bucket for the explicit reference/screen timings.
        (FillPricePolicy.MID, "MID", "mid"),
        (FillPricePolicy.MID, "MID", "exchange_reference"),
        (FillPricePolicy.MID, "MID", "broker_screen"),
        (FillPricePolicy.MID, "MID", "instant"),
        (FillPricePolicy.BID, "BID", "bid"),
        (FillPricePolicy.ASK, "ASK", "ask"),
        (FillPricePolicy.ASSESSMENT, "ASSESSMENT", "assessment"),
        (FillPricePolicy.ASSESSMENT, "ASSESSMENT", "daily_assessment"),
        (FillPricePolicy.LAST, "LAST", "last"),
        # NEXT_ELIGIBLE keeps its existing permissive contract.
        (FillPricePolicy.NEXT_ELIGIBLE, "LAST", "last"),
    ],
)
def test_engine2_fill_price_policy_admits_the_matching_row(
    policy: FillPricePolicy, basis: str, price_type: str
) -> None:
    definition = _definition(
        _component(targets=[_fill_target(basis=basis)], intraday_names=None)
    )
    run_definition = _run_definition(JUL1, JUL2, fill_price_policy=policy)

    result = _run_target(
        definition, _fill_pool(basis=basis, price_type=price_type), run_definition
    )

    assert result.events[0].price_evidence_refs == ["SAP:sap"]
    trace = result.events[0].evidence_selection_trace[0]
    assert trace["outcome"] == "MATCHED"
    assert trace["fill_price_policy"] == policy.value


@pytest.mark.parametrize(
    ("policy", "basis", "price_type"),
    [
        (FillPricePolicy.BID, "MID", "mid"),
        (FillPricePolicy.ASK, "MID", "mid"),
        (FillPricePolicy.LAST, "MID", "mid"),
        (FillPricePolicy.ASSESSMENT, "MID", "mid"),
        (FillPricePolicy.MID, "BID", "bid"),
    ],
)
def test_engine2_fill_price_policy_mismatch_blocks_with_a_stable_reason(
    policy: FillPricePolicy, basis: str, price_type: str
) -> None:
    definition = _definition(
        _component(targets=[_fill_target(basis=basis)], intraday_names=None)
    )
    run_definition = _run_definition(JUL1, JUL2, fill_price_policy=policy)

    result = _run_target(
        definition, _fill_pool(basis=basis, price_type=price_type), run_definition
    )

    assert result.events[0].outcome == "BLOCKED"
    assert "MISSING_PRICE_SERIES:SAP" in result.events[0].missing_inputs
    trace = result.events[0].evidence_selection_trace[0]
    assert trace["rejected_reasons"] == {"FILL_PRICE_POLICY_MISMATCH": 1}


def test_engine2_conflicting_basis_and_fill_policy_blocks_without_switching_basis() -> None:
    # The frozen declaration says MID; the run's fill policy says BID. The pool
    # holds a MID row (matches the declaration, fails the policy) and a BID row
    # (matches the policy, fails the declaration). Neither may stand in for the
    # other: an overridden basis must not be picked silently.
    definition = _definition(
        _component(targets=[_fill_target(basis="MID")], intraday_names=None)
    )
    run_definition = _run_definition(JUL1, JUL2, fill_price_policy=FillPricePolicy.BID)
    pool = _pool(
        [
            _observation(
                "sap-mid",
                "SAP",
                25.0,
                observed_at=_FILL_OBSERVED,
                delivery_start=datetime(2026, 7, 2, 4, 0, tzinfo=UTC),
                delivery_end=datetime(2026, 7, 3, 4, 0, tzinfo=UTC),
                basis="MID",
                price_type="mid",
            ),
            _observation(
                "sap-bid",
                "SAP",
                26.0,
                observed_at=_FILL_OBSERVED,
                delivery_start=datetime(2026, 7, 2, 4, 0, tzinfo=UTC),
                delivery_end=datetime(2026, 7, 3, 4, 0, tzinfo=UTC),
                basis="BID",
                price_type="bid",
            ),
        ]
    )

    result = _run_target(definition, pool, run_definition)

    event = result.events[0]
    assert event.outcome == "BLOCKED"
    assert event.price_evidence_refs == []
    trace = event.evidence_selection_trace[0]
    assert trace["rejected_reasons"] == {
        "FILL_PRICE_POLICY_MISMATCH": 1,
        "PRICE_BASIS_MISMATCH": 1,
    }


def test_engine2_fallback_cannot_bypass_the_fill_price_policy() -> None:
    target = _explicit_target(
        "da",
        ["SAP"],
        tenor="day-ahead",
        start=_FILL_TARGET_START,
        end=_FILL_TARGET_END,
        basis="ASSESSMENT",
    )
    definition = _definition(_component(targets=[target], intraday_names=None))
    run_definition = _run_definition(
        JUL1,
        JUL2,
        policy=MissingDataPolicy.USE_APPROVED_FALLBACK_SOURCE,
        fill_price_policy=FillPricePolicy.ASSESSMENT,
        fallback_sources={"SAP": "EEX_DAY_AHEAD"},
    )

    # Correct declared identity, but the legacy fill timing is a MID-like row:
    # the configured fallback must not be renamed into SAP.
    refused = _run_target(
        definition,
        _fill_pool(
            basis="ASSESSMENT",
            price_type="mid",
            observation_id="eex-mid",
            price_name="EEX_DAY_AHEAD",
            source_system="EEX_DAY_AHEAD",
        ),
        run_definition,
    )
    assert "FALLBACK_SOURCE_MISSING:SAP" in refused.events[0].missing_inputs

    accepted = _run_target(
        definition,
        _fill_pool(
            basis="ASSESSMENT",
            price_type="assessment",
            observation_id="eex-ok",
            price_name="EEX_DAY_AHEAD",
            source_system="EEX_DAY_AHEAD",
        ),
        run_definition,
    )
    assert accepted.events[0].price_evidence_refs == [
        "fallback:EEX_DAY_AHEAD->SAP:EEX_DAY_AHEAD:eex-ok"
    ]
    assert "SOURCE_FALLBACK_USED:SAP" in accepted.events[0].warnings


# --- schema-level conditional fields ----------------------------------------


def test_a_rolling_target_serializes_without_explicit_endpoints() -> None:
    target = StrategyEvidenceTarget.model_validate(
        _gas_day_target("da", ["SAP"], tenor="day-ahead", offset=1)
    )
    stored = target.model_dump(mode="json")
    assert "delivery_start_utc" not in stored
    assert "delivery_end_utc" not in stored
    assert stored["calendar_id"] == "EU-CAM-UTC-2025"
    assert stored["gas_day_offset"] == 1
    assert StrategyEvidenceTarget.model_validate(stored) == target


def test_an_explicit_target_does_not_gain_calendar_fields() -> None:
    target = StrategyEvidenceTarget.model_validate(_CARRY_TARGET)
    stored = target.model_dump(mode="json")
    assert "calendar_id" not in stored
    assert "gas_day_offset" not in stored


def test_component_required_names_are_read_from_the_declaration_map() -> None:
    component = StrategyComponentSpec.model_validate(
        _component(
            targets=[
                _gas_day_target("da", ["SAP"], tenor="day-ahead", offset=0),
                _gas_day_target("id", ["ICE_OCM"], tenor="within-day", offset=0),
            ]
        )
    )
    from eurogas_nexus.domain.backtest.target_selection import (
        component_declaration_gaps,
        required_price_names,
    )

    assert required_price_names(component) == ["SAP", "ICE_OCM"]
    assert component_declaration_gaps(component) == []
