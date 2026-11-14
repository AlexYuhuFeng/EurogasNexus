"""The GB demand script runs strict (explicit dates and ids) or rolling for the scheduler."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.ingestion.national_gas_demand import DemandDownload, parse_national_gas_csv

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "ingest_national_gas_demand.py"
HEADER = "Applicable At,Applicable For,Data Item,Value,Generated Time,Quality Indicator\n"
LABELS = {"PUBOB637": "Demand Actual, NTS, D+1", "PUBOB652": "Demand Actual, NTS, D+6"}


def _module():
    spec = importlib.util.spec_from_file_location("ingest_national_gas_demand_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'demand.sqlite').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[NationalGasActualDemandRecord.__table__])
    module = _module()
    calls = []

    def fake_download(provider_item_id, *, date_from, date_to, client=None, **_kwargs):
        calls.append((provider_item_id, date_from, date_to))
        day = date_to
        published = day + timedelta(days=1 if provider_item_id == "PUBOB637" else 6)
        stamp = f"{published:%d/%m/%Y} 12:20:01"
        body = (
            HEADER
            + f'{stamp},{day:%d/%m/%Y},"{LABELS[provider_item_id]}",176.708,{stamp},\n'
        ).encode()
        received = datetime.now(UTC)
        rows = parse_national_gas_csv(
            body,
            provider_item_id=provider_item_id,
            date_from=date_from,
            date_to=date_to,
            received_at_utc=received,
        )
        return DemandDownload(tuple(rows), body, "0" * 64, "https://example.invalid", received)

    monkeypatch.setattr(module, "download_national_gas_csv", fake_download)
    yield module, url, calls, engine
    engine.dispose()


def test_rolling_json_mode_reads_both_ids_and_reports_for_the_scheduler(script, capsys):
    module, url, calls, engine = script
    assert module.main(["--database-url", url, "--json", "--days", "8"]) == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    assert {call[0] for call in calls} == {"PUBOB637", "PUBOB652"}
    assert {(call[1], call[2]) for call in calls} == {(yesterday - timedelta(days=7), yesterday)}
    assert report["ok"] is True
    assert report["sources"]["national_gas_demand"] == {
        "records": 2, "inserted": 2, "updated": 0, "unchanged": 0, "revised": 0,
    }
    with engine.connect() as connection:
        assert connection.execute(
            select(func.count()).select_from(NationalGasActualDemandRecord)
        ).scalar() == 2

    # The same publications again: an append-only log reports them unchanged.
    assert module.main(["--database-url", url, "--json", "--days", "8"]) == 0
    again = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert again["sources"]["national_gas_demand"]["unchanged"] == 2


def test_strict_mode_is_unchanged(script, capsys):
    module, url, calls, _engine = script
    argv = [
        "--database-url", url, "--date-from", "2026-11-05", "--date-to", "2026-11-11",
        "--ids", "PUBOB637",
    ]
    assert module.main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok" and payload["inserted"] == 1
    assert calls == [("PUBOB637", date(2026, 11, 5), date(2026, 11, 11))]


@pytest.mark.parametrize(
    "argv",
    [
        ["--date-from", "2026-11-05", "--date-to", "2026-11-11"],  # strict needs ids
        ["--days", "3", "--date-from", "2026-11-05", "--date-to", "2026-11-07"],
        ["--days", "0"],
        ["--days", "40"],  # over the provider's 31-day window
    ],
)
def test_refuses_ambiguous_or_unbounded_windows(script, argv):
    module, url, calls, _engine = script
    with pytest.raises(SystemExit):
        module.main(["--database-url", url, *argv])
    assert calls == []
