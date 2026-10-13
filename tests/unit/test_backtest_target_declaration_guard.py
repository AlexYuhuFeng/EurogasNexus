"""CR-04 target-declaration guard and engine/2 enablement for BACKTEST runs.

The amendment requires historical evidence selection to resolve an explicit
per-leg delivery target. An *undeclared* frozen definition is still refused
before any evidence pool load, snapshot or run row, with the stable
``target_delivery_not_declared`` code. A *completely declared* definition is now
executable: it runs the target-aware engine/2 and persists engine/2 provenance,
rather than the legacy engine/1 selection.

The guard reads the frozen ``definition_json`` only. A request may not supply
the declaration, and no test-only bypass executes the legacy service semantics
the guard exists to stop.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.backtest_service import (
    TARGET_COMPONENT_SCOPE_UNSUPPORTED,
    TARGET_DELIVERY_NOT_DECLARED,
    TARGET_EVIDENCE_MAPPING_AMBIGUOUS,
    BacktestTemporalTargetError,
    execute_backtest_run,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    BacktestDecisionEventRecord,
    StrategyDataSnapshotRecord,
    StrategyRunRecord,
)
from eurogas_nexus.db.repositories import strategy_registry as repo
from eurogas_nexus.domain.backtest.contracts import (
    BacktestEconomicAssumptions,
    BacktestPeriod,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.ontology.vocabulary import MissingDataPolicy
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyEvidenceTarget,
    StrategyVersionDefinition,
)

REQUESTED_AT = datetime(2026, 10, 7, 16, 0, tzinfo=UTC)

_DECLARED_TARGETS = [
    StrategyEvidenceTarget.model_validate(
        {
            "leg_id": "day_ahead",
            "price_names": ["SAP"],
            "role": "DELIVERY_PRICE",
            "hub": "NBP",
            "tenor": "day-ahead",
            "price_basis": "MID",
            "target_basis": "EXPLICIT_INTERVAL",
            "delivery_start_utc": "2026-09-30T05:00:00Z",
            "delivery_end_utc": "2026-10-01T05:00:00Z",
        }
    ),
    StrategyEvidenceTarget.model_validate(
        {
            "leg_id": "intraday",
            "price_names": ["ICE_OCM"],
            "role": "DELIVERY_PRICE",
            "hub": "NBP",
            "tenor": "within-day",
            "price_basis": "MID",
            "target_basis": "EXPLICIT_INTERVAL",
            "delivery_start_utc": "2026-09-30T05:00:00Z",
            "delivery_end_utc": "2026-10-01T05:00:00Z",
        }
    ),
]


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _definition(*, targets: list[StrategyEvidenceTarget] | None) -> StrategyVersionDefinition:
    return StrategyVersionDefinition(
        components=[
            StrategyComponentSpec(
                component_id="ocm-da",
                component_type="OCM_VS_DAY_AHEAD",
                hubs=["NBP"],
                extension_json={
                    "weight": 1.0,
                    "day_ahead_price_names": ["SAP"],
                    "intraday_price_names": ["ICE_OCM"],
                    "positive_spread_threshold_gbp_mwh": 0.0,
                    "negative_spread_threshold_gbp_mwh": 0.0,
                    "target_bar_minutes": 5,
                },
                evidence_targets=targets,
            )
        ]
    )


def _two_component_definition(
    targets: list[StrategyEvidenceTarget] | None,
) -> StrategyVersionDefinition:
    """Two OCM components reusing the same price names.

    The engine flattens every component's observations and evaluates by
    ``price_name``, so this shape could cross-pollinate; the bounded first
    engine/2 must refuse it rather than pretend a per-component engine exists.
    """

    def component(component_id: str) -> StrategyComponentSpec:
        return StrategyComponentSpec(
            component_id=component_id,
            component_type="OCM_VS_DAY_AHEAD",
            hubs=["NBP"],
            extension_json={
                "weight": 1.0,
                "day_ahead_price_names": ["SAP"],
                "intraday_price_names": ["ICE_OCM"],
                "positive_spread_threshold_gbp_mwh": 0.0,
                "negative_spread_threshold_gbp_mwh": 0.0,
                "target_bar_minutes": 5,
            },
            evidence_targets=targets,
        )

    return StrategyVersionDefinition(components=[component("ocm-da"), component("ocm-da-2")])


def _ambiguous_role_definition(
    targets: list[StrategyEvidenceTarget] | None,
) -> StrategyVersionDefinition:
    """One name listed as both the day-ahead and the intraday leg."""

    return StrategyVersionDefinition(
        components=[
            StrategyComponentSpec(
                component_id="ocm-da",
                component_type="OCM_VS_DAY_AHEAD",
                hubs=["NBP"],
                extension_json={
                    "weight": 1.0,
                    "day_ahead_price_names": ["SAP"],
                    "intraday_price_names": ["sap"],
                    "positive_spread_threshold_gbp_mwh": 0.0,
                    "negative_spread_threshold_gbp_mwh": 0.0,
                    "target_bar_minutes": 5,
                },
                evidence_targets=targets,
            )
        ]
    )


def _frozen_version(
    session: Session,
    *,
    targets: list[StrategyEvidenceTarget] | None,
    definition: StrategyVersionDefinition | None = None,
):
    created = datetime(2026, 9, 5, tzinfo=UTC)
    repo.create_strategy(
        session,
        strategy_id="target-guard-strategy",
        name="Target guard strategy",
        description="CR-04 phase 1 guard",
        created_by="operator",
        now_utc=created,
    )
    version = repo.create_strategy_version(
        session,
        strategy_id="target-guard-strategy",
        definition=definition or _definition(targets=targets),
        hypothesis="guard",
        created_by="operator",
        now_utc=created,
        definition_overrides={
            "strategy_name": "Target guard strategy",
            "run_mode": "BACKTEST",
            "resource_contexts": [
                {
                    "resource_id": "r1",
                    "resource_name": "Resource 1",
                    "available_quantity_mwh_per_day": 100.0,
                    "all_in_cost_gbp_mwh": 20.0,
                    "required_tso_access": [],
                }
            ],
            "price_observations": [],
            "existing_shadow_pnl_gbp": 0.0,
        },
    )
    frozen = repo.freeze_strategy_version(
        session,
        strategy_version_id=version.strategy_version_id,
        frozen_by="operator",
        now_utc=created,
    )
    session.flush()
    return frozen


def _run_definition(start: datetime, end: datetime) -> BacktestRunDefinition:
    return BacktestRunDefinition(
        strategy_version_id="unused",
        period=BacktestPeriod(start_utc=start, end_utc=end),
        economic_assumptions=BacktestEconomicAssumptions(
            missing_data_policy=MissingDataPolicy.FAIL,
        ),
    )


def _historical_run_definition() -> BacktestRunDefinition:
    return _run_definition(REQUESTED_AT - timedelta(days=3), REQUESTED_AT - timedelta(days=1))


def _assert_no_writes(session: Session) -> None:
    assert session.query(StrategyRunRecord).count() == 0
    assert session.query(StrategyDataSnapshotRecord).count() == 0


def test_an_undeclared_frozen_definition_is_refused_with_a_stable_code() -> None:
    with Session(_engine()) as session:
        version = _frozen_version(session, targets=None)

        with pytest.raises(BacktestTemporalTargetError) as refused:
            execute_backtest_run(
                session,
                version=version,
                definition=_historical_run_definition(),
                requested_by="operator",
                requested_at_utc=REQUESTED_AT,
            )

        assert refused.value.code == TARGET_DELIVERY_NOT_DECLARED
        message = str(refused.value)
        assert "fork" in message.lower()
        assert "declare" in message.lower()
        # The refusal is before the evidence pool load and any write.
        _assert_no_writes(session)


def test_an_empty_declaration_is_not_authorization() -> None:
    with Session(_engine()) as session:
        version = _frozen_version(session, targets=[])

        with pytest.raises(BacktestTemporalTargetError) as refused:
            execute_backtest_run(
                session,
                version=version,
                definition=_historical_run_definition(),
                requested_by="operator",
                requested_at_utc=REQUESTED_AT,
            )

        assert refused.value.code == TARGET_DELIVERY_NOT_DECLARED
        _assert_no_writes(session)


def test_a_partially_declared_definition_is_refused_and_names_the_missing_leg() -> None:
    with Session(_engine()) as session:
        version = _frozen_version(session, targets=[_DECLARED_TARGETS[0]])

        with pytest.raises(BacktestTemporalTargetError) as refused:
            execute_backtest_run(
                session,
                version=version,
                definition=_historical_run_definition(),
                requested_by="operator",
                requested_at_utc=REQUESTED_AT,
            )

        assert refused.value.code == TARGET_DELIVERY_NOT_DECLARED
        assert "ICE_OCM" in str(refused.value)
        _assert_no_writes(session)


def test_a_fully_declared_definition_now_runs_engine2_and_persists() -> None:
    # Declared is executable: the frozen mapping runs the target-aware engine/2
    # and persists engine/2 provenance. (This fixture has no evidence rows, so
    # every decision is honestly BLOCKED with a missing-series reason rather
    # than silently reusing engine/1.)
    with Session(_engine()) as session:
        version = _frozen_version(session, targets=list(_DECLARED_TARGETS))

        run = execute_backtest_run(
            session,
            version=version,
            definition=_historical_run_definition(),
            requested_by="operator",
            requested_at_utc=REQUESTED_AT,
        )

        assert run.status == "BLOCKED"
        assert run.backtest_engine_version == "backtest-engine/2"
        assert run.manifest_json["backtest_engine_version"] == "backtest-engine/2"
        assert (
            run.manifest_json["evidence"]["evidence_selection"]["rules_version"]
            == "target-evidence-selection/v1"
        )
        assert session.query(StrategyRunRecord).count() == 1
        assert session.query(StrategyDataSnapshotRecord).count() == 1
        events = session.query(BacktestDecisionEventRecord).all()
        assert events
        assert "DELIVERY_TARGET_EXPIRED:SAP" in events[0].missing_inputs
        # The resolved target and refusal reason are persisted in the existing
        # event JSON, not fabricated as cost rows.
        assert events[0].attribution[-1]["dimension"] == "evidence_selection"


def test_a_malformed_frozen_definition_is_refused_not_guessed() -> None:
    with Session(_engine()) as session:
        version = _frozen_version(session, targets=list(_DECLARED_TARGETS))
        # Simulate stored corruption: the declaration is present but unreadable.
        version.definition_json = {
            **(version.definition_json or {}),
            "components": [
                {
                    "component_id": "ocm-da",
                    "component_type": "OCM_VS_DAY_AHEAD",
                    "evidence_targets": [{"leg_id": ""}],
                }
            ],
        }
        session.flush()

        with pytest.raises(BacktestTemporalTargetError) as refused:
            execute_backtest_run(
                session,
                version=version,
                definition=_historical_run_definition(),
                requested_by="operator",
                requested_at_utc=REQUESTED_AT,
            )

        assert refused.value.code == TARGET_DELIVERY_NOT_DECLARED
        _assert_no_writes(session)


def test_the_future_window_refusal_still_wins_over_the_target_guard() -> None:
    # A window that has not happened is invalid regardless of declarations, and
    # the existing guard runs first.
    with Session(_engine()) as session:
        version = _frozen_version(session, targets=None)

        with pytest.raises(ValueError) as refused:
            execute_backtest_run(
                session,
                version=version,
                definition=_run_definition(
                    REQUESTED_AT - timedelta(days=1), REQUESTED_AT + timedelta(days=3)
                ),
                requested_by="operator",
                requested_at_utc=REQUESTED_AT,
            )

        assert not isinstance(refused.value, BacktestTemporalTargetError)
        assert "after the request time" in str(refused.value)
        _assert_no_writes(session)


def test_the_guard_reads_the_frozen_record_not_the_request() -> None:
    # The run definition carries no declaration field at all; the only source
    # is the frozen row, so a caller cannot authorize a legacy run by request.
    with Session(_engine()) as session:
        version = _frozen_version(session, targets=None)
        definition = _historical_run_definition()
        assert not hasattr(definition, "evidence_targets")

        with pytest.raises(BacktestTemporalTargetError) as refused:
            execute_backtest_run(
                session,
                version=version,
                definition=definition,
                requested_by="operator",
                requested_at_utc=REQUESTED_AT,
            )

        assert refused.value.code == TARGET_DELIVERY_NOT_DECLARED


def test_multiple_components_are_refused_as_unsupported_scope_before_any_write() -> None:
    # Bounded first engine/2: the engine flattens observations across components
    # and evaluates by price_name, so a second component reusing a name with a
    # different hub/target could cross-pollinate. Refuse rather than claim a
    # per-component engine that is not built.
    with Session(_engine()) as session:
        version = _frozen_version(
            session,
            targets=None,
            definition=_two_component_definition(list(_DECLARED_TARGETS)),
        )

        with pytest.raises(BacktestTemporalTargetError) as refused:
            execute_backtest_run(
                session,
                version=version,
                definition=_historical_run_definition(),
                requested_by="operator",
                requested_at_utc=REQUESTED_AT,
            )

        assert refused.value.code == TARGET_COMPONENT_SCOPE_UNSUPPORTED
        message = str(refused.value)
        assert "one" in message.lower()
        assert "OCM_VS_DAY_AHEAD" in message
        _assert_no_writes(session)


def test_a_name_in_two_leg_roles_is_refused_as_ambiguous_before_any_write() -> None:
    # The evaluation keys evidence by price_name; the same name as both the
    # day-ahead and the intraday leg cannot be represented, so it is refused
    # before any evidence pool or run row exists.
    with Session(_engine()) as session:
        version = _frozen_version(
            session,
            targets=None,
            definition=_ambiguous_role_definition(list(_DECLARED_TARGETS)),
        )

        with pytest.raises(BacktestTemporalTargetError) as refused:
            execute_backtest_run(
                session,
                version=version,
                definition=_historical_run_definition(),
                requested_by="operator",
                requested_at_utc=REQUESTED_AT,
            )

        assert refused.value.code == TARGET_EVIDENCE_MAPPING_AMBIGUOUS
        assert "SAP" in str(refused.value)
        _assert_no_writes(session)
