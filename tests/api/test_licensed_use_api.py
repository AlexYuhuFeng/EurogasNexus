"""GOV-1 (P6) through the API: licensed reads are counted, and files carry the export decision."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import limits_service
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    LicensedDataUseRecord,
    MarketDataLicenceRecord,
    MarketQuoteRecord,
)
from eurogas_nexus.security.identity import principal_allows_source_family


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'use.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return engine


def _client(engine, *, role: str = "ANALYST", scopes=("EEX",)) -> TestClient:
    from eurogas_nexus.db.repositories.identity import (
        create_identity_api_key,
        create_identity_principal,
    )

    name = f"p-{role}-{'-'.join(scopes).replace('*', 'all')}".lower().rstrip("-")
    with Session(engine) as session:
        principal = create_identity_principal(
            session, name=name, display_name="p", role=role, data_scopes=list(scopes)
        )
        principal_id = principal.principal_id
        _, bearer = create_identity_api_key(session, principal_id, scopes=["*"])
        session.commit()
    client = TestClient(
        create_app(),
        headers={"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Identity": bearer},
    )
    client.principal_id = principal_id
    return client


def _uses(engine) -> list[LicensedDataUseRecord]:
    with Session(engine) as session:
        return list(session.query(LicensedDataUseRecord).order_by(
            LicensedDataUseRecord.source_family, LicensedDataUseRecord.surface
        ))


def _quote(quote_id: str, source_system: str) -> MarketQuoteRecord:
    now = datetime.now(UTC)
    return MarketQuoteRecord(
        quote_id=quote_id, source_system=source_system, venue="test",
        instrument_id=f"{source_system}-TTF-{quote_id}", hub="TTF", product="within-day",
        delivery_start_utc=now, delivery_end_utc=now + timedelta(days=1), bid_price=41.4,
        ask_price=41.5, last_price=41.45, currency="EUR", unit="MWh", observed_at_utc=now,
        received_at_utc=now, source_reference="test", freshness="simulated",
        quality_score=0.0, simulated=True,
    )


def test_a_licensed_read_is_counted_once_per_day_and_route(store):
    with Session(store) as session:
        session.add_all([_quote("eex", "EEX_Sim"), _quote("ice", "ICE_OCM_Sim")])
        session.commit()
    client = _client(store)
    for _ in range(3):
        response = client.get("/api/market/quotes")
        assert response.status_code == 200, response.text
    sources = {row["source_system"] for row in response.json()["data"]}
    assert sources == {"EEX_Sim"}  # the ICE row is filtered out, so it is not usage
    (use,) = _uses(store)
    assert (use.principal_id, use.source_family, use.reads) == (
        client.principal_id, "EEX", 3,
    )
    assert use.surface == "GET /api/market/quotes"
    assert use.usage_day == datetime.now(UTC).date()


def test_a_read_of_public_data_writes_no_usage(store):
    client = _client(store, scopes=())
    assert client.get("/api/market/quotes").status_code == 200
    assert _uses(store) == []


def _exposure(reads: set[str]):
    """Credit exposure rows whose marks came from these licensed families."""

    def compute(caller, today):
        for family in reads:
            principal_allows_source_family(caller.principal, family)
        return SimpleNamespace(
            rows=[{"counterparty_id": "C1", "exposure": 1.0}], warnings=[],
            marks_as_of=today.isoformat(),
        )

    return compute


def _licence(engine, family: str, *, redistribution: bool) -> None:
    with Session(engine) as session:
        session.add(
            MarketDataLicenceRecord(
                licence_id=f"lic-{family}", vendor=family, source_family=family.upper(),
                licence_type="ENTERPRISE", licensed_use="DISPLAY",
                valid_from=date(2026, 1, 1), redistribution_allowed=redistribution,
                updated_by="admin", updated_at_utc=datetime.now(UTC),
            )
        )
        session.commit()


def test_a_file_of_licensed_rows_is_marked_for_internal_use_and_counted_as_an_export(
    store, monkeypatch
):
    monkeypatch.setattr(limits_service, "credit_exposure_rows", _exposure({"EEX"}))
    client = _client(store, role="REVIEWER", scopes=("EEX",))
    csv = client.get("/api/portfolio/credit-exposure", params={"format": "csv"})
    assert csv.status_code == 200, csv.text
    assert csv.headers["x-eurogas-export-decision"] == "restricted"
    assert csv.headers["x-eurogas-licensed-sources"] == "EEX"
    assert csv.headers["x-eurogas-export-restrictions"] == "internal-use-only,no-redistribution"
    xlsx = client.get("/api/portfolio/credit-exposure", params={"format": "xlsx"})
    assert xlsx.status_code == 200, xlsx.text
    from io import BytesIO
    from zipfile import ZipFile

    with ZipFile(BytesIO(xlsx.content)) as book:
        sheet_text = " ".join(
            book.read(name).decode("utf-8") for name in book.namelist() if name.endswith(".xml")
        )
    assert "Licensed data" in sheet_text and "Internal use only" in sheet_text
    surfaces = [use.surface for use in _uses(store)]
    assert surfaces == [
        "export:csv GET /api/portfolio/credit-exposure",
        "export:xlsx GET /api/portfolio/credit-exposure",
    ]
    # JSON reads of the same rows are counted as reads, not exports.
    assert client.get("/api/portfolio/credit-exposure").status_code == 200
    assert "GET /api/portfolio/credit-exposure" in [use.surface for use in _uses(store)]


def test_a_licence_that_allows_redistribution_allows_the_file(store, monkeypatch):
    _licence(store, "EEX", redistribution=True)
    monkeypatch.setattr(limits_service, "credit_exposure_rows", _exposure({"EEX"}))
    client = _client(store, role="REVIEWER", scopes=("EEX",))
    response = client.get("/api/portfolio/credit-exposure", params={"format": "csv"})
    assert response.status_code == 200, response.text
    assert response.headers["x-eurogas-export-decision"] == "allowed"
    assert "x-eurogas-export-restrictions" not in response.headers


def test_a_file_of_data_whose_export_terms_are_not_registered_is_refused(store, monkeypatch):
    monkeypatch.setattr(limits_service, "credit_exposure_rows", _exposure({"Argus"}))
    client = _client(store, role="REVIEWER", scopes=("Argus",))
    refused = client.get("/api/portfolio/credit-exposure", params={"format": "csv"})
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["error"] == "export_denied"
    assert refused.json()["detail"]["licensed_families"] == ["Argus"]
    # Once the firm registers its licence, the file is delivered for internal use.
    _licence(store, "Argus", redistribution=False)
    allowed = client.get("/api/portfolio/credit-exposure", params={"format": "csv"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.headers["x-eurogas-export-decision"] == "restricted"


def test_a_file_without_licensed_data_is_allowed(store, monkeypatch):
    monkeypatch.setattr(limits_service, "credit_exposure_rows", _exposure(set()))
    client = _client(store, role="REVIEWER", scopes=())
    response = client.get("/api/portfolio/credit-exposure", params={"format": "pdf"})
    assert response.status_code == 200, response.text
    assert response.headers["x-eurogas-export-decision"] == "allowed"
    assert _uses(store) == []


def test_the_licence_register_shows_thirty_days_of_use(store):
    _licence(store, "EEX", redistribution=False)
    with Session(store) as session:
        session.add(_quote("eex", "EEX_Sim"))
        session.commit()
    reader = _client(store)
    reader.get("/api/market/quotes")
    reader.get("/api/market/quotes")
    admin = _client(store, role="ADMIN", scopes=("*",))
    response = admin.get("/api/access/market-data-licences")
    assert response.status_code == 200, response.text
    (licence,) = response.json()["data"]
    usage = licence["usage_30d"]
    assert usage["principals"] == 1 and usage["reads"] == 2 and usage["exports"] == 0
    assert usage["last_read_utc"]


def test_a_read_answers_when_its_usage_cannot_be_recorded(store):
    with Session(store) as session:
        session.add(_quote("eex", "EEX_Sim"))
        session.commit()
    client = _client(store)
    LicensedDataUseRecord.__table__.drop(store)  # the usage store is gone
    response = client.get("/api/market/quotes")
    assert response.status_code == 200, response.text
    assert response.json()["data"]
