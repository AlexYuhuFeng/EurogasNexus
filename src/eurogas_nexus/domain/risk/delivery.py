"""How a bilateral supply contract actually delivered: allocations against nominations and DCQ.

Upstream supply on a daily contract quantity (DCQ) is nominated each day by the buyer within
the contract's swing, renominated during the day, and finally allocated by the TSO or the
upstream system (Gassco, the entry TSO) at the delivery point. Three questions follow:

* **Did the seller deliver what was nominated?** Deviation per gas day is allocated minus
  nominated; days outside the contract's ``nomination_tolerance_pct`` are counted, short and
  long separately, and the absolute deviation is the volume the desk had to balance at the
  hub (an imbalance the desk pays for, not the seller, unless the contract says otherwise).
* **How volatile is the delivery?** Standard deviation and coefficient of variation of the
  daily allocation, and the 7-day trend against DCQ, so a field in decline or a seller
  under-delivering shows before month-end.
* **Was the swing used within the contract?** Days the allocation sits outside
  ``delivery_tolerance_pct`` of DCQ.

A day with no nomination or no allocation is counted as missing, never as zero.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DeliveryDay:
    gas_day: date
    nominated_mwh: float | None
    allocated_mwh: float | None


@dataclass(frozen=True)
class DeliveryTerms:
    contract_id: str
    contract_name: str
    hub: str
    dcq_mwh: float
    nomination_tolerance_pct: float
    delivery_tolerance_pct: float
    tso: str = ""


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _stdev(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def delivery_performance(terms: DeliveryTerms, days: Iterable[DeliveryDay]) -> dict[str, object]:
    """Summary of one contract over the given gas days (oldest first)."""

    ordered = sorted(days, key=lambda day: day.gas_day)
    allocated = [d.allocated_mwh for d in ordered if d.allocated_mwh is not None]
    paired = [
        (d.nominated_mwh, d.allocated_mwh)
        for d in ordered
        if d.nominated_mwh is not None and d.allocated_mwh is not None
    ]
    deviations = [a - n for n, a in paired]
    nom_tol = terms.nomination_tolerance_pct / 100
    short = sum(1 for n, a in paired if a < n - abs(n) * nom_tol - 1e-9)
    long = sum(1 for n, a in paired if a > n + abs(n) * nom_tol + 1e-9)
    del_tol = terms.delivery_tolerance_pct / 100
    outside_swing = sum(
        1 for a in allocated if abs(a - terms.dcq_mwh) > terms.dcq_mwh * del_tol + 1e-9
    )
    mean = _mean(allocated)
    stdev = _stdev(allocated)
    recent = [d.allocated_mwh for d in ordered[-7:] if d.allocated_mwh is not None]
    recent_mean = _mean(recent)
    trend = None
    if recent_mean is not None and terms.dcq_mwh > 0:
        trend = recent_mean / terms.dcq_mwh - 1
    flags = []
    if paired and (short + long) / len(paired) > 0.2:
        flags.append("deviates from nominations on more than 1 day in 5")
    if trend is not None and trend < -del_tol:
        flags.append(f"last 7 days {100 * trend:+.1f}% against DCQ")
    if stdev is not None and mean and stdev / mean > 0.15:
        flags.append("volatile delivery (CV above 15%)")
    missing = sum(1 for d in ordered if d.nominated_mwh is None or d.allocated_mwh is None)
    return {
        "contract_id": terms.contract_id,
        "contract": terms.contract_name,
        "hub": terms.hub,
        "tso": terms.tso,
        "dcq_mwh_d": round(terms.dcq_mwh, 1),
        "days": len(ordered),
        "missing_days": missing,
        "nominated_mwh": round(sum(n for n, _ in paired), 1),
        "allocated_mwh": round(sum(allocated), 1),
        "net_deviation_mwh": round(sum(deviations), 1),
        "imbalance_mwh": round(sum(abs(v) for v in deviations), 1),
        "mean_abs_deviation_mwh_d": None
        if not deviations
        else round(sum(abs(v) for v in deviations) / len(deviations), 1),
        "max_shortfall_mwh_d": round(min([0.0, *deviations]), 1),
        "short_days": short,
        "long_days": long,
        "outside_swing_days": outside_swing,
        "mean_allocated_mwh_d": None if mean is None else round(mean, 1),
        "stdev_allocated_mwh_d": None if stdev is None else round(stdev, 1),
        "cv_pct": None if stdev is None or not mean else round(100 * stdev / mean, 1),
        "trend_7d_vs_dcq_pct": None if trend is None else round(100 * trend, 1),
        "flags": "; ".join(flags),
        "status": "watch" if flags else "ok",
    }


def daily_series(terms: DeliveryTerms, days: Iterable[DeliveryDay]) -> list[dict[str, object]]:
    rows = []
    for day in sorted(days, key=lambda item: item.gas_day):
        deviation = (
            None
            if day.nominated_mwh is None or day.allocated_mwh is None
            else round(day.allocated_mwh - day.nominated_mwh, 1)
        )
        band = abs(day.nominated_mwh or 0.0) * terms.nomination_tolerance_pct / 100
        outside = None
        if deviation is not None and deviation < -band - 1e-9:
            outside = "short"
        elif deviation is not None and deviation > band + 1e-9:
            outside = "long"
        rows.append(
            {
                "gas_day": day.gas_day.isoformat(),
                "outside_tolerance": outside,
                "dcq_mwh": terms.dcq_mwh,
                "nominated_mwh": day.nominated_mwh,
                "allocated_mwh": day.allocated_mwh,
                "deviation_mwh": deviation,
            }
        )
    return rows
