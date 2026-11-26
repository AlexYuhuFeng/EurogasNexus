"""The supply corridors read: the shipped corridors with each entry series' latest stored flow.

The corridors (``reference_data/supply_corridors.json``) say where import gas enters the
European system and which ENTSOG flow series to read there. With a store, each series gets the
newest closed gas day of physical flow the ENTSOG ingestion holds for it (``latest_flow``:
energy in GWh/d as ENTSOG published it, the gas day, the operator), so the map shows the
corridor's live flow. A series the store does not hold reads ``latest_flow: null`` (missing,
never zero). The corridor's ``status`` stays the shipped one, built from ENTSOG with its date.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

#: Closed gas days searched for a series' newest flow.
LOOKBACK_DAYS = 10


def corridors_read(session: Any | None, *, now: datetime) -> dict[str, Any]:
    from eurogas_nexus.reference_data.supply_corridors import load_corridors

    data = load_corridors()
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    if session is not None:
        latest = _latest_flows(session, data, now=now)
    corridors = []
    for corridor in data["corridors"]:
        series = []
        for item in corridor["flow_series"]:
            series.append(
                {**item, "latest_flow": latest.get((item["point_key"], item["operator_key"]))}
            )
        flows = [s["latest_flow"] for s in series if s["latest_flow"]]
        corridors.append(
            {
                **corridor,
                "flow_series": series,
                "latest_flow_gwh_d": (
                    round(sum(flow["energy_gwh_d"] for flow in flows), 3) if flows else None
                ),
                "latest_flow_series": len(flows),
            }
        )
    return {
        "corridors": corridors,
        "gas_day": data.get("gas_day"),
        "source": data.get("source"),
        "geometry_source": data.get("geometry_source"),
        "status_rule": data.get("status_rule"),
        "flow_rule": (
            "Newest closed gas day of ENTSOG Physical Flow the store holds for each entry "
            f"series (point, operator, entry), within {LOOKBACK_DAYS} days; a corridor's "
            "latest flow adds its series that report one."
        ),
    }


def _latest_flows(session, data, *, now: datetime) -> dict[tuple[str, str], dict[str, Any]]:
    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.application.pipeline_supply import row_energy_gwh
    from eurogas_nexus.db.models import FlowObservationRecord
    from eurogas_nexus.domain.market.gas_day import gas_day_start_utc

    wanted = {
        (item["point_key"], item["operator_key"])
        for corridor in data["corridors"]
        for item in corridor["flow_series"]
    }
    open_day = gas_day_start_utc(now)
    naive = open_day.replace(tzinfo=None)
    sqlite = session.get_bind().dialect.name == "sqlite"
    end = naive if sqlite else open_day
    rows = (
        session.query(FlowObservationRecord)
        .filter(identity_clause(session, FlowObservationRecord))
        .filter(FlowObservationRecord.point_id.in_(sorted({p for p, _ in wanted})))
        .filter(FlowObservationRecord.kind == "actual")
        .filter(FlowObservationRecord.direction == "entry")
        .filter(FlowObservationRecord.period_start_utc >= end - timedelta(days=LOOKBACK_DAYS))
        .filter(FlowObservationRecord.period_end_utc <= end)
        .order_by(FlowObservationRecord.period_start_utc.desc())
        .limit(5000)
        .all()
    )
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        operator = str((row.metadata_json or {}).get("operatorKey") or "")
        key = (row.point_id, operator)
        if key not in wanted or key in out:
            continue
        energy, legacy = row_energy_gwh(row)
        if energy is None:
            continue
        out[key] = {
            "energy_gwh_d": round(energy, 3),
            "from_legacy_volume": legacy,
            "gas_day_start_utc": row.period_start_utc.isoformat(),
            "source_system": row.source_system,
            "source_record_id": row.source_record_id,
        }
    return out
