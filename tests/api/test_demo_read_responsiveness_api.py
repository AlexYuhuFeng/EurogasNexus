"""Server-side fixes for desk reads that timed out or came back empty on the demo (2026-11-17).

- Storage and LNG observation lists are bounded to a stated window, counted back from the
  newest observation in the store (not the clock).
- Large GET reads under /api are gzip-compressed; reads carrying session secrets are not.
- /api/runtime/db answers from the API's pool instead of opening three engines a call.
- Capacity in volume mode answers "nothing in volume" without loading every energy row.
- The demo catch-up progress is shown to source administrators only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public import sources as sources_module
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CapacityObservationRecord,
    LngObservationRecord,
    StorageObservationRecord,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

NEWEST = datetime(2026, 5, 29, tzinfo=UTC)


def _database(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'reads.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    for name in ("DATABASE_URL", "EUROGAS_NEXUS_DB_DSN", "EUROGAS_NEXUS_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return engine


def _storage(day: datetime, index: int) -> StorageObservationRecord:
    return StorageObservationRecord(
        observation_id=f"agsi-{index}", source_dataset="AGSI", facility_id="eu",
        facility_name="EU", country="EU", inventory_twh=600.0 + index,
        working_capacity_twh=1100.0, fill_pct=55.0, injection_twh_d=1.0, withdrawal_twh_d=1.0,
        period_start_utc=day, period_end_utc=day + timedelta(days=1),
        observed_at_utc=day + timedelta(hours=12), source_system="GIE",
        source_reference="test", freshness="live", research_only=True,
    )


def _lng(day: datetime, index: int) -> LngObservationRecord:
    return LngObservationRecord(
        observation_id=f"alsi-{index}", source_dataset="ALSI", terminal_id="eu",
        terminal_name="EU LNG", country="EU", inventory_twh=40.0, send_out_twh_d=3.0,
        dtmi_twh=60.0, period_start_utc=day, period_end_utc=day + timedelta(days=1),
        observed_at_utc=day + timedelta(hours=12), source_system="GIE",
        source_reference="test", freshness="live", research_only=True,
    )


def _seed_history(engine, days: int = 120) -> None:
    with Session(engine) as session:
        for index in range(days):
            day = NEWEST - timedelta(days=index)
            session.add(_storage(day, index))
            session.add(_lng(day, index))
        session.commit()


def test_observation_lists_return_a_stated_window_back_from_the_newest_row(
    tmp_path, monkeypatch
) -> None:
    _seed_history(_database(tmp_path, monkeypatch))
    client = TestClient(create_app())
    for path in ("/api/storage/observations", "/api/lng/observations"):
        payload = client.get(path).json()
        # The store's newest row is months before "today": the window follows the store.
        assert len(payload["data"]) == 45, path
        window = payload["meta"]["window"]
        assert window["days"] == 45
        assert window["newest_period_start_utc"].startswith("2026-05-29")
        assert window["period_start_from_utc"].startswith("2026-04-15")
        assert min(row["period_start_utc"] for row in payload["data"]).startswith("2026-04-15")

        longer = client.get(f"{path}?days=400").json()
        assert len(longer["data"]) == 120, path
        assert client.get(f"{path}?days=0").status_code == 422
        assert client.get(f"{path}?days=801").status_code == 422


def test_an_empty_store_states_no_window_and_no_rows(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    payload = TestClient(create_app()).get("/api/storage/observations").json()
    assert payload["data"] == []
    assert payload["meta"]["window"]["period_start_from_utc"] is None


def test_sites_and_terminals_stay_unbounded(tmp_path, monkeypatch) -> None:
    engine = _database(tmp_path, monkeypatch)
    with Session(engine) as session:
        session.add(_storage(NEWEST - timedelta(days=300), 1))
        session.commit()
    sites = TestClient(create_app()).get("/api/storage/sites").json()["data"]
    assert [site["site_id"] for site in sites] == ["eu"]


def test_large_reads_are_compressed_and_secret_bearing_reads_are_not(
    tmp_path, monkeypatch
) -> None:
    _seed_history(_database(tmp_path, monkeypatch))
    client = TestClient(create_app())
    read = client.get("/api/storage/observations", headers={"Accept-Encoding": "gzip"})
    assert read.status_code == 200
    assert read.headers.get("content-encoding") == "gzip"
    assert len(read.json()["data"]) == 45  # the client decodes it transparently

    plain = client.get("/api/storage/observations", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers

    me = client.get("/api/me", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in me.headers


def test_runtime_db_status_answers_from_the_pool(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    from eurogas_nexus.db import health

    def no_new_engines(*_args, **_kwargs):  # the old path opened engines per call
        raise AssertionError("runtime/db must not open its own engine")

    monkeypatch.setattr(health, "check_db_connectivity", no_new_engines)
    payload = TestClient(create_app()).get("/api/runtime/db").json()["data"]
    assert payload["connectivity"] == {"ok": True, "error": None}
    # create_all() made every model table; only the migration bookkeeping is absent.
    assert payload["missing_tables"] == ["alembic_version"]
    assert payload["alembic_revision"] is None


def test_runtime_db_status_reports_an_unreachable_store_without_its_url(monkeypatch) -> None:
    monkeypatch.setenv(
        "RUNTIME_STORE_DATABASE_URL", "postgresql+psycopg://user:secret@127.0.0.1:1/none"
    )
    payload = TestClient(create_app()).get("/api/runtime/db").json()["data"]
    assert payload["connectivity"]["ok"] is False
    assert "secret" not in json.dumps(payload)


def test_capacity_volume_mode_with_only_energy_rows_is_empty_and_says_why(
    tmp_path, monkeypatch
) -> None:
    engine = _database(tmp_path, monkeypatch)
    with Session(engine) as session:
        session.add(
            CapacityObservationRecord(
                observation_id="cap-energy", point_id="P", point_name="P", direction="entry",
                capacity_type="firm_technical", capacity_mcm_d=None, original_value=None,
                original_unit=None, period_start_utc=NEWEST, period_end_utc=NEWEST
                + timedelta(days=1), observed_at_utc=NEWEST, source_system="ENTSOG",
                source_reference="entsog", source_record_id="cap-energy", freshness="live",
                research_only=True, normalizer_version="entsog-native-units-v1",
                native_rate_json={"kind": "energy"},
            )
        )
        session.commit()
    payload = TestClient(create_app()).get("/api/physical/capacity").json()
    assert payload["data"] == []
    assert any("energy" in warning.lower() for warning in payload["meta"]["warnings"])


def _principal(role: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=f"p-{role}", name=role.lower(), principal_type="USER", role=role,
        status="ACTIVE", data_scopes=("*",), roles=(role,),
    )


def test_catch_up_progress_is_for_source_administrators_on_the_demo_only(
    tmp_path, monkeypatch
) -> None:
    status = tmp_path / "catch-up.json"
    status.write_text(json.dumps({"running": True, "done": 3, "total": 11, "step": "GIE"}))
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_CATCH_UP_STATUS", str(status))
    monkeypatch.setenv("EUROGAS_NEXUS_API_PROFILE", "demo")

    def progress(role: str):
        request = SimpleNamespace(state=SimpleNamespace(identity=_principal(role)))
        return sources_module._demo_catch_up_progress(request)

    assert progress("ADMIN")["done"] == 3
    assert progress("OPERATOR")["total"] == 11
    for role in ("ANALYST", "REVIEWER", "VIEWER"):
        assert progress(role) is None, role

    monkeypatch.setenv("EUROGAS_NEXUS_API_PROFILE", "customer")
    assert progress("ADMIN") is None
