"""The forward balance read: the NW Europe balance's inputs, dated forward (CP-25).

It composes the reads the product already serves, each under its own gates, so nothing
here bypasses an entitlement or a source gate:

- the measured balance and its 14-day base forecast (``GET /api/market/nwe-balance``:
  ENTSOG Norwegian landings, GIE ALSI send-out, GIE AGSI and National Gas storage, REMIT
  Norwegian outages);
- the region's storage fill and its 5-year band (``application.fundamentals_storage``);
- announced outages dated beyond the 14 days (``application.remit_outages``);
- the shipped Eurostat degree-day reference (``reference_data/nwe_hdd_eurostat.json``);
- the forward curve for the same months, for reference only (``position_inputs``).

``forward_balance_read(request, hub, period)`` is the one entry other reads cite
(Today, the daily report, Spreads, opportunities): a desk number with its source, class
and error, never a bare figure.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any

from fastapi import Request

from eurogas_nexus.domain.fundamentals.balance import BalanceHistoryDay
from eurogas_nexus.domain.fundamentals.forward_balance import (
    NOT_A_PRICE_FORECAST,
    HddReference,
    Overrides,
    StorageBand,
    SupplyOutage,
    build_forward_balance,
    weakest,
)

HUBS = {"nwe": {"code": "NWE", "reference_hub": "TTF"}}
#: Hubs whose zone balance the product cannot measure yet, and why (stated, not guessed).
ZONE_NOT_HELD = (
    "A zone's own balance needs its net cross-border flow (entry minus exit at every "
    "interconnection point), which the product does not read yet; the NW Europe balance "
    "is the region's, with transit inside the region netted out."
)
OUTAGE_HORIZON_DAYS = 120
#: Volume outages (mcm/d) are taken at the Norwegian calorific value the balance uses.
NORWEGIAN_GCV_KWH_M3 = 11.0


@lru_cache(maxsize=1)
def hdd_reference() -> tuple[HddReference, dict[str, Any]]:
    from eurogas_nexus.reference_data.network_bundle import bundle_path

    table = json.loads(
        bundle_path().with_name("nwe_hdd_eurostat.json").read_text(encoding="utf-8")
    )
    meta = {key: table[key] for key in ("method", "attribution", "licence", "weights",
                                        "eurostat_updated", "months")}
    meta["months"] = {"from": table["months"][0], "to": table["months"][-1]}
    return HddReference.from_table(table), meta


def _norway_outages(session, now: datetime) -> list[SupplyOutage]:
    from eurogas_nexus.application.remit_outages import load_outage_rows

    outages = []
    for row in load_outage_rows(session, now=now, horizon_days=OUTAGE_HORIZON_DAYS):
        if "NO" not in str(row.get("balancing_zone") or "").upper():
            continue
        gwh = row.get("unavailable_gwh_d")
        if gwh is None and row.get("unavailable_mcm_d") is not None:
            gwh = float(row["unavailable_mcm_d"]) * NORWEGIAN_GCV_KWH_M3
        if not gwh:
            continue
        start = datetime.fromisoformat(str(row["start_utc"])).date()
        end = datetime.fromisoformat(str(row["end_utc"])).date() if row.get("end_utc") else None
        outages.append(SupplyOutage("norway", start, end, float(gwh),
                                    source=f"REMIT {row.get('event_id')}"))
    return outages


def _storage_band(session, request: Request) -> tuple[StorageBand | None, dict | None]:
    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.application.fundamentals_storage import storage_read

    read = storage_read(session, current_principal(request), region="nwe", season=["NWE"])
    region = read.get("region") or {}
    season = region.get("season") or {}
    band = season.get("band")
    if band:
        return StorageBand(band["low"], band["high"], band["mean"], band.get("label")), region
    lines = [line["values"] for line in season.get("lines") or []]
    if season.get("last_year"):
        lines.append(season["last_year"]["values"])
    if lines:
        from eurogas_nexus.domain.fundamentals.storage_history import band_from_years

        built = band_from_years(lines)
        label = f"{len(lines)} prior year{'s' if len(lines) > 1 else ''} held"
        return StorageBand(built.low, built.high, built.mean, label), region
    return None, region or None


def _curve(request: Request, months: list[str], hub: str) -> list[dict[str, Any]]:
    """The forward curve for the same months, for reference only (entitled quotes)."""

    from eurogas_nexus.application.position_inputs import (
        CURVE_QUOTE_LOOKBACK_DAYS,
        curve_quotes,
    )
    from eurogas_nexus.domain.market.forward_curve import build_forward_curve

    today = datetime.now(UTC).date()
    try:
        curve = build_forward_curve(
            curve_quotes(request, today - timedelta(days=CURVE_QUOTE_LOOKBACK_DAYS), today),
            first_month=today.replace(day=1),
        )
    except Exception:  # noqa: BLE001 - a reference column never fails the balance
        return []
    return [
        {"hub": point.hub, "month": point.month, "price": round(point.price, 3),
         "method": point.method, "source": point.source}
        for point in curve.points
        if point.hub == hub and point.month in months
    ]


def _lines(nwe: dict[str, Any], hdd_meta: dict[str, Any], storage: dict | None,
           overridden: list[str], simulated: bool) -> list[dict[str, Any]]:
    """Each line's source, as-of and class; the class is the weakest of its inputs."""

    history = nwe.get("history") or []
    as_of = history[-1]["day"] if history else None
    assumptions = nwe.get("assumptions") or {}
    observed = "simulated" if simulated else "observed"
    rows = [
        {"id": "demand", "source": "Measured call (ENTSOG + GIE + National Gas); "
                                   "Eurostat HDD normals", "as_of": as_of,
         "inputs": [observed, "assumption"],
         "note": "normal weather from here on (no forecast temperature held)"},
        {"id": "norway", "source": "ENTSOG landings; REMIT outages", "as_of":
         assumptions.get("pipeline_complete_through") or as_of,
         "inputs": [observed, "scheduled", "forecast"]},
        {"id": "lng", "source": "GIE ALSI send-out", "as_of":
         assumptions.get("storage_lng_complete_through") or as_of,
         "inputs": [observed, "forecast"],
         "note": "no cargo schedule held: the 14-day average is carried"},
        {"id": "storage", "source": "GIE AGSI + National Gas; residual", "as_of":
         (storage or {}).get("as_of") or assumptions.get("storage_inventory_day"),
         "inputs": [observed, "forecast"]},
    ]
    manual = {"temperature_shift_c": "demand", "norway_gwh_d": "norway",
              "lng_gwh_d": "lng", "added_outage": None}
    for name in overridden:
        target = manual.get(name)
        for row in rows:
            if target is None or row["id"] == target or row["id"] == "storage":
                row["inputs"].append("manual")
    for row in rows:
        row["class"] = "simulated" if simulated else weakest(row["inputs"])
    rows.append({"id": "weather_normal", "source": hdd_meta["attribution"],
                 "as_of": hdd_meta["months"]["to"], "inputs": ["observed"],
                 "class": "observed",
                 "note": f"{hdd_meta['licence']}; country weights from Eurostat sector gas use, "
                         "not a reviewed regional weather profile"})
    return rows


def forward_balance_read(
    request: Request,
    *,
    hub: str = "nwe",
    period: str = "all",
    temperature_shift_c: float = 0.0,
    norway_gwh_d: float | None = None,
    lng_gwh_d: float | None = None,
    outage_line: str | None = None,
    outage_gwh_d: float | None = None,
    outage_from: date | None = None,
    outage_to: date | None = None,
    summary: bool = False,
) -> dict[str, Any]:
    """The forward balance envelope for ``hub`` (``nwe``); ``period`` trims to ``daily``
    or ``monthly``. ``summary`` (Today's headline) skips the daily backtest, so daily
    errors fall back to the fit's residual. Raises ``ValueError`` for a hub whose balance
    is not held."""

    from eurogas_nexus.api.routes.public.fundamentals import _env, _session_or_none, get_nwe_balance
    from eurogas_nexus.domain.fundamentals.storage_history import season_index
    from eurogas_nexus.domain.market.storage_targets import (
        DEFAULT_DEADLINE,
        DEFAULT_TARGET_PCT,
    )

    hub = hub.lower()
    if hub not in HUBS:
        raise ValueError(f"forward balance for {hub!r} is not held: {ZONE_NOT_HELD}")
    nwe_envelope = get_nwe_balance(request, days=14, history_days=800, format="json")
    nwe = nwe_envelope.get("data") or {}
    warnings = list((nwe_envelope.get("meta") or {}).get("warnings") or [])
    history = [
        BalanceHistoryDay(
            day=date.fromisoformat(row["day"]),
            norway_gwh=float(row["norway_gwh"]),
            lng_gwh=float(row["lng_gwh"]),
            storage_net_withdrawal_gwh=float(row["storage_net_withdrawal_gwh"]),
        )
        for row in nwe.get("history") or []
    ]
    reference, hdd_meta = hdd_reference()
    added = None
    if outage_line and outage_gwh_d:
        if outage_line not in {"norway", "lng"}:
            raise ValueError("outage_line must be norway or lng")
        start = outage_from or (history[-1].day + timedelta(days=1) if history else date.today())
        added = SupplyOutage(outage_line, start, outage_to, float(outage_gwh_d), source="manual")
    overrides = Overrides(temperature_shift_c=temperature_shift_c, norway_gwh_d=norway_gwh_d,
                          lng_gwh_d=lng_gwh_d, added_outage=added)
    band = storage = None
    outages: list[SupplyOutage] = []
    session = _session_or_none()
    if session is not None:
        with session:
            outages = _norway_outages(session, datetime.now(UTC))
            band, storage = _storage_band(session, request)
    simulated = bool((storage or {}).get("simulated"))
    result = build_forward_balance(
        history,
        nwe.get("forecast") or [],
        hdd=reference,
        outages=outages,
        band=band,
        season_index=season_index,
        target=(DEFAULT_TARGET_PCT, DEFAULT_DEADLINE),
        overrides=overrides,
        backtest={"origins": 0, "horizons": [], "skipped": "summary read"} if summary else None,
    )
    months = [row["month"] for row in result.monthly]
    reference_hub = HUBS[hub]["reference_hub"]
    data = {
        "hub": hub,
        "region": nwe.get("region"),
        "unit": "GWh/d",
        "as_of": result.as_of.isoformat() if result.as_of else None,
        "simulated": simulated,
        "headline": result.headline,
        "daily": result.daily if period in {"all", "daily"} else [],
        "monthly": result.monthly if period in {"all", "monthly"} else [],
        "lines": _lines(nwe, hdd_meta, storage, result.overridden, simulated),
        "demand_model": result.demand_fit.as_dict() if result.demand_fit else None,
        "backtest": result.backtest,
        "storage": {
            "fill_pct": (storage or {}).get("fill_pct"),
            "as_of": (storage or {}).get("as_of"),
            "band_label": band.label if band else None,
            "target": result.target,
        },
        "overridden": result.overridden,
        "what_if": {
            "temperature_shift_c": temperature_shift_c,
            "norway_gwh_d": norway_gwh_d,
            "lng_gwh_d": lng_gwh_d,
            "added_outage": None if added is None else {
                "line": added.line, "gwh_d": added.gwh_d, "from": added.start.isoformat(),
                "to": added.end.isoformat() if added.end else None},
        },
        "outages_applied": len(outages),
        "forward_curve": {
            "hub": reference_hub,
            "for_reference_only": True,
            "months": _curve(request, months, reference_hub),
        },
        "weather_reference": hdd_meta,
        "zone_note": ZONE_NOT_HELD,
        "not_a_price_forecast": NOT_A_PRICE_FORECAST,
    }
    return _env(data, "runtime-postgresql", [*warnings, *result.warnings])
