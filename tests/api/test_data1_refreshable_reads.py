"""DATA-1 (lesson P7): market reads that Excel's Power Query can refresh.

``format=csv`` on the price strip, observations and FX answers flat rows under a fixed header
(the same with or without rows, with or without ``as_of``). The file is metered and carries
the GOV-1 export decision of the licensed families it was read from; ``format=json`` (the
default) is unchanged.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.market_event_capture import capture_rows
from eurogas_nexus.application.price_strip import PRICE_STRIP_COLUMNS
from eurogas_nexus.application.refreshable_reads import FX_COLUMNS, OBSERVATION_COLUMNS
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    LicensedDataUseRecord,
    MarketDataLicenceRecord,
    MarketObservationRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

FIRST = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
CORRECTED = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)


def _settlement(price: float) -> MarketObservationRecord:
    return MarketObservationRecord(
        observation_id="obs-eex-ttf-2027-01-20261120", market_venue="EEX", product="TTF",
        price=price, unit="MWh", currency="EUR",
        period_start_utc=datetime(2027, 1, 1, tzinfo=UTC),
        period_end_utc=datetime(2027, 2, 1, tzinfo=UTC),
        observed_at_utc=datetime(2026, 11, 20, 17, 30, tzinfo=UTC), source_system="EEX",
        source_reference="operator-export:test.csv", source_record_id=None,
        freshness="current", quality_score=1.0, research_only=False,
        metadata_json={"hub": "TTF", "settlement": True},
    )


def _fixing(rate: float) -> FxObservationRecord:
    return FxObservationRecord(
        observation_id="fx-ecb-eurgbp-20261120", pair="EURGBP", base_currency="EUR",
        quote_currency="GBP", rate=rate, rate_type="reference", value_date="2026-11-20",
        observed_at_utc=datetime(2026, 11, 20, 15, 0, tzinfo=UTC), source_system="ECB",
        source_reference="ecb", source_record_id=None, freshness="current",
        research_only=False, metadata_json={},
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'pq.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    for price, rate, at in ((80.0, 0.87, FIRST), (81.5, 0.8712, CORRECTED)):
        with Session(engine) as session:
            stored = session.merge(_settlement(price))
            fixing = session.merge(_fixing(rate))
            capture_rows(session, settlements=[stored], fixings=[fixing], now_utc=at)
            session.commit()
    keys = {}
    with Session(engine) as session:
        for name, scopes in (("licensed", ["ECB", "EEX"]), ("public", ["ECB"])):
            owner = create_identity_principal(
                session, name=f"pq-{name}", display_name=name, role="ANALYST",
                data_scopes=scopes,
            )
            _, bearer = create_identity_api_key(
                session, owner.principal_id, display_name=name, scopes=scopes
            )
            keys[name] = (bearer, owner.principal_id)
        session.commit()

    def client(who: str = "licensed") -> TestClient:
        api = TestClient(
            create_app(),
            headers={
                "X-Eurogas-Identity": keys[who][0],
                "X-Eurogas-Api-Key": "test-public-api-token",
            },
        )
        api.principal_id = keys[who][1]
        return api

    return engine, client


def _licence(engine, family: str, *, redistribution: bool) -> None:
    with Session(engine) as session:
        session.add(
            MarketDataLicenceRecord(
                licence_id=f"lic-{family}", vendor=family, source_family=family,
                licence_type="ENTERPRISE", licensed_use="DISPLAY",
                valid_from=date(2026, 1, 1), redistribution_allowed=redistribution,
                updated_by="admin", updated_at_utc=datetime.now(UTC),
            )
        )
        session.commit()


def _table(response) -> tuple[list[str], list[dict[str, str]]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")  # Excel reads UTF-8 with the byte-order mark
    reader = csv.reader(io.StringIO(text[1:]))
    header, *body = list(reader)
    return header, [dict(zip(header, line, strict=True)) for line in body]


def _uses(engine) -> list[tuple[str, str]]:
    with Session(engine) as session:
        return sorted(
            (use.source_family, use.surface) for use in session.query(LicensedDataUseRecord)
        )


def test_the_price_strip_refreshes_as_flat_csv_with_a_fixed_header(store):
    engine, client = store
    _licence(engine, "EEX", redistribution=False)
    params = {"hub": "TTF", "start": "2027-01", "months": 3, "format": "csv"}
    response = client().get("/api/market/prices", params=params)
    header, rows = _table(response)
    assert header == list(PRICE_STRIP_COLUMNS)
    assert [row["month"] for row in rows] == ["2027-01", "2027-02", "2027-03"]
    assert float(rows[0]["value"]) == pytest.approx(81.5) and rows[0]["revision"] == "2"
    assert rows[1]["value"] == ""  # a month with no price keeps its row
    # GOV-1: the file carries the export decision of the licensed family it was read from.
    assert response.headers["x-eurogas-export-decision"] == "restricted"
    assert response.headers["x-eurogas-licensed-sources"] == "EEX"
    assert response.headers["x-eurogas-report-rows"] == "3"

    as_of = client().get("/api/market/prices", params={**params, "as_of": "2026-11-21T08:00Z"})
    header_then, then = _table(as_of)
    assert header_then == header
    assert float(then[0]["value"]) == pytest.approx(80.0) and then[0]["revision"] == "1"


def test_a_licensed_file_is_metered_as_an_export(store):
    engine, client = store
    _licence(engine, "EEX", redistribution=False)
    api = client()
    _table(api.get("/api/market/observations", params={"format": "csv"}))
    api.get("/api/market/observations")
    assert _uses(engine) == [
        ("EEX", "GET /api/market/observations"),
        ("EEX", "export:csv GET /api/market/observations"),
    ]


def test_a_file_of_licensed_data_whose_terms_are_unknown_is_refused(store):
    engine, client = store
    with Session(engine) as session:
        argus = _settlement(79.9)
        argus.observation_id = "obs-argus"
        argus.source_system = argus.market_venue = "Argus"
        session.add(argus)
        session.commit()
    eex_only = client().get("/api/market/observations", params={"format": "csv"})
    assert eex_only.status_code == 200  # this caller does not read Argus: the file is EEX only
    with Session(engine) as session:
        owner = create_identity_principal(
            session, name="pq-argus", display_name="argus", role="ANALYST",
            data_scopes=["Argus"],
        )
        _, bearer = create_identity_api_key(
            session, owner.principal_id, display_name="argus", scopes=["Argus"]
        )
        session.commit()
    argus_reader = TestClient(
        create_app(),
        headers={"X-Eurogas-Identity": bearer, "X-Eurogas-Api-Key": "test-public-api-token"},
    )
    refused = argus_reader.get("/api/market/observations", params={"format": "csv"})
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["error"] == "export_denied"
    assert refused.json()["detail"]["licensed_families"] == ["Argus"]
    # The JSON read of the same rows is a read, not a file.
    assert argus_reader.get("/api/market/observations").status_code == 200
    # Once the firm registers its licence, the file is delivered for internal use.
    _licence(engine, "Argus", redistribution=False)
    allowed = argus_reader.get("/api/market/observations", params={"format": "csv"})
    assert allowed.headers["x-eurogas-export-decision"] == "restricted"
    assert [row["source_system"] for row in _table(allowed)[1]] == ["Argus"]


def test_observations_and_fx_keep_their_header_with_or_without_rows_or_as_of(store):
    engine, client = store
    public = client("public")
    header, rows = _table(public.get("/api/market/observations", params={"format": "csv"}))
    assert header == list(OBSERVATION_COLUMNS) and rows == []  # EEX is not this caller's
    fx = public.get("/api/market/fx", params={"format": "csv"})
    header, rows = _table(fx)
    assert header == list(FX_COLUMNS)
    assert [(row["pair"], row["rate"], row["revision"]) for row in rows] == [
        ("EURGBP", "0.8712", "")
    ]
    assert fx.headers["x-eurogas-export-decision"] == "allowed"
    then = public.get("/api/market/fx", params={"format": "csv", "as_of": "2026-11-22T00:00Z"})
    header_then, rows = _table(then)
    assert header_then == header
    assert [(row["rate"], row["revision"], row["revision_basis"]) for row in rows] == [
        ("0.87", "1", "market_event")
    ]
    assert _uses(engine) == []  # public data writes no usage


def test_json_stays_the_default_and_an_unknown_format_is_refused(store):
    _, client = store
    api = client("public")
    assert api.get("/api/market/fx").json()["data"][0]["pair"] == "EURGBP"
    assert api.get("/api/market/fx", params={"format": "json"}).json()["data"]
    assert api.get("/api/market/fx", params={"format": "xml"}).status_code == 422
