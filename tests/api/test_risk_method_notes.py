"""Every risk figure the API returns carries its method note (NUM-05); no number changes."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import PortfolioPnlSnapshotRecord
from eurogas_nexus.domain.risk.method_notes import METHOD_NOTES, i18n_entries, method_note

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "scripts" / "demo" / "seed_demo_desk.py"
I18N = ROOT / "clients" / "web" / "src" / "i18n"


def _assert_note(note: dict, key: str) -> None:
    assert note["key"] == key
    assert note["summary"] and "{" not in note["summary"]
    assert note["excludes"] and all(isinstance(item, str) for item in note["excludes"])
    assert note["i18n"]["summary"] == f"risk.method.{key}.summary"
    assert len(note["i18n"]["excludes"]) == len(note["excludes"])
    assert isinstance(note["inputs_as_of"], dict)


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'desk.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    now = datetime.now(UTC)
    with Session(engine) as session:
        seed.seed(session, now)
        session.add(
            PortfolioPnlSnapshotRecord(
                pnl_snapshot_id="pnl-1",
                portfolio_id="demo",
                valuation_time_utc=now,
                realized_pnl_gbp=1.0,
                unrealized_pnl_gbp=2.0,
                indicative_pnl_gbp=3.0,
                cash_value_gbp=0.0,
                market_value_gbp=0.0,
                quantity_mwh=10.0,
                valuation_basis="test",
                source_system="ETRM",
                source_reference="test",
                warnings=[],
                research_only=True,
                human_review_required=True,
            )
        )
        session.commit()
    from eurogas_nexus.api.app import create_app

    return TestClient(create_app())


def test_position_ladder_figures_carry_methods(client):
    data = client.get("/api/portfolio/position-ladder").json()["data"]
    methods = data["methods"]
    _assert_note(methods["mark_to_market"], "mark_to_market")
    _assert_note(methods["var_95_1d"], "var_proxy")
    _assert_note(methods["tenor_exposure"], "tenor_exposure")
    assert methods["var_95_1d"]["params"]["observations"] == data["var_observations"]
    assert str(data["var_observations"]) in methods["var_95_1d"]["summary"]
    assert methods["mark_to_market"]["inputs_as_of"]["marks"]
    shocked = client.get(
        "/api/portfolio/position-ladder", params={"shock": "TTF:2027-01:1.0"}
    ).json()["data"]
    _assert_note(shocked["methods"]["scenario"], "tenor_shock")
    # The figures are the ones the ladder returned before notes existed.
    assert shocked["mark_to_market"] == data["mark_to_market"]


def test_credit_and_mandate_rows_carry_methods(client):
    credit = client.get("/api/portfolio/credit-exposure").json()["data"]["rows"]
    mandates = client.get("/api/portfolio/mandate-usage").json()["data"]["rows"]
    assert credit and mandates
    for row in credit:
        _assert_note(row["method"], "credit_exposure")
        assert row["method"]["inputs_as_of"]["marks"]
    for row in mandates:
        _assert_note(row["method"], "mandate_usage")
    # Downloads keep their columns: the note is JSON-only.
    csv = client.get("/api/portfolio/credit-exposure", params={"format": "csv"})
    assert "method" not in csv.text.splitlines()[0]


def test_pnl_figures_carry_methods(client):
    snapshots = client.get("/api/portfolio/pnl-snapshots").json()["data"]
    assert snapshots
    for row in snapshots:
        _assert_note(row["method"], "pnl_snapshot")
        assert row["method"]["inputs_as_of"]["valuation"] == row["valuation_time_utc"]
    summary = client.get("/api/portfolio/live-summary").json()["data"]
    _assert_note(summary["method"], "live_summary_pnl")


def test_every_note_has_english_and_chinese_strings_without_a_question_mark():
    entries = i18n_entries()
    for language in ("en", "zh"):
        strings = json.loads((I18N / f"{language}.json").read_text(encoding="utf-8"))
        missing = sorted(set(entries) - set(strings))
        assert missing == [], (language, missing)
        assert all("?" not in strings[key] for key in entries)
    english = json.loads((I18N / "en.json").read_text(encoding="utf-8"))
    assert all(english[key] == value for key, value in entries.items())
    for key in METHOD_NOTES:
        _assert_note(method_note(key, params={"observations": 20}), key)
