"""The agent capability path cannot bypass the CR-04 backtest rules.

``backtest.run`` goes through the same ``execute_backtest_run`` service as the
HTTP route, so an undeclared frozen definition arrives as a structured BLOCKED
result carrying the stable code - not as an escaping internal error and never as
a successful legacy run. A completely declared definition runs engine/2 and
persists engine/2 provenance through the same capability.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord
from eurogas_nexus.db.repositories import strategy_registry as repo
from eurogas_nexus.domain.agents.contracts import (
    AgentInvocationContext,
    CapabilityFailureCode,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyEvidenceTarget,
    StrategyVersionDefinition,
)

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def _runtime() -> CapabilityRuntime:
    from eurogas_nexus.application.agents.capability_handlers import (
        register_core_capabilities,
    )
    from eurogas_nexus.application.agents.registry import CapabilityRegistry
    from eurogas_nexus.application.agents.research_handlers import (
        register_research_capabilities,
    )

    registry = CapabilityRegistry()
    register_core_capabilities(registry)
    register_research_capabilities(registry)
    return CapabilityRuntime(registry)


def _analyst() -> AgentInvocationContext:
    return AgentInvocationContext(
        principal_id="analyst-1",
        role="ANALYST",
        roles=["ANALYST"],
        data_scopes=["*"],
    )


def _target(leg_id: str, name: str, tenor: str) -> StrategyEvidenceTarget:
    return StrategyEvidenceTarget.model_validate(
        {
            "leg_id": leg_id,
            "price_names": [name],
            "role": "DELIVERY_PRICE",
            "hub": "NBP",
            "tenor": tenor,
            "price_basis": "MID",
            "target_basis": "GAS_DAY",
            "calendar_id": "EU-CAM-UTC-2025",
            "gas_day_offset": 0,
        }
    )


def _frozen_version(database_url: str, *, declared: bool = False) -> str:
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    targets = (
        [_target("day_ahead", "SAP", "day-ahead"), _target("intraday", "ICE_OCM", "within-day")]
        if declared
        else None
    )
    with Session(engine) as session:
        from eurogas_nexus.db.repositories.identity import create_identity_principal

        owner = create_identity_principal(
            session,
            name="analyst-1",
            display_name="Analyst 1",
            role="ANALYST",
            data_scopes=["*"],
            now_utc=NOW,
        )
        owner.principal_id = "analyst-1"
        session.flush()
        repo.create_strategy(
            session,
            strategy_id="agent-target-guard",
            name="Agent target guard",
            description="CR-04 guard on the capability path",
            created_by="analyst-1",
            owner_principal_id="analyst-1",
            now_utc=NOW,
        )
        version = repo.create_strategy_version(
            session,
            strategy_id="agent-target-guard",
            definition=StrategyVersionDefinition(
                components=[
                    StrategyComponentSpec(
                        component_id="ocm-da-1",
                        component_type="OCM_VS_DAY_AHEAD",
                        hubs=["NBP"],
                        extension_json={
                            "weight": 1.0,
                            "day_ahead_price_names": ["SAP"],
                            "intraday_price_names": ["ICE_OCM"],
                        },
                        evidence_targets=targets,
                    )
                ]
            ),
            hypothesis="no declaration" if not declared else "declared",
            created_by="analyst-1",
            now_utc=NOW,
            definition_overrides={
                "strategy_name": "Agent target guard",
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
            frozen_by="analyst-1",
            now_utc=NOW,
        )
        session.commit()
        return frozen.strategy_version_id


def _seed_gas_day_rows(database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        for day in (6, 7):
            start = datetime(2026, 10, day, 4, 0, tzinfo=UTC)
            end = datetime(2026, 10, day + 1, 4, 0, tzinfo=UTC)
            observed = datetime(2026, 10, day, 4, 30, tzinfo=UTC)
            for name, price, tenor in (
                ("SAP", 25.0 + day, "day-ahead"),
                ("ICE_OCM", 30.0 + day, "within-day"),
            ):
                session.add(
                    MarketObservationRecord(
                        observation_id=f"agent-{name}-{day}",
                        market_venue=name,
                        product=f"NBP {tenor}",
                        price=price,
                        unit="GBP/MWh",
                        currency="GBP",
                        period_start_utc=start,
                        period_end_utc=end,
                        observed_at_utc=observed,
                        source_system=f"{name}_Sim",
                        source_reference=f"agent:{name}:{day}",
                        freshness="simulated_live",
                        quality_score=0.6,
                        research_only=True,
                        metadata_json={
                            "hub": "NBP",
                            "tenor": tenor,
                            "evidence_role": "DELIVERY_PRICE",
                            "price_basis": "MID",
                            "simulated": True,
                        },
                    )
                )
        session.commit()


def test_the_agent_backtest_capability_reports_the_service_refusal(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'agent-guard.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    version_id = _frozen_version(database_url)

    result = _runtime().invoke(
        "backtest.run",
        {
            "strategy_version_id": version_id,
            "period_start_utc": (NOW - timedelta(days=3)).isoformat(),
            "period_end_utc": (NOW - timedelta(days=1)).isoformat(),
        },
        _analyst(),
    )

    assert result.status == "BLOCKED"
    assert result.failure is not None
    assert result.failure.code == CapabilityFailureCode.BACKTEST_BLOCKED
    assert "target_delivery_not_declared" in (result.failure.detail or "")


def test_the_agent_backtest_capability_runs_a_declared_engine2_mapping(
    tmp_path, monkeypatch
) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'agent-declared.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    version_id = _frozen_version(database_url, declared=True)
    _seed_gas_day_rows(database_url)

    result = _runtime().invoke(
        "backtest.run",
        {
            "strategy_version_id": version_id,
            "period_start_utc": (NOW - timedelta(days=3)).isoformat(),
            "period_end_utc": (NOW - timedelta(days=1)).isoformat(),
        },
        _analyst(),
    )

    assert result.status == "SUCCESS", result.failure
    payload = result.data
    assert payload["backtest_engine_version"] == "backtest-engine/2"
    assert payload["backtest_metrics"]["candidate_decision_count"] == 2
    assert payload["backtest_metrics"]["events_reusing_admitted_price_refs"] == 0
