"""Versioned regional point mappings and degree-day policy, independent of a forecast run."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from eurogas_nexus.application.nwe_balance_scenario import ScenarioModel
from eurogas_nexus.application.research.weather_demand_inputs import (
    LEFT_HOLD_INSTANT,
    ForecastPointBinding,
)
from eurogas_nexus.domain.research.weather_demand import (
    DegreeDayFeaturePolicy,
    RegionLocationWeight,
)


class ProfileBinding(ScenarioModel):
    point_id: str = Field(min_length=1, max_length=160)
    series_id: str = Field(min_length=1, max_length=160)
    entity_id: str = Field(min_length=1, max_length=128)
    location_id: str = Field(min_length=1, max_length=160)
    region: Literal["NWE"]
    weight: Decimal = Field(ge=0, le=1, max_digits=18, decimal_places=12)

    @field_validator("weight")
    @classmethod
    def normalize_weight(cls, value):
        return value.normalize()


class WeatherRegionProfile(ScenarioModel):
    region: Literal["NWE"]
    point_bindings: tuple[ProfileBinding, ...] = Field(min_length=1, max_length=64)
    heating_base_c: float = Field(ge=-50, le=50)
    cooling_base_c: float = Field(ge=-50, le=50)
    gas_day_calendar: str = Field(min_length=1, max_length=64)
    max_hold_minutes: int = Field(ge=1, le=10080)
    min_covered_fraction: float = Field(ge=0, le=1)


def build_weather_profile(payload: WeatherRegionProfile):
    if len({b.point_id for b in payload.point_bindings}) != len(payload.point_bindings):
        raise ValueError("duplicate profile grid point")
    if sum((b.weight for b in payload.point_bindings), Decimal(0)) != 1:
        raise ValueError("profile weights must sum exactly to one")
    for binding in payload.point_bindings:
        ForecastPointBinding(**binding.model_dump(exclude={"weight"}))
    policy = DegreeDayFeaturePolicy(
        region=payload.region,
        heating_base_c=payload.heating_base_c,
        cooling_base_c=payload.cooling_base_c,
        max_gap_minutes=payload.max_hold_minutes,
        min_covered_fraction=payload.min_covered_fraction,
        location_weights=tuple(
            RegionLocationWeight(b.location_id, b.weight) for b in payload.point_bindings
        ),
        gas_day_calendar=payload.gas_day_calendar,
        temporal_method=LEFT_HOLD_INSTANT,
    )
    return {
        "feature_policy_hash": policy.policy_hash,
        "profile": payload.model_dump(mode="json"),
        "eligible_for_shadow": True,
        "requires_reviewer_adoption": True,
    }
