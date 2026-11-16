"""Report charts and rule commentary: well-formed SVG, tables equal to the series, rule text."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from eurogas_nexus.application.reports import commentary as rules
from eurogas_nexus.application.reports.charts import (
    chart_table,
    nice_ticks,
    render_chart,
    sparkline,
)

SVG = "{http://www.w3.org/2000/svg}"

LINE = {
    "type": "line", "title": "TTF front month", "unit": "EUR/MWh",
    "series": [
        {"name": "TTF", "points": [["2026-11-02", 31.4], ["2026-11-03", 31.75],
                                   ["2026-11-04", None], ["2026-11-05", 30.9]]},
        {"name": "THE", "points": [["2026-11-02", 32.1], ["2026-11-03", 32.6]]},
    ],
    "reference_lines": [{"label": "target", "value": 33.0}],
}
STACKED = {
    "type": "stacked_bar", "title": "Balance", "unit": "GWh/d",
    "series": [
        {"name": "Norway", "points": [["2026-11-01", 950.0], ["2026-11-02", 960.0]]},
        {"name": "Storage", "points": [["2026-11-01", -120.0], ["2026-11-02", 80.0]]},
    ],
}
SANKEY = {
    "type": "sankey", "title": "Sources and uses", "unit": "GWh/d",
    "nodes": [{"id": "n", "label": "Norway", "side": "source"},
              {"id": "l", "label": "LNG", "side": "source"},
              {"id": "d", "label": "Demand", "side": "use"},
              {"id": "i", "label": "Injection", "side": "use"}],
    "links": [{"source": "n", "target": "d", "value": 800.0},
              {"source": "n", "target": "i", "value": 100.0},
              {"source": "l", "target": "d", "value": 300.0}],
}
BAR = {"type": "bar", "title": "Outages", "unit": "GWh/d",
       "series": [{"name": "Unavailable", "points": [["Troll (NO)", 563.0],
                                                     ["Kollsnes (NO)", 120.5]]}]}


@pytest.mark.parametrize("spec", [LINE, {**LINE, "type": "step"}, STACKED,
                                  {**STACKED, "type": "stacked_area"}, SANKEY, BAR])
def test_every_chart_is_well_formed_accessible_svg(spec):
    svg = render_chart(spec, "c1")
    root = ET.fromstring(svg)  # raises on malformed XML
    assert root.tag == f"{SVG}svg"
    assert root.get("role") == "img"
    labelled = root.get("aria-labelledby").split()
    ids = {el.get("id") for el in root.iter() if el.get("id")}
    assert set(labelled) <= ids
    assert root.find(f"{SVG}title").text == spec["title"]
    # Nothing is fetched: no external reference anywhere in the drawing.
    assert not re.search(r"(href|src)\s*=", svg)
    assert "http" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")


def test_a_line_chart_breaks_at_a_missing_value_and_series_differ_in_dash():
    svg = render_chart(LINE, "c1")
    root = ET.fromstring(svg)
    polylines = list(root.iter(f"{SVG}polyline"))
    # TTF has a gap: two segments (two points, then one point drawn as a dot); THE one line.
    assert len(polylines) == 2
    dashes = {p.get("stroke-dasharray") for p in polylines}
    assert len(dashes) == 2  # greyscale-safe: the series do not rely on colour alone
    assert list(root.iter(f"{SVG}circle"))  # the lone point after the gap


@pytest.mark.parametrize("spec", [LINE, STACKED, SANKEY, BAR])
def test_the_data_table_holds_exactly_the_series_values(spec):
    header, rows = chart_table(spec)
    if spec["type"] == "sankey":
        assert header[-1] == "Flow (GWh/d)"
        got = {(r[0], r[1]): float(r[2].replace(",", "")) for r in rows}
        labels = {n["id"]: n["label"] for n in spec["nodes"]}
        assert got == {(labels[link["source"]], labels[link["target"]]): link["value"]
                       for link in spec["links"]}
        return
    if spec["type"] == "bar":
        assert [(r[0], float(r[1])) for r in rows] == [
            (label, value) for label, value in spec["series"][0]["points"]]
        return
    assert header[0] == "Day"
    for column, series in enumerate(spec["series"], start=1):
        expected = {x: y for x, y in series["points"]}
        for row in rows:
            cell = row[column]
            if row[0] not in expected:
                assert cell == ""
            elif expected[row[0]] is None:
                assert cell == "n/a"
            else:
                assert float(cell.replace(",", "")) == pytest.approx(expected[row[0]], abs=0.006)


def test_hover_values_are_native_tooltips():
    svg = render_chart(LINE, "c1")
    root = ET.fromstring(svg)
    titles = [t.text for t in root.iter(f"{SVG}title")]
    assert any("TTF: 31.75" in (t or "") for t in titles)


def test_ticks_cover_the_range():
    ticks = nice_ticks(28.3, 33.9)
    assert ticks[0] <= 28.3 and ticks[-1] >= 33.9
    assert sparkline([1.0, None, 2.0, 3.0], label="x").startswith("<svg")


# --------------------------------------------------------------------- rule commentary


def _price(**kw):
    row = {"hub": "TTF", "product": "Dec-26", "close": 31.4, "unit": "EUR/MWh",
           "day_change": -0.35, "period_change": None, "high": None, "low": None,
           "year_ago": None, "close_day": "2026-11-13", "simulated": False, "state": "current"}
    row.update(kw)
    return row


def test_price_headline_states_level_unit_and_direction():
    text = rules.prices([_price()], period_label=None)
    assert text["headline"] == "TTF Dec-26 31.40 EUR/MWh, down 0.35 EUR/MWh on the day."
    assert text["bullets"] == []


def test_a_simulated_price_says_so_next_to_the_value():
    text = rules.prices([_price(simulated=True)], period_label=None)
    assert "31.40 EUR/MWh (simulated)" in text["headline"]


def test_weekly_prices_use_the_period_change_range_and_name_stale_closes():
    rows = [_price(period_change=1.2, high=32.0, low=30.1, state="stale"),
            _price(hub="NBP", unit="GBp/th", close=84.5, period_change=-2.5, state="late")]
    text = rules.prices(rows, period_label="the week")
    assert "up 1.20 EUR/MWh over the week" in text["headline"]
    assert any("largest move was NBP, down 2.50 GBp/th" in b for b in text["bullets"])
    assert any("between 30.10 EUR/MWh and 32.00 EUR/MWh" in b for b in text["bullets"])
    assert len(text["bullets"]) <= 3


def test_storage_compares_with_a_year_earlier_in_points():
    text = rules.storage({"fill": 82.4, "day": "2026-11-13", "year_ago": 94.1,
                          "simulated": False, "state": "current", "period_change": -1.6,
                          "target": 90.0, "target_window": "10-01 and 12-01 (month-day)",
                          "inventory_twh": 700.0})
    assert text["headline"].startswith("NW Europe storage was 82.4% full on 13 Nov, 11.7 "
                                       "points below the same day a year earlier (94.1%)")
    assert text["bullets"][0] == "Fill fell 1.6 points over the last seven days."


def test_balance_labels_the_forecast_as_a_forecast():
    text = rules.balance({"call": 1500.0, "day": "2026-11-13", "norway": 1000.0, "lng": 300.0,
                          "storage": 200.0, "simulated": False, "forecast_call": 1600.0,
                          "forecast_day": "2026-11-20", "forecast_method": "HDD regression",
                          "forecast_fill": 78.2})
    assert text["bullets"][0].startswith("Forecast, not a measurement: 1,600 GWh/d")
    assert "HDD regression" in text["bullets"][0]


def test_outages_without_any_message_say_so():
    text = rules.outages({"active": 0, "total": 0, "horizon_days": 14})
    assert text["headline"] == "No active or upcoming outage is reported for the scope."


def test_no_rule_text_gives_advice():
    advice = re.compile(r"\b(buy|sell|hedge|nominate|recommend|should)\b", re.I)
    samples = [
        rules.prices([_price()], period_label="the week"),
        rules.outages({"active": 2, "total": 3, "horizon_days": 14, "active_gwh": 600.0,
                       "largest": {"facility": "Troll", "zone": "NO", "gwh": 500.0,
                                   "end": None}, "norway_active": 2, "norway_gwh": 600.0}),
        rules.position({"hubs": [{"hub": "NBP", "today": 28000.0, "front_month": -5000.0}],
                        "front_month": "Dec-26"}),
    ]
    for text in samples:
        assert not advice.search(" ".join([text["headline"], *text["bullets"]]))


def test_lng_states_its_side_of_the_average_and_outages_say_when_norway_is_clear():
    text = rules.lng({"latest": 2851.0, "latest_day": "2026-11-12", "avg_7": 2764.0,
                      "simulated": False, "left_out": [], "by_country": [("FR", 910.0)]})
    assert "above the seven-day average of 2,764 GWh/d" in text["headline"]
    clear = rules.outages({"active": 1, "total": 1, "horizon_days": 14, "active_gwh": 96.7,
                           "largest": None, "norway_active": 0, "norway_gwh": 0.0})
    assert "No active outage in Norway is among the messages held." in clear["bullets"]
