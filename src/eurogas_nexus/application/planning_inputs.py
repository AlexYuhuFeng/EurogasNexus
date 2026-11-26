"""What Book -> Planning starts from (AGENTS rule 19, live by default).

The nomination and storage assessments open on what the product already holds, not on empty
fields: the contracts in execution on the gas day (a picker, each with its DCQ, the annual
quantity over its delivery window and that window), the nomination windows of the TSO calendar
(declared windows, else the network-code defaults, said as such), and the storage facilities
with their latest inventory. The person may still type any field; the result then says which
inputs were entered by hand.

Planning only (AGENTS rule 8): nothing here nominates, books or submits.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time
from typing import Any

from eurogas_nexus.domain.market.hub_cutoffs import default_cutoffs
from eurogas_nexus.domain.ontology.markets import find_market


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def contract_choices(
    contracts: Iterable[Any],
    gas_day: date,
    *,
    window_of,
    hub_of,
    nominated: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Contracts delivering on ``gas_day``: id, name, hub, DCQ, ACQ over the window, window.

    ``window_of(contract)`` gives the first and last gas day (None when it cannot be read) and
    ``hub_of(contract)`` the hub; ``nominated`` the day's nominated MWh per contract, when held.
    """

    out = []
    for contract in contracts:
        if getattr(contract, "retired_at_utc", None) is not None:
            continue
        window = window_of(contract)
        if window is None or not (window[0] <= gas_day <= window[1]):
            continue
        dcq = float(contract.delivery_quantity_mwh_per_day or 0.0)
        days = (window[1] - window[0]).days + 1
        out.append(
            {
                "contract_id": contract.contract_id,
                "name": contract.contract_name or contract.contract_id,
                "hub": hub_of(contract),
                "dcq_mwh": round(dcq, 3),
                "acq_mwh": round(dcq * days, 1),
                "delivery_start": window[0].isoformat(),
                "delivery_end": window[1].isoformat(),
                "nomination_tolerance_pct": float(contract.nomination_tolerance_pct or 0.0),
                "nominated_mwh": None if nominated is None else nominated.get(contract.contract_id),
            }
        )
    return sorted(out, key=lambda item: (item["hub"] or "", item["name"]))


def window_choices(
    window_rows: Iterable[Any], hub: str | None, gas_day: date
) -> dict[str, Any]:
    """The TSO calendar's windows for the hub's country: declared ones, else the defaults.

    Each window carries its source; ``basis`` is ``held`` for a declared window and
    ``assumption`` for the network-code default (the screen says which).
    """

    market = find_market(hub) if hub else None
    country = ((market.country if market else "") or "").upper()
    held = [
        row for row in window_rows if not country or str(row.country).upper() == country
    ]
    if held:
        return {
            "basis": "held",
            "windows": [
                {
                    "window_id": row.window_id,
                    "name": row.name,
                    "opens_at": _hhmm(row.opens_at),
                    "closes_at": _hhmm(row.closes_at),
                    "maximum_change_mwh": row.maximum_change_mwh,
                    "source": row.source_reference,
                }
                for row in sorted(held, key=lambda item: item.opens_at)
            ],
        }
    # No declared window: the network-code default, said as an assumption. Renominations run
    # from the start of the gas day to the last renomination; window clocks are UTC, as the
    # nomination engine and the calendar read them (domain/market/nomination_windows.py).
    from eurogas_nexus.domain.market.nomination_windows import gas_day_bounds_utc

    start, _ = gas_day_bounds_utc(gas_day)
    last = next(cut for cut in default_cutoffs(gas_day) if cut.key == "last_renomination")
    windows = [
        {
            "window_id": "default-renomination",
            "name": "last_renomination",
            "opens_at": _hhmm(start.time()),
            "closes_at": _hhmm(last.at_utc.time()),
            "maximum_change_mwh": None,
            "source": last.source,
        }
    ]
    return {"basis": "assumption", "windows": windows}


def storage_choices(facilities: Iterable[Any], inventory_of) -> list[dict[str, Any]]:
    """Each active facility with its latest inventory (None when no observation is held)."""

    out = []
    for facility in facilities:
        latest = inventory_of(facility.facility_id)
        out.append(
            {
                "facility_id": facility.facility_id,
                "name": facility.name,
                "hub": facility.market_hub,
                "inventory_mwh": None if latest is None else float(latest.inventory_mwh),
                "inventory_as_of": None
                if latest is None
                else _iso(latest.observed_at_utc),
                "minimum_inventory_mwh": facility.minimum_inventory_mwh,
                "maximum_inventory_mwh": facility.maximum_inventory_mwh,
                "maximum_injection_mwh": facility.maximum_injection_mwh,
                "maximum_withdrawal_mwh": facility.maximum_withdrawal_mwh,
                "injection_efficiency": facility.injection_efficiency,
                "withdrawal_efficiency": facility.withdrawal_efficiency,
                "injection_cost_gbp_mwh": facility.injection_cost_gbp_mwh,
                "withdrawal_cost_gbp_mwh": facility.withdrawal_cost_gbp_mwh,
                "terminal_inventory_mwh": facility.terminal_inventory_mwh,
                "source": facility.source_reference,
            }
        )
    return sorted(out, key=lambda item: item["name"])


def _iso(value: datetime) -> str:
    return value.isoformat()
