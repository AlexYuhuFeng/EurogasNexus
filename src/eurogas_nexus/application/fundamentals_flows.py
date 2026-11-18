"""The flows fundamentals read: Norwegian and UK pipeline gas landed, by landing (CP-17).

``GET /api/fundamentals/flows`` (design basis 2, D.2 "Flows"). One deterministic read of the
ENTSOG physical flows at the landing registry's points (``application/pipeline_supply``:
one operator per point and gas day, closed days only, a day counted only when the usual
number of points reported), with the storage read's history rules
(``domain/fundamentals/storage_history``):

* **Totals first**: Norwegian pipeline gas landed in the EU (``norway``), and the UK
  terminals (``uk_terminal``: Easington and St Fergus land Norwegian and UK shelf gas
  together; ENTSOG does not split them, and the scope says so).
* **Then each landing**: the registry's points summed per landing (Dornum, Emden,
  Zeebrugge, Dunkerque, Nybro, Easington, St Fergus).
* The measure is the **7-day mean** of the daily energy landed (GWh/d), the day's own value
  beside it; against the same gas day last year and the N-year average and band (N =
  complete prior gas years held, stated; the band from the last five).
* Provider and simulated rows never mix: when the landing rows are part demo, part provider,
  the read says so and returns nothing rather than a sum of both.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.application.fundamentals_lng import mean_7d
from eurogas_nexus.domain.fundamentals.storage_history import (
    BAND_YEARS,
    average_on_day,
    band_from_years,
    by_gas_year,
    gas_year_label,
    gas_year_of,
    history_plan,
    is_complete,
    range_position,
    same_day_last_year,
    season_index,
    season_keys,
)

#: Registry point -> the landing it belongs to (one physical landing place, several ENTSOG
#: points or operators summed, as ``landed_supply`` sums them).
LANDINGS: dict[str, tuple[str, str]] = {
    "ITP-00188": ("dornum", "Dornum"),
    "ITP-00126": ("dornum", "Dornum"),
    "ITP-00160": ("emden", "Emden"),
    "ITP-00081": ("emden", "Emden"),
    "ITP-00080": ("emden", "Emden"),
    "ITP-00106": ("zeebrugge", "Zeebrugge"),
    "ITP-00045": ("dunkerque", "Dunkerque"),
    "ITP-00097": ("nybro", "Nybro"),
    "ITP-00091": ("easington", "Easington"),
    "ITP-00022": ("st_fergus", "St Fergus"),
}
SCOPES = {
    "norway": "Norwegian pipeline gas landed in the EU",
    "uk_terminal": "UK terminals (Norwegian and UK shelf gas together)",
}
SPARK_DAYS = 30
READ_YEARS = BAND_YEARS + 2


def _r(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def series_view(code: str, name: str, daily: dict[date, float], *, season: bool,
                simulated: bool, scope: str | None = None) -> dict[str, Any] | None:
    """A daily energy series (GWh/d) against its own history, on its 7-day mean."""

    smooth = mean_7d(daily)
    if not smooth:
        return None
    last = max(smooth)
    value = smooth[last]
    current = gas_year_of(last)
    seasons = by_gas_year(smooth)
    complete = [y for y, v in seasons.items() if y < current and is_complete(v)]
    plan = history_plan(complete, min(smooth))
    mean, low, high = average_on_day(seasons, list(plan.years), season_index(last))
    previous_day = same_day_last_year(last)
    previous = smooth.get(previous_day)
    position = range_position(value, low, high) if low is not None and high is not None else None
    view: dict[str, Any] = {
        "code": code,
        "name": name,
        "scope": scope,
        "simulated": simulated,
        "as_of": last.isoformat(),
        "flow_7d_gwh_d": _r(value),
        "flow_day_gwh_d": _r(daily.get(last)),
        "vs_last_year": {
            "day": previous_day.isoformat(),
            "flow_7d_gwh_d": _r(previous),
            "diff_gwh_d": _r(value - previous) if previous is not None else None,
        },
        "history": {
            "mode": plan.mode,
            "years": [gas_year_label(y) for y in plan.years],
            "label": plan.label,
            "history_from": min(smooth).isoformat(),
        },
        "vs_average": {
            "years": len(plan.years),
            "mean_gwh_d": _r(mean),
            "low_gwh_d": _r(low),
            "high_gwh_d": _r(high),
            "diff_gwh_d": _r(value - mean) if mean is not None else None,
            "range_position": _r(position[0]) if position else None,
            "outside": position[1] if position else None,
        },
        "spark": [{"day": d.isoformat(), "flow_7d_gwh_d": _r(smooth[d])}
                  for d in sorted(smooth)[-SPARK_DAYS:]],
    }
    if season:
        last_year = seasons.get(current - 1)
        series: dict[str, Any] = {
            "axis": season_keys(),
            "gas_year": gas_year_label(current),
            "this_year": [_r(v) for v in seasons.get(current, [None] * 365)],
            "last_year": ({"gas_year": gas_year_label(current - 1),
                           "values": [_r(v) for v in last_year]} if last_year else None),
            "lines": [],
            "band": None,
        }
        if plan.mode == "lines":
            series["lines"] = [
                {"gas_year": gas_year_label(y), "values": [_r(v) for v in seasons[y]]}
                for y in plan.years
                if y != current - 1
            ]
        elif plan.mode == "band":
            band = band_from_years([seasons[y] for y in plan.years], digits=1)
            series["band"] = {"years": [gas_year_label(y) for y in plan.years],
                              "label": plan.label, "low": band.low, "high": band.high,
                              "mean": band.mean}
        view["season"] = series
    return view


def _sources(session, since: datetime) -> set[str]:
    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.db.models import FlowObservationRecord as Flow

    naive = session.get_bind().dialect.name == "sqlite"
    return {
        value
        for (value,) in session.query(Flow.source_system)
        .filter(identity_clause(session, Flow))
        .filter(Flow.point_id.in_(sorted(LANDINGS)))
        .filter(Flow.period_start_utc >= (since.replace(tzinfo=None) if naive else since))
        .distinct()
        .all()
        if value
    }


def flows_read(session, principal, *, season: Iterable[str] = (), now: datetime | None = None
               ) -> dict[str, Any]:
    """Norwegian and UK pipeline landings, totals then each landing, against history."""

    from eurogas_nexus.application.pipeline_supply import landed_supply
    from eurogas_nexus.domain.dataops.entitlement import derived_result_access

    now = now or datetime.now(UTC)
    first = date(gas_year_of(now.date()) - READ_YEARS, 10, 1) - timedelta(days=8)
    since = datetime.combine(first, datetime.min.time(), tzinfo=UTC)
    sources = _sources(session, since)
    empty = {"totals": [], "landings": [], "simulated": False, "unit": "GWh/d", "warnings": []}
    if not sources:
        return {**empty, "warnings": ["No ENTSOG landing flows held"]}
    if derived_result_access(principal, sources).outcome.value != "ALLOWED":
        return {**empty, "warnings": ["The landing flows use data outside your licences"]}
    simulated = {str(s).endswith("_Sim") for s in sources}
    if len(simulated) > 1:
        return {**empty, "warnings": [
            "Landing flows are part provider data, part simulated: they are not added together."
        ]}
    is_sim = simulated.pop()
    supply = landed_supply(session, first)
    wanted = {code.lower() for code in season}
    totals = [
        view for scope, name in SCOPES.items()
        if (view := series_view(scope, name, supply.by_scope.get(scope, {}),
                                season=scope in wanted, simulated=is_sim, scope=scope))
    ]
    grouped: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    names: dict[str, str] = {}
    for point_id, days in supply.by_point.items():
        if point_id not in LANDINGS:
            continue
        code, name = LANDINGS[point_id]
        names[code] = name
        for day, value in days.items():
            grouped[code][day] += value
    scope_of = {code: ("uk_terminal" if code in {"easington", "st_fergus"} else "norway")
                for code, _ in LANDINGS.values()}
    landings = [
        view for code, days in grouped.items()
        if (view := series_view(code, names[code], dict(days), season=code in wanted,
                                simulated=is_sim, scope=scope_of[code]))
    ]
    landings.sort(key=lambda view: -(view["flow_7d_gwh_d"] or 0.0))
    return {
        "totals": totals,
        "landings": landings,
        "simulated": is_sim,
        "unit": "GWh/d",
        "incomplete_days": [d.isoformat() for d in supply.incomplete_days[-10:]],
        "method": (
            "ENTSOG physical flow at the landing registry's points (one operator per point and "
            "gas day; closed days only; a day counted only when the usual number of points "
            "reported), shown as the trailing 7-day mean. The UK terminals land Norwegian and UK "
            "shelf gas together. History as for storage: complete prior gas years held, the "
            "band from the last five."
        ),
        "warnings": [],
    }
