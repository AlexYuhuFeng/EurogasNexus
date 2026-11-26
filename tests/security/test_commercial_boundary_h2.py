"""Decision cases and analysis snapshots sit inside the commercial-data boundary (H2).

* Every GET route of the application, called by a platform administrator who holds no
  commercial role, is refused unless its path is platform, context or public-reference state
  (``PLATFORM_PATH_PREFIXES``). The boundary is default-commercial, so a new family is inside
  it the day it is added.
* One desk does not read another desk's decision case or analysis snapshot; the author does.
* The signed ERP hand-off needs the review floor and a party to the decision.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AnalysisSnapshotRecord,
    DecisionCaseRecord,
    TradingBookRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.security.permissions import serves_commercial_data

PUBLIC = "test-public-api-token"
NOW = datetime(2026, 11, 20, 9, tzinfo=UTC)


def _db(tmp_path, monkeypatch) -> str:
    url = f"sqlite+pysqlite:///{(tmp_path / 'h2.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", raising=False)
    return url


def _who(url, name, roles, scopes) -> dict[str, str]:
    with Session(create_engine(url, future=True)) as session:
        row = create_identity_principal(
            session, name=name, display_name=name, role=roles[0], data_scopes=scopes
        )
        row.roles = roles
        _key, bearer = create_identity_api_key(
            session, row.principal_id, display_name="t", scopes=["*"]
        )
        session.commit()
    return {"X-Eurogas-Api-Key": PUBLIC, "X-Eurogas-Identity": bearer}


def test_platform_administration_reads_no_commercial_get_route(tmp_path, monkeypatch):
    url = _db(tmp_path, monkeypatch)
    admin = _who(url, "platform-admin", ["ADMIN"], ["*"])
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    answered = []
    commercial = 0
    for path, operations in sorted(app.openapi()["paths"].items()):
        if "get" not in operations or "stream" in path:
            continue
        concrete = re.sub(r"{[^}]+}", "x", path)
        if not serves_commercial_data(concrete):
            continue
        commercial += 1
        response = client.get(concrete, headers=admin)
        if response.status_code != 403:
            answered.append(f"{path}: {response.status_code}")
    assert commercial > 100
    assert answered == []


def test_new_families_are_commercial_by_default():
    for path in (
        "/api/analysis-snapshots",
        "/api/analysis-snapshots/s1",
        "/api/data-products",
        "/api/decision-cases/c1/handoff",
        "/api/lng/cargoes/c1/plan",
        "/api/capacity/bookings",
        "/api/glossary/nbp/context",
        "/api/some-family-added-tomorrow",
    ):
        assert serves_commercial_data(path), path
    for path in ("/api/health", "/api/me", "/api/access/users", "/api/glossary/nbp"):
        assert not serves_commercial_data(path), path


def _seed_two_desks(url) -> None:
    with Session(create_engine(url, future=True)) as session:
        for book, entity in (("uk-nbp", "EGN-UK"), ("nl-ttf", "EGN-NL")):
            session.add(
                TradingBookRecord(
                    book_id=book, name=book, legal_entity=entity, region="europe",
                    business="gas", base_currency="EUR", active=True, updated_by="t",
                    updated_at_utc=NOW,
                )
            )
        for case_id, book, author, snapshot in (
            ("case-uk", "uk-nbp", "uk-trader", "snap-uk"),
            ("case-nl", "nl-ttf", "nl-trader", "snap-nl"),
        ):
            session.add(
                DecisionCaseRecord(
                    case_id=case_id, objective=f"cover the {book} short", status="DECIDED",
                    created_by=author, created_at_utc=NOW, updated_at_utc=NOW,
                    portfolio_ref=book, snapshot_id=snapshot,
                )
            )
            session.add(
                AnalysisSnapshotRecord(
                    snapshot_id=snapshot, schema_version="v1", as_of_utc=NOW,
                    gas_day="2026-11-20", gas_day_calendar="EU", time_basis="as_of",
                    created_at_utc=NOW, created_by=author, content_hash="0" * 64,
                    research_only=True,
                )
            )
        session.commit()


def test_one_desk_does_not_read_another_desks_cases_or_snapshots(tmp_path, monkeypatch):
    url = _db(tmp_path, monkeypatch)
    _seed_two_desks(url)
    nl = _who(url, "nl-trader", ["ANALYST"], ["BOOKS:ENTITY:EGN-NL"])
    head = _who(url, "head-office", ["REVIEWER"], ["BOOKS:*"])
    client = TestClient(create_app())

    listed = client.get("/api/decision-cases", headers=nl).json()["data"]
    assert [case["case_id"] for case in listed] == ["case-nl"]
    assert client.get("/api/decision-cases/case-uk", headers=nl).status_code == 404
    assert client.get("/api/decision-cases/case-nl", headers=nl).status_code == 200
    snapshots = client.get("/api/analysis-snapshots", headers=nl).json()["data"]
    assert {row["snapshot_id"] for row in snapshots} == {"snap-nl"}
    assert client.get("/api/analysis-snapshots/snap-uk", headers=nl).status_code == 404

    every = client.get("/api/decision-cases", headers=head).json()["data"]
    assert {case["case_id"] for case in every} == {"case-uk", "case-nl"}


def test_the_signed_handoff_needs_review_and_a_party_to_the_decision(tmp_path, monkeypatch):
    url = _db(tmp_path, monkeypatch)
    _seed_two_desks(url)
    monkeypatch.setenv("EUROGAS_NEXUS_HANDOFF_SIGNING_KEY", "k" * 40)
    viewer = _who(url, "uk-viewer", ["VIEWER"], ["BOOKS:*"])
    bystander = _who(url, "uk-risk", ["REVIEWER"], ["BOOKS:*"])
    author = _who(url, "uk-trader", ["ANALYST"], ["BOOKS:ENTITY:EGN-UK"])
    client = TestClient(create_app())
    path = "/api/decision-cases/case-uk/handoff"
    assert client.get(path, headers=viewer).status_code == 403
    refused = client.get(path, headers=bystander)
    assert refused.status_code == 403
    assert "handoff_not_a_party" in refused.text
    assert client.get(path, headers=author).status_code == 200
