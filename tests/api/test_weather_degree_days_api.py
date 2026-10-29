"""Route-level contract tests for ``POST /api/weather/degree-days``.

The app mounts only ``weather.router`` and installs a synthetic, already-
authenticated principal through a FastAPI dependency override.  This is test
scaffolding for the route contract, not evidence of SSO, production
authentication, or app-wide route permission.  Persisted inputs are created
through the existing typed ECMWF repository fixture and the actual 3-hourly
bridge fixture helpers; the tests do not construct response values directly.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from eurogas_nexus.domain.market.gas_day import DEFAULT_GAS_DAY_CALENDAR

try:
    from tests.api.test_ecmwf_forecasts_api import (
        EXPIRED,
        FUTURE_EXPIRY,
        _capture_forecast_queries,
        _certification,
    )
    from tests.api.test_ecmwf_forecasts_api import (
        authenticated_client as authenticated_client,
    )
    from tests.api.test_ecmwf_forecasts_api import (
        engine as engine,
    )
    from tests.api.test_ecmwf_forecasts_api import (
        session as session,
    )
    from tests.api.test_ecmwf_forecasts_api import (
        unauthenticated_client as unauthenticated_client,
    )
    from tests.db.test_ecmwf_weather_feature_bridge import (
        EARLY_RECEIPT,
        GAS_DAY,
        LATE_RECEIPT,
        LOCATION_ID,
        ORIGIN,
        _persist_day_revision,
        _repo,
    )
except ModuleNotFoundError:  # pytest prepend mode
    from test_ecmwf_forecasts_api import (  # type: ignore[no-redef]
        EXPIRED,
        FUTURE_EXPIRY,
        _capture_forecast_queries,
        _certification,
    )
    from test_ecmwf_forecasts_api import (
        authenticated_client as authenticated_client,
    )
    from test_ecmwf_forecasts_api import (
        engine as engine,
    )
    from test_ecmwf_forecasts_api import (
        session as session,
    )
    from test_ecmwf_forecasts_api import (
        unauthenticated_client as unauthenticated_client,
    )
    from test_ecmwf_weather_feature_bridge import (  # type: ignore[no-redef]
        EARLY_RECEIPT,
        GAS_DAY,
        LATE_RECEIPT,
        LOCATION_ID,
        ORIGIN,
        _persist_day_revision,
        _repo,
    )

DEGREE_DAYS_PATH = "/api/weather/degree-days"


def _point_binding(**overrides: object) -> dict[str, object]:
    binding: dict[str, object] = {
        "point_id": "point-a",
        "series_id": _repo.SERIES_ID,
        "entity_id": _repo.ENTITY_ID,
        "location_id": LOCATION_ID,
        "region": "GB",
        "weight": "1",
    }
    binding.update(overrides)
    return binding


def _payload(
    *, point_binding: dict[str, object] | None = None, **overrides: object
) -> dict[str, object]:
    body: dict[str, object] = {
        "region": "GB",
        "point_bindings": [point_binding or _point_binding()],
        "gas_days": [GAS_DAY.isoformat()],
        "prediction_origin": ORIGIN.isoformat(),
        "heating_base_c": 18.0,
        "cooling_base_c": 20.0,
        "gas_day_calendar": DEFAULT_GAS_DAY_CALENDAR,
        "max_hold_minutes": 180,
        "min_covered_fraction": 1.0,
    }
    body.update(overrides)
    return body


def _persist_day_steps(
    session,
    monkeypatch,
    *,
    steps: tuple[int, ...],
    temperature_c: float = 4.0,
    receipt: datetime = EARLY_RECEIPT,
    grib_suffix: bytes = b"-degree-days-gap",
) -> None:
    """Persist the same typed 3-hourly day fixture with selected steps omitted."""

    _repo._seed_identity(session, point_id="point-a")
    for step_hours in steps:
        monkeypatch.setattr(_repo, "STEP_HOURS", step_hours)
        transport, decoded, _ = _repo._fixture(
            receipt=receipt,
            locations=_repo.SINGLE_LOCATION,
            temperatures_celsius=(temperature_c,),
            grib_bytes=_repo.GRIB_BYTES + grib_suffix,
        )
        _repo._append_forecast(
            session,
            transport,
            decoded,
            (_repo._binding("point-a"),),
        )
    session.flush()


def _seed_full_day(
    session,
    monkeypatch,
    *,
    temperature_c: float,
    receipt: datetime,
    suffix: bytes,
) -> None:
    _repo._seed_identity(session, point_id="point-a")
    _persist_day_revision(
        session,
        monkeypatch,
        temperature_c=temperature_c,
        receipt=receipt,
        grib_bytes=_repo.GRIB_BYTES + suffix,
    )


def test_missing_identity_is_401_before_any_forecast_query(
    unauthenticated_client, engine
) -> None:
    with _capture_forecast_queries(engine) as statements:
        response = unauthenticated_client.post(DEGREE_DAYS_PATH, json=_payload())

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "authentication_required"
    assert statements == []


def test_missing_certification_is_503_before_any_forecast_query(
    authenticated_client, session, engine, monkeypatch
) -> None:
    _seed_full_day(
        session,
        monkeypatch,
        temperature_c=4.0,
        receipt=EARLY_RECEIPT,
        suffix=b"-degree-days-missing-cert",
    )
    session.commit()

    with _capture_forecast_queries(engine) as statements:
        response = authenticated_client.post(DEGREE_DAYS_PATH, json=_payload())

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "forecast_source_unavailable"
    assert statements == []


def test_expired_certification_is_503_before_any_forecast_query(
    authenticated_client, session, engine, monkeypatch
) -> None:
    _seed_full_day(
        session,
        monkeypatch,
        temperature_c=4.0,
        receipt=EARLY_RECEIPT,
        suffix=b"-degree-days-expired-cert",
    )
    session.add(_certification(expires_at_utc=EXPIRED))
    session.commit()

    with _capture_forecast_queries(engine) as statements:
        response = authenticated_client.post(DEGREE_DAYS_PATH, json=_payload())

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "forecast_source_unavailable"
    assert "expired" in detail["message"].casefold()
    assert statements == []


def test_point_binding_weights_not_exactly_one_are_rejected_422(
    authenticated_client,
) -> None:
    response = authenticated_client.post(
        DEGREE_DAYS_PATH,
        json=_payload(point_binding=_point_binding(weight="0.5")),
    )

    assert response.status_code == 422
    assert "weights must sum exactly to 1" in response.text


def test_actual_persisted_full_gas_day_at_4c_returns_hdd_14_and_coverage_1(
    authenticated_client, session, monkeypatch
) -> None:
    _seed_full_day(
        session,
        monkeypatch,
        temperature_c=4.0,
        receipt=EARLY_RECEIPT,
        suffix=b"-degree-days-full-day",
    )
    session.add(_certification(expires_at_utc=FUTURE_EXPIRY))
    session.commit()

    response = authenticated_client.post(DEGREE_DAYS_PATH, json=_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    day = data["daily"][0]

    assert data["region"] == "GB"
    assert day["gas_day"] == GAS_DAY.isoformat()
    assert day["daily_mean_temperature_c"] == pytest.approx(4.0)
    assert day["daily_mean_hdd"] == pytest.approx(14.0)
    assert day["covered_fraction"] == pytest.approx(1.0)
    assert day["coverage_complete"] is True
    assert day["missing_reason"] is None
    assert {
        "CALLER_DEFINED_REGION_WEIGHTS",
        "LEFT_HOLD_APPROXIMATION",
    } <= set(body["meta"]["warnings"])


@pytest.mark.parametrize(
    "steps",
    [
        pytest.param((3, 6, 9, 15, 18, 21, 24, 27, 30), id="internal-gap"),
        pytest.param((3, 6, 9, 12, 15, 18, 21, 24, 27), id="no-right-bracket"),
    ],
)
def test_gap_or_missing_bracket_returns_null_not_zero(
    authenticated_client, session, monkeypatch, steps
) -> None:
    _persist_day_steps(session, monkeypatch, steps=steps)
    session.add(_certification(expires_at_utc=FUTURE_EXPIRY))
    session.commit()

    response = authenticated_client.post(DEGREE_DAYS_PATH, json=_payload())

    assert response.status_code == 200, response.text
    day = response.json()["data"]["daily"][0]
    assert "daily_mean_hdd" in day
    assert day["daily_mean_hdd"] is None
    assert day["daily_mean_hdd"] != 0
    assert day["time_integral_heating_degree_day"] is None
    assert day["coverage_complete"] is False
    assert 0.0 < day["covered_fraction"] < 1.0
    assert day["missing_reason"] == "INSUFFICIENT_COVERAGE"


def test_later_receipt_is_excluded_at_the_prediction_origin(
    authenticated_client, session, monkeypatch
) -> None:
    _seed_full_day(
        session,
        monkeypatch,
        temperature_c=4.0,
        receipt=EARLY_RECEIPT,
        suffix=b"-degree-days-early",
    )
    _persist_day_revision(
        session,
        monkeypatch,
        temperature_c=20.0,
        receipt=LATE_RECEIPT,
        grib_bytes=_repo.GRIB_BYTES + b"-degree-days-late",
    )
    session.add(_certification(expires_at_utc=FUTURE_EXPIRY))
    session.commit()
    rows = _repo._rows(session)
    assert len(rows) == 20
    assert any(_repo._utc(row.available_at_utc) > ORIGIN for row in rows)

    response = authenticated_client.post(DEGREE_DAYS_PATH, json=_payload())

    assert response.status_code == 200, response.text
    day = response.json()["data"]["daily"][0]
    assert day["daily_mean_hdd"] == pytest.approx(14.0)
    assert day["coverage_complete"] is True


def test_mismatched_point_binding_is_refused_422(
    authenticated_client, session, monkeypatch
) -> None:
    _seed_full_day(
        session,
        monkeypatch,
        temperature_c=4.0,
        receipt=EARLY_RECEIPT,
        suffix=b"-degree-days-mismatch",
    )
    session.add(_certification(expires_at_utc=FUTURE_EXPIRY))
    session.commit()

    response = authenticated_client.post(
        DEGREE_DAYS_PATH,
        json=_payload(point_binding=_point_binding(point_id="point-b")),
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "invalid_degree_day_inputs"
    assert "no explicit caller binding" in detail["message"].casefold()
