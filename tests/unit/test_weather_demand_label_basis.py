"""Focused pure-stage1 contracts for explicit demand target label clocks.

The default basis must remain byte-identical to the pre-change root golden. The
nondefault basis is explicit retrospective research only and cannot be consumed
by the existing predictors or the frozen-model prediction runtime. All numeric
fixtures are synthetic mechanics; none is provider-history or accuracy evidence.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.application.research import (
    weather_demand_prediction_runtime as prediction_runtime,
)
from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_start_for_date,
)
from eurogas_nexus.domain.research.weather_demand import (
    DEMAND_TARGET_LABEL_METHOD_VERSION,
    FINAL_TARGET_TRUTH_LABEL,
    AmbiguousWeatherInputError,
    DemandPredictionRequest,
    DemandTargetLabelBasis,
    DemandTargetLabelBasisError,
    DemandTargetLabelEvidence,
    DemandTargetLabelFact,
    DemandTargetQuality,
    ModelMetrics,
    ModelSelectionStatus,
    PromotionStatus,
    RetrospectiveTargetLabelConsumptionError,
    TargetScope,
    ValidationBasis,
    WeatherDemandInputError,
    _assert_target_label_consistency,
    _resolve_targets_for_policy,
    fit_weather_demand_model,
    predict_baseline_demand,
    predict_selected_demand,
)
from tests.unit.test_weather_demand import _fit_fixture, _fit_policy

RETRO = DemandTargetLabelBasis.RETROSPECTIVE_PROVIDER_APPLICABILITY_RESEARCH

GOLDEN_SELECTION_HASH = (
    "7d2cbc5ee765b775b2f07c51cedc8bc3433c90fd60968112c8be17d523ef1647"
)
GOLDEN_BASELINE_HASH = (
    "a10059c3b9d4b816fb1df7342bc120a37e25b185976677cc72e1096d9d09e545"
)
GOLDEN_CANDIDATE_HASH = (
    "9cfaa82b64efaa5543b36414f152313d733914c25404135c7975cca749c59c58"
)
GOLDEN_BASELINE_METRICS = ModelMetrics(
    mae=10.370442566978678,
    rmse=12.070796800437817,
    bias=-0.029912426402879076,
    count=10,
)
GOLDEN_CANDIDATE_METRICS = ModelMetrics(
    mae=0.299112853998443,
    rmse=0.3524623653605083,
    bias=0.1932076979392292,
    count=10,
)


def _retro_policy():
    return replace(_fit_policy(), target_label_basis=RETRO)


def _retro_targets(targets):
    return tuple(
        replace(
            target,
            label_basis=RETRO,
            label_at=gas_day_start_for_date(target.gas_day + timedelta(days=1)),
        )
        for target in targets
    )


def _retro_fixture(*, rows: int = 40):
    targets, features = _fit_fixture(rows=rows)
    return _retro_targets(targets), features, _retro_policy()


def _retro_result():
    targets, features, policy = _retro_fixture()
    return fit_weather_demand_model(targets, features, policy), policy


def _label_fact() -> DemandTargetLabelFact:
    available = datetime(2025, 2, 1, 1, tzinfo=UTC)
    return DemandTargetLabelFact(
        gas_day=date(2025, 1, 31),
        scope=TargetScope.GB_NTS_THROUGHPUT,
        region="GB_NTS",
        unit="MSCM",
        value=100.0,
        quality=DemandTargetQuality.ACTUAL,
        revision=1,
        revision_id="target:2025-01-31",
        available_at=available,
        label_at=available - timedelta(hours=1),
        label_basis=RETRO,
        source_ref="target:2025-01-31",
    )


def test_default_golden_hashes_and_numeric_metrics_are_preserved() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    policy = _fit_policy()

    result = fit_weather_demand_model(targets, features, policy)

    assert result.selection_status is ModelSelectionStatus.CANDIDATE_SELECTED
    assert len(result.folds) == 10
    assert result.selection_hash == GOLDEN_SELECTION_HASH
    assert result.baseline_model.model_hash == GOLDEN_BASELINE_HASH
    assert result.candidate_model is not None
    assert result.candidate_model.model_hash == GOLDEN_CANDIDATE_HASH
    assert result.baseline_oos == GOLDEN_BASELINE_METRICS
    assert result.candidate_oos == GOLDEN_CANDIDATE_METRICS
    assert result.production_promotion is PromotionStatus.NOT_PROMOTED

    assert result.selected_model.target_label_basis is DemandTargetLabelBasis.ACTUAL_RECEIPT
    assert result.selected_model.target_label_policy_hash is None
    assert result.selected_model.target_label_facts == ()
    assert result.target_label_evidence is None
    assert not result.retrospective_target_labels
    assert result.selection_evidence is not None
    assert result.selection_evidence.target_label_evidence is None
    assert (
        result.selection_evidence.target_label_basis
        is DemandTargetLabelBasis.ACTUAL_RECEIPT
    )
    assert all(fold.training_target_facts == () for fold in result.folds)
    assert len(policy.target_label_policy_hash) == 64


def test_target_label_policy_hash_is_explicit_and_stable() -> None:
    default = _fit_policy()
    retro = replace(default, target_label_basis=RETRO)

    assert default.target_label_policy_hash == replace(default).target_label_policy_hash
    assert len(default.target_label_policy_hash) == 64
    assert default.target_label_policy_hash != retro.target_label_policy_hash
    assert len(retro.target_label_policy_hash) == 64


def test_label_evidence_requires_complete_facts_and_matching_policy_hash() -> None:
    policy = replace(_fit_policy(), target_label_basis=RETRO)
    fact = _label_fact()

    with pytest.raises(DemandTargetLabelBasisError, match="complete"):
        DemandTargetLabelEvidence(
            basis=RETRO,
            policy_hash=policy.target_label_policy_hash,
            analysis_as_of=policy.validation_as_of,
            revision_facts=(),
        )
    with pytest.raises(DemandTargetLabelBasisError, match="policy hash"):
        DemandTargetLabelEvidence(
            basis=RETRO,
            policy_hash=_fit_policy().target_label_policy_hash,
            analysis_as_of=policy.validation_as_of,
            revision_facts=(fact,),
        )


def test_final_truth_must_be_complete_latest_analysis_truth() -> None:
    policy = _retro_policy()
    first = _label_fact()
    second = replace(
        first,
        revision=2,
        revision_id="target:rev-2",
        value=101.0,
        label_at=first.label_at + timedelta(hours=1),
    )
    other_day = replace(
        first,
        gas_day=date(2025, 2, 2),
        revision_id="target:2025-02-02",
        source_ref="target:2025-02-02",
    )
    valid = DemandTargetLabelEvidence(
        basis=RETRO,
        policy_hash=policy.target_label_policy_hash,
        analysis_as_of=policy.validation_as_of,
        revision_facts=(first, second),
        final_truth=(second,),
    )
    assert valid.final_truth == (second,)

    tied = replace(second, label_at=first.label_at)
    with pytest.raises(DemandTargetLabelBasisError, match="equal effective label clocks"):
        replace(valid, revision_facts=(first, tied), final_truth=(tied,))
    with pytest.raises(DemandTargetLabelBasisError, match="final target truth"):
        replace(valid, final_truth=())
    with pytest.raises(DemandTargetLabelBasisError, match="final target truth"):
        replace(valid, final_truth=(first,))

    complete = replace(
        valid,
        revision_facts=(first, second, other_day),
        final_truth=(second, other_day),
    )
    assert complete.final_truth == (second, other_day)
    with pytest.raises(DemandTargetLabelBasisError, match="final target truth"):
        replace(complete, final_truth=(second,))


def test_capture_now_receipts_cannot_train_a_historical_cutoff() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    capture_now = datetime(2026, 10, 30, 12, tzinfo=UTC)
    late_targets = tuple(replace(target, available_at=capture_now) for target in targets)

    with pytest.raises(WeatherDemandInputError, match="no training rows"):
        fit_weather_demand_model(late_targets, features, _fit_policy())

    late_retro = tuple(
        replace(
            target,
            available_at=capture_now,
            label_basis=RETRO,
            label_at=gas_day_start_for_date(target.gas_day + timedelta(days=1)),
        )
        for target in targets
    )
    with pytest.raises(WeatherDemandInputError, match="no training rows"):
        fit_weather_demand_model(late_retro, features, _retro_policy())


def test_label_before_fold_but_receipt_after_analysis_is_excluded() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    policy = _retro_policy()
    retro_targets = _retro_targets(targets)
    excluded_day = date(2025, 1, 15)
    excluded = next(target for target in retro_targets if target.gas_day == excluded_day)
    excluded = replace(
        excluded,
        available_at=policy.validation_as_of + timedelta(seconds=1),
    )
    rows = tuple(
        excluded if target.gas_day == excluded_day else target for target in retro_targets
    )

    result = fit_weather_demand_model(rows, features, policy)

    label_evidence = result.target_label_evidence
    assert label_evidence is not None
    assert all(fact.gas_day != excluded_day for fact in label_evidence.revision_facts)
    assert all(fact.gas_day != excluded_day for fact in label_evidence.final_truth)
    assert all(
        fact.gas_day != excluded_day
        for fold in result.folds
        for fact in fold.training_target_facts
    )


def test_reconstructed_rows_yield_causal_rolling_folds_without_rewriting_receipt() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    retro_targets = _retro_targets(targets)
    default_result = fit_weather_demand_model(targets, features, _fit_policy())
    result = fit_weather_demand_model(retro_targets, features, _retro_policy())

    evidence = result.selection_evidence
    label_evidence = result.target_label_evidence
    assert evidence is not None
    assert label_evidence is not None
    assert result.retrospective_target_labels
    assert result.production_promotion is PromotionStatus.NOT_PROMOTED
    assert result.validation_basis is ValidationBasis.SYNTHETIC_NOT_REAL
    assert evidence.target_label_basis is RETRO
    assert evidence.target_label_policy_hash == label_evidence.policy_hash
    assert label_evidence.basis is RETRO
    assert label_evidence.policy_hash == _retro_policy().target_label_policy_hash
    assert label_evidence.analysis_as_of == _retro_policy().validation_as_of
    assert label_evidence.label_method == DEMAND_TARGET_LABEL_METHOD_VERSION
    assert label_evidence.final_truth_label == FINAL_TARGET_TRUTH_LABEL

    receipts = {target.revision_id: target.available_at for target in targets}
    assert len(label_evidence.revision_facts) == len(targets)
    assert all(
        fact.available_at == receipts[fact.revision_id]
        for fact in label_evidence.revision_facts
    )
    assert {fact.gas_day for fact in label_evidence.final_truth} == {
        target.gas_day for target in targets
    }
    assert len(result.folds) == len(default_result.folds)
    for fold in result.folds:
        assert fold.training_rows == len(fold.training_target_facts)
        assert all(
            fact.label_at <= fold.fold_origin for fact in fold.training_target_facts
        )
    assert any(
        fact.available_at > fold.fold_origin
        for fold in result.folds
        for fact in fold.training_target_facts
    )
    assert any(
        fold.training_rows > default_fold.training_rows
        for fold, default_fold in zip(result.folds, default_result.folds, strict=True)
    )


def test_changed_future_revision_does_not_affect_earlier_fold_training() -> None:
    pytest.importorskip("numpy")
    targets, features, policy = _retro_fixture()
    baseline = fit_weather_demand_model(targets, features, policy)
    future_day = date(2025, 2, 5)
    source = next(target for target in targets if target.gas_day == future_day)
    assert source.label_at is not None
    future = replace(
        source,
        revision=2,
        revision_id="target:future-revision",
        value=source.value + 50.0,
        label_at=source.label_at + timedelta(hours=1),
        source_ref="target:future-revision",
    )

    changed = fit_weather_demand_model(targets + (future,), features, policy)

    unchanged_before = [
        fold for fold in baseline.folds if fold.fold_origin < future.label_at
    ]
    changed_before = [
        fold for fold in changed.folds if fold.fold_origin < future.label_at
    ]
    assert [fold.training_target_facts for fold in unchanged_before] == [
        fold.training_target_facts for fold in changed_before
    ]
    assert [
        (
            fold.training_rows,
            fold.baseline_prediction,
            fold.candidate_prediction,
        )
        for fold in unchanged_before
    ] == [
        (
            fold.training_rows,
            fold.baseline_prediction,
            fold.candidate_prediction,
        )
        for fold in changed_before
    ]
    assert all(
        fact.revision_id != "target:future-revision"
        for fold in changed_before
        for fact in fold.training_target_facts
    )
    later_fold = next(
        fold for fold in changed.folds if fold.fold_origin >= future.label_at
    )
    assert any(
        fact.revision_id == "target:future-revision"
        for fact in later_fold.training_target_facts
    )
    assert changed.selection_hash != baseline.selection_hash
    label_evidence = changed.target_label_evidence
    assert label_evidence is not None
    final_fact = next(
        fact for fact in label_evidence.final_truth if fact.gas_day == future_day
    )
    assert final_fact.revision == 2
    assert final_fact.revision_id == "target:future-revision"
    changed_evidence = changed.selection_evidence
    assert changed_evidence is not None
    _assert_target_label_consistency(changed, changed_evidence)


def test_equal_effective_label_clocks_for_competing_publications_refuse() -> None:
    pytest.importorskip("numpy")
    targets, features, policy = _retro_fixture()
    source = targets[0]
    tied = replace(
        source,
        revision=2,
        revision_id="target:tied-publication",
        value=source.value + 1.0,
        source_ref="target:tied-publication",
    )

    with pytest.raises(AmbiguousWeatherInputError, match="equal effective label clocks"):
        fit_weather_demand_model(targets + (tied,), features, policy)


def test_rank_clock_inversion_is_refused_per_gas_day() -> None:
    policy = _retro_policy()
    day = date(2025, 1, 15)
    base = next(target for target in _fit_fixture()[0] if target.gas_day == day)
    receipt = datetime(2025, 1, 18, tzinfo=UTC)
    higher_rank_earlier_clock = replace(
        base,
        revision=2,
        revision_id="rev-2",
        label_basis=RETRO,
        available_at=receipt,
        label_at=datetime(2025, 1, 16, 0, tzinfo=UTC),
    )
    lower_rank_later_clock = replace(
        base,
        revision=1,
        revision_id="rev-1",
        label_basis=RETRO,
        available_at=receipt,
        label_at=datetime(2025, 1, 16, 6, tzinfo=UTC),
    )

    with pytest.raises(DemandTargetLabelBasisError, match="monotonically"):
        _resolve_targets_for_policy(
            (higher_rank_earlier_clock, lower_rank_later_clock),
            datetime(2025, 1, 17, tzinfo=UTC),
            policy,
        )


def test_naive_future_missing_and_mixed_label_clocks_are_refused() -> None:
    targets, _features = _fit_fixture(rows=3)
    source = targets[0]

    with pytest.raises(DemandTargetLabelBasisError, match="aware"):
        replace(
            source,
            label_basis=RETRO,
            label_at=datetime(2025, 1, 2),
        )
    with pytest.raises(DemandTargetLabelBasisError, match="follow"):
        replace(
            source,
            label_basis=RETRO,
            label_at=source.available_at + timedelta(seconds=1),
        )
    with pytest.raises(DemandTargetLabelBasisError, match="requires"):
        replace(source, label_basis=RETRO)
    with pytest.raises(DemandTargetLabelBasisError, match="cannot carry"):
        replace(source, label_at=source.available_at)
    with pytest.raises(DemandTargetLabelBasisError, match="genuine"):
        replace(
            _fit_policy(),
            target_label_basis=RETRO,
            validation_basis=ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS,
        )


def test_mixed_row_and_policy_label_bases_refuse() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    retro_targets = _retro_targets(targets)

    with pytest.raises(DemandTargetLabelBasisError, match="label basis"):
        fit_weather_demand_model(targets, features, _retro_policy())
    with pytest.raises(DemandTargetLabelBasisError, match="label basis"):
        fit_weather_demand_model(retro_targets, features, _fit_policy())


def test_nondefault_basis_changes_model_and_selection_identity() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    default = fit_weather_demand_model(targets, features, _fit_policy())
    retro_targets = _retro_targets(targets)
    retro = fit_weather_demand_model(retro_targets, features, _retro_policy())

    assert retro.baseline_model.model_hash != default.baseline_model.model_hash
    assert retro.candidate_model is not None
    assert default.candidate_model is not None
    assert retro.candidate_model.model_hash != default.candidate_model.model_hash
    assert retro.selected_model.model_hash != default.selected_model.model_hash
    assert retro.selection_hash != default.selection_hash
    assert retro.selected_model.target_label_basis is RETRO
    assert retro.selected_model.target_label_policy_hash == (
        _retro_policy().target_label_policy_hash
    )
    assert retro.target_label_evidence is not None
    assert retro.production_promotion is PromotionStatus.NOT_PROMOTED


def test_changed_label_clock_changes_model_and_selection_hashes() -> None:
    pytest.importorskip("numpy")
    targets, features, policy = _retro_fixture()
    first = fit_weather_demand_model(targets, features, policy)
    shifted_targets = tuple(
        replace(target, label_at=target.label_at - timedelta(hours=2))
        for target in targets
    )
    second = fit_weather_demand_model(shifted_targets, features, policy)

    assert first.selected_model.target_revision_ids == (
        second.selected_model.target_revision_ids
    )
    assert first.selected_model.model_hash != second.selected_model.model_hash
    assert first.selection_hash != second.selection_hash


def test_lost_defaulted_and_tampered_label_evidence_is_refused() -> None:
    pytest.importorskip("numpy")
    result, _policy = _retro_result()
    evidence = result.selection_evidence
    assert evidence is not None
    label_evidence = evidence.target_label_evidence
    assert label_evidence is not None

    with pytest.raises(DemandTargetLabelBasisError, match="policy hash"):
        replace(
            label_evidence,
            policy_hash=_fit_policy().target_label_policy_hash,
        )
    with pytest.raises(DemandTargetLabelBasisError, match="actual-receipt model"):
        replace(
            result.selected_model,
            target_label_basis=DemandTargetLabelBasis.ACTUAL_RECEIPT,
        )

    lost = replace(evidence, target_label_evidence=None, folds=(), fold_count=0)
    with pytest.raises(DemandTargetLabelBasisError, match="lost"):
        _assert_target_label_consistency(result, lost)

    fact = result.selected_model.target_label_facts[0]
    tampered_fact = replace(fact, label_at=fact.label_at + timedelta(minutes=1))
    assert tampered_fact.label_at <= tampered_fact.available_at
    tampered_facts = tuple(
        tampered_fact if item == fact else item
        for item in label_evidence.revision_facts
    )
    tampered_truth = tuple(
        tampered_fact if item == fact else item for item in label_evidence.final_truth
    )
    tampered_label_evidence = replace(
        label_evidence,
        revision_facts=tampered_facts,
        final_truth=tampered_truth,
    )
    tampered_evidence = replace(
        evidence, target_label_evidence=tampered_label_evidence
    )
    assert tampered_evidence.selection_hash != evidence.selection_hash
    with pytest.raises(DemandTargetLabelBasisError, match="training label facts"):
        _assert_target_label_consistency(result, tampered_evidence)


def test_model_label_facts_must_bind_rows_revisions_identity_and_cutoff() -> None:
    pytest.importorskip("numpy")
    result, _policy = _retro_result()
    model = result.selected_model
    assert model.target_label_facts

    with pytest.raises(DemandTargetLabelBasisError, match="training_rows"):
        replace(model, target_label_facts=model.target_label_facts[:1])
    with pytest.raises(DemandTargetLabelBasisError, match="target_revision_ids"):
        replace(model, target_revision_ids=model.target_revision_ids[:-1])

    fact = model.target_label_facts[0]
    with pytest.raises(DemandTargetLabelBasisError, match="target identity"):
        replace(
            model,
            target_label_facts=(replace(fact, unit="MWH"),) + model.target_label_facts[1:],
        )
    last_fact = model.target_label_facts[-1]
    with pytest.raises(DemandTargetLabelBasisError, match="training cutoff"):
        replace(
            model,
            target_label_facts=model.target_label_facts[:-1]
            + (
                replace(
                    last_fact,
                    label_at=model.training_cutoff + timedelta(hours=1),
                ),
            ),
        )


def test_consistency_refuses_altered_model_facts_with_retained_model_hash() -> None:
    pytest.importorskip("numpy")
    result, _policy = _retro_result()
    evidence = result.selection_evidence
    assert evidence is not None
    model = result.selected_model
    fact = model.target_label_facts[0]
    altered_fact = replace(fact, label_at=fact.label_at + timedelta(minutes=1))
    altered_model = replace(
        model,
        target_label_facts=(altered_fact,) + model.target_label_facts[1:],
    )
    assert altered_model.model_hash == model.model_hash
    altered_result = replace(result, selected_model=altered_model)

    with pytest.raises(DemandTargetLabelBasisError, match="training label facts"):
        _assert_target_label_consistency(altered_result, evidence)


def test_consistency_refuses_dropped_model_facts_even_if_constructor_bypassed() -> None:
    pytest.importorskip("numpy")
    result, _policy = _retro_result()
    evidence = result.selection_evidence
    assert evidence is not None
    model = result.selected_model
    tampered_model = replace(model)
    object.__setattr__(tampered_model, "target_label_facts", model.target_label_facts[:1])
    assert tampered_model.model_hash == model.model_hash
    tampered_result = replace(result, selected_model=tampered_model)

    with pytest.raises(DemandTargetLabelBasisError, match="training_rows"):
        _assert_target_label_consistency(tampered_result, evidence)


def test_fold_facts_must_bind_row_count_and_fold_origin() -> None:
    pytest.importorskip("numpy")
    result, _policy = _retro_result()
    evidence = result.selection_evidence
    assert evidence is not None
    fold = evidence.folds[0]
    assert fold.training_target_facts

    dropped = replace(fold, training_target_facts=fold.training_target_facts[:-1])
    dropped_evidence = replace(
        evidence,
        folds=(dropped,) + evidence.folds[1:],
    )
    with pytest.raises(DemandTargetLabelBasisError, match="training row count"):
        _assert_target_label_consistency(result, dropped_evidence)

    fact = fold.training_target_facts[-1]
    late_fact = replace(fact, label_at=fold.fold_origin + timedelta(minutes=1))
    assert late_fact.label_at <= late_fact.available_at
    late_fold = replace(
        fold,
        training_target_facts=fold.training_target_facts[:-1] + (late_fact,),
    )
    late_evidence = replace(
        evidence,
        folds=(late_fold,) + evidence.folds[1:],
    )
    with pytest.raises(DemandTargetLabelBasisError, match="fold origin"):
        _assert_target_label_consistency(result, late_evidence)


def test_both_domain_predictors_refuse_retrospective_label_basis() -> None:
    pytest.importorskip("numpy")
    result, _policy = _retro_result()
    gas_day = date(2025, 2, 15)
    origin = gas_day_start_for_date(gas_day) - timedelta(days=2)
    request = DemandPredictionRequest(
        gas_day=gas_day,
        prediction_origin=origin,
        target_scope=TargetScope.REGION,
        region="GB",
        target_unit="MSCM",
        gas_day_calendar=DEFAULT_GAS_DAY_CALENDAR,
        weather_feature=None,
    )

    with pytest.raises(RetrospectiveTargetLabelConsumptionError):
        predict_selected_demand(result, request)
    with pytest.raises(RetrospectiveTargetLabelConsumptionError):
        predict_baseline_demand(result, request)


def test_demand_prediction_constructor_refuses_retrospective_basis() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    result = fit_weather_demand_model(targets, features, _fit_policy())
    gas_day = date(2025, 2, 15)
    origin = gas_day_start_for_date(gas_day) - timedelta(days=2)
    prediction = predict_baseline_demand(
        result,
        DemandPredictionRequest(
            gas_day=gas_day,
            prediction_origin=origin,
            target_scope=TargetScope.REGION,
            region="GB",
            target_unit="MSCM",
            gas_day_calendar=DEFAULT_GAS_DAY_CALENDAR,
            weather_feature=None,
        ),
    )
    assert prediction.target_label_basis is DemandTargetLabelBasis.ACTUAL_RECEIPT

    with pytest.raises(
        RetrospectiveTargetLabelConsumptionError,
        match="direct prediction construction",
    ):
        replace(
            prediction,
            target_label_basis=RETRO,
            target_label_policy_hash=_retro_policy().target_label_policy_hash,
        )


def test_application_prediction_request_refuses_nondefault_model_and_evidence() -> None:
    pytest.importorskip("numpy")
    from tests.unit.test_weather_demand_prediction_runtime import (
        _fit_weather_result,
    )
    from tests.unit.test_weather_demand_prediction_runtime import (
        _request as runtime_request,
    )

    result = _fit_weather_result()
    retro_result, _retro_policy_used = _retro_result()
    label_policy = replace(_fit_policy(), target_label_basis=RETRO)
    fact = _label_fact()
    nondefault_model = retro_result.selected_model
    assert nondefault_model.target_label_basis is RETRO
    with pytest.raises(
        prediction_runtime.WeatherDemandPredictionTargetLabelBasisError,
        match="not supported",
    ):
        runtime_request(replace(result, selected_model=nondefault_model))

    evidence = result.selection_evidence
    assert evidence is not None
    label_evidence = DemandTargetLabelEvidence(
        basis=RETRO,
        policy_hash=label_policy.target_label_policy_hash,
        analysis_as_of=evidence.validation_as_of,
        revision_facts=(fact,),
        final_truth=(fact,),
    )
    tampered_evidence = replace(evidence, target_label_evidence=label_evidence)
    with pytest.raises(
        prediction_runtime.WeatherDemandPredictionTargetLabelBasisError,
        match="not supported",
    ):
        runtime_request(replace(result, selection_evidence=tampered_evidence))
