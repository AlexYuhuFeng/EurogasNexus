"""Recording a gas-day step's status by hand: refused or recorded, never a server error."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.gas_day_checklist import STATUSES, STEPS
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.market.gas_day import gas_day_label
from eurogas_nexus.security.permissions import ROLE_REQUIREMENTS, Permission

PUBLIC_TOKEN = "test-public-api-token"


def _client(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'desk.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    who = {}
    with Session(engine) as session:
        for name, role in (
            ("analyst", "ANALYST"),
            ("viewer", "VIEWER"),
            ("scheduler", "SCHEDULER"),
            ("reviewer", "REVIEWER"),
        ):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            who[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return TestClient(create_app()), who


def _body(**overrides):
    today = gas_day_label(datetime.now(UTC))
    body = {
        "gas_day": today,
        "line_ref": "contract:nobody",
        "step": STEPS[0],
        "status": STATUSES[0],
    }
    body.update(overrides)
    return body


def test_every_permission_category_names_its_minimum_role():
    assert set(ROLE_REQUIREMENTS) == set(Permission)


def test_status_write_refuses_or_records_but_never_fails(tmp_path, monkeypatch):
    client, who = _client(tmp_path, monkeypatch)

    viewer = client.post("/api/desk/gas-day/status", headers=who["viewer"], json=_body())
    assert viewer.status_code == 403

    unknown = client.post(
        "/api/desk/gas-day/status", headers=who["analyst"], json=_body(step="teleport")
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "unknown_step"

    outside = client.post("/api/desk/gas-day/status", headers=who["analyst"], json=_body())
    assert outside.status_code == 404
    assert outside.json()["detail"]["code"] == "line_not_in_scope"


def test_a_scheduler_records_status_and_nothing_else(tmp_path, monkeypatch):
    """Persona review QA-T-06: the person who schedules could not record a nomination."""

    client, who = _client(tmp_path, monkeypatch)
    # The scheduler passes the permission check and reaches the scope check.
    recorded = client.post("/api/desk/gas-day/status", headers=who["scheduler"], json=_body())
    assert recorded.status_code == 404, recorded.text
    assert recorded.json()["detail"]["code"] == "line_not_in_scope"
    # A reviewer outranks a scheduler but does not schedule.
    reviewer = client.post("/api/desk/gas-day/status", headers=who["reviewer"], json=_body())
    assert reviewer.status_code == 403
    assert reviewer.json()["detail"]["permission"] == "gas_day.record"
    # Nothing beyond the status: no book edits, no strategies, no review decisions.
    for path, body in (
        ("/api/portfolio/trader-mandates/M1", {"trader": "x", "display_name": "x"}),
        ("/api/opportunities/settings", {"persistence": 2}),
    ):
        assert client.put(path, headers=who["scheduler"], json=body).status_code == 403, path
