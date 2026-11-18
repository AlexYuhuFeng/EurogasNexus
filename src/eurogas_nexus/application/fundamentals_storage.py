"""The storage fundamentals read: a region and each of its countries against their own history.

``GET /api/fundamentals/storage`` (design basis 2, D.2 and E; J.4). One deterministic read of
the stored GIE AGSI rows (or the demo desk's simulated rows), no model:

* **Region first.** ``eu``: GIE's own EU aggregate (the provider defines it: the sum of the
  EU member states with storage, checked by ``reconciliation``). ``nwe``: north-west Europe,
  the sum of the balance's countries that publish a working capacity, on days every one of
  them reported.
* **Then each country** of the region: fill %, stock TWh, working capacity, day and week
  change, against the same gas day last year, against the N-year average and band (N = the
  complete prior gas years actually held, stated), injection/withdrawal and the 7-day net
  rate, the EU filling target where it applies, 30 days for a sparkline and, for the entities
  asked for in ``season``, the full gas-year series with the history band or lines.
* **Missing countries are stated**, with the reason, never dropped silently.
* **Real and simulated never mix.** Per entity, provider rows win; an entity with only demo
  rows is marked simulated. A region sum is built from one kind only; when its members are
  mixed it says so instead of adding them.

Entitlement: rows the caller may not read (``row_allowed``) are not used, and the identity
withholding rule applies (``identity_clause``), as on every storage read.
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
    change_over,
    gas_year_label,
    gas_year_of,
    history_plan,
    is_complete,
    range_position,
    same_day_last_year,
    season_index,
    season_keys,
)

#: GIE AGSI's EU member states with storage, checked live on 2026-11-17 (``country=XX``):
#: the EU aggregate equals their sum to rounding. IE answers with an empty placeholder
#: (status N, no storage); LT, LU, SI, FI, EE and GR answer with no data.
EU_STORAGE_COUNTRIES: dict[str, str] = {
    "AT": "Austria",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "CZ": "Czechia",
    "DE": "Germany",
    "DK": "Denmark",
    "ES": "Spain",
    "FR": "France",
    "HR": "Croatia",
    "HU": "Hungary",
    "IT": "Italy",
    "LV": "Latvia",
    "NL": "Netherlands",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "SE": "Sweden",
    "SK": "Slovakia",
}
#: Countries GIE lists without storage data; named in ``missing`` with that reason.
NO_STORAGE_PUBLISHED: dict[str, str] = {
    "GB": "GIE publishes no GB storage since Brexit; National Gas publishes stock without a "
          "working capacity, so no fill can be computed",
    "LU": "No gas storage in Luxembourg",
    "IE": "No gas storage in Ireland",
}
REGIONS = {
    "eu": {"code": "EU", "name": "EU total",
           "definition": "GIE AGSI EU aggregate: the EU member states with storage"},
    "nwe": {"code": "NWE", "name": "North-west Europe",
            "definition": "Sum of BE, DE, DK, FR, NL (GB and LU publish no working capacity), "
                          "on days every one of them reported"},
}
NAMES = {**EU_STORAGE_COUNTRIES, "GB": "United Kingdom", "LU": "Luxembourg", "IE": "Ireland",
         "EU": "EU total", "UA": "Ukraine"}
SPARK_DAYS = 30
#: Prior gas years read beyond the band's five, so a year with a gap does not shorten it.
READ_YEARS = BAND_YEARS + 2


@dataclass
class _Entity:
    code: str
    simulated: bool
    sources: set[str] = field(default_factory=set)
    inventory: dict[date, float] = field(default_factory=dict)
    capacity: dict[date, float] = field(default_factory=dict)
    fill: dict[date, float] = field(default_factory=dict)
    injection: dict[date, float] = field(default_factory=dict)
    withdrawal: dict[date, float] = field(default_factory=dict)
    received: datetime | None = None


def _gas_day(start: datetime) -> date:
    """The gas day of a stored period start (05:00/04:00 UTC): seven hours on, its date."""

    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return (start.astimezone(UTC) + timedelta(hours=7)).date()


def _members(region: str) -> list[str]:
    if region == "nwe":
        from eurogas_nexus.domain.fundamentals.balance import NWE_COUNTRIES

        return list(NWE_COUNTRIES)
    return list(EU_STORAGE_COUNTRIES)


def _load(session, principal, codes: Iterable[str], since: datetime) -> dict[str, _Entity]:
    """Rows per entity, provider rows winning over demo rows (never both in one entity)."""

    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models.observation import StorageObservationRecord as Storage

    wanted = sorted({c.upper() for c in codes} | {c.lower() for c in codes})
    naive = session.get_bind().dialect.name == "sqlite"
    rows = (
        session.query(
            Storage.period_start_utc,
            Storage.country,
            Storage.facility_id,
            Storage.source_system,
            Storage.inventory_twh,
            Storage.working_capacity_twh,
            Storage.fill_pct,
            Storage.injection_twh_d,
            Storage.withdrawal_twh_d,
            Storage.observed_at_utc,
        )
        .filter(identity_clause(session, Storage))
        .filter(Storage.country.in_(wanted))
        .filter(Storage.period_start_utc >= (since.replace(tzinfo=None) if naive else since))
        .all()
    )
    by_code: dict[str, dict[bool, list]] = {}
    for row in rows:
        if not row_allowed(principal, row.source_system):
            continue
        # Country aggregates only: a facility row under a country would be counted twice.
        if str(row.facility_id or "").upper() != str(row.country or "").upper():
            continue
        simulated = str(row.source_system or "").endswith("_Sim")
        by_code.setdefault(str(row.country).upper(), {}).setdefault(simulated, []).append(row)
    entities: dict[str, _Entity] = {}
    for code, kinds in by_code.items():
        simulated = False not in kinds
        entity = _Entity(code=code, simulated=simulated)
        for row in kinds[simulated]:
            day = _gas_day(row.period_start_utc)
            entity.sources.add(str(row.source_system))
            if row.inventory_twh is not None and row.working_capacity_twh:
                entity.inventory[day] = float(row.inventory_twh)
                entity.capacity[day] = float(row.working_capacity_twh)
                entity.fill[day] = (
                    float(row.fill_pct)
                    if row.fill_pct is not None
                    else 100 * float(row.inventory_twh) / float(row.working_capacity_twh)
                )
            if row.injection_twh_d is not None:
                entity.injection[day] = float(row.injection_twh_d)
            if row.withdrawal_twh_d is not None:
                entity.withdrawal[day] = float(row.withdrawal_twh_d)
            received = row.observed_at_utc
            if received is not None:
                received = received.replace(tzinfo=UTC) if received.tzinfo is None else received
                entity.received = max(entity.received or received, received)
        if entity.fill:
            entities[code] = entity
    return entities


def _sum_region(code: str, members: list[_Entity]) -> _Entity | None:
    """A region as the sum of its members, on days every member reported."""

    if not members:
        return None
    kinds = {m.simulated for m in members}
    if len(kinds) > 1:
        return None
    region = _Entity(code=code, simulated=kinds.pop())
    days = set.intersection(*(set(m.inventory) for m in members))
    for day in days:
        inventory = sum(m.inventory[day] for m in members)
        capacity = sum(m.capacity[day] for m in members)
        region.inventory[day] = inventory
        region.capacity[day] = capacity
        region.fill[day] = 100 * inventory / capacity if capacity else 0.0
        if all(day in m.injection for m in members):
            region.injection[day] = sum(m.injection[day] for m in members)
        if all(day in m.withdrawal for m in members):
            region.withdrawal[day] = sum(m.withdrawal[day] for m in members)
    for member in members:
        region.sources |= member.sources
        if member.received:
            region.received = max(region.received or member.received, member.received)
    return region if region.fill else None


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _target_applies(code: str) -> bool:
    return code in EU_STORAGE_COUNTRIES or code == "EU"


def _entity_view(entity: _Entity, name: str, *, season: bool) -> dict[str, Any]:
    from eurogas_nexus.domain.market.storage_targets import (
        DEFAULT_DEADLINE,
        DEFAULT_TARGET_PCT,
        DEFAULT_WINDOW_OPEN,
    )

    last = max(entity.fill)
    fill = entity.fill[last]
    current_year = gas_year_of(last)
    seasons = by_gas_year(entity.fill)
    complete = [year for year, values in seasons.items()
                if year < current_year and is_complete(values)]
    plan = history_plan(complete, min(entity.fill))
    index = season_index(last)
    avg_years = list(plan.years)
    mean, low, high = average_on_day(seasons, avg_years, index)
    previous_day = same_day_last_year(last)
    previous = entity.fill.get(previous_day)
    net = {
        day: entity.withdrawal[day] - entity.injection[day]
        for day in entity.withdrawal
        if day in entity.injection
    }
    week = [net[last - timedelta(days=k)] for k in range(7) if last - timedelta(days=k) in net]
    rate_7d = sum(week) / len(week) if len(week) == 7 else None
    fill_week = change_over(entity.fill, last, 7)
    target: dict[str, Any] | None = None
    if _target_applies(entity.code):
        pct = DEFAULT_TARGET_PCT
        per_day = fill_week / 7 if fill_week is not None else None
        target = {
            "pct": pct,
            "window_open": f"{DEFAULT_WINDOW_OPEN[0]:02d}-{DEFAULT_WINDOW_OPEN[1]:02d}",
            "deadline": f"{DEFAULT_DEADLINE[0]:02d}-{DEFAULT_DEADLINE[1]:02d}",
            "gap_pts": _r(fill - pct),
            "days_to_target_at_7d_rate": (
                int(-(-(pct - fill) // per_day)) if per_day and per_day > 0 and fill < pct else None
            ),
        }
    position = range_position(fill, low, high) if low is not None and high is not None else None
    view: dict[str, Any] = {
        "code": entity.code,
        "name": name,
        "simulated": entity.simulated,
        "sources": sorted(entity.sources),
        "as_of": last.isoformat(),
        "received_at_utc": entity.received.isoformat() if entity.received else None,
        "fill_pct": _r(fill),
        "stock_twh": _r(entity.inventory.get(last), 3),
        "working_capacity_twh": _r(entity.capacity.get(last), 3),
        "day_change_pts": _r(change_over(entity.fill, last, 1)),
        "day_change_twh": _r(change_over(entity.inventory, last, 1), 3),
        "week_change_pts": _r(fill_week),
        "week_change_twh": _r(change_over(entity.inventory, last, 7), 3),
        "injection_twh_d": _r(entity.injection.get(last), 4),
        "withdrawal_twh_d": _r(entity.withdrawal.get(last), 4),
        "net_withdrawal_7d_twh_d": _r(rate_7d, 4),
        "vs_last_year": {
            "day": previous_day.isoformat(),
            "fill_pct": _r(previous),
            "diff_pts": _r(fill - previous) if previous is not None else None,
        },
        "history": {
            "mode": plan.mode,
            "years": [gas_year_label(year) for year in plan.years],
            "label": plan.label,
            "history_from": min(entity.fill).isoformat(),
        },
        "vs_average": {
            "years": len(avg_years),
            "label": f"{len(avg_years)}-yr avg" if avg_years else None,
            "mean_pct": _r(mean),
            "low_pct": _r(low),
            "high_pct": _r(high),
            "diff_pts": _r(fill - mean) if mean is not None else None,
            "range_position": _r(position[0], 1) if position else None,
            "outside": position[1] if position else None,
        },
        "target": target,
        "spark": [
            {"day": day.isoformat(), "fill_pct": _r(entity.fill[day])}
            for day in sorted(entity.fill)[-SPARK_DAYS:]
        ],
    }
    if season:
        this_year = seasons.get(current_year, [None] * 365)
        last_year = seasons.get(current_year - 1)
        series: dict[str, Any] = {
            "axis": season_keys(),
            "gas_year": gas_year_label(current_year),
            "this_year": [_r(v) for v in this_year],
            "last_year": (
                {"gas_year": gas_year_label(current_year - 1),
                 "values": [_r(v) for v in last_year]}
                if last_year else None
            ),
            "lines": [],
            "band": None,
        }
        if plan.mode == "lines":
            series["lines"] = [
                {"gas_year": gas_year_label(year), "values": [_r(v) for v in seasons[year]]}
                for year in plan.years
                if year != current_year - 1
            ]
        elif plan.mode == "band":
            band = band_from_years([seasons[year] for year in plan.years])
            series["band"] = {
                "years": [gas_year_label(year) for year in plan.years],
                "label": plan.label,
                "low": band.low,
                "high": band.high,
                "mean": band.mean,
            }
        view["season"] = series
    return view


def storage_read(
    session,
    principal,
    *,
    region: str = "eu",
    season: Iterable[str] = (),
    focus: Iterable[str] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """The region, its countries, the countries missing and the region's reconciliation."""

    region = region.lower()
    if region not in REGIONS:
        raise ValueError(f"unknown region {region!r}; expected one of {sorted(REGIONS)}")
    now = now or datetime.now(UTC)
    since = datetime(gas_year_of(now.date()) - READ_YEARS, 10, 1, tzinfo=UTC) - timedelta(days=1)
    members = _members(region)
    codes = [*members, "EU"] if region == "eu" else members
    entities = _load(session, principal, codes, since)
    wanted_season = {code.upper() for code in season} or {REGIONS[region]["code"]}
    focus_order = [code.upper() for code in focus]
    definition = REGIONS[region]
    warnings: list[str] = []

    if region == "eu":
        region_entity = entities.get("EU")
    else:
        held = [entities[c] for c in members if c in entities]
        region_entity = _sum_region("NWE", held)
        if held and region_entity is None:
            warnings.append(
                "The region's countries are part provider data, part simulated: they are "
                "not added together."
            )

    countries = [entities[c] for c in members if c in entities]
    countries.sort(key=lambda e: (
        focus_order.index(e.code) if e.code in focus_order else len(focus_order),
        -(e.capacity[max(e.capacity)] if e.capacity else 0.0),
    ))
    missing = [
        {"code": c, "name": NAMES.get(c, c),
         "reason": NO_STORAGE_PUBLISHED.get(c, "No storage rows held for this country")}
        for c in members if c not in entities
    ]

    reconciliation = None
    if region == "eu" and region_entity is not None:
        day = max(region_entity.inventory)
        parts = [
            e for e in countries
            if day in e.inventory and e.simulated == region_entity.simulated
        ]
        if parts:
            total = sum(e.inventory[day] for e in parts)
            reconciliation = {
                "day": day.isoformat(),
                "region_stock_twh": round(region_entity.inventory[day], 3),
                "countries_stock_twh": round(total, 3),
                "countries_counted": len(parts),
                "countries_expected": len(members),
                "difference_twh": round(region_entity.inventory[day] - total, 3),
                "complete": len(parts) == len(members),
            }

    return {
        "region": (
            {**_entity_view(region_entity, definition["name"],
                            season=definition["code"] in wanted_season),
             "code": definition["code"], "definition": definition["definition"]}
            if region_entity is not None
            else None
        ),
        "countries": [
            _entity_view(e, NAMES.get(e.code, e.code), season=e.code in wanted_season)
            for e in countries
        ],
        "missing": missing,
        "reconciliation": reconciliation,
        "simulated": any(e.simulated for e in entities.values()),
        "unit": "%",
        "method": (
            "Fill = stock / working capacity (GIE's own 'full' where published). Gas year "
            "1 Oct-30 Sep; 29 Feb has no slot. A prior gas year counts as held with values on "
            "at least 95% of its days; with five or more held the band is the min-max and the "
            "mean of the last five, with one to four each year is a line; a day any of them "
            "lacks is a gap. 'vs N-yr avg' uses the N years held. Net withdrawal = withdrawal "
            "- injection, 7-day mean."
        ),
        "warnings": warnings,
    }
