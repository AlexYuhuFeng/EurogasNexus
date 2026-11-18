"""The public LNG terminal tariff register (CP-11): terms first, versioned, four eyes.

Operator documents are synthetic TerminalCost figures here: no operator document is fetched
or reproduced (their sites restrict reuse; see docs/legal/DATA_SOURCE_TERMS.md).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import lng_terminal_tariff_register as register
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    LngTerminalTariffRecord,
    NotificationOutboxRecord,
)
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.ingestion.lng_terminal_tariffs import TerminalCost
from eurogas_nexus.security import rate_limit as rate_limit_module

PUBLIC_TOKEN = "test-public-api-token"
ROOT = Path(__file__).resolve().parents[2]


def _zeebrugge(sha: str, fixed: float = 640_000.5) -> TerminalCost:
    return TerminalCost(
        terminal_id="zeebrugge:term",
        name="Zeebrugge",
        country="BE",
        hub="ZTP",
        regime="regulated_indexed",
        product="term",
        currency="EUR",
        fixed_per_cargo=fixed,
        fuel_retention_pct=1.3,
        effective_from="March 2027",
        period="March 2027",
        source_url="https://example.invalid/sim.xlsx",
        source_sha256=sha,
        excludes=("port fees",),
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'lngt.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", PUBLIC_TOKEN)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rate_limit_module._WINDOWS.clear()
    bearers = {}
    with Session(engine) as session:
        for name, role in (
            ("t-admin", "ADMIN"),
            ("t-ops", "OPERATOR"),
            ("t-ops2", "OPERATOR"),
            ("t-analyst", "ANALYST"),
        ):
            row = identity_repository.create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _key, bearers[name] = identity_repository.create_identity_api_key(
                session, row.principal_id
            )
            bearers[name + ":id"] = row.principal_id
        session.commit()
    return engine, bearers


def _h(bearer):
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def test_no_document_is_read_without_the_firms_permission(store):
    engine, _bearers = store
    with Session(engine) as session:
        state = register.operator_state(session, "fluxys_lng")
        assert state["permission_state"] == "needs_firm_terms"
        assert "written consent" in state["finding"] and state["legal_url"].startswith("https://")
        with pytest.raises(register.TariffRegisterError) as refused:
            register.record_document(
                session, [_zeebrugge("a" * 64)], operator="fluxys_lng", document_title="sim"
            )
        assert refused.value.code == "needs_firm_terms"
        assert session.query(LngTerminalTariffRecord).count() == 0


def test_versioned_candidates_one_attention_item_and_four_eyes(store):
    engine, bearers = store
    with Session(engine) as session:
        register.record_operator_permission(
            session,
            "fluxys_lng",
            permitted=True,
            reference="Fluxys letter 2026-11-01",
            actor=bearers["t-admin:id"],
        )
        first = register.record_document(
            session,
            [_zeebrugge("a" * 64)],
            operator="fluxys_lng",
            document_title="Fluxys LNG price simulator",
        )
        again = register.record_document(
            session,
            [_zeebrugge("a" * 64)],
            operator="fluxys_lng",
            document_title="Fluxys LNG price simulator",
        )
        changed = register.record_document(
            session,
            [_zeebrugge("b" * 64, 650_000.0)],
            operator="fluxys_lng",
            document_title="next month",
        )
        session.commit()
        # 1 per-cargo figure + 1 gas-in-kind figure per document; never overwritten.
        assert first == {"added": 2, "unchanged": False, "attention": True}
        assert again == {"added": 0, "unchanged": True, "attention": False}
        assert changed["added"] == 2
        rows = session.query(LngTerminalTariffRecord).all()
        assert len(rows) == 4 and {row.review_status for row in rows} == {"CANDIDATE"}
        titles = [n.title for n in session.query(NotificationOutboxRecord).all()]
        assert titles == [
            "Fluxys LNG tariff published: review 2 values",
            "Fluxys LNG tariff changed: review 2 values",
        ]
        recorded = next(
            row for row in rows if row.source_sha256 == "a" * 64 and row.charge_basis == "per_cargo"
        )
        tariff_id = recorded.tariff_id
        assert (
            recorded.recorded_by == "tariff-refresh"
            and recorded.valid_from.isoformat() == "2027-03-01"
        )

    client = TestClient(create_app(Settings(api_profile="release")))
    # An analyst cannot review; an operator can; the recorder never can.
    assert (
        client.post(
            f"/api/lng/terminal-tariffs/{tariff_id}/review", headers=_h(bearers["t-analyst"])
        ).status_code
        == 403
    )
    ok = client.post(f"/api/lng/terminal-tariffs/{tariff_id}/review", headers=_h(bearers["t-ops"]))
    assert ok.status_code == 200 and ok.json()["data"]["review_status"] == "REVIEWED"
    with Session(engine) as session:
        own = register.record_document(  # noqa: F841 - same digest: unchanged
            session,
            [_zeebrugge("a" * 64)],
            operator="fluxys_lng",
            document_title="x",
            actor=bearers["t-ops2:id"],
        )
        row = LngTerminalTariffRecord(
            **{
                **{
                    c.name: getattr(recorded, c.name)
                    for c in LngTerminalTariffRecord.__table__.columns
                },
                "tariff_id": "desk-1",
                "recorded_by": bearers["t-ops2:id"],
                "source_sha256": "c" * 64,
            }
        )
        session.add(row)
        session.commit()
    four_eyes = client.post(
        "/api/lng/terminal-tariffs/desk-1/review", headers=_h(bearers["t-ops2"])
    )
    assert four_eyes.status_code == 403 and four_eyes.json()["detail"]["code"] == "four_eyes"

    view = client.get("/api/lng/terminal-tariffs", headers=_h(bearers["t-analyst"])).json()["data"]
    assert view["counts"]["reviewed"] == 1 and view["counts"]["terminals"] == 1
    fluxys = next(op for op in view["operators"] if op["operator"] == "fluxys_lng")
    assert fluxys["permission_state"] == "permitted" and fluxys["reference"]
    with Session(engine) as session:
        actions = {e.action for e in session.query(AuditEventRecord).all()}
        assert {"lng_tariff.operator_terms", "lng_tariff.document", "lng_tariff.review"} <= actions


def test_price_reads_reviewed_then_candidate_then_reason(store):
    engine, bearers = store
    client = TestClient(create_app(Settings(api_profile="release")))
    params = {"terminal_id": "zeebrugge:term", "arrival_month": "2027-04", "cargo_mwh": 900000}
    gated = client.get(
        "/api/lng/terminal-tariffs/price", params=params, headers=_h(bearers["t-analyst"])
    ).json()["data"]
    assert gated["basis"] == "missing" and gated["reason"] == "needs_firm_terms"
    with Session(engine) as session:
        register.record_operator_permission(
            session, "fluxys_lng", permitted=True, reference="letter", actor="admin"
        )
        register.record_document(
            session, [_zeebrugge("a" * 64)], operator="fluxys_lng", document_title="sim"
        )
        session.commit()
    indicative = client.get(
        "/api/lng/terminal-tariffs/price",
        params={**params, "product": "term"},
        headers=_h(bearers["t-analyst"]),
    ).json()["data"]
    # Candidate only: 640,000.50 EUR per cargo, indicative; gas in kind is reported, not added.
    assert indicative["basis"] == "candidate_public" and indicative["indicative"] is True
    assert indicative["charge"] == pytest.approx(640_000.5)
    assert indicative["excludes"] == ["port fees"]


def test_only_an_administrator_records_an_operators_permission(store):
    _engine, bearers = store
    client = TestClient(create_app(Settings(api_profile="release")))
    body = {"permitted": True, "reference": "Elengy e-mail 2026-11-02"}
    assert (
        client.put(
            "/api/lng/terminal-tariffs/operators/elengy", json=body, headers=_h(bearers["t-ops"])
        ).status_code
        == 403
    )
    missing = client.put(
        "/api/lng/terminal-tariffs/operators/elengy",
        json={"permitted": True, "reference": " "},
        headers=_h(bearers["t-admin"]),
    )
    assert missing.status_code == 422
    ok = client.put(
        "/api/lng/terminal-tariffs/operators/elengy", json=body, headers=_h(bearers["t-admin"])
    )
    assert ok.status_code == 200 and ok.json()["data"]["permission_state"] == "permitted"
    assert (
        client.put(
            "/api/lng/terminal-tariffs/operators/nowhere", json=body, headers=_h(bearers["t-admin"])
        ).status_code
        == 404
    )


def test_the_refresh_reads_nothing_for_an_operator_without_permission(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "tests.refresh_lng_terminal_tariffs", ROOT / "scripts/ops/refresh_lng_terminal_tariffs.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    fetched = []
    monkeypatch.setattr(script, "_get", lambda url: fetched.append(url) or b"")
    costs, problems = script.collect("https://example.invalid/det", set())
    assert costs == {} and problems == [] and fetched == []
