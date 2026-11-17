"""Release acceptance: a fresh installation reaches live ENTSOG data through the approval step.

Why this test exists. On the first live bring-up (2026-11-12) and again on the public demo
(2026-11-16) a fresh store with its keys configured ingested ECB and EIA but refused ENTSOG
and GIE with ``source_gate_blocked``: the fail-closed gate requires a certification record,
and nothing in the product produced one (the operator command was not even in the customer
image). The gate is deliberate governance and stays; this test holds the product path
through it: on a fresh database

1. without an approval the read is refused before any fetch, with the stable reason
   ``source_not_approved`` in the report and on the run row, and the source reads
   "Not approved yet" with the action "Admin -> Connectors";
2. an administrator's approval (who, why, terms accepted) runs the bounded live
   validation and is audited;
3. the same ingestion command then stores rows.

The provider is mocked at the transport (``fetch_entsog_dataset``); nothing leaves the
machine.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord, IngestionRunRecord
from eurogas_nexus.db.models.observation import AuditEventRecord
from eurogas_nexus.db.repositories.certification import latest_certification
from eurogas_nexus.domain.ingestion.certification import certification_gate
from eurogas_nexus.domain.ingestion.source_approval import (
    NOT_APPROVED_CODE,
    approval_state,
)
from eurogas_nexus.ingestion import entsog_transport
from scripts.ops import ingest_public_sources as script
from tests.fixtures.entsog_protocol import connectionpoint, observation, query_result


class _NoNetworkClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def close(self) -> None:
        return None

    def get(self, *args, **kwargs):  # pragma: no cover - the transport is mocked
        raise AssertionError("no network in a release test")


@pytest.fixture
def fresh_store(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'fresh.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(script, "resolve_database_url", lambda: "sqlite+pysqlite:///fresh")
    monkeypatch.setattr(script, "get_engine", lambda url: engine)
    monkeypatch.setattr(script, "create_session_factory", lambda active: factory)
    monkeypatch.setattr(script.httpx, "Client", _NoNetworkClient)
    return factory


def _mock_entsog(monkeypatch) -> list[str]:
    calls: list[str] = []

    def fetch(client, dataset, **kwargs):
        calls.append(dataset)
        if dataset == "connectionpoints":
            return query_result("connectionpoints", [connectionpoint()])
        return query_result(
            "operationaldatas", [observation(), observation("two", value=0)]
        )

    monkeypatch.setattr(script, "fetch_entsog_dataset", fetch)
    monkeypatch.setattr(entsog_transport, "fetch_entsog_dataset", fetch)
    return calls


def _ingest(monkeypatch, capsys) -> tuple[int, dict]:
    monkeypatch.setattr(
        sys,
        "argv",
        ["ingest_public_sources.py", "--source", "entsog", "--entsog-from", "2026-10-10",
         "--entsog-to", "2026-10-11", "--limit", "100", "--json"],
    )
    code = script.main()
    return code, json.loads(capsys.readouterr().out)


def _state(session) -> dict:
    record = latest_certification(session, "ENTSOG")
    gate = certification_gate(
        "ENTSOG", stage=(record or {}).get("stage", ""), checks=(record or {}).get("checks")
    )
    return approval_state(
        "ENTSOG", certification=record, gate_allows_live=gate.allows_live,
        credential_state="not_required", connectivity_status="no_records",
    )


def test_fresh_install_without_approval_is_refused_with_a_stable_visible_reason(
    fresh_store, monkeypatch, capsys
):
    calls = _mock_entsog(monkeypatch)
    code, report = _ingest(monkeypatch, capsys)

    assert code == 1 and report["ok"] is False
    assert report["failures"] == [
        {"source": "ENTSOG", "code": "source_gate_blocked", "reason": NOT_APPROVED_CODE}
    ]
    assert calls == []  # refused before any provider request
    with fresh_store() as session:
        run = session.query(IngestionRunRecord).one()
        assert run.status == "failed" and run.error_code == NOT_APPROVED_CODE
        state = _state(session)
    assert state["state"] == "not_approved" and state["reason"] == NOT_APPROVED_CODE
    assert state["action"] == "Admin → Connectors"
    assert "ENTSOG TP" in state["terms"]["attribution"]


def test_fresh_install_approval_then_ingestion_stores_rows(fresh_store, monkeypatch, capsys):
    from eurogas_nexus.application.public_source_approval import (
        ApprovalError,
        approve_public_source,
    )

    calls = _mock_entsog(monkeypatch)
    now = datetime(2026, 11, 16, 9, tzinfo=UTC)
    with fresh_store() as session:
        with pytest.raises(ApprovalError) as refused:
            approve_public_source(
                session, "src-entsog", actor="admin.anna", reason="first run",
                accept_terms=False, now=now, client=_NoNetworkClient(),
            )
        assert refused.value.code == "terms_not_accepted"
        result = approve_public_source(
            session, "src-entsog", actor="admin.anna", reason="first run, ticket OPS-1",
            accept_terms=True, now=now, client=_NoNetworkClient(),
        )
        session.commit()
        assert result["state"] == "approved" and result["changed"] is True
        assert result["approval"]["approved_by"] == "admin.anna"
        audit = (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "approve_public_source")
            .one()
        )
        assert audit.principal == "admin.anna" and "first run, ticket OPS-1" in audit.detail
        # Idempotent: approving again changes nothing.
        again = approve_public_source(
            session, "entsog", actor="admin.ben", reason="again", accept_terms=True,
            now=now, client=_NoNetworkClient(),
        )
        assert again["changed"] is False and again["approval"]["approved_by"] == "admin.anna"
    assert {"connectionpoints", "operationaldatas"} <= set(calls)  # the live validation ran

    code, report = _ingest(monkeypatch, capsys)

    assert code == 0 and report["ok"] is True, report
    with fresh_store() as session:
        assert session.query(FlowObservationRecord).count() > 0
        assert _state(session)["state"] == "approved"
        stored = session.query(FlowObservationRecord).count()

    # Revoked: the next read is refused again and nothing stored is deleted.
    from eurogas_nexus.application.public_source_approval import revoke_public_source_approval

    with fresh_store() as session:
        revoke_public_source_approval(
            session, "src-entsog", actor="admin.anna", reason="terms review", now=now
        )
        session.commit()
        assert _state(session)["state"] == "not_approved"
    code, report = _ingest(monkeypatch, capsys)
    assert code == 1 and report["failures"][0]["reason"] == NOT_APPROVED_CODE
    with fresh_store() as session:
        assert session.query(FlowObservationRecord).count() == stored


def test_gie_approved_before_its_key_waits_for_the_key(fresh_store, monkeypatch):
    from eurogas_nexus.application import public_source_approval as approval

    monkeypatch.setattr(approval, "resolve_provider_key", lambda system, factory=None: None)
    with fresh_store() as session:
        result = approval.approve_public_source(
            session, "gie", actor="admin.anna", reason="storage for the desk",
            accept_terms=True, client=_NoNetworkClient(),
        )
        session.commit()
        assert result["state"] == "approved_waiting_for_key"
        record = latest_certification(session, "GIE")
        state = approval_state(
            "GIE", certification=record, gate_allows_live=False,
            credential_state="missing", connectivity_status="needs_credential",
        )
    assert state["state"] == "approved_waiting_for_key"
    assert script._gate_blockers  # the gate validates it at the first read with the key
