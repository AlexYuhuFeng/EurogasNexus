"""Reproducible caller-declared weather scenarios for the regional supply call.

This composition keeps the current live read separate from an explicit scenario.
The input hash identifies the supplied evidence, not a persisted or certified dataset.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from eurogas_nexus.domain.fundamentals.balance import (
    BalanceHistoryDay,
    Outage,
    forecast_balance,
)
from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date

ENGINE_VERSION = "nwe-balance-scenario/1"


class ScenarioModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


class BalanceHistoryInput(ScenarioModel):
    day: date
    norway_gwh: float = Field(ge=0)
    lng_gwh: float = Field(ge=0)
    storage_net_withdrawal_gwh: float
    available_at: AwareDatetime
    source_reference: str = Field(min_length=1, max_length=512)


class HddInput(ScenarioModel):
    day: date
    hdd: float = Field(ge=0, le=10_000)
    available_at: AwareDatetime
    source_reference: str = Field(min_length=1, max_length=512)


class WeatherInput(ScenarioModel):
    region: Literal["NWE"]
    feature_policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    heating_base_c: float = Field(ge=-50, le=50)
    gas_day_calendar: str = Field(min_length=1, max_length=64)
    history: tuple[HddInput, ...] = Field(min_length=1, max_length=800)
    forecast: tuple[HddInput, ...] = Field(default=(), max_length=31)


class OutageInput(ScenarioModel):
    start: date
    end: date | None = None
    unavailable_gwh_d: float = Field(ge=0)
    available_at: AwareDatetime
    source_reference: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def valid_window(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError("outage end must follow start")
        return self


class NweBalanceScenarioRequest(ScenarioModel):
    gas_day_calendar: str = "EU-CAM-UTC-2025"
    maximum_history_lag_days: int = Field(default=0, ge=0, le=31)
    prediction_origin: AwareDatetime
    start: date
    days: int = Field(ge=1, le=31)
    history: tuple[BalanceHistoryInput, ...] = Field(min_length=7, max_length=800)
    weather: WeatherInput | None = None
    outages: tuple[OutageInput, ...] = Field(default=(), max_length=256)
    inventory_twh: float | None = Field(default=None, ge=0)
    working_capacity_twh: float | None = Field(default=None, gt=0)
    # The desk's own trigger, e.g. "buy prompt cover when the call exceeds X GWh/d". With it
    # the result says whether the weather forecast changed that decision on any day (#50).
    decision_threshold_gwh: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_evidence(self):
        current_day = date.fromisoformat(
            gas_day_label(self.prediction_origin, self.gas_day_calendar)
        )
        if self.start < current_day:
            raise ValueError("scenario start must not precede prediction origin date")
        if len(self.history) < 7:
            if not self.history and getattr(self, "use_runtime_history", False):
                return self
            raise ValueError("at least seven historical gas days are required")
        if len({row.day for row in self.history}) != len(self.history):
            raise ValueError("balance history contains duplicate days")
        ordered = sorted(row.day for row in self.history)
        last_complete = current_day - timedelta(days=1)
        if (
            not last_complete - timedelta(days=self.maximum_history_lag_days)
            <= ordered[-1]
            <= last_complete
        ) or any(
            right - left != timedelta(days=1)
            for left, right in zip(ordered, ordered[1:], strict=False)
        ):
            raise ValueError("history must be consecutive, completed and within the declared lag")
        evidence = list(self.history) + list(self.outages)
        if any(row.day >= self.start for row in self.history):
            raise ValueError("balance history must precede scenario start")
        if self.weather is not None:
            weather = self.weather
            if weather.gas_day_calendar != self.gas_day_calendar:
                raise ValueError("weather and balance must use the same gas-day calendar")
            gas_day_start_for_date(self.start, weather.gas_day_calendar)
            for rows, historical in ((weather.history, True), (weather.forecast, False)):
                if len({row.day for row in rows}) != len(rows):
                    raise ValueError("weather contains duplicate days")
                for row in rows:
                    if historical and row.day >= self.start:
                        raise ValueError("historical HDD must precede scenario start")
                    if not historical and not self.start <= row.day < self.start + timedelta(
                        days=self.days
                    ):
                        raise ValueError("forecast HDD must lie inside scenario horizon")
                evidence.extend(rows)
        if any(row.available_at > self.prediction_origin for row in evidence):
            raise ValueError("evidence was unavailable at prediction origin")
        return self


def run_nwe_balance_scenario(payload: NweBalanceScenarioRequest) -> dict:
    """Compare an explicit HDD scenario with the identical no-weather baseline."""
    history = [
        BalanceHistoryDay(**row.model_dump(exclude={"available_at", "source_reference"}))
        for row in sorted(payload.history, key=lambda row: row.day)
    ]
    outages = [
        Outage(row.start, row.end, row.unavailable_gwh_d)
        for row in sorted(payload.outages, key=lambda row: row.model_dump_json())
    ]
    common = dict(
        start=payload.start,
        days=payload.days,
        norway_outages=outages,
        inventory_twh=payload.inventory_twh,
        working_capacity_twh=payload.working_capacity_twh,
    )
    baseline = forecast_balance(history, **common)
    weather = payload.weather
    hdd = {row.day: row.hdd for row in (*weather.history, *weather.forecast)} if weather else None
    selected = forecast_balance(history, hdd=hdd, **common)
    if any(row.call_gwh < 0 for row in selected.days):
        raise ValueError("weather regression produced a negative regional call")
    weather_days = sum(row.methods["call"] == "weather_regression" for row in selected.days)
    status = (
        "BASELINE_ONLY"
        if not weather_days
        else ("WEATHER_COMPLETE" if weather_days == payload.days else "WEATHER_PARTIAL")
    )
    warnings = list(selected.warnings)
    current_day = date.fromisoformat(
        gas_day_label(payload.prediction_origin, payload.gas_day_calendar)
    )
    lag = (current_day - timedelta(days=1) - history[-1].day).days
    if lag:
        warnings.append(f"BALANCE_HISTORY_LAG_DAYS:{lag}")
    if weather is not None and selected.model is None:
        warnings.append(
            "HDD_MODEL_NOT_FITTED: at least 30 matched, non-singular training days are required."
        )
    if weather is not None and weather_days < payload.days:
        warnings.append(
            "WEATHER_HORIZON_INCOMPLETE: baseline used on days without a fitted HDD prediction."
        )
    # Uncertainty: a 95 % band from the fit's in-sample standard error on weather days. It
    # is the regression's own error, not forecast skill; a vintage that is far out adds more.
    sigma = selected.model.residual_std_gwh if selected.model is not None else None
    bands = []
    for row in selected.days:
        weather_day = row.methods["call"] == "weather_regression" and sigma is not None
        half = 1.96 * sigma if weather_day else None
        bands.append({
            "day": row.day.isoformat(),
            "call_low_gwh": None if half is None else round(row.call_gwh - half, 1),
            "call_high_gwh": None if half is None else round(row.call_gwh + half, 1),
        })
    decision = None
    if payload.decision_threshold_gwh is not None:
        threshold = payload.decision_threshold_gwh
        changed, uncertain = [], []
        for row, base, band in zip(selected.days, baseline.days, bands, strict=True):
            if (row.call_gwh > threshold) != (base.call_gwh > threshold):
                changed.append(row.day.isoformat())
            low, high = band["call_low_gwh"], band["call_high_gwh"]
            if low is not None and low <= threshold <= high:
                uncertain.append(row.day.isoformat())
        decision = {
            "threshold_gwh": threshold,
            "rule": "act when the call exceeds the threshold",
            "baseline_days_over": sum(base.call_gwh > threshold for base in baseline.days),
            "weather_days_over": sum(row.call_gwh > threshold for row in selected.days),
            "changed": bool(changed),
            "changed_days": changed,
            "threshold_inside_band_days": uncertain,
        }
    canonical = payload.model_dump(mode="json")
    canonical["history"] = sorted(canonical["history"], key=lambda row: row["day"])
    if weather is not None:
        for key in ("history", "forecast"):
            canonical["weather"][key] = sorted(
                canonical["weather"][key], key=lambda row: row["day"]
            )
    canonical["outages"] = sorted(
        canonical["outages"], key=lambda row: json.dumps(row, sort_keys=True)
    )

    digest = hashlib.sha256(
        json.dumps(
            {"engine_version": ENGINE_VERSION, "inputs": canonical},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    evidence = [*payload.history, *payload.outages]
    if weather:
        evidence.extend((*weather.history, *weather.forecast))
    return {
        "data": {
            "input_hash": digest,
            "engine_version": ENGINE_VERSION,
            "input_basis": "CALLER_DECLARED_SCENARIO",
            "persisted": False,
            "status": status,
            "unit": "GWh/d",
            "target": "NWE_FLEXIBLE_SUPPLY_CALL",
            "forecast": [row.as_dict() for row in selected.days],
            "baseline": [row.as_dict() for row in baseline.days],
            "comparison": [
                {
                    "day": row.day.isoformat(),
                    "call_delta_gwh": row.call_gwh - base.call_gwh,
                    "storage_delta_gwh": row.storage_net_withdrawal_gwh
                    - base.storage_net_withdrawal_gwh,
                }
                for row, base in zip(selected.days, baseline.days, strict=True)
            ],
            "model": vars(selected.model) if selected.model is not None else None,
            "uncertainty": bands,
            "decision": decision,
            "inputs": canonical,
        },
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": sorted({row.source_reference for row in evidence}),
            "warnings": warnings,
            "validation_basis": "SCENARIO_IN_SAMPLE_FIT",
        },
    }
