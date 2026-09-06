"""Domain tests for versioned strategy registry and run manifests."""

from datetime import UTC, datetime

from eurogas_nexus.domain.strategy_lab.registry import (
    RUN_SCHEMA_VERSION,
    STRATEGY_SCHEMA_VERSION,
    StrategyComponentSpec,
    StrategyRunManifest,
    StrategyRunType,
    StrategyVersionDefinition,
    StrategyVersionStatus,
    valid_version_transition,
)


def test_version_definition_hash_is_deterministic_and_semantic() -> None:
    first = StrategyVersionDefinition(
        components=[
            StrategyComponentSpec(
                component_id="ocm-da",
                component_type="OCM_VS_DAY_AHEAD",
                extension_json={"weight": 1.0},
            )
        ]
    )
    second = StrategyVersionDefinition(
        components=[
            StrategyComponentSpec(
                component_id="ocm-da",
                component_type="OCM_VS_DAY_AHEAD",
                extension_json={"weight": 1.0},
            )
        ]
    )

    assert first.content_hash() == second.content_hash()
    assert first.content_hash().startswith("sha256:")


def test_run_manifest_hash_covers_strategy_version_evidence_and_time_boundary() -> None:
    manifest = StrategyRunManifest(
        run_id="run-1",
        run_type=StrategyRunType.EVALUATION,
        run_mode="SHADOW_RUN",
        strategy_id="strategy-1",
        strategy_name="NBP spread",
        strategy_version_id="strategy-version-1",
        version_number=3,
        strategy_version_content_hash="sha256:version",
        strategy_definition={"components": [{"component_id": "c1"}]},
        parameters={"weight": 1.0},
        assumptions={"missing_data_policy": "BLOCK_OR_PARTIAL"},
        evidence={"dataset_snapshot_id": "snapshot-1"},
        time_boundary={"data_cutoff_utc": "2026-07-01T12:00:00Z"},
        evaluation_start_utc=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        evaluation_end_utc=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        data_cutoff_utc=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        dataset_snapshot_id="snapshot-1",
        source_refs=["ice:ocm"],
        resource_snapshot_refs=["res-1"],
        engine_version="strategy-lab-evaluator/v1",
        application_version="0.5.0",
        git_commit_sha="abc123",
        deterministic_seed="seed-1",
    )

    payload = manifest.model_dump(mode="json")

    assert payload["run_id"] == "run-1"
    assert payload["strategy_version_content_hash"] == "sha256:version"
    assert payload["strategy_definition"]["components"][0]["component_id"] == "c1"
    assert payload["evidence"]["dataset_snapshot_id"] == "snapshot-1"
    assert payload["time_boundary"]["data_cutoff_utc"] == "2026-07-01T12:00:00Z"
    assert manifest.content_hash().startswith("sha256:")


def test_valid_version_transition_never_mutates_frozen_definitions() -> None:
    assert valid_version_transition(
        StrategyVersionStatus.DRAFT, StrategyVersionStatus.FROZEN
    )
    assert valid_version_transition(
        StrategyVersionStatus.FROZEN, StrategyVersionStatus.RETIRED
    )
    assert not valid_version_transition(
        StrategyVersionStatus.FROZEN, StrategyVersionStatus.FROZEN
    )
    assert not valid_version_transition(
        StrategyVersionStatus.FROZEN, StrategyVersionStatus.DRAFT
    )


def test_schema_version_constants_are_pinned() -> None:
    assert STRATEGY_SCHEMA_VERSION == "strategy-definition/v1"
    assert RUN_SCHEMA_VERSION == "strategy-run-manifest/v1"
