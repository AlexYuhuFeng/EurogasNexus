"""Bilateral delivery against nominations and DCQ; the allocation import."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.domain.risk.delivery import (
    DeliveryDay,
    DeliveryTerms,
    daily_series,
    delivery_performance,
)
from eurogas_nexus.ingestion.contract_deliveries import (
    DeliveryImportError,
    parse_contract_deliveries,
)

TERMS = DeliveryTerms("C1", "Troll supply", "NBP", 10_000.0, 2.0, 10.0, tso="Gassco")
START = date(2026, 10, 1)


def test_steady_delivery_is_ok():
    days = [DeliveryDay(START + timedelta(days=i), 10_000.0, 10_050.0) for i in range(30)]
    row = delivery_performance(TERMS, days)
    assert row["status"] == "ok" and row["short_days"] == row["long_days"] == 0
    assert row["imbalance_mwh"] == 1_500.0 and row["net_deviation_mwh"] == 1_500.0
    assert row["cv_pct"] == 0.0 and row["outside_swing_days"] == 0


def test_shortfalls_volatility_and_trend_are_flagged():
    days = []
    for i in range(30):
        allocated = 10_000.0 if i < 23 else 7_000.0  # last week falls away
        if i % 4 == 0:
            allocated -= 1_000.0  # recurrent short delivery
        days.append(DeliveryDay(START + timedelta(days=i), 10_000.0, allocated))
    days.append(DeliveryDay(START + timedelta(days=30), 10_000.0, None))  # allocation pending
    row = delivery_performance(TERMS, days)
    assert row["short_days"] >= 10 and row["long_days"] == 0
    assert row["missing_days"] == 1 and row["days"] == 31
    assert row["max_shortfall_mwh_d"] == -4_000.0
    assert row["status"] == "watch"
    assert "against DCQ" in row["flags"] and "1 day in 5" in row["flags"]
    assert row["outside_swing_days"] >= 7
    series = daily_series(TERMS, days)
    assert series[-1]["deviation_mwh"] is None and series[0]["deviation_mwh"] == -1_000.0
    assert series[0]["outside_tolerance"] == "short" and series[1]["outside_tolerance"] is None
    assert series[-1]["outside_tolerance"] is None


def test_import_keys_by_contract_and_day_and_keeps_missing_as_missing():
    text = (
        "Contract_ID,Gas_Day,Nominated_MWh,Allocated_MWh,TSO\n"
        "C1,2026-10-01,10000,9800,Gassco\n"
        "C1,2026-10-02,10000,,Gassco\n"
        "C1,2026-10-01,10000,9900,Gassco\n"  # final allocation replaces provisional
    )
    rows = parse_contract_deliveries(
        text, source_system="GASSCO", source_reference="t", now_utc=datetime.now(UTC)
    )
    assert len(rows) == 2
    first = next(r for r in rows if r["gas_day"] == date(2026, 10, 1))
    assert first["allocated_mwh"] == 9900 and first["tso"] == "Gassco"
    assert next(r for r in rows if r["gas_day"] == date(2026, 10, 2))["allocated_mwh"] is None
    with pytest.raises(DeliveryImportError, match="missing column"):
        parse_contract_deliveries(
            "contract_id,gas_day\n",
            source_system="x",
            source_reference="t",
            now_utc=datetime.now(UTC),
        )
    with pytest.raises(DeliveryImportError, match="zero or more"):
        parse_contract_deliveries(
            "contract_id,gas_day,nominated_mwh,allocated_mwh\nC1,2026-10-01,-1,5\n",
            source_system="x",
            source_reference="t",
            now_utc=datetime.now(UTC),
        )
