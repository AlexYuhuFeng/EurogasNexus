"""NEWS-1 test helpers: a SQLite store with held REMIT messages, contracts, cargoes and books.

Everything here is invented for the tests (books, contracts, cargoes, message ids); asset and
operator names are real so the gazetteer tags them.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine

from eurogas_nexus.application.news_ingest import FetchResult
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    LngCargoRecord,
    RemitUmmRecord,
    TradingBookRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.domain.observations.remit_umm import parse_umm_export
from eurogas_nexus.ingestion.lng_positions import parse_lng_cargoes

FIXTURES = Path(__file__).resolve().parent / "news"
GOVUK_FEED = "https://www.gov.uk/government/organisations/department-for-energy-security-and-net-zero.atom"


def store(tmp_path, name: str = "news.sqlite"):
    """``(url, engine)`` of a fresh SQLite store with every table."""

    url = f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    return url, engine


def book(book_id: str, entity: str, now: datetime) -> TradingBookRecord:
    return TradingBookRecord(book_id=book_id, name=book_id, legal_entity=entity,
                             region="europe", business="gas", base_currency="EUR",
                             active=True, updated_by="t", updated_at_utc=now)


def contract(contract_id: str, point: str, book_id: str | None, now: datetime
             ) -> UpstreamResourceContractRecord:
    return UpstreamResourceContractRecord(
        contract_id=contract_id, contract_name=f"{contract_id} supply",
        resource_type="PIPELINE_IMPORT", delivery_point_name=point, gas_year="2026",
        delivery_quantity_mwh_per_day=12_000.0, contract_price_gbp_mwh=30.0,
        settlement_frequency="monthly", upstream_payment_lag_days=20,
        screen_sale_cash_lag_days=1, delivery_tolerance_pct=2.0, nomination_tolerance_pct=1.0,
        tolerance_risk_allowance_gbp_mwh=None, annual_financing_rate_pct=5.0,
        owned_entry_capacity_mwh_per_day=None, owned_exit_capacity_mwh_per_day=None,
        allowed_exit_points=["NBP"], eligible_sale_modes=["LOCAL_MARKET_SALE"], notes=None,
        book_id=book_id, created_at_utc=now, updated_at_utc=now,
    )


def cargoes(now: datetime, rows: list[tuple[str, str, str, str]]) -> list[LngCargoRecord]:
    """Cargo records from ``(cargo_id, vessel, terminal, book_id)``, laden, ETA in 3 days."""

    lines = ["cargo_id,vessel_name,status,load_port,load_lat,load_lon,destination_terminal,"
             "eta,position_lat,position_lon,position_at,track,energy_gwh,book_id"]
    for cargo_id, vessel, terminal, book_id in rows:
        lines.append(
            f"{cargo_id},{vessel},laden,Hammerfest,70.68,23.6,{terminal},"
            f"{(now + timedelta(days=3)).isoformat()},62.0,4.5,{now.isoformat()},"
            f"23.6 70.68 {(now - timedelta(days=2)).isoformat()};4.5 62.0 {now.isoformat()},"
            f"950,{book_id}"
        )
    return [LngCargoRecord(**row) for row in parse_lng_cargoes(
        "\n".join(lines) + "\n", source_system="ETRM", source_reference="t", now_utc=now)]


def remit(now: datetime, message_id: str, asset: str, *, zone: str = "NO",
          version: int = 1, unavailable: float = 25, technical: float | None = 145,
          participant: str = "Gassco AS", start_hours: int = -3, days: int = 2
          ) -> list[RemitUmmRecord]:
    row = {
        "messageId": message_id,
        "version": version,
        "publicationDateTime": (now + timedelta(hours=start_hours - 1)).isoformat(),
        "eventStatus": "Active",
        "unavailabilityType": "Unplanned",
        "eventStart": (now + timedelta(hours=start_hours)).isoformat(),
        "eventStop": (now + timedelta(days=days)).isoformat(),
        "affectedAssetName": asset,
        "affectedAssetType": "Production",
        "balancingZone": zone,
        "unitMeasure": "mcm/d",
        "unavailableCapacity": unavailable,
        "marketParticipantName": participant,
    }
    if technical is not None:
        row["technicalCapacity"] = technical
    return [RemitUmmRecord(**m.as_record(), source_system="REMIT", ingested_at_utc=now)
            for m in parse_umm_export(json.dumps([row]), source_reference="fixture")]


class FakeFetcher:
    """Serves ``robots.txt`` and one feed body from memory; records every request."""

    def __init__(self, body: bytes, *, robots: tuple[int, bytes] = (404, b""),
                 etag: str | None = '"v1"') -> None:
        self.body = body
        self.robots = robots
        self.etag = etag
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> FetchResult:
        self.calls.append((url, dict(headers)))
        if url.endswith("/robots.txt"):
            return FetchResult(self.robots[0], self.robots[1], {})
        if self.etag and headers.get("If-None-Match") == self.etag:
            return FetchResult(304, b"", {})
        return FetchResult(200, self.body, {"etag": self.etag} if self.etag else {})


def govuk_feed() -> bytes:
    return (FIXTURES / "govuk_desnz.atom").read_bytes()
