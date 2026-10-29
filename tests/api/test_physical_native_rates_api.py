"""Focused RFC0005 physical reader-admission API tests.

These use real SQLite-persisted model rows so row admission, SQL ordering,
bounding and serialization are exercised together.  PostgreSQL remains the
root reviewer's authoritative environment.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import JSON, create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public import physical as physical_module
from eurogas_nexus.application.agents import db_bridge
from eurogas_nexus.application.physical_native_rates import (
    NativeRateProjectionError,
    serialize_native_rate,
)
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import CapacityObservationRecord, FlowObservationRecord
from eurogas_nexus.ingestion.entsog_native_units import (
    NORMALIZER_VERSION,
    EntsogNativeUnitError,
    parse_entsog_native_rate,
)

_PERIOD_START = datetime(2026, 6, 1, tzinfo=UTC)
_PERIOD_END = datetime(2026, 6, 2, tzinfo=UTC)
_OBSERVED_AT = datetime(2026, 6, 1, 12, tzinfo=UTC)
_PAYLOAD_SHA256 = "a" * 64


def _metadata(archive_id: str = "archive-native-1") -> dict[str, str]:
    return {
        "normalized_period_start_utc": "2026-06-01T00:00:00+00:00",
        "normalized_period_end_utc": "2026-06-02T00:00:00+00:00",
        "source_receipt_at_utc": "2026-06-01T12:00:00+00:00",
        "raw_archive_id": archive_id,
        "payload_sha256": _PAYLOAD_SHA256,
    }


def _native_payload(value_text: str, *, volume: bool) -> dict[str, object]:
    units = (
        (
            "m3/d",
            "m³/d",
            "Mcm/d",
            "mcm/d",
            "MCM/d",
            "m3/day",
            "m³/day",
            "m3/h",
            "m³/h",
            "m3",
            "m³",
            "Mcm",
        )
        if volume
        else (
            "kWh/d",
            "kWh/day",
            "MWh/d",
            "GWh/d",
            "kWh/h",
            "MWh/h",
            "GWh/h",
            "kWh",
            "MWh",
            "GWh",
        )
    )
    expected_kind = "volume" if volume else "energy"
    for unit in units:
        try:
            rate = parse_entsog_native_rate(value_text, unit)
        except EntsogNativeUnitError:
            continue
        if rate.quantity_kind != expected_kind:
            continue
        if expected_kind == "volume" and rate.volume_mcm_per_day is None:
            continue
        if expected_kind == "energy" and rate.energy_kwh_per_day is None:
            continue
        return serialize_native_rate(rate)
    raise AssertionError(f"no supported native {expected_kind} unit in test fixture")


def _flow_observation(**overrides) -> FlowObservationRecord:
    values = {
        "observation_id": "flow-1",
        "point_id": "BE-IUK-ZEEBRUGGE-ENTRY",
        "point_name": "Zeebrugge Interconnector Entry",
        "direction": "entry",
        "kind": "actual",
        "flow_mcm_d": None,
        "period_start_utc": _PERIOD_START,
        "period_end_utc": _PERIOD_END,
        "observed_at_utc": _OBSERVED_AT,
        "source_system": "ENTSOG",
        "source_reference": "entsog-operationaldatas",
        "source_record_id": "flow-source-1",
        "freshness": "live",
        "research_only": True,
        "metadata_json": _metadata(),
    }
    values.update(overrides)
    return FlowObservationRecord(**values)


def _capacity_observation(**overrides) -> CapacityObservationRecord:
    values = {
        "observation_id": "capacity-1",
        "point_id": "BE-IUK-ZEEBRUGGE-ENTRY",
        "point_name": "Zeebrugge Interconnector Entry",
        "direction": "entry",
        "capacity_type": "firm_technical",
        "capacity_mcm_d": None,
        "original_value": None,
        "original_unit": None,
        "period_start_utc": _PERIOD_START,
        "period_end_utc": _PERIOD_END,
        "observed_at_utc": _OBSERVED_AT,
        "source_system": "ENTSOG",
        "source_reference": "entsog-operationaldatas",
        "source_record_id": "capacity-source-1",
        "freshness": "live",
        "research_only": True,
        "metadata_json": _metadata("archive-capacity-1"),
    }
    values.update(overrides)
    return CapacityObservationRecord(**values)


def _database(monkeypatch, tmp_path, name: str):
    path = tmp_path / f"{name}.sqlite"
    database_url = f"sqlite+pysqlite:///{path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    for env_name in (
        "DATABASE_URL",
        "EUROGAS_NEXUS_DB_DSN",
        "EUROGAS_NEXUS_DATABASE_URL",
        "EUROGAS_NEXUS_RUNTIME_STORE_DATABASE_URL",
    ):
        monkeypatch.delenv(env_name, raising=False)
    return engine


def _clear_database_env(monkeypatch) -> None:
    for env_name in (
        "RUNTIME_STORE_DATABASE_URL",
        "DATABASE_URL",
        "EUROGAS_NEXUS_DB_DSN",
        "EUROGAS_NEXUS_DATABASE_URL",
        "EUROGAS_NEXUS_RUNTIME_STORE_DATABASE_URL",
    ):
        monkeypatch.delenv(env_name, raising=False)


def test_volume_withholds_legacy_entsog_and_keeps_non_entsog(
    tmp_path, monkeypatch
) -> None:
    engine = _database(monkeypatch, tmp_path, "legacy-volume")
    with Session(engine) as session:
        session.add_all(
            [
                _flow_observation(
                    observation_id="legacy-entsog",
                    source_system=" entsog ",
                    flow_mcm_d=5.5,
                ),
                _flow_observation(
                    observation_id="non-entsog",
                    point_name="Bacton",
                    source_system="National Gas",
                    source_reference="national-gas",
                    source_record_id="ng-1",
                    flow_mcm_d=7.5,
                ),
            ]
        )
        session.commit()

    client = TestClient(create_app())
    response = client.get("/api/physical/flows")

    assert response.status_code == 200
    payload = response.json()
    assert [row["observation_id"] for row in payload["data"]] == ["non-entsog"]
    assert payload["data"][0]["flow_mcm_d"] == 7.5
    warnings = " ".join(payload["meta"]["warnings"]).lower()
    assert "legacy entsog" in warnings
    assert "does not mean" in warnings

    native_response = client.get("/api/physical/flows?quantity_basis=native")
    assert native_response.status_code == 200
    assert native_response.json()["data"] == []


def test_volume_default_returns_all_admitted_rows_beyond_limit(
    tmp_path, monkeypatch
) -> None:
    engine = _database(monkeypatch, tmp_path, "volume-unbounded")
    with Session(engine) as session:
        session.add_all(
            [
                _flow_observation(
                    observation_id=f"volume-{index:03d}",
                    point_id=f"POINT-{index:03d}",
                    point_name=f"Point {index:03d}",
                    source_system="National Gas",
                    source_reference="national-gas",
                    source_record_id=f"ng-{index:03d}",
                    flow_mcm_d=float(index + 1),
                )
                for index in range(205)
            ]
        )
        session.commit()

    response = TestClient(create_app()).get("/api/physical/flows")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert len(rows) == 205
    assert {row["observation_id"] for row in rows} == {
        f"volume-{index:03d}" for index in range(205)
    }

    limited_response = TestClient(create_app()).get("/api/physical/flows?limit=1")
    assert limited_response.status_code == 200
    assert len(limited_response.json()["data"]) == 205


def test_native_energy_is_never_exposed_as_volume(tmp_path, monkeypatch) -> None:
    engine = _database(monkeypatch, tmp_path, "native-energy")
    exact_value = "987654321.123456789"
    native = _native_payload(exact_value, volume=False)
    assert native["quantity_kind"] == "energy"
    assert native["volume_mcm_per_day"] is None
    with Session(engine) as session:
        session.add(
            _flow_observation(
                observation_id="native-energy",
                flow_mcm_d=999.0,
                normalizer_version=native["normalizer_version"],
                native_rate_json=native,
            )
        )
        session.commit()

    client = TestClient(create_app())
    volume_response = client.get("/api/physical/flows")
    assert volume_response.status_code == 200
    assert volume_response.json()["data"] == []

    native_response = client.get("/api/physical/flows?quantity_basis=native")
    assert native_response.status_code == 200
    rows = native_response.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    assert row["quantity_basis"] == "native"
    assert "flow_mcm_d" not in row
    assert "original_value" not in row
    assert row["native_rate_json"]["value_text"] == exact_value
    assert row["native_rate_json"]["volume_mcm_per_day"] is None


def test_native_volume_is_exact_in_both_modes_and_filter_is_invoked(
    tmp_path, monkeypatch
) -> None:
    engine = _database(monkeypatch, tmp_path, "native-volume")
    exact_value = "123456789.123456789012345678"
    native = _native_payload(exact_value, volume=True)
    canonical_volume = float(native["volume_mcm_per_day"])
    with Session(engine) as session:
        session.add(
            _flow_observation(
                observation_id="native-volume",
                flow_mcm_d=canonical_volume,
                normalizer_version=native["normalizer_version"],
                native_rate_json=native,
            )
        )
        session.commit()

    real_filter_rows = physical_module.filter_rows
    filter_calls: list[int] = []

    def _spy_filter_rows(request, rows, **kwargs):
        materialized = list(rows)
        filter_calls.append(len(materialized))
        return real_filter_rows(request, materialized, **kwargs)

    monkeypatch.setattr(physical_module, "filter_rows", _spy_filter_rows)

    client = TestClient(create_app())
    volume_response = client.get("/api/physical/flows")
    assert volume_response.status_code == 200
    volume_rows = volume_response.json()["data"]
    assert len(volume_rows) == 1
    assert volume_rows[0]["flow_mcm_d"] == canonical_volume
    assert "native_rate_json" not in volume_rows[0]

    native_response = client.get("/api/physical/flows?quantity_basis=native")
    assert native_response.status_code == 200
    native_rows = native_response.json()["data"]
    assert len(native_rows) == 1
    row = native_rows[0]
    assert row["quantity_basis"] == "native"
    assert "flow_mcm_d" not in row
    assert "original_value" not in row
    assert row["source_system"] == "ENTSOG"
    assert row["normalizer_version"] == native["normalizer_version"]
    assert row["native_rate_json"]["value_text"] == exact_value
    assert row["native_rate_json"]["native_value"] == exact_value
    assert row["raw_archive_id"] == "archive-native-1"
    assert row["payload_sha256"] == _PAYLOAD_SHA256
    assert row["received_at_utc"] == "2026-06-01T12:00:00+00:00"
    assert filter_calls == [1, 1]


def test_capacity_native_volume_and_legacy_withheld(tmp_path, monkeypatch) -> None:
    engine = _database(monkeypatch, tmp_path, "capacity-native")
    native = _native_payload("4321.123456789012345", volume=True)
    canonical_volume = float(native["volume_mcm_per_day"])
    with Session(engine) as session:
        session.add_all(
            [
                _capacity_observation(
                    observation_id="capacity-native",
                    capacity_mcm_d=canonical_volume,
                    original_value=123,
                    original_unit="m3/d",
                    normalizer_version=native["normalizer_version"],
                    native_rate_json=native,
                ),
                _capacity_observation(
                    observation_id="capacity-legacy",
                    capacity_mcm_d=112.5,
                    original_value=1186875000,
                    original_unit="kwh/d",
                ),
            ]
        )
        session.commit()

    client = TestClient(create_app())
    volume_response = client.get("/api/physical/capacity")
    assert volume_response.status_code == 200
    volume_payload = volume_response.json()
    assert [row["observation_id"] for row in volume_payload["data"]] == [
        "capacity-native"
    ]
    assert volume_payload["data"][0]["capacity_mcm_d"] == canonical_volume
    assert volume_payload["data"][0]["original_value"] == 123
    warnings = " ".join(volume_payload["meta"]["warnings"]).lower()
    assert "legacy entsog" in warnings

    native_response = client.get("/api/physical/capacity?quantity_basis=native")
    assert native_response.status_code == 200
    native_rows = native_response.json()["data"]
    assert len(native_rows) == 1
    row = native_rows[0]
    assert row["capacity_type"] == "firm_technical"
    assert row["quantity_basis"] == "native"
    assert "capacity_mcm_d" not in row
    assert "original_value" not in row
    assert "original_unit" not in row


def test_agent_malformed_native_row_is_not_an_empty_reading(
    tmp_path, monkeypatch
) -> None:
    engine = _database(monkeypatch, tmp_path, "agent-native")
    native_energy = _native_payload("987654321.123456789", volume=False)
    with Session(engine) as session:
        session.add_all(
            [
                _flow_observation(
                    observation_id="agent-legacy",
                    flow_mcm_d=5.5,
                ),
                _flow_observation(
                    observation_id="agent-energy",
                    flow_mcm_d=9.0,
                    normalizer_version=native_energy["normalizer_version"],
                    native_rate_json=native_energy,
                ),
            ]
        )
        session.commit()

    with Session(engine) as session:
        assert db_bridge.flow_rows(session) == []

    with Session(engine) as session:
        session.add(
            _flow_observation(
                observation_id="agent-partial",
                flow_mcm_d=1.0,
                normalizer_version=NORMALIZER_VERSION,
                native_rate_json={"broken": "secret-raw-value"},
            )
        )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(NativeRateProjectionError):
            db_bridge.flow_rows(session)


def test_invalid_native_payload_is_typed_503_without_echo(tmp_path, monkeypatch) -> None:
    engine = _database(monkeypatch, tmp_path, "native-invalid")
    with Session(engine) as session:
        session.add(
            _flow_observation(
                observation_id="native-invalid",
                flow_mcm_d=1.0,
                normalizer_version=NORMALIZER_VERSION,
                native_rate_json={"broken": "secret-raw-value"},
            )
        )
        session.commit()

    client = TestClient(create_app())
    for url in (
        "/api/physical/flows?quantity_basis=native",
        "/api/physical/flows",
    ):
        response = client.get(url)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "native_rate_invalid"
        assert "secret-raw-value" not in response.text
        assert "invalid_native_rate_payload" not in response.text


def test_row_filter_runs_before_native_projection(tmp_path, monkeypatch) -> None:
    engine = _database(monkeypatch, tmp_path, "filter-before-native")
    with Session(engine) as session:
        session.add(
            _flow_observation(
                observation_id="native-partial",
                flow_mcm_d=1.0,
                normalizer_version=NORMALIZER_VERSION,
                native_rate_json={"broken": "secret-raw-value"},
            )
        )
        session.commit()

    seen: list[dict] = []

    def _drop_rows(request, rows, **kwargs):
        seen.extend(rows)
        return []

    monkeypatch.setattr(physical_module, "filter_rows", _drop_rows)

    rows, warnings = physical_module._load_flow_observations(
        request=object(),
        quantity_basis="native",
        limit=200,
        point_id=None,
    )

    assert rows == []
    assert warnings == []
    assert len(seen) == 1
    assert seen[0]["source_system"] == "ENTSOG"
    assert seen[0]["record"].observation_id == "native-partial"

    with pytest.raises(HTTPException) as excinfo:
        physical_module._load_flow_observations(
            quantity_basis="native",
            limit=200,
            point_id=None,
        )
    assert excinfo.value.status_code == 503
    assert excinfo.value.detail["code"] == "native_rate_invalid"


def test_native_query_casefolds_source_and_includes_partial_pair(
    tmp_path, monkeypatch
) -> None:
    engine = _database(monkeypatch, tmp_path, "native-casefold-partial")
    native = _native_payload("100.5", volume=True)
    with Session(engine) as session:
        # JSON null is SQL non-NULL; codec refusal is tested with DB checks intact.
        session.add_all(
            [
                _flow_observation(
                    observation_id="native-casefold",
                    point_id="casefold-point",
                    flow_mcm_d=float(native["volume_mcm_per_day"]),
                    normalizer_version=native["normalizer_version"],
                    native_rate_json=native,
                    source_system=" entsog ",
                ),
                _flow_observation(
                    observation_id="native-partial",
                    point_id="partial-point",
                    flow_mcm_d=1.0,
                    normalizer_version=NORMALIZER_VERSION,
                    native_rate_json=JSON.NULL,
                ),
            ]
        )
        session.commit()

    client = TestClient(create_app())
    casefold_response = client.get(
        "/api/physical/flows?quantity_basis=native&point_id=casefold-point"
    )
    assert casefold_response.status_code == 200
    casefold_rows = casefold_response.json()["data"]
    assert [row["observation_id"] for row in casefold_rows] == ["native-casefold"]
    assert casefold_rows[0]["source_system"] == "ENTSOG"

    partial_response = client.get(
        "/api/physical/flows?quantity_basis=native&point_id=partial-point"
    )
    assert partial_response.status_code == 503
    assert partial_response.json()["detail"]["code"] == "native_rate_invalid"


def test_native_overflow_is_refused_not_truncated(tmp_path, monkeypatch) -> None:
    engine = _database(monkeypatch, tmp_path, "native-overflow")
    native = _native_payload("100.5", volume=True)
    canonical_volume = float(native["volume_mcm_per_day"])
    with Session(engine) as session:
        session.add_all(
            [
                _flow_observation(
                    observation_id="native-overflow-1",
                    flow_mcm_d=canonical_volume,
                    normalizer_version=native["normalizer_version"],
                    native_rate_json=native,
                ),
                _flow_observation(
                    observation_id="native-overflow-2",
                    flow_mcm_d=canonical_volume,
                    normalizer_version=native["normalizer_version"],
                    native_rate_json=native,
                ),
            ]
        )
        session.commit()

    response = TestClient(create_app()).get(
        "/api/physical/flows?quantity_basis=native&limit=1"
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "native_query_overflow"


def test_no_database_is_an_explicit_empty_response(monkeypatch) -> None:
    _clear_database_env(monkeypatch)
    client = TestClient(create_app())

    for url in (
        "/api/physical/flows",
        "/api/physical/capacity",
        "/api/physical/flows?quantity_basis=native",
    ):
        response = client.get(url)
        assert response.status_code == 200
        payload = response.json()
        assert payload["data"] == []
        assert payload["meta"]["source_references"] == ["runtime-db-not-configured"]
        assert payload["meta"]["warnings"]


def test_limit_mode_and_point_validation(monkeypatch) -> None:
    _clear_database_env(monkeypatch)
    client = TestClient(create_app())

    assert client.get("/api/physical/flows?limit=0").status_code == 422
    assert client.get("/api/physical/flows?limit=2001").status_code == 422
    assert (
        client.get("/api/physical/flows?quantity_basis=native_volume").status_code
        == 422
    )
    assert (
        client.get(f"/api/physical/flows?point_id={'x' * 128}").status_code == 200
    )
    assert (
        client.get(f"/api/physical/flows?point_id={'x' * 129}").status_code == 422
    )


def test_anonymous_is_rejected_under_full_app_config(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "test-public-token")
    client = TestClient(create_app(Settings(api_profile="release")))

    for url in ("/api/physical/flows", "/api/physical/capacity"):
        response = client.get(url)
        assert response.status_code == 401
