"""A licensed venue's label is written only by that venue's connector, and every write is
audited (security review H4)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord, MarketQuoteRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.ingestion.licensed_quote_import import parse_quote_export

PUBLIC = "test-public-api-token"


def _client(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'h4.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    keys = {}
    with Session(engine) as session:
        for name, kind, scopes in (
            ("eex-connector", "SERVICE", ["PUBLISH:EEX", "EEX"]),
            ("ops-person", "USER", ["PUBLISH:EEX", "EEX"]),
        ):
            row = create_identity_principal(
                session, name=name, display_name=name, role="OPERATOR",
                principal_type=kind, data_scopes=scopes,
            )
            _key, keys[name] = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=scopes
            )
        session.commit()
    client = TestClient(create_app())
    return engine, client, keys


def _tick():
    now = datetime.now(UTC).isoformat()
    return {"source_system": "EEX", "quotes": [
        {"hub": "TTF", "product": "DA", "exchange_time": now, "bid": 41, "ask": 41.1}]}


def test_only_the_connector_service_key_publishes_and_every_attempt_is_audited(
    tmp_path, monkeypatch
):
    engine, client, keys = _client(tmp_path, monkeypatch)

    def headers(name=None):
        base = {"X-Eurogas-Api-Key": PUBLIC}
        return {**base, "X-Eurogas-Identity": keys[name]} if name else base

    person = client.post("/api/market/ticks", json=_tick(), headers=headers("ops-person"))
    assert person.status_code == 403
    token = client.post(
        "/api/market/ticks", json=_tick(), headers={**headers(), "X-Eurogas-Principal": "ops"}
    )
    assert token.status_code == 403
    stored = client.post("/api/market/ticks", json=_tick(), headers=headers("eex-connector"))
    assert stored.status_code == 200, stored.text
    with Session(engine) as session:
        actions = [
            row.action
            for row in session.query(AuditEventRecord).order_by(AuditEventRecord.event_ts_utc)
            if row.action.startswith("market.ticks")
        ]
        assert actions.count("market.ticks.refused") == 2
        assert actions.count("market.ticks.ingested") == 1
        assert session.query(MarketQuoteRecord).filter_by(source_system="EEX").count() == 1


def test_a_screen_export_is_labelled_a_file_import_by_its_importer():
    text = "timestamp,hub,product,bid,ask\n2026-11-20T09:00:00Z,TTF,DA,41.0,41.2\n"
    result = parse_quote_export(
        text,
        source_system="Trayport",
        source_reference="operator-export:screen.csv",
        received_at_utc=datetime(2026, 11, 20, 9, 1, tzinfo=UTC),
        imported_by="anna.ops",
    )
    [row] = result.rows
    assert row["venue"] == "Trayport (file import)"
    assert row["metadata_json"]["origin"] == "file_import"
    assert row["metadata_json"]["imported_by"] == "anna.ops"
    # Entitlement still follows the licensed family.
    assert row["source_system"] == "Trayport"
