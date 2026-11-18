"""The LNG fundamentals read: send-out by country against its own history (CP-17).

``GET /api/fundamentals/lng`` (design basis 2, D.2 "LNG"). One deterministic read of the
stored GIE ALSI rows (or the demo desk's simulated rows), with the storage read's history
rules (``domain/fundamentals/storage_history``):

* The measure is **send-out as a 7-day mean** (GWh/d): daily send-out moves with cargo
  arrivals, so a range drawn from daily values would be a fence of spikes. The day's own
  send-out is returned beside it.
* The EU total is GIE's own aggregate (code ``eu``); then each country GIE ALSI publishes,
  ordered by send-out. Countries with no rows are listed with the reason.
* Against history: the same gas day last year, and the N-year average and band of the 7-day
  mean (N = complete prior gas years held, stated; the band from the last five; a day any of
  them lacks is a gap). A terminal opened recently has fewer years and says so (Germany and
  Finland from winter 2022/23).
* Inventory (TWh) and the inventory against the maximum the terminals declare (DTMI), %.
* Provider and simulated rows never mix in one entity.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

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

#: Countries GIE ALSI publishes LNG for (checked live on 2026-11-18).
ALSI_COUNTRIES: dict[str, str] = {
    "BE": "Belgium",
    "DE": "Germany",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GR": "Greece",
    "HR": "Croatia",
    "IT": "Italy",
    "LT": "Lithuania",
    "NL": "Netherlands",
    "PL": "Poland",
    "PT": "Portugal",
}
MEAN_DAYS = 7
SPARK_DAYS = 30
READ_YEARS = BAND_YEARS + 2


@dataclass
class _Entity:
    code: str
    simulated: bool
    sources: set[str] = field(default_factory=set)
    send_out: dict[date, float] = field(default_factory=dict)  # GWh/d
    inventory: dict[date, float] = field(default_factory=dict)  # TWh
    dtmi: dict[date, float] = field(default_factory=dict)  # TWh


def _gas_day(start: datetime) -> date:
    start = start.replace(tzinfo=UTC) if start.tzinfo is None else start.astimezone(UTC)
    return (start + timedelta(hours=7)).date()


def _load(session, principal, codes: Iterable[str], since: datetime) -> dict[str, _Entity]:
    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models.observation import LngObservationRecord as Lng

    wanted = sorted({c.upper() for c in codes} | {c.lower() for c in codes})
    naive = session.get_bind().dialect.name == "sqlite"
    rows = (
        session.query(
            Lng.period_start_utc, Lng.country, Lng.terminal_id, Lng.source_system,
            Lng.send_out_twh_d, Lng.inventory_twh, Lng.dtmi_twh,
        )
        .filter(identity_clause(session, Lng))
        .filter(Lng.country.in_(wanted))
        .filter(Lng.period_start_utc >= (since.replace(tzinfo=None) if naive else since))
        .all()
    )
    by_code: dict[str, dict[bool, list]] = {}
    for row in rows:
        if not row_allowed(principal, row.source_system):
            continue
        # Country aggregates only (a terminal row under a country would be counted twice).
        if str(row.terminal_id or "").upper() != str(row.country or "").upper():
            continue
        simulated = str(row.source_system or "").endswith("_Sim")
        by_code.setdefault(str(row.country).upper(), {}).setdefault(simulated, []).append(row)
    out: dict[str, _Entity] = {}
    for code, kinds in by_code.items():
        simulated = False not in kinds
        entity = _Entity(code=code, simulated=simulated)
        for row in kinds[simulated]:
            day = _gas_day(row.period_start_utc)
            entity.sources.add(str(row.source_system))
            if row.send_out_twh_d is not None:
                entity.send_out[day] = 1000 * float(row.send_out_twh_d)
            if row.inventory_twh is not None:
                entity.inventory[day] = float(row.inventory_twh)
            if row.dtmi_twh:
                entity.dtmi[day] = float(row.dtmi_twh)
        if entity.send_out:
            out[code] = entity
    return out


def mean_7d(values: dict[date, float]) -> dict[date, float]:
    """The trailing 7-day mean, only where all seven days are held (a gap stays a gap)."""

    out = {}
    for day in values:
        window = [values.get(day - timedelta(days=k)) for k in range(MEAN_DAYS)]
        if all(v is not None for v in window):
            out[day] = sum(window) / MEAN_DAYS  # type: ignore[arg-type]
    return out


def _r(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _view(entity: _Entity, name: str, *, season: bool) -> dict[str, Any] | None:
    smooth = mean_7d(entity.send_out)
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
    inventory = entity.inventory.get(last)
    dtmi = entity.dtmi.get(last)
    position = range_position(value, low, high) if low is not None and high is not None else None
    view: dict[str, Any] = {
        "code": entity.code,
        "name": name,
        "simulated": entity.simulated,
        "sources": sorted(entity.sources),
        "as_of": last.isoformat(),
        "send_out_7d_gwh_d": _r(value),
        "send_out_day_gwh_d": _r(entity.send_out.get(last)),
        "inventory_twh": _r(inventory, 3),
        "inventory_pct_of_dtmi": _r(100 * inventory / dtmi) if inventory and dtmi else None,
        "vs_last_year": {
            "day": previous_day.isoformat(),
            "send_out_7d_gwh_d": _r(previous),
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
        "spark": [{"day": d.isoformat(), "send_out_7d_gwh_d": _r(smooth[d])}
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


def lng_read(session, principal, *, season: Iterable[str] = (), now: datetime | None = None
             ) -> dict[str, Any]:
    """The EU total and each ALSI country's send-out against its history."""

    now = now or datetime.now(UTC)
    since = datetime(gas_year_of(now.date()) - READ_YEARS, 10, 1, tzinfo=UTC) - timedelta(days=8)
    entities = _load(session, principal, [*ALSI_COUNTRIES, "EU"], since)
    wanted = {c.upper() for c in season} or {"EU"}
    region = entities.get("EU")
    region_view = _view(region, "EU total", season="EU" in wanted) if region else None
    countries = [
        view for code in ALSI_COUNTRIES if code in entities
        if (view := _view(entities[code], ALSI_COUNTRIES[code], season=code in wanted))
    ]
    countries.sort(key=lambda view: -(view["send_out_7d_gwh_d"] or 0.0))
    return {
        "region": region_view,
        "countries": countries,
        "missing": [{"code": c, "name": n, "reason": "No LNG rows held for this country"}
                    for c, n in ALSI_COUNTRIES.items() if c not in entities],
        "simulated": any(e.simulated for e in entities.values()),
        "unit": "GWh/d",
        "method": (
            "Send-out is GIE ALSI's daily send-out, shown as the trailing 7-day mean (all seven "
            "days held). Gas year 1 Oct-30 Sep; 29 Feb has no slot. A prior gas year counts as "
            "held with values on at least 95% of its days; with five or more held the band is "
            "the min-max and mean of the last five, with one to four each year is a line. "
            "Inventory against the declared maximum (DTMI) where published."
        ),
    }
