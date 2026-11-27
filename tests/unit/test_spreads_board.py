"""Research → Spreads opens on the spread board, computed from what is held (owner, 2026-11-19).

Fixture prices and tariffs are illustrative (not market values): TTF and THE month-ahead closes
over 40 days, a TTF curve for two years, the TTF → THE crossing's tariffs (0.10 EUR/MWh a leg)
until the end of gas year 2026/27.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.application.spreads_board import (
    board,
    carry_cost,
    locational_rows,
    time_rows,
)
from eurogas_nexus.application.spreads_workbench import evaluate_curve
from eurogas_nexus.domain.research.strategy_spec import spec_from_dict
from tests.unit.test_spreads_workbench import TODAY, _holdings, _row, _tariff


def _month_ahead(hub: str, base: float, days: int = 40) -> list[dict]:
    rows = []
    for back in range(days, 0, -1):
        day = TODAY - timedelta(days=back)
        front = (day.replace(day=1) + timedelta(days=32)).replace(day=1)
        end = (front + timedelta(days=32)).replace(day=1)
        row = _row(
            hub,
            "month-ahead",
            base + back / 100,
            "EUR/MWh",
            day=day,
            start=datetime(front.year, front.month, 1, tzinfo=UTC),
            end=datetime(end.year, end.month, 1, tzinfo=UTC),
        )
        row["price_mwh"], row["unit_mwh"] = row["price"], "EUR/MWh"
        rows.append(row)
    return rows


def _curve(hub: str, months: int = 30) -> list[dict]:
    rows = []
    first = (TODAY.replace(day=1) + timedelta(days=32)).replace(day=1)
    for index in range(months):
        year, month = divmod(first.month - 1 + index, 12)
        start = date(first.year + year, month + 1, 1)
        price = 30.0 + (3.0 if start.month in (10, 11, 12, 1, 2, 3) else 0.0) + index / 100
        row = _row(hub, f"{start:%Y-%m}", price, "EUR/MWh")
        row["price_mwh"], row["unit_mwh"] = price, "EUR/MWh"
        rows.append(row)
    return rows


def _crossing_tariffs(a: str, b: str, *, until: datetime | None = None) -> list[dict]:
    from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

    graph = shipped_market_area_graph()
    crossing = graph.crossings(graph.hub_for(a), graph.hub_for(b))[0]
    out = []
    for leg in graph.legs(crossing):
        row = _tariff(leg.point_key, leg.tso.split(" / ")[0], leg.direction, 0.10)
        if until is not None:
            row["effective_to"] = until
        out.append(row)
    return out


@pytest.fixture
def holdings():
    rows = _month_ahead("TTF", 30.0) + _month_ahead("THE", 30.5) + _curve("TTF")
    return _holdings(rows, _crossing_tariffs("TTF", "THE"))


def test_locational_row_gross_net_of_the_cheapest_route_range_and_spark(holdings):
    """THE − TTF front month: 30.51 − 30.01 = +0.50 gross; gas moves TTF → THE; the route's
    two legs at 0.10 each: net 0.30. Its 40 closes are all +0.50: the 100th percentile."""

    rows = locational_rows(holdings, ["THE"])
    month = rows[0]["tenors"][0]
    assert month["tenor"] == "MA" and month["available"]
    assert month["gross"] == pytest.approx(0.50, abs=1e-9)
    assert month["direction"] == "TTF → THE"
    assert month["route"]["complete"] and month["route"]["hubs"] == ["TTF", "THE"]
    assert month["net"] == pytest.approx(0.50 - month["cost"], abs=1e-9)
    assert month["cost"] == pytest.approx(0.10 * 2, abs=1e-9)
    assert month["percentile"] == 100.0 and month["range"]["days"] == 40
    assert len(month["spark"]["values"]) == 30
    # Day-ahead not held: said so, never zero.
    assert rows[0]["tenors"][1]["available"] is False
    # The row opens the workbench on THE − TTF net of TTF → THE.
    spec = rows[0]["spec"]
    assert spec["legs"][0]["hub"] == "THE" and spec["cost"] == {"from_hub": "TTF", "to_hub": "THE"}


def test_a_route_without_tariffs_is_named_not_priced(holdings):
    rows = _month_ahead("TTF", 30.0) + _month_ahead("PEG", 29.0)
    month = locational_rows(_holdings(rows, []), ["PEG"])[0]["tenors"][0]
    assert month["direction"] == "PEG → TTF"
    assert month["net"] is None and month["route"]["complete"] is False
    assert month["route"]["missing"]


def test_time_spreads_and_the_storage_carry(holdings):
    """TTF curve: winter months 33.xx, summer 30.xx. Win − Sum ≈ +3.0; with a carry held
    (capacity fee 2.00, fuel 1 % of the summer price, financing 4 %/yr for six months) the
    carry is 2.00 + 0.30xx + 0.60xx and the net is Win − Sum minus it."""

    hub = time_rows(holdings, "TTF", None)
    by_key = {row["key"]: row for row in hub["rows"]}
    assert by_key["da_ma"]["available"] is False
    # Said as a code with its parameters, so the client says it in the reader's language.
    assert by_key["da_ma"]["reasons"] == [{"code": "no_da_or_ma", "params": {}}]
    assert by_key["m1_m2"]["available"] and by_key["m1_m2"]["spec"]["kind"] == "history"
    season = by_key["win_sum"]
    assert season["available"] and season["value"] == pytest.approx(3.0, abs=0.1)
    assert season["carry"]["total"] is None  # nothing in the assumption set
    assert season["carry"]["reasons"][0]["code"] == "no_carry"
    carry = {"storage.capacity_fee": 2.0, "storage.fuel": 1.0, "financing.rate": 4.0}
    held = {row["key"]: row for row in time_rows(holdings, "TTF", carry)["rows"]}["win_sum"]
    summer = held["far"]
    assert held["carry"]["total"] == pytest.approx(2.0 + 0.01 * summer + 0.04 * 0.5 * summer)
    assert held["net_of_carry"] == pytest.approx(held["value"] - held["carry"]["total"])
    assert carry_cost({}, 30.0)["total"] is None


def test_the_board_lists_focus_hubs_first_and_says_simulated(holdings):
    data = board(holdings, ["THE"], carry=None, cross=[{"key": "clean_spark", "available": False}])
    assert data["hubs"][0] == "THE" and data["reference"] == "TTF"
    assert [row["hub"] for row in data["locational"]] == ["THE"]
    assert data["simulated"] is False
    assert data["cross"][0]["key"] == "clean_spark"


def test_net_of_transport_is_priced_to_the_last_published_gas_year():
    """Tariffs in force to 30 Sep 2027: Dec-26 .. Sep-27 net of transport, Oct-27 on gross only;
    the result says "priced to Sep-27" and takes its class from the priced months."""

    rows = _curve("TTF", 14) + [
        {**row, "hub": "THE", "price": row["price"] + 0.5} for row in _curve("TTF", 14)
    ]
    until = datetime(2027, 9, 30, tzinfo=UTC)
    data = _holdings(rows, _crossing_tariffs("TTF", "THE", until=until))
    spec = spec_from_dict(
        {
            "kind": "curve",
            "legs": [{"hub": "THE", "weight": 1}, {"hub": "TTF", "weight": -1}],
            "unit": "EUR/MWh",
            "fx": "forward",
            "cost": {"from_hub": "TTF", "to_hub": "THE"},
        }
    )
    result = evaluate_curve(spec, data)
    assert result["coverage"] == {
        "priced_to": "Sep-27",
        "unpriced_from": "Oct-27",
        "months_priced": 10,
        "reason": "tariff not published",
    }
    assert result["input_class"] != "missing"


def test_nbp_time_spreads_in_pence_per_therm_and_identical_demo_years_are_not_a_finding():
    """NBP's time spreads in its own quotation (p/th, the shared unit rule), the EUR/MWh value
    for hover; two simulated calendar years of the same shape are "not informative"."""

    rows = []
    first = (TODAY.replace(day=1) + timedelta(days=32)).replace(day=1)
    for index in range(40):
        year, month = divmod(first.month - 1 + index, 12)
        start = date(first.year + year, month + 1, 1)
        price = 34.0 if start.month in (10, 11, 12, 1, 2, 3) else 30.0  # repeats every year
        row = _row("NBP", f"{start:%Y-%m}", price, "GBP/MWh", simulated=True)
        row["price_mwh"], row["unit_mwh"] = price, "GBP/MWh"
        rows.append(row)
    hub = time_rows(_holdings(rows, []), "NBP", None)
    assert hub["unit"] == "GBP/MWh" and hub["native_unit"] in {"GBp/th", "p/th"}
    season = next(row for row in hub["rows"] if row["key"] == "win_sum")
    # 4.00 GBP/MWh = 4.00 x 100 / 34.1214 = 11.72 p/th.
    assert season["native_value"] == pytest.approx(4.0 * 100 / 34.1214163, abs=1e-3)
    assert season["reporting_value"] == pytest.approx(4.0 / 0.87, rel=0.02)
    cal = next(row for row in hub["rows"] if row["key"].startswith("cal"))
    assert cal["available"] is False and cal["uninformative"] is True


def test_a_pair_without_closes_gives_its_reason_as_a_code(holdings):
    rows = _month_ahead("TTF", 30.0)
    month = locational_rows(_holdings(rows, []), ["PEG"])[0]["tenors"][0]
    assert month["available"] is False
    assert month["reasons"] == [
        {"code": "no_close_both", "params": {"tenor": "MA", "hub": "PEG", "reference": "TTF"}}
    ]


def test_the_prompt_day_ahead_is_the_next_working_day_as_the_tick_intake_stores_it():
    from datetime import date

    from eurogas_nexus.application.prompt_market import prompt_days
    from eurogas_nexus.domain.market.products import resolve_product

    friday, monday = date(2026, 11, 20), date(2026, 11, 23)
    assert prompt_days(friday) == {"within_day": friday, "day_ahead": monday}
    assert prompt_days(monday)["day_ahead"] == date(2026, 11, 24)
    assert prompt_days(friday)["day_ahead"] == resolve_product("DA", friday).first_gas_day


def test_named_pairs_replace_the_hubs_against_ttf(holdings):
    """Desk → Board asks for the desk's pairs (TTF–THE here, THE as the reference) and a time
    row for each of its hubs, held or not."""

    pairs = [("TTF", "THE"), ("PVB", "TTF")]
    data = board(holdings, ["TTF", "THE", "PVB"], carry=None, pairs=pairs)
    assert [row["pair"] for row in data["locational"]] == ["TTF–THE", "PVB–TTF"]
    month = data["locational"][0]["tenors"][0]
    assert month["available"]
    assert month["gross"] == pytest.approx(30.01 - 30.51)  # TTF − THE: the sign follows the pair
    assert month["direction"] == "TTF → THE"
    assert [leg["hub"] for leg in month["legs"]] == ["TTF", "THE"]
    missing = data["locational"][1]["tenors"][0]
    assert not missing["available"] and missing["reasons"][0]["code"] == "no_close_both"
    assert [row["hub"] for row in data["time"]] == ["TTF", "THE", "PVB"]
    # Without pairs the board is as before: each hub against TTF.
    assert [row["pair"] for row in board(holdings, [], carry=None)["locational"]] == ["THE–TTF"]


def test_the_board_reads_named_pairs_from_its_address():
    from fastapi import HTTPException

    from eurogas_nexus.api.routes.public.spreads import _pairs

    assert _pairs(None) is None and _pairs("") is None
    assert _pairs("ttf-nbp, ZTP–NBP,PVB-TTF") == [("TTF", "NBP"), ("ZTP", "NBP"), ("PVB", "TTF")]
    with pytest.raises(HTTPException):
        _pairs("not a pair")
