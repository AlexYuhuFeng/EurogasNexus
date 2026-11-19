"""How much of the network the tariff register can price: the coverage table.

For every crossing of the market-area graph (``domain/route_cost/market_area_graph.py``), in
each direction, the legs a route must price (exit from the first market area, any pipeline
charge, entry to the next) are read exactly as route pricing reads them
(``application/route_tariff_cost.price_leg``): a leg is **held** when a register row of the
stated product and firmness is in force on the day and its unit can be read per MWh, else
**missing** ("nothing held at point" when the register holds no row of the product at any
of the crossing's points). Each held leg states its source and data class (``sourced`` for a final
publication, ``indicative``, ``simulated``); a crossing is priced only when every leg is held.

Two further tables cover what the graph does not join yet:

- **corridors** (``reference_data/tariff_scope.CORRIDOR_POINTS``: CEGH, CZ, PSV, PVB, Swiss
  transit): per point and direction, whether the register holds an exit row filed under the
  first market area and an entry row filed under the second (ENTSOG's balancing-zone labels,
  ``market_area``);
- **supply entry** (LNG terminals, Norwegian landing points): whether an entry row is held.

Nothing here prices a route; it says which legs a route would find, so a gap is named before a
trader meets it.

本模块计算费率登记表对市场区域图每个跨境点、每个方向的覆盖情况（出口、管道、入口各段是否
持有、来源与数据类别），以及图外走廊与供应入口的覆盖。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.application.route_tariff_cost import price_leg, weakest

#: ENTSOG balancing-zone labels (``fromBZ``/``toBZ``, stored as ``market_area``) -> market code.
BZ_LABELS: dict[str, str] = {
    "Netherlands": "TTF",
    "DE THE BZ": "THE",
    "BeLux": "ZTP",
    "TRF": "PEG",
    "UK": "NBP",
    "IUK": "IUK",
    "Joint Bal Zone DK/SE": "ETF",
    "Ireland": "IBP",
    "Austria": "CEGH",
    "Czech": "CZ",
    "Italy": "PSV",
    "Spain": "PVB",
    "Switzerland": "CH",
}


def gas_year_start(on: date) -> date:
    """First gas day of the gas year containing ``on``."""

    return date(on.year if on.month >= 10 else on.year - 1, 10, 1)


def leg_source(leg: Any) -> str | None:
    """Where a held leg's tariff came from, in desk words."""

    if leg.value is None:
        return None
    tariff_id = str(leg.tariff_id or "")
    if (leg.status or "").upper() == "SIMULATOR_ONLY":
        return "simulated (demo)"
    if tariff_id.startswith("entsog-"):
        return "ENTSOG TP"
    if tariff_id.startswith("entry-"):
        # A reviewed entry carries the operator's status; a candidate is filed indicative
        # with "awaiting review" in its source.
        if "awaiting review" in str(leg.source or ""):
            return "public tariff, awaiting review"
        return "reviewed public tariff"
    return "register (administrator)"


def can_be_entered(leg: Any) -> bool:
    """A missing leg an administrator can enter: the reference network names its operator."""

    return leg.value is None and bool(leg.tso) and leg.tso != "unknown TSO"


def graph_coverage(
    graph: Any,
    rows: Iterable[Mapping[str, Any]],
    *,
    on: date,
    product: str = "ANNUAL",
    firmness: str = "FIRM",
) -> list[dict[str, Any]]:
    """One entry per crossing of the graph and direction, with its legs held or missing."""

    rows = list(rows)
    moment = datetime(on.year, on.month, on.day, tzinfo=UTC)
    published_points = {
        str(row.get("point_id"))
        for row in rows
        if str(row.get("capacity_product") or product).upper() == product.upper()
        and _in_force(row, moment)
    }
    out: list[dict[str, Any]] = []
    hubs = sorted(graph.hub_names)
    for start in hubs:
        for target in sorted(graph.neighbours(start)):
            for crossing in graph.crossings(start, target):
                legs = [
                    price_leg(spec, rows, on, product=product, firmness=firmness)
                    for spec in graph.legs(crossing)
                ]
                held = all(leg.value is not None for leg in legs)
                silent = not any(point in published_points for point in crossing.points)
                out.append(
                    {
                        "from": graph.hub_names.get(start, start),
                        "to": graph.hub_names.get(target, target),
                        "points": list(crossing.points),
                        "via": " / ".join(
                            str(graph.points.get(point, {}).get("name") or point)
                            for point in crossing.points
                        ),
                        "representative": crossing.points[0] in graph.representative,
                        # No register row of the product in force at any of the crossing's
                        # points (with ENTSOG read: capacity is sold at a virtual point or
                        # the operator publishes nothing there).
                        "status": "priced"
                        if held
                        else ("nothing held at point" if silent else "missing"),
                        "class": weakest(leg.input_class for leg in legs),
                        "can_be_entered": _crossing_enterable(legs),
                        "legs": [
                            {
                                "role": leg.role,
                                "point": leg.point_key,
                                "point_name": leg.point_name,
                                "tso": leg.tso,
                                "direction": leg.direction,
                                "held": leg.value is not None,
                                "class": leg.input_class,
                                "source": leg_source(leg),
                                "gas_year": leg.gas_year,
                                "status": leg.status,
                                "can_be_entered": can_be_entered(leg),
                            }
                            for leg in legs
                        ],
                    }
                )
    return out


def _crossing_enterable(legs: list[Any]) -> str:
    """ "-" when priced, "yes" when every missing leg names its operator, else "no"."""

    missing = [leg for leg in legs if leg.value is None]
    if not missing:
        return "-"
    return "yes" if all(can_be_entered(leg) for leg in missing) else "no (no operator named)"


def _in_force(row: Mapping[str, Any], moment: datetime) -> bool:
    def aware(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        return datetime(value.year, value.month, value.day, tzinfo=UTC)

    start, end = aware(row.get("effective_from")), aware(row.get("effective_to"))
    return (start is None or start <= moment) and (end is None or end >= moment)


def _matching(
    rows: list[Mapping[str, Any]],
    point: str,
    direction: str,
    area: str | None,
    moment: datetime,
    product: str,
    firmness: str,
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if row.get("point_id") == point
        and str(row.get("direction") or "").upper() == direction
        and str(row.get("capacity_product") or product).upper() == product
        and str(row.get("firmness") or firmness).upper() == firmness
        and (area is None or BZ_LABELS.get(str(row.get("market_area") or "")) == area)
        and _in_force(row, moment)
    ]


def _row_class(rows: list[Mapping[str, Any]]) -> str:
    if not rows:
        return "missing"
    statuses = {str(row.get("tariff_status") or "").upper() for row in rows}
    if "FINAL" in statuses:
        return "sourced"
    if statuses <= {"SIMULATOR_ONLY"}:
        return "simulated"
    return "indicative"


def corridor_coverage(
    rows: Iterable[Mapping[str, Any]],
    *,
    on: date,
    product: str = "ANNUAL",
    firmness: str = "FIRM",
    points: Mapping[str, tuple[str, tuple[str, ...]]] | None = None,
) -> list[dict[str, Any]]:
    """Corridor points outside the graph: exit and entry held, per direction."""

    from eurogas_nexus.reference_data.tariff_scope import CORRIDOR_POINTS

    rows = list(rows)
    moment = datetime(on.year, on.month, on.day, tzinfo=UTC)
    out = []
    for point, (label, areas) in sorted((points or CORRIDOR_POINTS).items()):
        if len(areas) != 2:
            continue
        for start, target in (areas, areas[::-1]):
            exit_rows = _matching(rows, point, "EXIT", start, moment, product, firmness)
            entry_rows = _matching(rows, point, "ENTRY", target, moment, product, firmness)
            out.append(
                {
                    "from": start,
                    "to": target,
                    "points": [point],
                    "via": label,
                    "exit": _row_class(exit_rows),
                    "entry": _row_class(entry_rows),
                    "status": "priced" if exit_rows and entry_rows else "missing",
                    "class": weakest([_row_class(exit_rows), _row_class(entry_rows)]),
                    "in_graph": False,
                }
            )
    return out


def supply_coverage(
    rows: Iterable[Mapping[str, Any]],
    *,
    on: date,
    product: str = "ANNUAL",
    firmness: str = "FIRM",
) -> list[dict[str, Any]]:
    """LNG terminal and Norwegian landing points: entry into the market area held or not."""

    from eurogas_nexus.reference_data.tariff_scope import LNG_ENTRY_POINTS, NORWAY_LANDING_POINTS

    rows = list(rows)
    moment = datetime(on.year, on.month, on.day, tzinfo=UTC)
    named = _points_with_operators()
    out = []
    for kind, table in (("LNG", LNG_ENTRY_POINTS), ("Norway", NORWAY_LANDING_POINTS)):
        for point, (label, areas) in sorted(table.items()):
            entry_rows = _matching(rows, point, "ENTRY", None, moment, product, firmness)
            out.append(
                {
                    "kind": kind,
                    "point": point,
                    "via": label,
                    "into": list(areas),
                    "entry": _row_class(entry_rows),
                    "tso": sorted({str(row.get("tso")) for row in entry_rows}),
                    "status": "held" if entry_rows else "missing",
                    # Enterable when the reference network names an operator at the point.
                    "can_be_entered": not entry_rows and point in named,
                }
            )
    return out


def _points_with_operators() -> set[str]:
    from eurogas_nexus.reference_data.network_bundle import load_bundle

    bundle = load_bundle()
    points = {
        str(row.get("point_key"))
        for row in bundle.get("access") or []
        if "-TSO-" in str(row.get("operator_key") or "")
    }
    points |= {
        str(node["point_key"])
        for node in bundle.get("nodes") or []
        if any("-TSO-" in str(op) for op in node.get("operators") or [])
    }
    return points


def coverage_report(
    graph: Any,
    rows: Iterable[Mapping[str, Any]],
    *,
    today: date,
    product: str = "ANNUAL",
    firmness: str = "FIRM",
) -> dict[str, Any]:
    """The coverage tables for the current gas year (as of ``today``) and the next."""

    rows = list(rows)
    current = max(today, gas_year_start(today))
    following = date(gas_year_start(today).year + 1, 10, 1)
    report: dict[str, Any] = {"product": product, "firmness": firmness, "years": {}}
    for label, on in (("current", current), ("next", following)):
        graph_rows = graph_coverage(graph, rows, on=on, product=product, firmness=firmness)
        corridors = corridor_coverage(rows, on=on, product=product, firmness=firmness)
        supply = supply_coverage(rows, on=on, product=product, firmness=firmness)
        report["years"][label] = {
            "on": on.isoformat(),
            "gas_year": f"{gas_year_start(on).year}/{(gas_year_start(on).year + 1) % 100:02d}",
            "graph": graph_rows,
            "corridors": corridors,
            "supply": supply,
            "summary": {
                "graph_crossings": len(graph_rows),
                "graph_priced": sum(1 for row in graph_rows if row["status"] == "priced"),
                "graph_none_published": sum(
                    1 for row in graph_rows if row["status"] == "nothing held at point"
                ),
                "graph_drawn": sum(1 for row in graph_rows if row["representative"]),
                "graph_drawn_priced": sum(
                    1 for row in graph_rows if row["representative"] and row["status"] == "priced"
                ),
                "corridor_crossings": len(corridors),
                "corridor_priced": sum(1 for row in corridors if row["status"] == "priced"),
                "supply_points": len(supply),
                "supply_held": sum(1 for row in supply if row["status"] == "held"),
            },
        }
    return report


def _yes_no(row: Mapping[str, Any]) -> str:
    if row["status"] == "held":
        return "-"
    return "yes" if row["can_be_entered"] else "no (point not in the reference network)"


def _leg_cell(leg: Mapping[str, Any]) -> str:
    if not leg["held"]:
        return f"{leg['direction'].lower()} {leg['point']} {leg['tso']}: MISSING"
    return f"{leg['direction'].lower()} {leg['point']} {leg['tso']}: {leg['class']}"


def render_markdown(report: Mapping[str, Any]) -> str:
    """The report as Markdown tables (graph, corridors, supply) per gas year."""

    lines: list[str] = []
    for label, year in report["years"].items():
        summary = year["summary"]
        lines.append(
            f"## {label} gas year {year['gas_year']} (on {year['on']}), "
            f"{report['firmness'].lower()} {report['product'].lower()}"
        )
        lines.append(
            f"graph {summary['graph_priced']}/{summary['graph_crossings']} crossings priced "
            f"({summary['graph_none_published']} at points where the register holds no tariff, "
            f"{summary['graph_drawn_priced']}/{summary['graph_drawn']} drawn crossings priced); "
            f"corridors {summary['corridor_priced']}/{summary['corridor_crossings']}; "
            f"supply entry {summary['supply_held']}/{summary['supply_points']} held"
        )
        lines.append("")
        lines.append(
            "| Edge | Direction | Via | Held/missing | Source | Class | Can be entered | Legs |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for row in year["graph"]:
            sources = sorted({leg["source"] for leg in row["legs"] if leg["source"]})
            lines.append(
                f"| {'-'.join(sorted((row['from'], row['to'])))} | {row['from']} → {row['to']} "
                f"| {row['via']}{' (drawn)' if row['representative'] else ''} "
                f"| {row['status']} | {', '.join(sources) or '-'} | {row['class']} "
                f"| {row['can_be_entered']} "
                f"| {'; '.join(_leg_cell(leg) for leg in row['legs'])} |"
            )
        lines.append("")
        lines.append(
            "| Corridor (not in graph) | Direction | Via | Exit | Entry | Held/missing "
            "| Can be entered |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for row in year["corridors"]:
            lines.append(
                f"| {'-'.join(sorted((row['from'], row['to'])))} | {row['from']} → {row['to']} "
                f"| {row['via']} ({row['points'][0]}) | {row['exit']} | {row['entry']} "
                f"| {row['status']} | {'-' if row['status'] == 'priced' else 'yes'} |"
            )
        lines.append("")
        lines.append("| Supply entry | Point | Into | Entry | TSO | Can be entered |")
        lines.append("|---|---|---|---|---|---|")
        for row in year["supply"]:
            lines.append(
                f"| {row['kind']} | {row['via']} ({row['point']}) | {', '.join(row['into'])} "
                f"| {row['entry']} | {', '.join(row['tso']) or '-'} "
                f"| {_yes_no(row)} |"
            )
        lines.append("")
    return "\n".join(lines)
