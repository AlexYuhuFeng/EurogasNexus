"""The coverage table: which crossings of the graph the tariff register can price.

Register rows are made up; the graph is the shipped reference bundle's.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.application.tariff_coverage import (
    corridor_coverage,
    coverage_report,
    graph_coverage,
    render_markdown,
    supply_coverage,
)
from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

ON = date(2026, 11, 19)


def row(
    point,
    tso,
    direction,
    *,
    market_area="",
    status="FINAL",
    unit="EUR/(kWh/h)/y",
    start=date(2026, 1, 1),
    end=date(2026, 12, 31),
    tariff_id=None,
    product="ANNUAL",
    currency="EUR",
):
    return {
        "tariff_id": tariff_id or f"entsog-{tso}-{point}-{direction}".lower(),
        "tso": tso,
        "point_id": point,
        "direction": direction,
        "gas_year": "2026",
        "tariff_value": 1.0,
        "currency": currency,
        "unit": unit,
        "effective_from": datetime.combine(start, datetime.min.time(), tzinfo=UTC),
        "effective_to": datetime.combine(end, datetime.min.time(), tzinfo=UTC),
        "tariff_status": status,
        "source_table": "fixture",
        "capacity_product": product,
        "firmness": "FIRM",
        "market_area": market_area,
    }


@pytest.fixture(scope="module")
def graph():
    return shipped_market_area_graph()


def by_crossing(entries, start, target, point):
    return next(
        entry
        for entry in entries
        if entry["from"] == start and entry["to"] == target and entry["points"][0] == point
    )


def test_a_crossing_is_priced_only_when_each_leg_is_held_in_its_direction(graph):
    rows = [
        row("ITP-10012", "GTS", "EXIT"),
        row("ITP-10012", "Gasunie Deutschland", "ENTRY", status="INDICATIVE"),
    ]
    entries = graph_coverage(graph, rows, on=ON)
    ttf_the = by_crossing(entries, "TTF", "THE", "ITP-10012")
    assert ttf_the["status"] == "priced" and ttf_the["class"] == "indicative"
    assert ttf_the["representative"] is True
    assert [leg["source"] for leg in ttf_the["legs"]] == ["ENTSOG TP", "ENTSOG TP"]
    # The other direction needs the THE exit and the TTF entry: neither is held.
    the_ttf = by_crossing(entries, "THE", "TTF", "ITP-10012")
    assert the_ttf["status"] == "missing" and the_ttf["class"] == "missing"
    assert [leg["held"] for leg in the_ttf["legs"]] == [False, False]
    # Every crossing of the graph is listed in both directions.
    assert len(entries) == 2 * len(
        {(e["from"], e["to"], tuple(e["points"])) for e in entries if e["from"] < e["to"]}
    )


def test_a_crossing_where_no_tariff_is_published_is_named_so(graph):
    entries = graph_coverage(graph, [row("ITP-10012", "GTS", "EXIT")], on=ON)
    bocholtz = by_crossing(entries, "TTF", "THE", "ITP-00169")
    assert bocholtz["status"] == "nothing held at point"


def test_a_pipeline_crossing_has_three_legs_and_simulated_rows_say_so(graph):
    rows = [
        row(
            "ITP-00063",
            "GTS",
            "EXIT",
            unit="EUR/MWh",
            status="SIMULATOR_ONLY",
            tariff_id="demo-sim-gts",
        ),
        row("ITP-00207", "BBL company", "EXIT"),
        row(
            "ITP-00207",
            "National Gas TSO",
            "ENTRY",
            unit="p/kWh/d",
            tariff_id="admin-ng",
            currency="GBP",
        ),
    ]
    ttf_nbp = by_crossing(graph_coverage(graph, rows, on=ON), "TTF", "NBP", "ITP-00063")
    assert [leg["role"] for leg in ttf_nbp["legs"]] == [
        "market_area_exit",
        "pipeline",
        "market_area_entry",
    ]
    assert ttf_nbp["status"] == "priced" and ttf_nbp["class"] == "simulated"
    assert [leg["source"] for leg in ttf_nbp["legs"]] == [
        "simulated (demo)",
        "ENTSOG TP",
        "register (administrator)",
    ]


def test_a_row_out_of_force_or_of_another_product_is_not_held(graph):
    rows = [
        row("ITP-10012", "GTS", "EXIT", start=date(2025, 1, 1), end=date(2025, 12, 31)),
        row("ITP-10012", "Gasunie Deutschland", "ENTRY", product="MONTHLY"),
    ]
    ttf_the = by_crossing(graph_coverage(graph, rows, on=ON), "TTF", "THE", "ITP-10012")
    assert ttf_the["status"] in {"missing", "nothing held at point"}


def test_corridors_outside_the_graph_by_balancing_zone():
    points = {"ITP-00040": ("Tarvisio (IT) / Arnoldstein (AT)", ("CEGH", "PSV"))}
    rows = [
        row("ITP-00040", "Gas Connect Austria", "EXIT", market_area="Austria"),
        row("ITP-00040", "Snam Rete Gas", "ENTRY", market_area="Italy"),
    ]
    entries = {(e["from"], e["to"]): e for e in corridor_coverage(rows, on=ON, points=points)}
    assert entries[("CEGH", "PSV")]["status"] == "priced"
    assert entries[("PSV", "CEGH")]["status"] == "missing"
    assert entries[("PSV", "CEGH")]["exit"] == "missing"


def test_supply_entry_points():
    rows = [row("LNG-00060", "Gasunie Deutschland", "ENTRY")]
    entries = {e["point"]: e for e in supply_coverage(rows, on=ON)}
    assert entries["LNG-00060"]["status"] == "held"
    assert entries["LNG-00060"]["tso"] == ["Gasunie Deutschland"]
    assert entries["LNG-00027"]["status"] == "missing"


def test_the_report_covers_the_current_and_next_gas_year_and_renders(graph):
    rows = [row("ITP-10012", "GTS", "EXIT"), row("ITP-10012", "Gasunie Deutschland", "ENTRY")]
    report = coverage_report(graph, rows, today=ON)
    current, following = report["years"]["current"], report["years"]["next"]
    assert (current["gas_year"], current["on"]) == ("2026/27", "2026-11-19")
    assert (following["gas_year"], following["on"]) == ("2027/28", "2027-10-01")
    assert current["summary"]["graph_priced"] >= 1
    assert following["summary"]["graph_priced"] == 0  # the 2026 rows end in December
    text = render_markdown(report)
    assert (
        "| Edge | Direction | Via | Held/missing | Source | Class | Can be entered | Legs |" in text
    )
    assert "TTF → THE" in text and "VIP TTF-THE-H (drawn)" in text


def test_a_missing_leg_can_be_entered_when_the_network_names_its_operator(graph):
    entries = graph_coverage(graph, [], on=ON)
    ttf_the = by_crossing(entries, "TTF", "THE", "ITP-10012")
    assert ttf_the["can_be_entered"] == "yes"
    assert all(leg["can_be_entered"] for leg in ttf_the["legs"])
    # VIP France - Germany: ENTSOG names no operator on the PEG side.
    the_peg = by_crossing(entries, "THE", "PEG", "ITP-00540")
    assert the_peg["can_be_entered"] == "no (no operator named)"
    assert [leg["can_be_entered"] for leg in the_peg["legs"]] == [True, False]
    held = graph_coverage(
        graph,
        [row("ITP-10012", "GTS", "EXIT"), row("ITP-10012", "Gasunie Deutschland", "ENTRY")],
        on=ON,
    )
    assert by_crossing(held, "TTF", "THE", "ITP-10012")["can_be_entered"] == "-"


def test_reviewed_and_awaiting_entries_say_where_they_come_from(graph):
    rows = [
        {
            **row("ITP-10012", "GTS", "EXIT", tariff_id="entry-tte-1"),
            "source_table": "Reviewed public tariff, entered by an administrator",
        },
        {
            **row(
                "ITP-10012",
                "Gasunie Deutschland",
                "ENTRY",
                tariff_id="entry-tte-2",
                status="INDICATIVE",
            ),
            "source_table": "Public tariff entered by an administrator, awaiting review",
        },
    ]
    ttf_the = by_crossing(graph_coverage(graph, rows, on=ON), "TTF", "THE", "ITP-10012")
    assert [leg["source"] for leg in ttf_the["legs"]] == [
        "reviewed public tariff",
        "public tariff, awaiting review",
    ]
    assert ttf_the["class"] == "indicative"


def test_supply_entry_outside_the_reference_network_cannot_be_entered():
    entries = {e["point"]: e for e in supply_coverage([], on=ON)}
    assert entries["LNG-00027"]["can_be_entered"] is True  # Gate, GTS in the network
    assert entries["LNG-00012"]["can_be_entered"] is False  # Barcelona, outside NWE
