"""SDK client for a cargo in transit as one plan (``/api/lng/cargoes``).

A firm cargo at sea is followed from its ETA to the hub months its gas lands in: berth against
the regas slot window, boil-off to berth, gas in kind, send-out by gas day (06:00 CET), the
physical and hedged energy per hub and delivery month, and what to do about any gap (roll, sell,
buy back, short-notice cover, find a slot, demurrage). Decision support only: nothing here
trades, nominates or books a slot.

Typical use::

    from eurogas_nexus_sdk.lng_cargo_plan import fetch_cargo_plan, try_cargo_eta

    plan = fetch_cargo_plan("http://127.0.0.1:8000", "SAB-0412")
    for month in plan.months:
        print(month.hub, month.month, month.physical_mwh, month.hedge_mwh, month.net_mwh)
    change = try_cargo_eta("http://127.0.0.1:8000", "SAB-0412", eta_utc="2026-12-25T12:00:00Z")
    print(change["headline"])

Every call needs the deployment token (``EUROGAS_NEXUS_PUBLIC_API_TOKEN``) and, for a book's
cargoes, an identity (``EUROGAS_NEXUS_IDENTITY_BEARER``) whose role reads that book.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from eurogas_nexus_sdk import _http


class CargoPlanMonth(BaseModel):
    """Physical and hedged energy for one hub and delivery month."""

    model_config = ConfigDict(extra="allow")

    hub: str
    month: str
    physical_mwh: float
    hedge_mwh: float
    net_mwh: float
    trading: bool


class CargoPlanSuggestion(BaseModel):
    """One thing to do about the plan; ``kind`` is roll, sell, buy_back, short_notice,
    find_slot, demurrage or deadline."""

    model_config = ConfigDict(extra="allow")

    kind: str
    text: str
    mwh: float | None = None


class CargoPlan(BaseModel):
    """The plan for one firm cargo, with the inputs it used and their sources."""

    model_config = ConfigDict(extra="allow")

    cargo_id: str
    slot_status: str
    berth_utc: datetime | None = None
    boil_off_mwh: float
    gas_in_kind_mwh: float
    delivered_mwh: float
    months: list[CargoPlanMonth]
    suggestions: list[CargoPlanSuggestion]
    inputs: list[dict[str, Any]]
    last_change: dict[str, Any] | None = None
    advisory: str | None = None


def _base(base_url: str) -> str:
    return base_url.rstrip("/")


def _data(response: Any) -> Any:
    response.raise_for_status()
    return response.json()["data"]


def _plan(data: dict[str, Any]) -> CargoPlan:
    plan = data["plan"]
    return CargoPlan(
        **{key: value for key, value in plan.items() if key not in {"cargo_id", "months"}},
        cargo_id=data["cargo"]["cargo_id"],
        months=plan["months"],
        inputs=data["inputs"],
        last_change=data.get("last_change"),
        advisory=data.get("advisory"),
    )


def fetch_cargo_plans(base_url: str) -> list[dict[str, Any]]:
    """Return one line per firm cargo in transit: slot status, last change and next step.

    Args:
        base_url: Base URL of the backend server.
    """

    return _data(_http.get(f"{_base(base_url)}/api/lng/cargoes/plans"))


def fetch_cargo_plan(
    base_url: str,
    cargo_id: str,
    *,
    berth_delay_hours: float = 0.0,
    laytime_hours: float = 36.0,
    demurrage_per_day: float | None = None,
) -> CargoPlan:
    """Return the plan for one firm cargo, from its ETA to the hub months.

    Args:
        base_url: Base URL of the backend server.
        cargo_id: The cargo's id as the ETRM import recorded it.
        berth_delay_hours: Expected wait at the berth beyond the slot (queue, weather).
        laytime_hours: Laytime allowed before demurrage starts.
        demurrage_per_day: Demurrage rate in the charter's currency; ``None`` for none.

    Raises:
        httpx.HTTPStatusError: 404 ``cargo_not_found`` for a market cargo or an unknown id,
            422 when the inputs cannot describe the cargo (the detail names what is missing).
    """

    params: dict[str, Any] = {
        "berth_delay_hours": berth_delay_hours,
        "laytime_hours": laytime_hours,
    }
    if demurrage_per_day is not None:
        params["demurrage_per_day"] = demurrage_per_day
    url = f"{_base(base_url)}/api/lng/cargoes/{quote(cargo_id, safe='')}/plan"
    return _plan(_data(_http.get(url, params=params)))


def try_cargo_eta(
    base_url: str,
    cargo_id: str,
    *,
    eta_utc: datetime | str | None = None,
    slot_id: str | None = None,
    berth_delay_hours: float = 0.0,
    laytime_hours: float = 36.0,
    demurrage_per_day: float | None = None,
) -> dict[str, Any]:
    """Compare the stored plan with one under a changed schedule; nothing is stored.

    Returns the change: ``headline``, ``boil_off_change_mwh``, ``delivered_change_mwh``,
    the month shifts, and the plan ``before`` and ``after``.
    """

    body: dict[str, Any] = {
        "berth_delay_hours": berth_delay_hours,
        "laytime_hours": laytime_hours,
    }
    if eta_utc is not None:
        body["eta_utc"] = eta_utc.isoformat() if isinstance(eta_utc, datetime) else eta_utc
    if slot_id is not None:
        body["slot_id"] = slot_id
    if demurrage_per_day is not None:
        body["demurrage_per_day"] = demurrage_per_day
    url = f"{_base(base_url)}/api/lng/cargoes/{quote(cargo_id, safe='')}/plan/what-if"
    return _data(_http.post(url, json=body))["change"]


def record_cargo_hedges(
    base_url: str, cargo_id: str, legs: list[dict[str, Any]]
) -> dict[str, Any]:
    """Replace the hedge legs that cover a cargo (needs a role with portfolio write).

    Each leg is ``{"hub": "TTF", "month": "2027-01", "mwh": -250000, "reference": "EEX 123"}``;
    a short hedge is negative. The previous set is retired, the change is audited and a
    ``cargo.changed`` market event is published so dependent results recompute.
    """

    url = f"{_base(base_url)}/api/lng/cargoes/{quote(cargo_id, safe='')}/hedges"
    return _data(_http.put(url, json={"legs": legs}))
