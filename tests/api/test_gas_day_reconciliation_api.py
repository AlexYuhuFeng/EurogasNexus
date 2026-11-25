"""``GET /api/desk/gas-day/{gas_day}/reconciliation`` (SCHED-1): JSON, CSV and refusals.

The demo desk with the Aldermoor sale's nominations taken away: the deal (6,000 MWh a day
out at NBP) is not nominated, 0 - (-6,000) = +6,000 MWh long, on any day the request runs.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.gas_day_reconciliation import CSV_COLUMNS
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import GasDayNominationEventRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.market.gas_day import gas_day_label

PUBLIC_TOKEN = "test-public-api-token"
DEMO = Path(__file__).resolve().parents[2] / "scripts" / "demo"


def _seed_module():
    spec = importlib.util.spec_from_file_location("seed_demo_desk_recon_api",
                                                  DEMO / "seed_demo_desk.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _client(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'recon.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    who = {}
    with Session(engine) as session:
        _seed_module().seed(session, datetime.now(UTC), history_days=2)
        session.execute(delete(GasDayNominationEventRecord).where(
            GasDayNominationEventRecord.line_ref == "trade:demo-etrm-ald-1"))
        for name, role in (("scheduler", "SCHEDULER"), ("viewer", "VIEWER"),
                           ("admin", "ADMIN")):
            row = create_identity_principal(
                session, name=f"recon.{name}", display_name=name, role=role,
                data_scopes=["*"])
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"])
            who[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        session.commit()
    engine.dispose()
    return TestClient(create_app()), who


def _path(**_):
    return f"/api/desk/gas-day/{gas_day_label(datetime.now(UTC))}/reconciliation"


def test_json_csv_and_refusals(tmp_path, monkeypatch):
    client, who = _client(tmp_path, monkeypatch)

    body = client.get(_path(), headers=who["scheduler"], params={"hub": "NBP"})
    assert body.status_code == 200, body.text
    data = body.json()["data"]
    aldermoor = [item for item in data["breaks"]
                 if item["counterparty"] == "Aldermoor Energy plc"]
    (item,) = aldermoor
    assert item["kind"] == "not_nominated" and item["mwh_at_risk"] == 6_000
    assert "long 6,000 MWh" in item["explanation"] and item["next_step"]
    assert item["explanation_zh"] and item["next_step_zh"]
    assert data["execution"].startswith("none")
    assert {group["hub"] for group in data["groups"]} == {"NBP"}

    # A viewer may read it too (portfolio.read); the filter narrows to the break kind.
    only = client.get(_path(), headers=who["viewer"],
                      params={"kind": "not_nominated", "breaks_only": "true"})
    assert only.status_code == 200
    assert {b["kind"] for b in only.json()["data"]["breaks"]} == {"not_nominated"}
    assert all(g["state"] == "break" for g in only.json()["data"]["groups"])

    exported = client.get(_path(), headers=who["scheduler"],
                          params={"format": "csv", "counterparty": "aldermoor"})
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(exported.text.lstrip("\ufeff"))))  # Excel BOM
    assert tuple(rows[0]) == tuple(CSV_COLUMNS)
    assert len(rows) == 2 and "not_nominated" in rows[1]

    refused = client.get(_path(), headers=who["admin"])
    assert refused.status_code == 403
    unknown = client.get(_path(), headers=who["scheduler"], params={"kind": "teleport"})
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "unknown_kind"
    far = client.get("/api/desk/gas-day/2020-01-01/reconciliation", headers=who["scheduler"])
    assert far.status_code == 422
    assert far.json()["detail"]["code"] == "gas_day_out_of_range"
    # A firm-wide caller filtering on a book nobody holds sees nothing (a mandated trader
    # asking for another's book is refused: tests/integration/test_gas_day_reconciliation.py).
    nobody = client.get(_path(), headers=who["scheduler"], params={"book_id": "nobody"})
    assert nobody.status_code == 200 and nobody.json()["data"]["groups"] == []
    bad = client.get(_path(), headers=who["scheduler"], params={"format": "xlsx"})
    assert bad.status_code == 422
