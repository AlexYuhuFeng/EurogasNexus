"""Assumption sets and firm marks over the API (CP-07): who may read, write and approve.

- a viewer reads but cannot write; an analyst (trader) writes drafts and marks;
- only the risk function (REVIEWER held itself) approves, never the author (four eyes);
- a platform administrator without a commercial role reads nothing here;
- every change is audited without the values;
- a firm mark is labelled "firm's mark" everywhere it is returned;
- a set owned by a book is hidden from a caller outside that book.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord, TradingBookRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _setup(tmp_path, monkeypatch, roles=None):
    url = f"sqlite+pysqlite:///{(tmp_path / 'assumptions.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    who = {}
    with Session(engine) as session:
        for book in ("uk-nbp", "nl-ttf"):
            session.add(
                TradingBookRecord(
                    book_id=book,
                    name=book,
                    legal_entity="EGN-" + book[:2].upper(),
                    region="europe",
                    business="gas",
                    base_currency="EUR",
                    active=True,
                    updated_by="t",
                    updated_at_utc=datetime.now(UTC),
                )
            )
        for name, role, scopes in roles or (
            ("viewer", "VIEWER", ["*"]),
            ("trader", "ANALYST", ["*"]),
            ("trader2", "ANALYST", ["*"]),
            ("risk", "REVIEWER", ["*"]),
            ("admin", "ADMIN", ["*"]),
            ("uktrader", "ANALYST", ["BOOKS:BOOK:UK-NBP"]),
        ):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=scopes
            )
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            who[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
            who[name + "_id"] = row.principal_id
        session.commit()
    client = TestClient(create_app(Settings(api_profile="release")))
    return client, engine, who


VALUES = {
    "effective_from": "2026-10-01",
    "values": [
        {"key": "financing.rate", "value": 3.0, "range_low": 2.0, "range_high": 4.0},
        {"key": "lng.charter_hire", "value": 174000, "currency": "USD"},
    ],
}


def test_roles_for_assumption_sets(tmp_path, monkeypatch) -> None:
    client, engine, who = _setup(tmp_path, monkeypatch)

    assert (
        client.post(
            "/api/assumption-sets", headers=who["viewer"], json={"name": "Base"}
        ).status_code
        == 403
    )
    made = client.post(
        "/api/assumption-sets", headers=who["trader"], json={"name": "Base", "description": "x"}
    )
    assert made.status_code == 200, made.text
    set_id = made.json()["data"]["set_id"]
    assert (
        client.post(
            "/api/assumption-sets", headers=who["trader"], json={"name": "Base"}
        ).status_code
        == 409
    )

    bad = client.post(
        f"/api/assumption-sets/{set_id}/versions",
        headers=who["trader"],
        json={"effective_from": "2026-10-01", "values": [{"key": "lng.charter_hire", "value": 1}]},
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "currency_required"
    draft = client.post(
        f"/api/assumption-sets/{set_id}/versions", headers=who["trader"], json=VALUES
    )
    assert draft.status_code == 200, draft.text
    version = draft.json()["data"]["versions"][0]
    assert version["review_state"] == "draft" and version["created_by"] == who["trader_id"]
    hire = next(v for v in version["values"] if v["key"] == "lng.charter_hire")
    assert (hire["value"], hire["unit"], hire["currency"]) == ("174000", "USD/day", "USD")

    # Approval: not an analyst, not the author, only the risk function.
    approve = f"/api/assumption-sets/{set_id}/versions/1/approve"
    assert client.post(approve, headers=who["trader2"]).status_code == 403
    assert client.post(approve, headers=who["viewer"]).status_code == 403
    approved = client.post(approve, headers=who["risk"])
    assert approved.status_code == 200, approved.text
    data = approved.json()["data"]
    assert data["approved_version"] == 1 and data["versions"][0]["approved_by"] == who["risk_id"]
    assert client.post(approve, headers=who["risk"]).json()["detail"]["code"] == "not_a_draft"

    # Reads: a viewer reads; a platform administrator without a commercial role does not.
    listed = client.get("/api/assumption-sets", headers=who["viewer"])
    assert listed.status_code == 200
    assert any(item["key"] == "capacity.load_factor" for item in listed.json()["data"]["catalogue"])
    assert client.get(f"/api/assumption-sets/{set_id}", headers=who["viewer"]).status_code == 200
    assert client.get("/api/assumption-sets", headers=who["admin"]).status_code == 403
    assert client.get(f"/api/assumption-sets/{set_id}", headers=who["admin"]).status_code == 403

    # The audit trail names what changed, never the values.
    with Session(engine) as session:
        events = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action.like("assumption_set%"))
            .all()
        )
    actions = sorted(event.action for event in events)
    assert actions == [
        "assumption_set.create",
        "assumption_set.version.approve",
        "assumption_set.version.create",
    ]
    for event in events:
        assert "174000" not in (event.detail or "") and "3.0" not in (event.detail or "")
    created = next(e for e in events if e.action == "assumption_set.version.create")
    assert "lng.charter_hire" in created.detail and "values_sha256" in created.detail


def test_four_eyes_holds_even_for_a_person_with_both_roles(tmp_path, monkeypatch) -> None:
    from eurogas_nexus.db.repositories.commercial_assumptions import (
        approve_assumption_version,
        create_assumption_set,
        create_assumption_version,
    )
    from eurogas_nexus.domain.valuation.assumptions import (
        AssumptionError,
        validate_assumption_value,
    )

    _client, engine, _who = _setup(tmp_path, monkeypatch, roles=())
    with Session(engine) as session:
        made = create_assumption_set(session, name="S", book_id=None, description="", actor="kim")
        create_assumption_version(
            session,
            set_id=made["set_id"],
            values=[validate_assumption_value("financing.rate", 3)],
            effective_from=date(2026, 10, 1),
            effective_to=None,
            note="",
            actor="kim",
        )
        try:
            approve_assumption_version(session, set_id=made["set_id"], version=1, actor="KIM")
        except AssumptionError as exc:
            assert exc.code == "four_eyes_required"
        else:  # pragma: no cover - the rule failed
            raise AssertionError("an author approved their own values")


def test_book_owned_sets_follow_book_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "true")
    client, _engine, who = _setup(tmp_path, monkeypatch)
    made = client.post(
        "/api/assumption-sets", headers=who["trader"], json={"name": "NL", "book_id": "nl-ttf"}
    )
    assert made.status_code == 200, made.text
    set_id = made.json()["data"]["set_id"]
    assert client.get(f"/api/assumption-sets/{set_id}", headers=who["uktrader"]).status_code == 404
    names = [
        s["name"]
        for s in client.get("/api/assumption-sets", headers=who["uktrader"]).json()["data"]["sets"]
    ]
    assert "NL" not in names
    refused = client.post(
        "/api/assumption-sets", headers=who["uktrader"], json={"name": "X", "book_id": "nl-ttf"}
    )
    assert refused.status_code == 404
    assert client.get(f"/api/assumption-sets/{set_id}", headers=who["trader"]).status_code == 200


def test_firm_marks_are_labelled_and_audited_without_values(tmp_path, monkeypatch) -> None:
    client, engine, who = _setup(tmp_path, monkeypatch)
    grid = {
        "marks": [
            {"hub": "TTF", "period": "2027-01", "value": 31.2, "unit": "EUR/MWh"},
            {"hub": "NBP", "period": "2027-01", "value": 78.0, "unit": "p/th"},
        ]
    }
    assert client.put("/api/market/firm-marks", headers=who["viewer"], json=grid).status_code == 403
    assert client.put("/api/market/firm-marks", headers=who["risk"], json=grid).status_code == 403
    stored = client.put("/api/market/firm-marks", headers=who["trader"], json=grid)
    assert stored.status_code == 200, stored.text
    assert {row["input_class"] for row in stored.json()["data"]["marks"]} == {"firm_mark"}

    again = {"marks": [{"hub": "TTF", "period": "2027-01", "value": 31.5, "unit": "EUR/MWh"}]}
    assert (
        client.put("/api/market/firm-marks", headers=who["trader2"], json=again).status_code == 200
    )
    read = client.get("/api/market/firm-marks", headers=who["viewer"]).json()["data"]
    rows = {(row["hub"], row["period"]): row for row in read["marks"]}
    assert rows[("TTF", "2027-01")]["value"] == "31.5"
    assert rows[("NBP", "2027-01")]["unit"] == "GBp/th"
    assert all(row["class_label"] == "firm's mark" for row in read["marks"])
    assert "not prices from the market" in read["statement"]
    assert client.get("/api/market/firm-marks", headers=who["admin"]).status_code == 403

    bad = {"marks": [{"hub": "TTF", "period": "Jan-27", "value": 31.5, "unit": "EUR/MWh"}]}
    refused = client.put("/api/market/firm-marks", headers=who["trader"], json=bad)
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "period_invalid"

    with Session(engine) as session:
        events = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "market.firm_marks.update")
            .all()
        )
    assert len(events) == 2
    for event in events:
        assert (
            "31.2" not in event.detail and "31.5" not in event.detail and "78" not in event.detail
        )
        assert "TTF:2027-01" in event.detail
