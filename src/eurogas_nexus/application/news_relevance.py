"""Which news items touch the firm's book, and whose work each one changes (NEWS-1).

The firm's exposures are read from the store, never typed: active contracts and their delivery
hub (``upstream_resource_contracts``, the hub resolved from the delivery point through the
ontology), open cargoes with their vessel and destination terminal (``lng_cargoes``), and the
hubs of the nomination steps recorded over the last :data:`NOMINATION_DAYS` gas days
(``gas_day_nomination_events``). An item touches an exposure when it names, deterministically:

* the vessel of an open cargo (the LNG desk, ``trader`` in the cargo route), or the cargo's
  destination terminal;
* a hub the firm holds a contract at (the trader), directly or through an asset that sits in
  or lands into that hub's market area (``domain/news/tagging``);
* a hub the firm nominates at (the scheduler).

Each match says why ("names Langeled, which lands at NBP, where contract C-12 delivers"), the
book it is in, and the platform's own figure (the contract's daily quantity, the cargo's
energy and ETA). The caller sees only matches in books they may see.

新闻与账簿的关联：按合同交付枢纽、在途船货（船名/接收站）与近期提名枢纽确定性匹配。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.news.tagging import tag_text

NOMINATION_DAYS = 7
OPEN_CARGO_STATUSES = ("loading", "laden", "discharging")
#: The role whose work a match changes, and the job functions that role is.
ROLE_FUNCTIONS: dict[str, tuple[str, ...]] = {
    "trader": ("TRADER",),
    "lng": ("TRADER",),
    "scheduler": ("OPERATIONS",),
}
_WEIGHT = {"vessel": 3, "terminal": 3, "contract": 2, "nomination": 2}


@dataclass(frozen=True)
class Exposure:
    """One thing the firm holds that news can touch."""

    kind: str  # contract, cargo, nomination
    ref: str
    book_id: str | None
    label: str
    hubs: tuple[str, ...] = ()
    vessel: str | None = None
    terminal_ids: tuple[str, ...] = ()
    #: The platform's own figure for it, as one plain line with units.
    figure: str = ""
    source: str = ""


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _quantity(value: Any) -> str:
    number = float(value)
    return f"{number:,.0f}" if abs(number) >= 100 else f"{number:,.1f}".rstrip("0").rstrip(".")


def firm_exposures(session, *, now: datetime) -> list[Exposure]:
    """Every exposure the store holds (see the module text), in all books."""

    from eurogas_nexus.db.models import (
        GasDayNominationEventRecord,
        LngCargoRecord,
        UpstreamResourceContractRecord,
    )
    from eurogas_nexus.domain.ontology.identity import resolve_hub

    out: list[Exposure] = []
    for row in (
        session.query(UpstreamResourceContractRecord)
        .filter(UpstreamResourceContractRecord.retired_at_utc.is_(None))
        .limit(5_000)
    ):
        hub = resolve_hub(row.delivery_point_name).hub
        if not hub:
            continue
        out.append(
            Exposure(
                kind="contract",
                ref=row.contract_id,
                book_id=row.book_id,
                label=f"contract {row.contract_name}",
                hubs=(hub,),
                figure=(
                    f"contract {row.contract_name} delivers "
                    f"{_quantity(row.delivery_quantity_mwh_per_day)} MWh/d at {hub}, gas year "
                    f"{row.gas_year}"
                ),
                source=f"contract:{row.contract_id}",
            )
        )
    for row in (
        session.query(LngCargoRecord)
        .filter(LngCargoRecord.status.in_(OPEN_CARGO_STATUSES))
        .limit(2_000)
    ):
        terminal = row.destination_terminal or ""
        terminal_ids = tuple(
            e.entity_id for e in tag_text(terminal).entities if e.kind == "terminal"
        )
        hubs = tuple(sorted({h for e in tag_text(terminal).entities for h in e.hubs}))
        eta = _aware(row.eta_utc)
        energy = f", {_quantity(row.energy_gwh)} GWh" if row.energy_gwh is not None else ""
        out.append(
            Exposure(
                kind="cargo",
                ref=row.cargo_id,
                book_id=row.book_id,
                label=f"cargo on {row.vessel_name}",
                hubs=hubs,
                vessel=row.vessel_name,
                terminal_ids=terminal_ids,
                figure=(
                    f"cargo on {row.vessel_name} ({row.status}) to {terminal or 'no terminal'}"
                    + (f", ETA {eta:%d %b %Y %H:%M} UTC" if eta else "") + energy
                ),
                source=f"cargo:{row.cargo_id}",
            )
        )
    since = (now - timedelta(days=NOMINATION_DAYS)).date()
    seen: set[tuple[str, str | None]] = set()
    for row in (
        session.query(GasDayNominationEventRecord.hub, GasDayNominationEventRecord.book_id)
        .filter(GasDayNominationEventRecord.gas_day >= since)
        .distinct()
        .limit(2_000)
    ):
        key = (str(row[0]).upper(), row[1])
        if key in seen or not row[0]:
            continue
        seen.add(key)
        out.append(
            Exposure(
                kind="nomination",
                ref=f"{key[0]}:{key[1] or '-'}",
                book_id=key[1],
                label=f"nominations at {key[0]}",
                hubs=(key[0],),
                figure=f"nomination steps recorded at {key[0]} in the last {NOMINATION_DAYS} "
                "gas days",
                source=f"nominations:{key[0]}",
            )
        )
    return out


def matches(item: dict[str, Any], exposures: list[Exposure],
            visible_books: set[str] | None = None) -> list[dict[str, Any]]:
    """The exposures an item touches, strongest first, each with its reason and role.

    ``item`` is a stored row as a dict (``entities``, ``hubs``). ``visible_books`` limits the
    matches to books a caller may see (``None``: every book).
    """

    entities = item.get("entities") or []
    item_hubs = set(item.get("hubs") or [])
    vessels = {str(e.get("name", "")).casefold() for e in entities if e.get("kind") == "vessel"}
    terminals = {e.get("entity_id") for e in entities if e.get("kind") == "terminal"}
    out = []
    for exposure in exposures:
        if visible_books is not None and (exposure.book_id is None
                                          or exposure.book_id not in visible_books):
            continue
        reason = None
        basis = None
        if exposure.kind == "cargo":
            if exposure.vessel and exposure.vessel.casefold() in vessels:
                reason, basis = f"names the vessel {exposure.vessel}", "vessel"
            elif terminals & set(exposure.terminal_ids):
                reason, basis = "names the cargo's destination terminal", "terminal"
        else:
            shared = sorted(item_hubs & set(exposure.hubs))
            if shared:
                via = [e.get("name") for e in entities
                       if shared[0] in (e.get("hubs") or []) and e.get("kind") != "hub"]
                how = f" (through {via[0]})" if via else ""
                reason = f"names {shared[0]}{how}"
                basis = exposure.kind
        if reason is None:
            continue
        role = {"cargo": "lng", "contract": "trader", "nomination": "scheduler"}[exposure.kind]
        out.append(
            {
                "kind": exposure.kind,
                "ref": exposure.ref,
                "book_id": exposure.book_id,
                "label": exposure.label,
                "role": role,
                "for": list(ROLE_FUNCTIONS[role]),
                "reason": reason,
                "basis": basis,
                "weight": _WEIGHT[basis or exposure.kind],
                "figure": exposure.figure,
                "source": exposure.source,
            }
        )
    out.sort(key=lambda m: (-m["weight"], m["kind"], m["ref"]))
    return out


def relevance_score(found: list[dict[str, Any]]) -> int:
    """Higher means the item touches more of the caller's book (0: none)."""

    return sum(m["weight"] for m in found)


__all__ = [
    "NOMINATION_DAYS",
    "ROLE_FUNCTIONS",
    "Exposure",
    "firm_exposures",
    "matches",
    "relevance_score",
]
