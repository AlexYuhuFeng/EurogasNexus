"""Persisted-weather composition uses the certified, bounded weather reader."""

from datetime import timedelta

import pytest
from fastapi import Request

from eurogas_nexus.api.balance_weather import compose_balance_weather
from eurogas_nexus.api.schemas.nwe_balance import NweBalanceRequest
from tests.api.test_ecmwf_forecasts_api import authenticated_client as authenticated_client
from tests.api.test_ecmwf_forecasts_api import engine as engine
from tests.api.test_ecmwf_forecasts_api import session as session
from tests.api.test_weather_degree_days_api import (
    EARLY_RECEIPT,
    FUTURE_EXPIRY,
    GAS_DAY,
    ORIGIN,
    _certification,
    _payload,
    _point_binding,
    _seed_full_day,
)


def payload():
    window = _payload(region="NWE", point_binding=_point_binding(region="NWE"))
    return {
        "prediction_origin": ORIGIN.isoformat(),
        "start": GAS_DAY.isoformat(),
        "days": 1,
        "maximum_history_lag_days": 1,
        "history": [
            dict(
                day=(GAS_DAY - timedelta(days=i)).isoformat(),
                norway_gwh=100,
                lng_gwh=40,
                storage_net_withdrawal_gwh=20,
                available_at=EARLY_RECEIPT.isoformat(),
                source_reference="test:balance",
            )
            for i in range(1, 8)
        ],
        "persisted_weather": [window],
    }


def test_stored_read_preserves_actual_vintage_and_availability(
    authenticated_client, session, monkeypatch
):
    from tests.api.test_ecmwf_forecasts_api import SYNTHETIC_PRINCIPAL

    _seed_full_day(
        session, monkeypatch, temperature_c=4, receipt=EARLY_RECEIPT, suffix=b"-balance-weather"
    )
    session.add(_certification(expires_at_utc=FUTURE_EXPIRY))
    session.commit()
    request = Request({"type": "http", "method": "POST", "path": "/api/market/nwe-balance"})
    request.state.identity = SYNTHETIC_PRINCIPAL
    resolved, evidence, warnings = compose_balance_weather(
        NweBalanceRequest.model_validate(payload()), request
    )
    assert resolved.weather is None  # no historical temperatures invented from today's forecast
    assert evidence[0]["vintage"] is not None
    assert "PERSISTED_HDD_HISTORY_UNAVAILABLE" in warnings
    assert evidence[0]["source_refs"]


@pytest.mark.parametrize("change", ["region", "origin", "overlap", "mixed"])
def test_reject_mismatched_persisted_windows(change):
    body = payload()
    if change == "region":
        body["persisted_weather"][0]["region"] = "GB"
    elif change == "origin":
        body["persisted_weather"][0]["prediction_origin"] = "2026-01-01T00:00:00Z"
    elif change == "overlap":
        body["persisted_weather"].append(body["persisted_weather"][0])
    else:
        from tests.api.test_nwe_balance_scenario import scenario

        body["weather"] = scenario()["weather"]
    with pytest.raises(ValueError):
        NweBalanceRequest.model_validate(body)
