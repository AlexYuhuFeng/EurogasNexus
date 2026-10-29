"""Route-level contract tests for ``GET /api/weather/forecasts``.

This test mounts only ``weather.router`` in a small FastAPI app.  It does not
install the production app-wide route-permission stack, so a 200 here is not
evidence of global route permission; the next contract check is a full-app
test over the real dependency chain.  The dependency override below supplies a
synthetic, already-authenticated principal as test scaffolding, not evidence
that the override path is a production authentication bypass.

Rows are persisted through the existing typed ECMWF repository fixture, and
the response hashes are compared with the actual stored provenance rather than
with values guessed from the API schema.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from eurogas_nexus.api.dependencies.identity import require_identity_for_route
from eurogas_nexus.api.routes.public import weather as weather_routes
from eurogas_nexus.api.schemas.weather_forecasts import (
    ForecastPointReading,
    ForecastReadEnvelope,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.certification import ProviderCertificationRecord
from eurogas_nexus.db.session import create_session_factory
from eurogas_nexus.security.identity import AuthenticatedPrincipal

try:
    from tests.db import test_ecmwf_forecast_repository as repo
except ModuleNotFoundError:  # pytest prepend mode
    import test_ecmwf_forecast_repository as repo  # type: ignore[no-redef]

SOURCE = "ECMWF_OPEN_DATA"
ORIGIN = datetime(2026, 1, 2, 4, 0, tzinfo=UTC)
VALID_FROM = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
VALID_TO = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
EARLY_RECEIPT = datetime(2026, 1, 2, 3, 0, tzinfo=UTC)
LATE_RECEIPT = datetime(2026, 1, 2, 6, 0, tzinfo=UTC)
FUTURE_EXPIRY = datetime(2099, 1, 1, tzinfo=UTC)
EXPIRED = datetime(2000, 1, 1, tzinfo=UTC)
EARLY_BYTES = repo.GRIB_BYTES + b"-early-available"
LATE_BYTES = repo.GRIB_BYTES + b"-late-available"
EARLY_SHA = hashlib.sha256(EARLY_BYTES).hexdigest()
LATE_SHA = hashlib.sha256(LATE_BYTES).hexdigest()
FORECAST_TABLE = repo.ForecastObservationRecord.__tablename__.casefold()

SYNTHETIC_PRINCIPAL = AuthenticatedPrincipal(
    principal_id="principal:test-weather-reader",
    name="Test Weather Reader",
    principal_type="SERVICE",
    role="ANALYST",
    status="ACTIVE",
    data_scopes=("*",),
    roles=("ANALYST",),
    email=None,
    identity_source="TEST_SYNTHETIC",
    auth_method="test_dependency_override",
)


@pytest.fixture()
def engine():
    sqlite_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        sqlite_engine,
        tables=[
            repo.CanonicalEntityRecord.__table__,
            repo.SourceEntityMappingRecord.__table__,
            repo.SeriesDefinitionRecord.__table__,
            repo.ForecastObservationRecord.__table__,
            ProviderCertificationRecord.__table__,
        ],
    )
    try:
        yield sqlite_engine
    finally:
        sqlite_engine.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session


def _make_app(engine, monkeypatch) -> FastAPI:
    app = FastAPI()
    app.state.settings = SimpleNamespace(allow_anonymous_callers=False)
    app.include_router(weather_routes.router)
    factory = create_session_factory(engine)
    monkeypatch.setattr(weather_routes, "get_session_factory", lambda: factory)
    return app


@pytest.fixture()
def authenticated_client(engine, monkeypatch):
    app = _make_app(engine, monkeypatch)

    async def _identity_override(request: Request) -> None:
        request.state.identity = SYNTHETIC_PRINCIPAL
        request.state.identity_authenticated = True

    app.dependency_overrides[require_identity_for_route] = _identity_override
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def unauthenticated_client(engine, monkeypatch):
    app = _make_app(engine, monkeypatch)
    with TestClient(app) as client:
        yield client


def _certification(*, expires_at_utc: datetime | None) -> ProviderCertificationRecord:
    return ProviderCertificationRecord(
        certification_id="certification-ecmwf-api-test",
        source_system=SOURCE,
        dataset="ecmwf_open_data_2t",
        environment="test",
        stage="live_validated",
        checks=["simulated_shape_match", "live_sample_validation"],
        evidence={"fixture": "tests/api/test_ecmwf_forecasts_api.py"},
        evaluated_by="operator:test",
        note="Synthetic route contract fixture; not production certification.",
        evaluated_at_utc=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        adapter_version="test",
        credential_label=None,
        entitlement_scope="*",
        sample_period_start_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        sample_period_end_utc=datetime(2026, 1, 1, 6, 0, tzinfo=UTC),
        tests_performed=["route_contract_fixture"],
        expires_at_utc=expires_at_utc,
        evidence_ref="tests/api/test_ecmwf_forecasts_api.py",
    )


def _seed_forecast_rows(
    session: Session, *, include_late: bool = False
) -> tuple[repo.ForecastObservationRecord, ...]:
    binding = repo._seed_identity(session, point_id="point-a")
    revisions = [(EARLY_RECEIPT, EARLY_BYTES, 5.0)]
    if include_late:
        revisions.append((LATE_RECEIPT, LATE_BYTES, 6.0))
    for receipt, grib_bytes, temperature_c in revisions:
        field, decoded, _ = repo._fixture(
            receipt=receipt,
            locations=repo.SINGLE_LOCATION,
            temperatures_celsius=(temperature_c,),
            grib_bytes=grib_bytes,
        )
        repo._append_forecast(session, field, decoded, (binding,))
    session.flush()
    return tuple(repo._rows(session))


def _params() -> dict[str, object]:
    return {
        "series_ids": [repo.SERIES_ID],
        "entity_ids": [repo.ENTITY_ID],
        "prediction_origin": ORIGIN.isoformat(),
        "valid_from": VALID_FROM.isoformat(),
        "valid_to": VALID_TO.isoformat(),
        "limit": "10",
    }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@contextmanager
def _capture_forecast_queries(engine) -> Iterator[list[str]]:
    statements: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany) -> None:
        if FORECAST_TABLE in statement.casefold():
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _listener)


def test_missing_identity_is_401_before_any_forecast_query(
    unauthenticated_client, engine
) -> None:
    with _capture_forecast_queries(engine) as statements:
        response = unauthenticated_client.get(
            "/api/weather/forecasts", params=_params()
        )

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "authentication_required"
    assert statements == []


def test_missing_certification_is_503_before_any_forecast_query(
    authenticated_client, session, engine
) -> None:
    _seed_forecast_rows(session)
    session.commit()

    with _capture_forecast_queries(engine) as statements:
        response = authenticated_client.get(
            "/api/weather/forecasts", params=_params()
        )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "forecast_source_unavailable"
    assert statements == []


def test_expired_certification_is_503_before_any_forecast_query(
    authenticated_client, session, engine
) -> None:
    _seed_forecast_rows(session)
    session.add(_certification(expires_at_utc=EXPIRED))
    session.commit()

    with _capture_forecast_queries(engine) as statements:
        response = authenticated_client.get(
            "/api/weather/forecasts", params=_params()
        )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "forecast_source_unavailable"
    assert "expired" in detail["message"].casefold()
    assert statements == []


def test_valid_certification_returns_future_typed_reading_with_stored_hashes(
    authenticated_client, session
) -> None:
    rows = _seed_forecast_rows(session)
    session.add(_certification(expires_at_utc=FUTURE_EXPIRY))
    session.flush()
    row = rows[0]
    expected_observation_id = row.forecast_observation_id
    expected_available_at = _utc(row.available_at_utc)
    expected_raw_sha256 = row.provenance["grib"]["sha256"]
    expected_content_sha256 = row.provenance["content_sha256"]
    assert expected_raw_sha256 == EARLY_SHA
    session.commit()

    response = authenticated_client.get("/api/weather/forecasts", params=_params())

    assert response.status_code == 200, response.text
    body = response.json()
    envelope = ForecastReadEnvelope.model_validate_json(response.text)
    assert envelope.meta.research_only is True
    assert envelope.meta.source_references == (SOURCE,)
    assert len(envelope.data) == 1

    reading = envelope.data[0]
    assert set(body["data"][0]) == set(ForecastPointReading.model_fields)
    assert reading.observation_id == expected_observation_id
    assert reading.point_id == "point-a"
    assert reading.series_id == repo.SERIES_ID
    assert reading.entity_id == repo.ENTITY_ID
    assert reading.source_system == SOURCE
    assert reading.provider == "ECMWF"
    assert reading.unit == "degC"
    assert reading.valid_at_utc > ORIGIN
    assert reading.available_at_utc == expected_available_at
    assert reading.raw_grib_sha256 == expected_raw_sha256
    assert reading.record_content_sha256 == expected_content_sha256


def test_late_availability_is_excluded_at_prediction_origin(
    authenticated_client, session
) -> None:
    rows = _seed_forecast_rows(session, include_late=True)
    session.add(_certification(expires_at_utc=FUTURE_EXPIRY))
    session.flush()
    early = next(
        row for row in rows if row.provenance["grib"]["sha256"] == EARLY_SHA
    )
    late = next(row for row in rows if row.provenance["grib"]["sha256"] == LATE_SHA)
    assert _utc(early.available_at_utc) <= ORIGIN
    assert _utc(late.available_at_utc) > ORIGIN
    early_id = early.forecast_observation_id
    late_id = late.forecast_observation_id
    session.commit()

    response = authenticated_client.get("/api/weather/forecasts", params=_params())

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [item["observation_id"] for item in data] == [early_id]
    assert late_id not in {item["observation_id"] for item in data}
    assert data[0]["temperature_c"] == pytest.approx(5.0)
