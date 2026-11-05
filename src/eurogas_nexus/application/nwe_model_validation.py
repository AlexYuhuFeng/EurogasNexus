"""Expanding-window NWE weather validation with disjoint interval calibration.

Uses only records declared available at each fold origin. Validation reports
remain research evidence; model registry adoption is a separate reviewer act.
"""

from datetime import date
from statistics import mean

from pydantic import AwareDatetime, Field

from eurogas_nexus.application.nwe_balance_scenario import (
    BalanceHistoryInput,
    HddInput,
    ScenarioModel,
)
from eurogas_nexus.domain.analysis_contracts import content_hash
from eurogas_nexus.domain.fundamentals.balance import BalanceHistoryDay, fit_weather_model

VERSION = "nwe-weather-walk-forward/1"


class ValidationRequest(ScenarioModel):
    feature_policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    heating_base_c: float = Field(ge=-50, le=50)
    gas_day_calendar: str = Field(min_length=1, max_length=64)
    validation_as_of: AwareDatetime
    history: tuple[BalanceHistoryInput, ...] = Field(min_length=45, max_length=800)
    features: tuple[HddInput, ...] = Field(min_length=45, max_length=800)
    fold_origins: dict[date, AwareDatetime] = Field(min_length=14, max_length=366)
    coverage: float = Field(default=0.9, gt=0.5, lt=1)
    minimum_relative_improvement: float = Field(default=0.02, ge=0, le=1)


def validate_weather_model(payload: ValidationRequest, checkpoint=lambda: None) -> dict:
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

    gas_day_start_for_date(payload.validation_as_of.date(), payload.gas_day_calendar)
    if len({r.day for r in payload.history}) != len(payload.history) or len(
        {r.day for r in payload.features}
    ) != len(payload.features):
        raise ValueError("duplicate historical day or weather feature")
    features = {r.day: r for r in payload.features}
    truth = {r.day: r for r in payload.history if r.available_at <= payload.validation_as_of}
    folds, omitted = [], []
    for day, origin in sorted(payload.fold_origins.items()):
        checkpoint()
        if origin > payload.validation_as_of or origin.date() != day:
            raise ValueError("fold origins must match their day and precede validation cutoff")
        past = [r for r in payload.history if r.day < day and r.available_at <= origin]
        weather = {
            r.day: r.hdd for r in payload.features if r.day < day and r.available_at <= origin
        }
        point, actual = features.get(day), truth.get(day)
        history = [
            BalanceHistoryDay(r.day, r.norway_gwh, r.lng_gwh, r.storage_net_withdrawal_gwh)
            for r in sorted(past, key=lambda r: r.day)
        ]
        model = fit_weather_model(history, weather)
        if (
            model is None
            or point is None
            or point.available_at > origin
            or actual is None
            or actual.available_at <= origin
        ):
            omitted.append(day.isoformat())
            continue
        predicted = model.call(point.hdd, day)
        if predicted < 0:
            omitted.append(day.isoformat())
            continue
        measured = actual.norway_gwh + actual.lng_gwh + actual.storage_net_withdrawal_gwh
        baseline = mean(row.call_gwh for row in history[-28:])
        folds.append(
            {
                "day": day.isoformat(),
                "origin": origin.isoformat(),
                "actual": measured,
                "candidate": predicted,
                "baseline": baseline,
                "training_days": len(history),
                "residual": measured - predicted,
            }
        )
    if len(folds) < 14:
        return {
            "status": "INSUFFICIENT_OOS",
            "folds": folds,
            "omitted": omitted,
            "engine_version": VERSION,
            "eligible_for_shadow": False,
        }
    calibration, test = folds[: len(folds) // 2], folds[len(folds) // 2 :]
    errors = sorted(abs(row["residual"]) for row in calibration)
    import math

    rank = math.ceil((len(errors) + 1) * payload.coverage)
    radius = errors[rank - 1] if rank <= len(errors) else None
    candidate_mae = mean(abs(r["residual"]) for r in test)
    baseline_mae = mean(abs(r["actual"] - r["baseline"]) for r in test)
    improvement = (baseline_mae - candidate_mae) / baseline_mae if baseline_mae > 0 else 0
    final_history = [
        BalanceHistoryDay(r.day, r.norway_gwh, r.lng_gwh, r.storage_net_withdrawal_gwh)
        for r in sorted(truth.values(), key=lambda r: r.day)
    ]
    final_weather = {
        r.day: r.hdd for r in payload.features if r.available_at <= payload.validation_as_of
    }
    frozen = fit_weather_model(final_history, final_weather)
    return {
        "status": "CANDIDATE_SELECTED"
        if improvement >= payload.minimum_relative_improvement
        else "BASELINE_RETAINED",
        "engine_version": VERSION,
        "candidate_mae": candidate_mae,
        "baseline_mae": baseline_mae,
        "relative_improvement": improvement,
        "interval_radius": radius,
        "test_interval_coverage": mean(abs(r["residual"]) <= radius for r in test)
        if radius is not None
        else None,
        "calibration_days": len(calibration),
        "test_days": len(test),
        "folds": folds,
        "omitted": omitted,
        "eligible_for_shadow": improvement >= payload.minimum_relative_improvement,
        "validation_basis": "DECLARED_POINT_IN_TIME_RESEARCH",
        "validation_input_hash": content_hash(payload.model_dump(mode="json")),
        "production_promoted": False,
        "frozen_coefficients": vars(frozen) if frozen is not None else None,
        "selection_available_at": payload.validation_as_of.isoformat(),
    }
