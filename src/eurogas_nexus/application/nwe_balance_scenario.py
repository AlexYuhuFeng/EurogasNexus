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
from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

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
    forecast: tuple[HddInput, ...] = Field(min_length=1, max_length=31)


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
    prediction_origin: AwareDatetime
    start: date
    days: int = Field(ge=1, le=31)
    history: tuple[BalanceHistoryInput, ...] = Field(min_length=7, max_length=800)
    weather: WeatherInput | None = None
    outages: tuple[OutageInput, ...] = Field(default=(), max_length=256)
    inventory_twh: float | None = Field(default=None, ge=0)
    working_capacity_twh: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.start < self.prediction_origin.date():
            raise ValueError("scenario start must not precede prediction origin date")
        if len({row.day for row in self.history}) != len(self.history):
            raise ValueError("balance history contains duplicate days")
        ordered = sorted(row.day for row in self.history)
        if ordered[-1] != self.start - timedelta(days=1) or any(
            right - left != timedelta(days=1)
            for left, right in zip(ordered, ordered[1:], strict=False)
        ):
            raise ValueError("balance history must be consecutive and end the day before start")
        evidence = list(self.history) + list(self.outages)
        if any(row.day >= self.start for row in self.history):
            raise ValueError("balance history must precede scenario start")
        if self.weather is not None:
            weather = self.weather
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
    if weather is not None and selected.model is None:
        warnings.append(
            "HDD_MODEL_NOT_FITTED: at least 30 matched, non-singular training days are required."
        )
    if weather is not None and weather_days < payload.days:
        warnings.append(
            "WEATHER_HORIZON_INCOMPLETE: baseline used on days without a fitted HDD prediction."
        )
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
