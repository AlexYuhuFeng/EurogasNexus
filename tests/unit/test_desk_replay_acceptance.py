"""Desk replay acceptance pack (#50), checked against an independent reference.

The reference below recomputes each case from first principles - wall-clock hours of the gas
day from the local 06:00 boundaries in Europe/Berlin (zoneinfo arithmetic, not the engine's
gas-day helper), outage MWh hour by hour, then the gap and the cost of each response - so a
defect in the engine's interval or revision handling cannot hide behind the same code.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from eurogas_nexus.domain.portfolio.desk_replay import DeskReplay, replay

BERLIN = ZoneInfo("Europe/Berlin")


def _gas_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(6), BERLIN).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(6), BERLIN).astimezone(UTC)
    return start, end


def _reference_loss(day: date, outages: list[tuple[datetime, datetime, Decimal]]) -> Decimal:
    start, end = _gas_day_bounds(day)
    loss = Decimal(0)
    cursor = start
    while cursor < end:  # hour by hour, so a 23- or 25-hour day counts itself
        nxt = cursor + timedelta(hours=1)
        for left, right, mw in outages:
            overlap = (min(nxt, right) - max(cursor, left)).total_seconds()
            if overlap > 0:
                loss += mw * Decimal(str(overlap)) / Decimal(3600)
        cursor = nxt
    return loss


def _evidence(record_id: str, revision: int, available_at: datetime) -> dict:
    return {
        "record_id": record_id,
        "revision": revision,
        "available_at": available_at.isoformat(),
        "source_ref": f"fixture:{record_id}",
    }


AS_OF = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)
DAY = date(2026, 10, 24)  # 25-hour gas day: summer time ends inside it


def _case(**overrides) -> dict:
    start, end = _gas_day_bounds(DAY)
    case = {
        "book_id": "BOOK-1",
        "hub_id": "THE",
        "gas_day": DAY.isoformat(),
        "currency": "EUR",
        "as_of": AS_OF.isoformat(),
        "positions": [
            {**_evidence("avail-1", 1, AS_OF - timedelta(hours=6)),
             "resource_id": "R1", "kind": "AVAILABLE", "mwh": "2400"},
            {**_evidence("commit-1", 1, AS_OF - timedelta(hours=6)),
             "resource_id": "R1", "kind": "COMMITMENT", "mwh": "2300"},
        ],
        "outages": [
            # Revision 1: 10 MW all day. Revision 2 (known before as_of): 20 MW for 12 hours.
            {**_evidence("out-1", 1, AS_OF - timedelta(hours=5)),
             "resource_id": "R1", "starts_at": start.isoformat(), "ends_at": end.isoformat(),
             "unavailable_mw": "10"},
            {**_evidence("out-1", 2, AS_OF - timedelta(hours=1)),
             "resource_id": "R1", "starts_at": start.isoformat(),
             "ends_at": (start + timedelta(hours=12)).isoformat(), "unavailable_mw": "20"},
            # Revision 3 arrives after as_of: a replay must not see it.
            {**_evidence("out-1", 3, AS_OF + timedelta(hours=2)),
             "resource_id": "R1", "starts_at": start.isoformat(), "ends_at": end.isoformat(),
             "unavailable_mw": "90"},
        ],
        "alternatives": [
            {**_evidence("buy-exec", 1, AS_OF - timedelta(minutes=10)),
             "resource_id": "R1", "kind": "BUY_GAS", "quantity_mwh": "500", "cost_per_mwh": "31.5",
             "deadline": (AS_OF + timedelta(hours=3)).isoformat(), "right_confirmed": True,
             "price_basis": "EXECUTABLE",
             "price_valid_until": (AS_OF + timedelta(minutes=30)).isoformat(),
             "credit_per_mwh": "31.5"},
            {**_evidence("buy-stale", 1, AS_OF - timedelta(hours=2)),
             "resource_id": "R1", "kind": "BUY_GAS", "quantity_mwh": "500", "cost_per_mwh": "30",
             "deadline": (AS_OF + timedelta(hours=3)).isoformat(), "right_confirmed": True,
             "price_basis": "EXECUTABLE",
             "price_valid_until": (AS_OF - timedelta(minutes=1)).isoformat()},
            {**_evidence("route-indicative", 1, AS_OF - timedelta(hours=1)),
             "resource_id": "R1", "kind": "CHANGE_ROUTE", "quantity_mwh": "300",
             "cost_per_mwh": "2", "deadline": (AS_OF + timedelta(hours=3)).isoformat(),
             "right_confirmed": False, "price_basis": "INDICATIVE",
             "price_valid_until": (AS_OF + timedelta(hours=3)).isoformat()},
        ],
    }
    case.update(overrides)
    return case


def test_the_engine_matches_the_independent_reference_on_a_25_hour_gas_day() -> None:
    start, end = _gas_day_bounds(DAY)
    assert end - start == timedelta(hours=25)
    result = replay(DeskReplay.model_validate(_case()))
    resource = result["resources"][0]

    # Reference: only revision 2 of the outage is visible at as_of (20 MW for 12 hours).
    loss = _reference_loss(DAY, [(start, start + timedelta(hours=12), Decimal(20))])
    deliverable = max(Decimal(2400) - loss, Decimal(0))
    gap = max(Decimal(2300) - deliverable, Decimal(0))
    assert resource["outage_loss_mwh"] == loss == Decimal(240)
    assert resource["deliverable_mwh"] == deliverable
    assert resource["keep_plan_gap_mwh"] == gap == Decimal(140)
    assert resource["prior_gap_mwh"] == Decimal(0)

    by_id = {row["record_id"]: row for row in resource["alternatives"]}
    assert by_id["buy-exec"]["quantity_mwh"] == gap
    assert by_id["buy-exec"]["incremental_cost"] == gap * Decimal("31.5")
    assert by_id["buy-exec"]["remaining_gap_mwh"] == Decimal(0)
    assert by_id["buy-stale"]["blocked"] == ["WINDOW_CLOSED"]
    assert set(by_id["route-indicative"]["blocked"]) == {
        "RIGHT_UNCONFIRMED",
        "PRICE_NOT_ACTIONABLE",
    }


def test_a_replay_from_its_frozen_inputs_reproduces_the_decision() -> None:
    first = replay(DeskReplay.model_validate(_case()))
    again = replay(DeskReplay.model_validate(first["frozen_inputs"]))
    assert again["input_sha256"] == first["input_sha256"]
    assert again["resources"] == first["resources"]
    # The future revision (90 MW) never entered the frozen inputs.
    revisions = [row["revision"] for row in first["frozen_inputs"]["outages"]]
    assert revisions == [2]


def test_missing_commitment_evidence_is_unknown_not_zero() -> None:
    case = _case()
    case["positions"][1]["mwh"] = None
    resource = replay(DeskReplay.model_validate(case))["resources"][0]
    assert resource["committed_mwh"] is None
    assert resource["remaining_mwh"] is None
    assert resource["keep_plan_gap_mwh"] is None
    assert all("GAP_UNKNOWN" in row.get("blocked", []) for row in resource["alternatives"])


def test_re_importing_the_same_revision_is_idempotent_and_a_conflict_is_refused() -> None:
    case = _case()
    case["outages"].append(dict(case["outages"][1]))
    loss = replay(DeskReplay.model_validate(case))["resources"][0]["outage_loss_mwh"]
    assert loss == Decimal(240)
    conflicting = dict(case["outages"][1], unavailable_mw="25")
    case["outages"].append(conflicting)
    with pytest.raises(ValueError, match="Conflicting evidence"):
        replay(DeskReplay.model_validate(case))


def test_evidence_for_an_unknown_resource_stays_visible() -> None:
    case = _case()
    case["alternatives"].append(
        {**case["alternatives"][0], "record_id": "orphan", "resource_id": "R9"}
    )
    result = replay(DeskReplay.model_validate(case))
    assert result["unmatched_record_ids"] == ["orphan"]
