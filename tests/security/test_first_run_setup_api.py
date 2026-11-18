"""First-run setup API: ADMIN only, state recorded and audited, demo and UAT mark it done."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import first_run_setup
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord, LngTerminalTermsRecord
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.security import rate_limit as rate_limit_module

PUBLIC_TOKEN = "test-public-api-token"
ROOT = Path(__file__).resolve().parents[2]


def _store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'setup.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", PUBLIC_TOKEN)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rate_limit_module._WINDOWS.clear()
    bearers = {}
    with Session(engine) as session:
        for name, role in (("setup-admin", "ADMIN"), ("setup-analyst", "ANALYST")):
            row = identity_repository.create_identity_principal(
                session, name=name, display_name=name, role=role
            )
            if name == "setup-analyst":
                row.job_functions = ["PLATFORM_ADMINISTRATOR"]  # composition, never a grant
            _key, bearers[role] = identity_repository.create_identity_api_key(
                session, row.principal_id
            )
        session.commit()
    return engine, bearers


def _headers(bearer):
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def test_admin_reads_and_records_the_flow_others_cannot(tmp_path, monkeypatch):
    engine, bearers = _store(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    assert client.get("/api/setup", headers=_headers(bearers["ANALYST"])).status_code == 403
    assert client.put(
        "/api/setup", headers=_headers(bearers["ANALYST"]), json={"status": "dismissed"}
    ).status_code == 403

    first = client.get("/api/setup", headers=_headers(bearers["ADMIN"])).json()["data"]
    assert first["state"]["status"] == "not_started" and first["show_on_sign_in"] is True
    assert [step["step"] for step in first["catalogue"]["steps"]][0] == "welcome"
    assert first["terminal_tariffs"]["held"] == 0

    moved = client.put(
        "/api/setup", headers=_headers(bearers["ADMIN"]),
        json={"status": "in_progress", "step": "prices"},
    ).json()["data"]
    assert moved["state"]["current_step"] == "prices" and moved["show_on_sign_in"] is True
    bad = client.put(
        "/api/setup", headers=_headers(bearers["ADMIN"]),
        json={"status": "in_progress", "step": "nowhere"},
    )
    assert bad.status_code == 422
    done = client.put(
        "/api/setup", headers=_headers(bearers["ADMIN"]), json={"status": "dismissed"}
    ).json()["data"]
    assert done["show_on_sign_in"] is False
    with Session(engine) as session:
        events = [e for e in session.query(AuditEventRecord).all() if e.action == "setup.state"]
        assert [e.outcome for e in events] == ["in_progress", "dismissed"]


def test_terminal_tariffs_held_and_their_source(tmp_path, monkeypatch):
    engine, bearers = _store(tmp_path, monkeypatch)
    from datetime import UTC, datetime

    from eurogas_nexus.db.models import LngTerminalTariffRecord

    with Session(engine) as session:
        now = datetime.now(UTC)
        # The firm's own terms (desk-entered, no source document) ...
        session.add(LngTerminalTermsRecord(
            terminal_id="gate", name="Gate", hub="TTF", regas_tariff_per_mwh=1.0,
            source_note="our contract", updated_by="desk", updated_at_utc=now,
        ))
        # ... and one public register figure for another terminal.
        session.add(LngTerminalTariffRecord(
            tariff_id="t1", terminal_id="zeebrugge:term", operator="fluxys_lng",
            terminal_name="Zeebrugge", hub="ZTP", regime="regulated_indexed",
            service="bundled_slot", product="term", charge_basis="per_cargo", amount=1.0,
            currency="EUR", unit="EUR/cargo", indexation="cpi_monthly", excludes=[],
            source_url="https://example.invalid/doc", source_sha256="a" * 64,
            retrieved_at_utc=now, document_title="doc", review_status="CANDIDATE",
            recorded_by="tariff-refresh", created_at_utc=now,
        ))
        session.commit()
    client = TestClient(create_app(Settings(api_profile="release")))
    facts = client.get("/api/setup", headers=_headers(bearers["ADMIN"])).json()["data"]
    tariffs = facts["terminal_tariffs"]
    assert tariffs["held"] == 2 and tariffs["from_operator"] == 1 and tariffs["desk_entered"] == 1
    assert tariffs["candidate"] == 1 and len(tariffs["operators_needing_terms"]) == 3


def test_demo_start_marks_the_flow_configured_and_keeps_an_admin_choice(tmp_path, monkeypatch):
    engine, _bearers = _store(tmp_path, monkeypatch)
    spec = importlib.util.spec_from_file_location(
        "tests.start_public_demo_setup", ROOT / "scripts/demo/start_public_demo.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    with Session(engine) as session:
        script.mark_setup_configured(session)
        session.commit()
        state = first_run_setup.setup_state(session)
        assert state["status"] == "completed" and state["configured_by"] == "demo_profile"
        first_run_setup.update_setup_state(
            session, status="in_progress", step="ai", actor="someone"
        )
        first_run_setup.update_setup_state(session, status="dismissed", step=None, actor="x")
        script.mark_setup_configured(session)
        assert first_run_setup.setup_state(session)["status"] == "dismissed"
