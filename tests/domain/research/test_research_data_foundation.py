"""CR-14 domain tests: ontology, temporal truth, datasets, leakage safety.

These tests pin the research data foundation semantics before any DB or HTTP
adapter exists. They are intentionally dependency-light.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from eurogas_nexus.domain.research.capabilities import (
    REGISTERED_RESEARCH_CAPABILITIES,
    CapabilityReadWriteClass,
)
from eurogas_nexus.domain.research.datasets import (
    DatasetEvidenceRecord,
    DatasetPointInTimePolicy,
    DatasetSpec,
    build_dataset,
)
from eurogas_nexus.domain.research.features import (
    FeatureAvailabilityClass,
    FeatureDefinition,
    feature_dependency_closure,
)
from eurogas_nexus.domain.research.leakage import LeakageValidator
from eurogas_nexus.domain.research.ontology import (
    ONTOLOGY_SCHEMA_VERSION,
    CanonicalEntityType,
    canonical_entity_id,
)
from eurogas_nexus.domain.research.resampling import (
    MissingDataPolicy,
    ResampledValue,
    ResamplingAggregation,
    ResamplingPolicy,
    bounded_resample,
)
from eurogas_nexus.domain.research.series import series_id_for
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind
from eurogas_nexus.domain.research.temporal import (
    DatasetMode,
    ObservationKind,
    TemporalIntegrityState,
    as_of_cutoff_for_origin,
    as_of_eligible,
    forecast_vintage_at,
)
from eurogas_nexus.domain.research.units import UnitConversion, convert_value


def _dt(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def _feature(
    feature_id: str,
    dependencies: list[str],
    *,
    availability: str = "DERIVED_AS_OF",
) -> FeatureDefinition:
    return FeatureDefinition(
        feature_id=feature_id,
        name=feature_id,
        description=f"Test feature {feature_id}.",
        category="market",
        input_dependencies=dependencies,
        output_unit="GBP/MWh",
        frequency="1h",
        availability_class=FeatureAvailabilityClass(availability),
        transformation=f"builtin:{feature_id}",
        transformation_version="v1",
        missing_data_policy="mask",
    )


def _target(target_id: str = "NBP_DA_PRICE_D1", *, horizon: str = "H1") -> TargetDefinition:
    return TargetDefinition(
        target_id=target_id,
        name=target_id,
        description=f"Test target {target_id}.",
        target_type=TargetKind.PRICE,
        entity_type="market_hub",
        entity_id="NBP",
        metric="NBP_DA_PRICE_D1",
        horizon=horizon,
        target_window="1h",
        unit="GBP/MWh",
        aggregation="first",
        label_calculation="first_observation_at_or_after_origin_plus_horizon",
    )


def _record(
    record_id: str,
    series_id: str,
    observed_at: datetime,
    *,
    available_at: datetime | None,
    value: float,
    kind: ObservationKind = ObservationKind.ACTUAL,
    integrity: TemporalIntegrityState = TemporalIntegrityState.TEMPORAL_VERIFIED,
    source_reference: str | None = None,
) -> DatasetEvidenceRecord:
    return DatasetEvidenceRecord(
        record_id=record_id,
        series_id=series_id,
        entity_id="ent:market_hub:NBP",
        observed_at=observed_at,
        available_at=available_at,
        ingested_at=available_at,
        value=value,
        unit="GBP/MWh",
        currency="GBP",
        observation_kind=kind,
        temporal_integrity=integrity,
        source_reference=source_reference or f"test:{record_id}",
    )


def _spec(
    *,
    features: list[FeatureDefinition],
    targets: list[TargetDefinition],
    mode: DatasetMode = DatasetMode.STRICT,
    start: datetime | None = None,
    end: datetime | None = None,
    entity_ids: list[str] | None = None,
) -> DatasetSpec:
    return DatasetSpec(
        dataset_spec_id="spec-test",
        name="Test point-in-time dataset",
        description="CR-14 test fixture.",
        target_ids=[target.target_id for target in targets],
        feature_ids=[feature.feature_id for feature in features],
        entity_ids=entity_ids
        or ["ent:market_hub:NBP", "ent:market_hub:TTF"],
        start=start or _dt(2026, 1, 1, 0),
        end=end or _dt(2026, 1, 1, 2),
        forecast_origin_frequency="1h",
        point_in_time_policy=DatasetPointInTimePolicy(mode=mode),
        minimum_coverage=0.0,
    )


def _sample_records() -> list[DatasetEvidenceRecord]:
    return [
        _record("nbp-00", "market.price.NBP.DAY_AHEAD", _dt(2026, 1, 1, 0),
                available_at=_dt(2026, 1, 1, 0), value=20.0),
        _record("ttf-00", "market.price.TTF.DAY_AHEAD", _dt(2026, 1, 1, 0),
                available_at=_dt(2026, 1, 1, 0), value=18.0),
        _record("nbp-01", "market.price.NBP.DAY_AHEAD", _dt(2026, 1, 1, 1),
                available_at=_dt(2026, 1, 1, 1), value=21.0),
        _record("ttf-01", "market.price.TTF.DAY_AHEAD", _dt(2026, 1, 1, 1),
                available_at=_dt(2026, 1, 1, 1), value=19.0),
        _record("nbp-02", "market.price.NBP.DAY_AHEAD", _dt(2026, 1, 1, 2),
                available_at=_dt(2026, 1, 1, 2), value=22.0),
        _record("ttf-02", "market.price.TTF.DAY_AHEAD", _dt(2026, 1, 1, 2),
                available_at=_dt(2026, 1, 1, 2), value=20.0),
    ]


def test_ontology_has_versioned_stable_canonical_identifiers() -> None:
    assert ONTOLOGY_SCHEMA_VERSION == "energy-ontology/v1"
    assert (
        canonical_entity_id(CanonicalEntityType.MARKET_HUB, "nbp")
        == "ent:market_hub:NBP"
    )
    assert canonical_entity_id("Market Hub", "TTF") == "ent:market_hub:TTF"
    with pytest.raises(ValueError):
        canonical_entity_id("market_hub", "  ")


def test_available_ingested_and_observed_are_distinct_temporal_facts() -> None:
    cutoff = _dt(2026, 1, 2, 0)
    available = _record(
        "available", "series", _dt(2026, 1, 1, 0),
        available_at=_dt(2026, 1, 1, 12), value=1,
    )
    future = _record(
        "future", "series", _dt(2026, 1, 1, 0),
        available_at=_dt(2026, 1, 2, 1), value=2,
    )
    # ingested_at is before the cutoff but must never be positive proof.
    future.ingested_at = _dt(2026, 1, 1, 0)
    missing = _record(
        "missing",
        "series",
        _dt(2026, 1, 1, 0),
        available_at=None,
        value=3,
        integrity=TemporalIntegrityState.TEMPORAL_APPROXIMATE,
    )

    assert as_of_eligible(available, cutoff) == (True, None)
    assert as_of_eligible(future, cutoff) == (
        False,
        "OBSERVATION_AVAILABLE_AFTER_CUTOFF",
    )
    assert as_of_eligible(missing, cutoff) == (
        False,
        "OBSERVATION_AVAILABILITY_UNKNOWN",
    )
    exploratory = as_of_eligible(
        missing,
        cutoff,
        policy=DatasetPointInTimePolicy(mode=DatasetMode.EXPLORATORY),
    )
    assert exploratory == (
        True,
        "OBSERVATION_AVAILABILITY_APPROXIMATED_FROM_OBSERVED_AT",
    )


def test_forecast_vintage_uses_latest_availability_not_latest_valid_time() -> None:
    older_available = _record(
        "v1",
        "market.price.TTF.DAY_AHEAD",
        _dt(2026, 1, 2, 0),
        available_at=_dt(2026, 1, 1, 9),
        value=18.0,
        kind=ObservationKind.FORECAST,
    )
    newer_available = _record(
        "v2",
        "market.price.TTF.DAY_AHEAD",
        _dt(2026, 1, 1, 12),
        available_at=_dt(2026, 1, 1, 10),
        value=17.5,
        kind=ObservationKind.FORECAST,
    )
    not_yet_available = _record(
        "v3",
        "market.price.TTF.DAY_AHEAD",
        _dt(2026, 1, 2, 3),
        available_at=_dt(2026, 1, 1, 11),
        value=17.0,
        kind=ObservationKind.FORECAST,
    )
    selected = forecast_vintage_at(
        forecasts=[older_available, newer_available, not_yet_available],
        cutoff=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
    )
    assert selected is not None
    assert selected.record_id == "v2"
    assert selected.value == 17.5


def test_cutoff_for_origin_is_versioned_deterministic() -> None:
    origin = _dt(2026, 1, 1, 6)
    assert as_of_cutoff_for_origin(
        origin, min_availability_delay_seconds=3600
    ) == _dt(2026, 1, 1, 5)


def test_series_identity_is_derived_from_semantic_fields() -> None:
    assert (
        series_id_for(
            metric_type="price",
            entity_type="market_hub",
            entity_id="NBP",
            product_id="DAY_AHEAD",
        )
        == "price.market_hub.nbp.day_ahead.observed"
    )


def test_unit_conversion_is_explicit_and_versioned() -> None:
    conversion = UnitConversion(
        conversion_id="conv-gj-mwh",
        method="multiply",
        source_unit="GJ",
        target_unit="MWh",
        factor=0.2777778,
        version="units/v1",
        effective_from=_dt(2026, 1, 1),
    )
    assert conversion.applies_to(_dt(2026, 1, 2))
    assert not conversion.applies_to(_dt(2025, 12, 31))
    assert round(convert_value(1000.0, conversion), 4) == 277.7778


def test_resampling_has_bounded_carry_forward_and_no_global_ffill() -> None:
    base = _dt(2026, 1, 1, 6)
    observed = ResampledValue(timestamp=base, value=10.0, is_observed=True)
    missing = ResampledValue(
        timestamp=base + timedelta(hours=1), value=11.0, is_observed=False
    )
    policy = ResamplingPolicy(
        semantic_type="market_price",
        aggregation=ResamplingAggregation.LAST,
        carry_forward_policy=MissingDataPolicy.CARRY_FORWARD,
        maximum_carry_seconds=1800,
        missing_data_policy=MissingDataPolicy.DROP,
    )

    carried = bounded_resample(
        [observed, missing], [base + timedelta(hours=1, minutes=15)], policy
    )
    assert carried[0] is not None
    assert carried[0].is_imputed is True
    assert carried[0].quality_state == "FORWARD_FILLED"
    assert carried[0].source_age_seconds == 900.0

    too_stale = bounded_resample([observed], [base + timedelta(hours=2)], policy)
    assert too_stale[0] is None

    no_ffill = ResamplingPolicy(
        semantic_type="market_price",
        carry_forward_policy=MissingDataPolicy.DROP,
        maximum_carry_seconds=0,
    )
    not_carried = bounded_resample(
        [observed, missing],
        [base + timedelta(hours=1, minutes=15)],
        no_ffill,
    )
    assert not_carried[0] is None


def test_feature_hash_version_and_dependency_closure() -> None:
    left = _feature("a", [])
    middle = _feature("b", ["a"])
    right = _feature("c", ["b"])
    assert left.content_hash() == left.content_hash()
    assert left.version() == f"a@v1@{left.content_hash()[:8]}"
    assert feature_dependency_closure(right, {"a": left, "b": middle}) == ["a", "b"]

    changed = left.model_copy(update={"metadata": {"owner": "changed"}})
    assert changed.content_hash() != left.content_hash()


def test_targets_are_never_training_features() -> None:
    target = _target()
    assert target.feature_prohibited_ids() == {"NBP_DA_PRICE_D1"}
    assert target.qualified_version().startswith("NBP_DA_PRICE_D1@target/v1@")


def test_build_dataset_is_point_in_time_reproducible_and_immutable() -> None:
    feature = _feature(
        "NBP_TTF_DA_SPREAD",
        ["market.price.NBP.DAY_AHEAD", "market.price.TTF.DAY_AHEAD"],
    )
    target = _target()
    spec = _spec(features=[feature], targets=[target])
    records = _sample_records()
    result = build_dataset(
        spec,
        records,
        {feature.feature_id: feature},
        {target.target_id: target},
        ResamplingPolicy(semantic_type="market_price"),
    )

    assert len(result.rows) == 4
    feature_rows = [row for row in result.rows if row.get("feature_id")]
    target_rows = [row for row in result.rows if row.get("target_id")]
    assert [row["value"] for row in feature_rows] == [2.0, 2.0]
    assert [row["target_value"] for row in target_rows] == [21.0, 22.0]
    assert result.quality_report["coverage"] == 1.0
    assert result.leakage_issues == []
    assert result.as_metadata()["source_cutoff_utc"] == spec.end.isoformat()
    assert result.as_metadata()["entitlement_envelope"] == {}

    rebuilt = build_dataset(
        spec,
        records,
        {feature.feature_id: feature},
        {target.target_id: target},
        ResamplingPolicy(semantic_type="market_price"),
    )
    assert rebuilt.content_hash == result.content_hash
    assert rebuilt.dataset_snapshot_id == result.dataset_snapshot_id

    changed_records = list(records)
    changed_records[1] = changed_records[1].model_copy(update={"value": 19.0})
    changed = build_dataset(
        spec,
        changed_records,
        {feature.feature_id: feature},
        {target.target_id: target},
        ResamplingPolicy(semantic_type="market_price"),
    )
    assert changed.content_hash != result.content_hash
    assert changed.dataset_snapshot_id != result.dataset_snapshot_id


def test_dataset_rejects_unknown_or_target_as_feature_ids() -> None:
    feature = _feature(
        "NBP_TTF_DA_SPREAD",
        ["market.price.NBP.DAY_AHEAD", "market.price.TTF.DAY_AHEAD"],
    )
    target = _target()
    registry = {feature.feature_id: feature}
    records = _sample_records()

    with pytest.raises(ValueError, match="unknown feature_id"):
        build_dataset(
            _spec(features=[_feature("UNKNOWN", [])], targets=[target]),
            records,
            registry,
            {target.target_id: target},
            ResamplingPolicy(semantic_type="market_price"),
        )

    with pytest.raises(ValueError, match="target ids used as features"):
        build_dataset(
            _spec(features=[feature, _feature(target.target_id, [])], targets=[target]),
            records,
            {
                feature.feature_id: feature,
                target.target_id: _feature(target.target_id, []),
            },
            {target.target_id: target},
            ResamplingPolicy(semantic_type="market_price"),
        )


def test_strict_dataset_rejects_unavailable_temporal_insufficient_input() -> None:
    feature = _feature(
        "NBP_TTF_DA_SPREAD",
        ["market.price.NBP.DAY_AHEAD", "market.price.TTF.DAY_AHEAD"],
    )
    target = _target()
    registry = {feature.feature_id: feature}
    records = [
        _record(
            "nbp",
            "market.price.NBP.DAY_AHEAD",
            _dt(2026, 1, 1, 0),
            available_at=None,
            value=20.0,
            integrity=TemporalIntegrityState.TEMPORAL_INSUFFICIENT,
        ),
        _record(
            "ttf",
            "market.price.TTF.DAY_AHEAD",
            _dt(2026, 1, 1, 0),
            available_at=None,
            value=18.0,
            integrity=TemporalIntegrityState.TEMPORAL_INSUFFICIENT,
        ),
    ]
    strict = build_dataset(
        _spec(features=[feature], targets=[target], mode=DatasetMode.STRICT),
        records,
        registry,
        {target.target_id: target},
        ResamplingPolicy(semantic_type="market_price"),
    )
    assert strict.quality_report["build_blocked"] is True
    assert [
        issue
        for issue in strict.leakage_issues
        if issue["code"].startswith("TEMPORAL")
    ]

    exploratory = build_dataset(
        _spec(features=[feature], targets=[target], mode=DatasetMode.EXPLORATORY),
        records,
        registry,
        {target.target_id: target},
        ResamplingPolicy(semantic_type="market_price"),
    )
    assert exploratory.quality_report["build_blocked"] is False


def test_leakage_validator_blocks_future_observations_and_targets_as_features() -> None:
    validator = LeakageValidator(mode="STRICT")
    origin = _dt(2026, 1, 1, 12)
    rows = [
        {
            "forecast_origin": origin,
            "available_at": _dt(2026, 1, 1, 13),
            "quality_state": "OBSERVED",
        },
        {
            "forecast_origin": origin,
            "available_at": origin,
            "forecast_issued_at": _dt(2026, 1, 1, 13),
            "quality_state": "OBSERVED",
        },
        {
            "forecast_origin": origin,
            "available_at": origin,
            "feature_id": "TARGET_1",
            "quality_state": "OBSERVED",
        },
    ]
    issues = validator.validate(rows, target_ids={"TARGET_1"})
    assert {issue.code for issue in issues} == {
        "OBSERVATION_AVAILABLE_AFTER_ORIGIN",
        "FORECAST_ISSUED_AFTER_ORIGIN",
        "TARGET_USED_AS_FEATURE",
    }


def test_capability_contracts_are_typed_and_never_expose_db_tables() -> None:
    names = {capability.name for capability in REGISTERED_RESEARCH_CAPABILITIES}
    assert {
        "ontology.resolve_entity",
        "data.get_observations_as_of",
        "analytics.get_feature_definition",
        "dataset.build",
        "dataset.export",
    } <= names
    for capability in REGISTERED_RESEARCH_CAPABILITIES:
        assert capability.input_schema["type"] == "object"
        assert capability.output_schema["type"] == "object"
        assert capability.required_permission.startswith("research")
        assert "SELECT" not in capability.description
        assert capability.read_write_class in CapabilityReadWriteClass
    build = next(
        capability
        for capability in REGISTERED_RESEARCH_CAPABILITIES
        if capability.name == "dataset.build"
    )
    assert build.timeout_seconds >= 60
    assert build.side_effect_class.value == "persists_snapshot"


def test_export_metadata_contract_includes_lineage_and_entitlement() -> None:
    feature = _feature(
        "NBP_TTF_DA_SPREAD",
        ["market.price.NBP.DAY_AHEAD", "market.price.TTF.DAY_AHEAD"],
    )
    target = _target()
    spec = _spec(features=[feature], targets=[target])
    spec.entitlement_envelope = {"export_policy": "EXPORT_ALLOWED"}
    result = build_dataset(
        spec,
        _sample_records(),
        {feature.feature_id: feature},
        {target.target_id: target},
        ResamplingPolicy(semantic_type="market_price"),
    )
    metadata = result.as_metadata()
    assert metadata["entitlement_envelope"] == {"export_policy": "EXPORT_ALLOWED"}
    assert "test:nbp-00" in metadata["lineage"]
    assert isinstance(metadata["content_hash"], str)
    assert len(metadata["content_hash"]) == 64
