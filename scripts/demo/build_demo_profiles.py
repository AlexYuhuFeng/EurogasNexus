"""Derive the demo desk's seasonal shapes from the live public series (development only).

The demo seed (``seed_demo_desk.py``) writes 400 days of simulated flows, storage and LNG and
a month of simulated power fundamentals. So that its magnitudes and seasonality are
believable, it scales its random paths by a small set of shapes taken once from a store that
holds the live public series, and writes them to ``scripts/demo/demo_profiles.json``:

- monthly mean entry energy at each of the balance's landing points (ENTSOG);
- recent median flow at a set of located NWE points, for the map (ENTSOG);
- monthly mean fill, injection and withdrawal per AGSI country and the EU total, and the
  latest working capacity (GIE AGSI);
- monthly mean send-out, stock and DTMI per ALSI country and the EU total (GIE ALSI);
- monthly mean GB storage flows and LNG send-out (National Gas);
- an hour-of-day mean of load and wind, solar and gas generation per bidding zone
  (ENTSO-E). No price is taken.

Only aggregates leave the store (twelve monthly means or 24 hourly means a series, rounded
to three significant figures); no observation is copied. Everything the seed generates from
them is flagged simulated. These are public, free sources (``docs/legal/DATA_SOURCE_TERMS.md``);
no licensed data is read.

    RUNTIME_STORE_DATABASE_URL=<store with the live public series> \
        python scripts/demo/build_demo_profiles.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean, median

from eurogas_nexus.application.pipeline_supply import LANDING_POINTS, row_energy_gwh, row_operator
from eurogas_nexus.db.models import FlowObservationRecord
from eurogas_nexus.db.models.observation import LngObservationRecord, StorageObservationRecord
from eurogas_nexus.db.models.power import PowerObservationRecord
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.reference_data.network_bundle import load_bundle

OUT = Path(__file__).with_name("demo_profiles.json")
AGSI_CODES = ("BE", "DE", "DK", "FR", "NL", "EU")
ALSI_CODES = ("BE", "DE", "FR", "NL", "EU")
POWER_ZONES = ("DE_LU", "NL", "BE", "FR")
POWER_METRICS = (
    "load_actual",
    "wind_onshore_generation",
    "wind_offshore_generation",
    "solar_generation",
    "gas_generation",
)
MAP_POINTS = 40


def sig(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    if value == 0:
        return 0.0
    return round(value, -int(math.floor(math.log10(abs(value)))) + (digits - 1))


def monthly(values: dict[int, list[float]]) -> list[float | None]:
    """Twelve monthly means (January first); a month with no value takes its neighbours'."""

    means = [mean(values[m]) if values.get(m) else None for m in range(1, 13)]
    known = [i for i, v in enumerate(means) if v is not None]
    if not known:
        return [None] * 12
    for i in range(12):
        if means[i] is None:
            nearest = min(known, key=lambda k: min((i - k) % 12, (k - i) % 12))
            means[i] = means[nearest]
    return [sig(v) for v in means]


def build(session) -> dict:
    landing: dict[str, dict] = {}
    by_point: dict[tuple[str, str], dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    landing_keys = {(p.point_id, p.operator) for p in LANDING_POINTS}
    for row in (
        session.query(FlowObservationRecord)
        .filter(FlowObservationRecord.point_id.in_([p.point_id for p in LANDING_POINTS]))
        .filter(FlowObservationRecord.direction == "entry")
        .filter(FlowObservationRecord.kind == "actual")
    ):
        key = (row.point_id, row_operator(row))
        energy, from_volume = row_energy_gwh(row)
        if key in landing_keys and energy is not None and not from_volume:
            by_point[key][row.period_start_utc.month].append(energy)
    for point in LANDING_POINTS:
        landing[point.point_id] = {
            "operator": point.operator,
            "name": point.label,
            "gwh_d_by_month": monthly(by_point[(point.point_id, point.operator)]),
        }

    bundle = load_bundle()
    located = {n["point_key"]: n for n in bundle["nodes"] if n["located"] and n["type"] != "hub"}
    since = datetime.now(UTC) - timedelta(days=21)
    recent: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in (
        session.query(FlowObservationRecord)
        .filter(FlowObservationRecord.point_id.in_(sorted(located)))
        .filter(FlowObservationRecord.period_start_utc >= since)
        .filter(FlowObservationRecord.kind == "actual")
    ):
        energy, from_volume = row_energy_gwh(row)
        if energy is not None and not from_volume and energy > 0:
            recent[(row.point_id, row_operator(row), row.direction)].append(energy)
    medians = sorted(
        ((median(v), k) for k, v in recent.items() if len(v) >= 5),
        reverse=True,
    )
    map_flows, used = [], set()
    for value, (point_id, operator, direction) in medians:
        if point_id in used or len(map_flows) >= MAP_POINTS:
            continue
        used.add(point_id)
        map_flows.append(
            {
                "point_id": point_id,
                "name": located[point_id]["name"],
                "operator": operator,
                "direction": direction,
                "gwh_d": sig(value),
            }
        )

    storage = {}
    for code in AGSI_CODES:
        rows = (
            session.query(StorageObservationRecord)
            .filter(StorageObservationRecord.source_system == "GIE")
            .filter(StorageObservationRecord.facility_id.in_([code, code.lower()]))
            .all()
        )
        fill, inj, wd = defaultdict(list), defaultdict(list), defaultdict(list)
        for row in rows:
            m = row.period_start_utc.month
            if row.fill_pct is not None:
                fill[m].append(row.fill_pct)
            if row.injection_twh_d is not None:
                inj[m].append(row.injection_twh_d)
            if row.withdrawal_twh_d is not None:
                wd[m].append(row.withdrawal_twh_d)
        newest = max(rows, key=lambda r: r.period_start_utc, default=None)
        storage[code] = {
            "working_capacity_twh": sig(newest.working_capacity_twh) if newest else None,
            "fill_pct_by_month": monthly(fill),
            "injection_twh_d_by_month": monthly(inj),
            "withdrawal_twh_d_by_month": monthly(wd),
        }

    lng = {}
    for code in ALSI_CODES:
        send, stock, dtmi = defaultdict(list), defaultdict(list), defaultdict(list)
        for row in (
            session.query(LngObservationRecord)
            .filter(LngObservationRecord.source_system == "GIE")
            .filter(LngObservationRecord.terminal_id.in_([code, code.lower()]))
        ):
            m = row.period_start_utc.month
            for target, value in (
                (send, row.send_out_twh_d),
                (stock, row.inventory_twh),
                (dtmi, row.dtmi_twh),
            ):
                if value is not None:
                    target[m].append(value)
        lng[code] = {
            "send_out_twh_d_by_month": monthly(send),
            "inventory_twh_by_month": monthly(stock),
            "dtmi_twh_by_month": monthly(dtmi),
        }

    gb_wd, gb_inj, gb_lng = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in session.query(StorageObservationRecord).filter(
        StorageObservationRecord.source_system == "NATIONAL_GAS"
    ):
        if row.withdrawal_twh_d is not None:
            gb_wd[row.period_start_utc.month].append(row.withdrawal_twh_d)
        if row.injection_twh_d is not None:
            gb_inj[row.period_start_utc.month].append(row.injection_twh_d)
    for row in session.query(LngObservationRecord).filter(
        LngObservationRecord.source_system == "NATIONAL_GAS"
    ):
        if row.send_out_twh_d is not None:
            gb_lng[row.period_start_utc.month].append(row.send_out_twh_d)
    gb = {
        "storage_withdrawal_twh_d_by_month": monthly(gb_wd),
        "storage_injection_twh_d_by_month": monthly(gb_inj),
        "lng_send_out_twh_d_by_month": monthly(gb_lng),
    }

    power = {}
    for zone in POWER_ZONES:
        hourly: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in (
            session.query(PowerObservationRecord)
            .filter(PowerObservationRecord.zone == zone)
            .filter(PowerObservationRecord.metric.in_(POWER_METRICS))
        ):
            hourly[row.metric][row.period_start_utc.hour].append(row.value)
        power[zone] = {
            metric: [sig(mean(hourly[metric][h])) if hourly[metric][h] else 0.0 for h in range(24)]
            for metric in POWER_METRICS
            if hourly.get(metric)
        }

    return {
        "note": (
            "Seasonal shapes for the demo desk, aggregated from public series (ENTSOG, GIE "
            "AGSI/ALSI, National Gas, ENTSO-E fundamentals; no prices). Monthly means or "
            "hour-of-day means, three significant figures. The demo seed generates simulated "
            "values from them and flags every row simulated."
        ),
        "built_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "landing_points": landing,
        "map_flows": map_flows,
        "storage": storage,
        "lng": lng,
        "gb": gb,
        "power_hourly_mw": power,
    }


def main() -> int:
    if not resolve_database_url():
        print("RUNTIME_STORE_DATABASE_URL is required", file=sys.stderr)
        return 2
    with get_session_factory()() as session:
        profiles = build(session)
        session.rollback()  # read-only
    OUT.write_text(json.dumps(profiles, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(profiles['landing_points'])} landing points, "
          f"{len(profiles['map_flows'])} map points, {len(profiles['storage'])} storage codes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
