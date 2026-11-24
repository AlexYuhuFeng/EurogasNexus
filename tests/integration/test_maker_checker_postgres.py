"""P-17 on PostgreSQL: a proposal, its approval under a row lock, and the figure's provenance.

Runs against a database migrated to head (``0081_change_requests``), set in
``EUROGAS_NEXUS_TEST_POSTGRES_URL`` or ``RUNTIME_STORE_DATABASE_URL``. The approval reads the
proposal ``FOR UPDATE``, so a second approval of the same change waits and then finds it
decided; the approved row and its audit rows commit together.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.models import AuditEventRecord, ChangeRequestRecord, CreditLineRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Needs a PostgreSQL database migrated to head.",
)
PUBLIC_TOKEN = "test-public-api-token"


def test_a_credit_line_is_proposed_approved_and_keeps_its_provenance(monkeypatch):
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", _POSTGRES_URL)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(_POSTGRES_URL, future=True)
    suffix = uuid4().hex[:8]
    headers: dict[str, dict[str, str]] = {}
    ids: dict[str, str] = {}
    with Session(engine) as session:
        for name in ("maker", "checker"):
            row = create_identity_principal(
                session,
                name=f"p17-{name}-{suffix}",
                display_name=f"P17 {name}",
                role="REVIEWER",
                data_scopes=["*"],
            )
            ids[name] = row.principal_id
            _key, bearer = create_identity_api_key(session, ids[name], scopes=["*"])
            headers[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        session.commit()
    client = TestClient(create_app())
    key = f"P17-{suffix}"
    proposed = client.put(
        f"/api/portfolio/credit-lines/{key}",
        json={
            "name": "P17 Counterparty",
            "limit_amount": 750_000,
            "currency": "EUR",
            "change_reason": "postgres acceptance",
        },
        headers=headers["maker"],
    )
    assert proposed.status_code == 202, proposed.text
    change_id = proposed.json()["data"]["change"]["change_id"]
    with Session(engine) as session:
        assert session.get(CreditLineRecord, key) is None
        assert session.get(ChangeRequestRecord, change_id).state == "pending"

    approve = f"/api/portfolio/change-requests/{change_id}/approve"
    assert client.post(approve, headers=headers["maker"]).status_code == 403
    approved = client.post(approve, headers=headers["checker"])
    assert approved.status_code == 200, approved.text
    assert client.post(approve, headers=headers["checker"]).status_code == 409

    line = client.get(f"/api/portfolio/credit-lines/{key}", headers=headers["checker"]).json()
    provenance = line["data"]["provenance"]
    assert provenance["second_approval"] is True
    assert provenance["set_by"] == ids["maker"] and provenance["approved_by"] == ids["checker"]
    with Session(engine) as session:
        stored = session.get(CreditLineRecord, key)
        assert stored.limit_amount == 750_000 and stored.change_id == change_id
        actions = {
            event.action
            for event in session.query(AuditEventRecord).filter(
                AuditEventRecord.resource == f"credit_line:{key}"
            )
        }
        assert {
            "change_request.propose",
            "change_request.approve",
            "risk.credit_line.update",
        } <= actions
        # Leave the shared database as it was found.
        session.query(CreditLineRecord).filter_by(counterparty_id=key).delete()
        session.query(ChangeRequestRecord).filter_by(change_id=change_id).delete()
        session.commit()
