"""Readiness, revisions and genuine expanding-window computation semantics."""

from datetime import UTC, datetime, timedelta

import pytest

from eurogas_nexus.application.nwe_model_validation import ValidationRequest, validate_weather_model
from eurogas_nexus.domain.analysis_contracts import (
    ReadinessRequest,
    analysis_manifest,
    evaluate_readiness,
)


def readiness():
    return dict(
        as_of="2026-11-05T10:00:00Z",
        requirements=[
            dict(
                requirement_id="nbp-da",
                series_id="gas",
                entity_id="NBP",
                product="DA",
                unit="GBP/MWh",
                start="2026-11-06T05:00:00Z",
                end="2026-11-07T05:00:00Z",
                maximum_age_seconds=86400,
                source_priority=["ICE_OCM", "operator-input"],
            )
        ],
        evidence=[],
    )


def evidence(**changes):
    need = readiness()["requirements"][0]
    row = {k: need[k] for k in ("series_id", "entity_id", "product", "unit", "start", "end")}
    row.update(
        record_id="price-1",
        source="ICE_OCM",
        available_at="2026-11-05T09:00:00Z",
        observed_at="2026-11-05T08:00:00Z",
        revision=1,
        record_hash="a" * 64,
        quality_status="VALIDATED",
    )
    return {**row, **changes}


def test_task_coverage_and_revision_hash_change():
    body = readiness()
    assert not evaluate_readiness(ReadinessRequest.model_validate(body))["ready"]
    body["evidence"] = [evidence()]
    first = evaluate_readiness(ReadinessRequest.model_validate(body))
    assert first["ready"]
    body["evidence"].append(
        evidence(
            record_id="price-2",
            revision=2,
            record_hash="b" * 64,
            available_at="2026-11-05T09:30:00Z",
        )
    )
    second = evaluate_readiness(ReadinessRequest.model_validate(body))
    assert first["dependency_hash"] != second["dependency_hash"]
    assert second["requirements"][0]["record_versions"] == {"price-2": "b" * 64}


@pytest.mark.parametrize(
    "change",
    [
        dict(available_at="2026-11-05T11:00:00Z"),
        dict(unit="EUR/MWh"),
        dict(product="MA"),
        dict(end="2026-11-06T12:00:00Z"),
        dict(observed_at="2026-11-01T00:00:00Z"),
    ],
)
def test_coverage_refuses_wrong_basis_stale_future_and_partial(change):
    body = readiness()
    body["evidence"] = [evidence(**change)]
    assert not evaluate_readiness(ReadinessRequest.model_validate(body))["ready"]


def validation():
    first = datetime(2026, 1, 1, 6, tzinfo=UTC)
    history, features, origins = [], [], {}
    for i in range(100):
        stamp = first + timedelta(days=i)
        day = stamp.date()
        hdd = 5 + i % 9
        call = 1500 + 120 * hdd - (200 if day.weekday() >= 5 else 0)
        history.append(
            dict(
                day=day.isoformat(),
                norway_gwh=1000,
                lng_gwh=400,
                storage_net_withdrawal_gwh=call - 1400,
                available_at=(stamp + timedelta(days=1)).isoformat(),
                source_reference="fixture:actual",
            )
        )
        features.append(
            dict(
                day=day.isoformat(),
                hdd=hdd,
                available_at=(stamp - timedelta(days=1)).isoformat(),
                source_reference="fixture:forecast",
            )
        )
        if i >= 60:
            origins[day.isoformat()] = stamp.isoformat()
    return dict(
        feature_policy_hash="a" * 64,
        heating_base_c=15.5,
        gas_day_calendar="EU-CAM-UTC-2025",
        validation_as_of=(first + timedelta(days=102)).isoformat(),
        history=history,
        features=features,
        fold_origins=origins,
    )


def test_walk_forward_beats_baseline_without_using_target_truth_for_training():
    report = validate_weather_model(ValidationRequest.model_validate(validation()))
    assert report["status"] == "CANDIDATE_SELECTED"
    assert report["candidate_mae"] < 1e-7
    assert report["relative_improvement"] > 0.99
    assert report["calibration_days"] == report["test_days"] == 20
    assert report["production_promoted"] is False
    assert report["frozen_coefficients"]["slope_per_hdd"] == pytest.approx(120)


def test_future_forecast_receipts_remove_folds_instead_of_looking_ahead():
    body = validation()
    for row in body["features"]:
        row["available_at"] = body["validation_as_of"]
    report = validate_weather_model(ValidationRequest.model_validate(body))
    assert report["status"] == "INSUFFICIENT_OOS"
    assert not report["eligible_for_shadow"]


def test_manifest_tracks_engine_and_version_changes():
    left = analysis_manifest("joint", "v1", {"price": 10}, versions={"contract": "c1"})
    right = analysis_manifest("joint", "v1", {"price": 10}, versions={"contract": "c2"})
    assert left["input_hash"] == right["input_hash"]
    assert left["manifest_hash"] != right["manifest_hash"]
