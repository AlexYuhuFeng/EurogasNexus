"""Frozen NWE research predictions and later shadow outcome measurement."""

from datetime import datetime
from statistics import mean

from pydantic import AwareDatetime, Field, model_validator

from eurogas_nexus.application.nwe_balance_scenario import (
    BalanceHistoryInput,
    HddInput,
    ScenarioModel,
)
from eurogas_nexus.domain.fundamentals.balance import WeatherModel


class FrozenPrediction(ScenarioModel):
    model_id: str
    model_version: str
    selection_available_at: AwareDatetime
    prediction_origin: AwareDatetime
    coefficients: dict[str, float]
    feature_policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    features: tuple[HddInput, ...] = Field(min_length=1, max_length=31)
    reference_interval_radius: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_origin(self):
        if self.prediction_origin < self.selection_available_at:
            raise ValueError("model selection was unavailable at prediction origin")
        if len({r.day for r in self.features}) != len(self.features):
            raise ValueError("duplicate forecast day")
        if any(
            r.available_at > self.prediction_origin or r.day < self.prediction_origin.date()
            for r in self.features
        ):
            raise ValueError("forecast features are unavailable or historical")
        return self


def predict_frozen(payload: FrozenPrediction):
    model = WeatherModel(**payload.coefficients)
    points = []
    for row in sorted(payload.features, key=lambda row: row.day):
        value = model.call(row.hdd, row.day)
        if value < 0:
            raise ValueError("negative frozen supply-call prediction")
        points.append({"day": row.day.isoformat(), "call_gwh": value})
    return {
        "model_id": payload.model_id,
        "model_version": payload.model_version,
        "prediction_origin": payload.prediction_origin.isoformat(),
        "points": points,
        "reference_interval_radius": payload.reference_interval_radius,
        "interval_basis": "HISTORICAL_WALK_FORWARD_REFERENCE_NOT_PROSPECTIVE_CALIBRATION",
        "production_promoted": False,
    }


class ShadowEvaluation(ScenarioModel):
    prediction: dict
    actuals: tuple[BalanceHistoryInput, ...] = Field(min_length=1, max_length=31)
    evaluation_as_of: AwareDatetime
    maximum_mae_gwh: float = Field(ge=0)


def evaluate_shadow(payload: ShadowEvaluation):
    origin = datetime.fromisoformat(payload.prediction["prediction_origin"])
    if payload.evaluation_as_of <= origin:
        raise ValueError("shadow evaluation must follow the prediction origin")
    if len({r.day for r in payload.actuals}) != len(payload.actuals):
        raise ValueError("duplicate actual day")
    actuals = {
        r.day.isoformat(): r
        for r in payload.actuals
        if origin < r.available_at <= payload.evaluation_as_of
    }
    measured, missing = [], []
    for point in payload.prediction["points"]:
        row = actuals.get(point["day"])
        if row is None:
            missing.append(point["day"])
            continue
        actual = row.norway_gwh + row.lng_gwh + row.storage_net_withdrawal_gwh
        measured.append({"day": point["day"], "error": actual - point["call_gwh"]})
    mae = mean(abs(r["error"]) for r in measured) if measured else None
    return {
        "model_id": payload.prediction["model_id"],
        "model_version": payload.prediction["model_version"],
        "status": "COMPLETE" if not missing else "INCOMPLETE",
        "missing_days": missing,
        "mae_gwh": mae,
        "bias_gwh": mean(r["error"] for r in measured) if measured else None,
        "drifted": mae > payload.maximum_mae_gwh if mae is not None else None,
        "measured": measured,
        "automatic_promotion": False,
    }
