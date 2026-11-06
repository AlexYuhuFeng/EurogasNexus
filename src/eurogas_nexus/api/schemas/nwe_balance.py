"""Optional persisted-weather composition on the existing scenario operation."""

from pydantic import Field, model_validator

from eurogas_nexus.api.schemas.weather_degree_days import WeatherDegreeDayRequest
from eurogas_nexus.application.nwe_balance_scenario import (
    BalanceHistoryInput,
    NweBalanceScenarioRequest,
)


class NweBalanceRequest(NweBalanceScenarioRequest):
    use_runtime_history: bool = False
    history: tuple[BalanceHistoryInput, ...] = Field(default=(), max_length=800)
    weather_profile_id: str | None = Field(default=None, min_length=1, max_length=64)
    persisted_weather: tuple[WeatherDegreeDayRequest, ...] = Field(default=(), max_length=63)

    @model_validator(mode="after")
    def matching_weather_requests(self):
        if self.use_runtime_history and self.history:
            raise ValueError("runtime history cannot be mixed with declared history")
        if self.weather_profile_id is not None and not self.persisted_weather:
            raise ValueError("a reviewed weather profile requires persisted forecast windows")
        if self.persisted_weather and self.weather is not None:
            raise ValueError("choose declared weather or persisted weather, not both")
        policy = None
        days = set()
        for item in self.persisted_weather:
            if item.region != "NWE" or item.prediction_origin != self.prediction_origin:
                raise ValueError(
                    "persisted weather must use NWE and the scenario prediction origin"
                )
            identity = item.model_dump(mode="json", exclude={"gas_days"})
            if policy is not None and identity != policy:
                raise ValueError("all weather windows must use identical point weights and policy")
            policy = identity
            if days.intersection(item.gas_days):
                raise ValueError("persisted weather windows must not overlap")
            days.update(item.gas_days)
        return self
