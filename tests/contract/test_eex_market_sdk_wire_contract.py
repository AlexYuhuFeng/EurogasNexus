"""EEX exact evidence must survive the actual HTTP envelope into the typed SDK.

The backend route, repository projection, JSON envelope and SDK response model are
all exercised. Only the HTTP transport is bridged to the in-process ASGI app so the
test needs no listening socket; authentication, data, metadata and warnings are the
real route's.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
import pytest
from eurogas_nexus_sdk.market import (
    NormalizedMarketObservation,
    fetch_normalized_market_observations_result,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

import eurogas_nexus.db.session as db_session
from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord
from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR
from eurogas_nexus.ingestion.eex_ngp import (
    EexNgpGasDayCalendarContract,
    eex_ttf_ngp_receipt_observations,
    parse_eex_ttf_ngp_csv,
)

RECEIPT = datetime(2026, 10, 29, 14, 54, 5, 623743, tzinfo=UTC)
EEX_CSV = (
    "\ufeffGasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let\r\n"
    "29/10/2026;+123.4500000000000000001;+42.500000000000000000;"
    "Final NGP;29/10/2026 12:00\r\n"
)


def _seed_actual_eex_observation(engine) -> None:
    parsed = parse_eex_ttf_ngp_csv(EEX_CSV, retrieved_at_utc=RECEIPT)
    observations = eex_ttf_ngp_receipt_observations(
        parsed,
        received_at_utc=RECEIPT,
        gas_day_calendar_contract=EexNgpGasDayCalendarContract(
            calendar_id=EU_CAM_UTC_CALENDAR,
            evidence="test-owned receipt/calendar evidence for the wire boundary",
        ),
    )
    with Session(engine) as session:
        session.add(MarketObservationRecord(**observations[0]))
        session.add(
            FxObservationRecord(
                observation_id="fx-eurgbp-20261029",
                pair="EURGBP",
                base_currency="EUR",
                quote_currency="GBP",
                rate=0.85,
                rate_type="reference",
                value_date="2026-10-29",
                observed_at_utc=RECEIPT,
                source_system="ECB",
                source_reference="ecb-eurofxref",
                source_record_id=None,
                freshness="unknown",
                research_only=True,
                metadata_json=None,
            )
        )
        session.commit()


@pytest.fixture()
def wire_client(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> tuple[TestClient, dict]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    request.addfinalizer(engine.dispose)
    MarketObservationRecord.__table__.create(engine)
    FxObservationRecord.__table__.create(engine)
    _seed_actual_eex_observation(engine)

    def session_factory() -> Session:
        return Session(engine)

    monkeypatch.setattr(db_session, "resolve_database_url", lambda: "sqlite+pysqlite://")
    monkeypatch.setattr(db_session, "get_session_factory", lambda: session_factory)

    client = TestClient(create_app())
    request.addfinalizer(client.close)
    captured: dict = {}

    def fake_get(url: str, **kwargs):
        captured["url"] = url
        captured["headers"] = dict(kwargs.get("headers") or {})
        split = urlsplit(url)
        path = split.path or "/"
        if split.query:
            path = f"{path}?{split.query}"
        return client.get(
            path,
            headers=kwargs.get("headers"),
            params=kwargs.get("params"),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    return client, captured


def test_typed_result_carries_all_exact_evidence_and_full_meta(
    wire_client: tuple[TestClient, dict],
) -> None:
    _client, captured = wire_client

    result = fetch_normalized_market_observations_result("http://testserver")

    assert captured["url"].endswith("/api/market/normalized")
    assert captured["headers"]["Authorization"] == "Bearer test-public-api-token"
    assert result.meta.source_references == ["runtime-postgresql"]
    assert result.meta.warnings == []
    assert result.meta.research_only is True
    assert result.meta.human_review_required is True

    assert len(result.data) == 1
    sdk: NormalizedMarketObservation = result.data[0]
    assert sdk.source_price_status == "exact"
    assert sdk.source_price_exact == "123.4500000000000000001"
    assert sdk.source_price_raw == "+123.4500000000000000001"
    assert sdk.source_price_volume_mwh_exact == "42.500000000000000000"
    assert sdk.source_price_volume_raw == "+42.500000000000000000"
    assert sdk.source_price_volume_status == "valid"
    assert sdk.source_price_provenance == "eex_ngp_exact_source_decimal"
    assert sdk.source_price_issue is None
    assert sdk.source_price_issue_detail is None
    assert sdk.source_price_source_system == "EEX"
    assert sdk.source_price_source_reference == "eex-ttf-ngp-15-mins"
    assert sdk.source_price_source_dataset == "ttf-ngp-15min"
    assert sdk.price_float_provenance == "canonical_float_of_validated_exact_decimal"
    assert sdk.price_semantics == "reference_index_never_an_executable_bid_or_ask"
    assert sdk.executable_quote is False
    assert sdk.price_name == "EEX_TTF_NGP"

    # The GBP value is an approximation because the FX input is a float; the
    # envelope must not claim an exact converted rate.
    assert sdk.price_gbp_mwh_exact is None
    assert sdk.price_gbp_mwh_provenance == (
        "exact_source_decimal_times_float_fx_approximation"
    )

    assert sdk.metadata_json["publication_time_utc"] is None
    assert sdk.metadata_json["publication_time_basis"] == "unknown"
    assert sdk.metadata_json["availability_basis"] == "response_receipt"
    assert sdk.metadata_json["available_at_utc"] == RECEIPT.isoformat()
    assert sdk.metadata_json["retrieved_at_utc"] == RECEIPT.isoformat()
