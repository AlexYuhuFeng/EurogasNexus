"""Repository and orchestration tests for the versioned strategy registry."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    StrategyRunRecord,
    StrategyVersionRecord,
)
from eurogas_nexus.db.repositories import strategy_registry as repo
from eurogas_nexus.db.repositories.strategy import strategy_run_payload
from eurogas_nexus.domain.strategy_lab.registry import (
    STRATEGY_SCHEMA_VERSION,
    StrategyComponentSpec,
    StrategyRunManifest,
    StrategyVersionDefinition,
    canonical_content_hash,
)
from eurogas_nexus.domain.strategy_lab.run_orchestration import (
    StrategyVersionExecutionError,
    evaluation_scenario_from_version,
    execute_evaluation_run,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _definition(*, include_execution_fields: bool = False) -> dict:
    definition = StrategyVersionDefinition(
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
                    "time_window_start": "05:00",
                    "time_window_end": "05:30",
                },
            )
        ]
    )
    stored = definition.model_dump(mode="json")
    if include_execution_fields:
        now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
        stored.update(
            {
                "strategy_name": "NBP OCM vs day-ahead",
                "run_mode": "SHADOW_RUN",
                "resource_contexts": [
                    {
                        "resource_id": "res-1",
                        "resource_name": "Resource 1",
                        "available_quantity_mwh_per_day": 100.0,
                        "all_in_cost_gbp_mwh": 20.0,
                        "required_tso_access": [],
                        "company_accessible_tsos": None,
                    }
                ],
                "price_observations": [
                    {
                        "observation_id": "ice-ocm-1",
                        "source_system": "ICE",
                        "venue": "OCM",
                        "hub": "NBP",
                        "product": "NBP Within-Day",
                        "price_name": "ICE_OCM",
                        "price_gbp_mwh": 30.0,
                        "observed_at_utc": (now - timedelta(hours=1)).isoformat(),
                        "delivery_start_utc": now.isoformat(),
                        "delivery_end_utc": (now + timedelta(hours=24)).isoformat(),
                        "bar_minutes": 5,
                        "source_reference": "ice-ocm:1",
                    },
                    {
                        "observation_id": "sap-da-1",
                        "source_system": "SAP",
                        "venue": "NBP",
                        "hub": "NBP",
                        "product": "NBP Day-Ahead",
                        "price_name": "SAP",
                        "price_gbp_mwh": 25.0,
                        "observed_at_utc": (now - timedelta(hours=1)).isoformat(),
                        "delivery_start_utc": now.isoformat(),
                        "delivery_end_utc": (now + timedelta(hours=24)).isoformat(),
                        "bar_minutes": None,
                        "source_reference": "sap:nbp:1",
                    },
                ],
                "existing_shadow_pnl_gbp": 0.0,
            }
        )
    return stored


def _create_frozen_version(
    session: Session, strategy_id: str = "strategy-1"
) -> StrategyVersionRecord:
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    repo.create_strategy(
        session,
        strategy_id=strategy_id,
        name="NBP spread",
        description="research",
        created_by="operator",
        now_utc=now,
    )
    version = repo.create_strategy_version(
        session,
        strategy_id=strategy_id,
        definition=StrategyVersionDefinition.model_validate(_definition()),
        hypothesis="intraday premium",
        created_by="operator",
        now_utc=now,
        definition_overrides={
            "strategy_name": "NBP OCM vs day-ahead",
            "run_mode": "SHADOW_RUN",
            "resource_contexts": [
                {
                    "resource_id": "res-1",
                    "resource_name": "Resource 1",
                    "available_quantity_mwh_per_day": 100.0,
                    "all_in_cost_gbp_mwh": 20.0,
                    "required_tso_access": [],
                    "company_accessible_tsos": None,
                }
            ],
            "price_observations": [
                {
                    "observation_id": "ice-ocm-1",
                    "source_system": "ICE",
                    "venue": "OCM",
                    "hub": "NBP",
                    "product": "NBP Within-Day",
                    "price_name": "ICE_OCM",
                    "price_gbp_mwh": 30.0,
                    "observed_at_utc": (now - timedelta(hours=1)).isoformat(),
                    "delivery_start_utc": now.isoformat(),
                    "delivery_end_utc": (now + timedelta(hours=24)).isoformat(),
                    "bar_minutes": 5,
                    "source_reference": "ice-ocm:1",
                },
                {
                    "observation_id": "sap-da-1",
                    "source_system": "SAP",
                    "venue": "NBP",
                    "hub": "NBP",
                    "product": "NBP Day-Ahead",
                    "price_name": "SAP",
                    "price_gbp_mwh": 25.0,
                    "observed_at_utc": (now - timedelta(hours=1)).isoformat(),
                    "delivery_start_utc": now.isoformat(),
                    "delivery_end_utc": (now + timedelta(hours=24)).isoformat(),
                    "bar_minutes": None,
                    "source_reference": "sap:nbp:1",
                },
            ],
            "existing_shadow_pnl_gbp": 0.0,
        },
    )
    return repo.freeze_strategy_version(
        session,
        strategy_version_id=version.strategy_version_id,
        frozen_by="operator",
        now_utc=now,
    )


def test_strategy_version_immutable_and_current_pointer(session) -> None:
    version = _create_frozen_version(session)
    strategy = repo.get_strategy(session, "strategy-1")

    assert strategy is not None
    assert strategy.current_version_id == version.strategy_version_id
    assert version.status == "FROZEN"
    assert version.frozen_at_utc is not None
    assert version.content_hash == canonical_content_hash(version.definition_json)
    assert version.definition_json["resource_contexts"][0]["resource_id"] == "res-1"

    with pytest.raises(repo.StrategyRegistryError):
        repo.freeze_strategy_version(
            session,
            strategy_version_id=version.strategy_version_id,
            frozen_by="operator",
            now_utc=datetime.now(UTC),
        )


def test_fork_preserves_full_frozen_definition_and_parent(session) -> None:
    source = _create_frozen_version(session)
    fork = repo.fork_strategy_version(
        session,
        source_version_id=source.strategy_version_id,
        definition=None,
        hypothesis="forked",
        created_by="operator",
        now_utc=datetime.now(UTC),
    )

    assert fork.version_number == 2
    assert fork.parent_version_id == source.strategy_version_id
    assert fork.definition_json == source.definition_json
    assert fork.status == "DRAFT"

    with pytest.raises(repo.StrategyRegistryError):
        repo.fork_strategy_version(
            session,
            source_version_id=fork.strategy_version_id,
            definition=None,
            hypothesis=None,
            created_by="operator",
            now_utc=datetime.now(UTC),
        )


def test_professional_run_records_complete_reproducibility_contract(session) -> None:
    version = _create_frozen_version(session)
    requested_at = datetime(2026, 7, 1, 10, 5, tzinfo=UTC)

    run = execute_evaluation_run(
        session,
        version=version,
        requested_by="operator",
        run_id="run-1",
        requested_at_utc=requested_at,
        deterministic_seed="seed-1",
        trigger_type="MANUAL",
        correlation_request_id="corr-1",
    )

    assert run.strategy_version_id == version.strategy_version_id
    assert run.run_type == "EVALUATION"
    assert run.status == "SUCCESS"
    assert run.research_only is True
    assert run.human_review_required is True
    assert run.manifest_json is not None
    assert run.manifest_hash is not None
    assert run.dataset_snapshot_id is not None

    manifest = StrategyRunManifest.model_validate(run.manifest_json)
    assert manifest.content_hash() == run.manifest_hash
    assert manifest.strategy_version_content_hash == version.content_hash
    assert manifest.strategy_definition == version.definition_json
    assert manifest.parameters == version.definition_json
    assert manifest.evidence["dataset_snapshot_id"] == run.dataset_snapshot_id
    assert manifest.time_boundary["data_cutoff_utc"].startswith("2026-07-01T09:00")
    assert manifest.requested_by == "operator"
    assert manifest.correlation_request_id == "corr-1"

    payload = strategy_run_payload(run)
    assert payload["strategy_version_id"] == version.strategy_version_id
    assert payload["run_type"] == "EVALUATION"
    assert payload["manifest_json"] == run.manifest_json
    assert payload["manifest_hash"] == run.manifest_hash
    assert payload["engine_version"]
    assert payload["application_version"]
    assert payload["strategy_schema_version"] == STRATEGY_SCHEMA_VERSION


def test_execute_rejects_draft_versions(session) -> None:
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    repo.create_strategy(
        session,
        strategy_id="strategy-draft",
        name="Draft strategy",
        description="",
        created_by="operator",
        now_utc=now,
    )
    version = repo.create_strategy_version(
        session,
        strategy_id="strategy-draft",
        definition=StrategyVersionDefinition.model_validate(_definition()),
        hypothesis="",
        created_by="operator",
        now_utc=now,
        definition_overrides=_definition(include_execution_fields=True),
    )

    with pytest.raises(StrategyVersionExecutionError):
        execute_evaluation_run(session, version=version, requested_by="operator")


def test_legacy_run_payload_exposes_new_provenance_as_null(session) -> None:
    session.add(
        StrategyRunRecord(
            run_id="legacy-run",
            strategy_id="legacy-strategy",
            run_mode="SHADOW_RUN",
            status="SUCCESS",
            started_at_utc=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
            input_snapshot={"strategy_name": "legacy"},
            result_snapshot={"paper_pnl_gbp": 1.0},
            source_refs=[],
            warnings=[],
            missing_inputs=[],
            research_only=True,
            human_review_required=True,
        )
    )
    session.flush()
    from sqlalchemy import update

    session.execute(
        update(StrategyRunRecord).where(StrategyRunRecord.run_id == "legacy-run").values(
            run_type=None
        )
    )
    session.flush()
    session.expire_all()

    payload = strategy_run_payload(session.get(StrategyRunRecord, "legacy-run"))

    assert payload["strategy_version_id"] is None
    assert payload["run_type"] is None
    assert payload["manifest_json"] is None
    assert payload["manifest_hash"] is None



def test_typed_risk_controls_are_honoured_and_unknown_component_fails_closed(
    session,
) -> None:
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    definition = StrategyVersionDefinition.model_validate(_definition())
    definition.risk_controls.max_ocm_allocation_pct = 60.0
    definition.risk_controls.min_day_ahead_allocation_pct = 40.0
    execution_fields = _definition(include_execution_fields=True)
    payload = definition.model_dump(mode="json")
    for key in (
        "strategy_name",
        "run_mode",
        "resource_contexts",
        "price_observations",
        "existing_shadow_pnl_gbp",
    ):
        payload[key] = execution_fields[key]
    version = StrategyVersionRecord(
        strategy_version_id="strategy-version-typed-risk",
        strategy_id="strategy-typed-risk",
        version_number=1,
        schema_version=STRATEGY_SCHEMA_VERSION,
        status="FROZEN",
        hypothesis="",
        definition_json=payload,
        parent_version_id=None,
        created_by="operator",
        created_at_utc=now,
        frozen_at_utc=now,
        content_hash=canonical_content_hash(payload),
        research_only=True,
    )

    scenario = evaluation_scenario_from_version(version)
    assert scenario.risk_control.max_ocm_allocation_pct == 60.0
    assert scenario.risk_control.min_day_ahead_allocation_pct == 40.0

    unknown = StrategyVersionRecord(
        strategy_version_id="strategy-version-unknown-component",
        strategy_id="strategy-unknown-component",
        version_number=1,
        schema_version=STRATEGY_SCHEMA_VERSION,
        status="FROZEN",
        hypothesis="",
        definition_json={
            "components": [{"component_id": "c1", "component_type": "HUB_SPREAD"}]
        },
        parent_version_id=None,
        created_by="operator",
        created_at_utc=now,
        frozen_at_utc=now,
        content_hash="sha256:unknown",
        research_only=True,
    )

    with pytest.raises(StrategyVersionExecutionError):
        evaluation_scenario_from_version(unknown)