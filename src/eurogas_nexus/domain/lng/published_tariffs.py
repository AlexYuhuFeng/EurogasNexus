"""Published LNG terminal and entry charges, per tariff period, as a cargo prices them.

The figures live in ``reference_data/lng_terminal_published_tariffs.json``: one row per published
charge, transcribed by a person from the regulator's or operator's own document, with its URL,
publication date, the date it was read, the publisher's status (FINAL or INDICATIVE) and a terms
note. Nothing is fetched here. This module picks the charges in force for an arrival month and
turns them into what a cargo pays:

* **in force** when ``valid_from <= month start <= valid_to`` (open ends allowed);
* else **carried forward**: the latest period that has already ended, when the next one is not
  yet published (DET's price sheet is approved each December). A period that starts after the
  arrival month is never used for it (EET's cap from September 2027 does not price January);
* a terminal with no published price for a new booking (exempt, contracted, negotiated) has no
  regas charge and says why (``not_published``); none is ever invented.

Conversions (each stated in the result):

* ``per_berthing``: the figure per cargo; ``per_mwh_unloaded``: times the MWh unloaded;
* ``eur_per_bcm_year``: a long-term throughput price, at full utilisation and the desk's
  11.0 kWh/m3 (``domain/market/units.DESK_ASSUMED_GCV_KWH_PER_M3``);
* entry ``p_kwh_d`` (NTS daily firm capacity at 100 % load factor) and ``p_kwh``: x 10 to
  GBP/MWh; ``eur_mwh_d_year`` (French PITTM, daily product = 1/365 of the yearly term): / 365.

Pure and deterministic.

公开发布的 LNG 接收站及管网入口费率（按费率期选取；仅转录、带来源与日期，不臆造数值）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from typing import Any

from eurogas_nexus.domain.market.units import DESK_ASSUMED_GCV_KWH_PER_M3

RESOURCE = "lng_terminal_published_tariffs.json"
SCHEMA_VERSION = "eurogas.lng-terminal-published-tariffs/1"
KINDS = frozenset({"regas", "gas_in_kind", "entry_capacity", "entry_commodity", "fsru_co2"})
BASES = frozenset(
    {
        "per_berthing",
        "per_mwh_unloaded",
        "eur_per_bcm_year",
        "percent_in_kind",
        "p_kwh_d",
        "p_kwh",
        "eur_mwh_d_year",
        "tco2_per_gj_fuel",
    }
)
STATUSES = frozenset({"FINAL", "INDICATIVE"})
#: MWh in one bcm at the desk's gross calorific value.
MWH_PER_BCM = Decimal(str(DESK_ASSUMED_GCV_KWH_PER_M3)) * Decimal(1_000_000)
_TEN = Decimal(10)
_DAYS = Decimal(365)


class PublishedTariffError(ValueError):
    """The reference file is malformed."""


@dataclass(frozen=True)
class PublishedCharge:
    """One published figure of one terminal or entry point, as the publisher stated it."""

    charge_id: str
    kind: str
    basis: str
    value: Decimal
    currency: str
    published_unit: str
    product: str
    valid_from: date | None
    valid_to: date | None
    period_label: str
    status: str
    published_on: date | None
    read_on: date
    source_title: str
    source_url: str
    terms: str
    note: str = ""
    months: tuple[int, ...] = ()

    def in_force(self, day: date) -> bool:
        """Whether the charge's period covers ``day``."""

        if self.valid_from is not None and day < self.valid_from:
            return False
        return self.valid_to is None or day <= self.valid_to


@dataclass(frozen=True)
class PublishedTerminal:
    """A terminal, its regime and every charge held for it."""

    terminal_id: str
    name: str
    operator: str
    country: str
    hub: str
    regime: str
    entry_tso: str
    entry_point: str
    charges: tuple[PublishedCharge, ...]
    not_published: str = ""
    #: A gated operator (``lng_terminal_tariff_register.OPERATOR_TERMS``): no figure is held.
    permission_operator: str | None = None
    #: Ids a firm's own terms may use for this terminal (``gate`` for ``gate-terminal``): the
    #: firm's row then stands for it, with this reference filling only what the firm lacks.
    aliases: tuple[str, ...] = ()

    def known_as(self, terminal_id: str) -> bool:
        """Whether a firm's terminal id names this terminal."""

        key = terminal_id.lower()
        return key == self.terminal_id or key in self.aliases


@dataclass(frozen=True)
class ChargeUse:
    """A charge chosen for one arrival month; ``carried_forward`` when its period has ended."""

    charge: PublishedCharge
    carried_forward: bool = False

    def version(self) -> dict[str, Any]:
        """The version a result names: period, status, dates, source and terms."""

        charge = self.charge
        return {
            "charge_id": charge.charge_id,
            "period": charge.period_label,
            "valid_from": charge.valid_from.isoformat() if charge.valid_from else None,
            "valid_to": charge.valid_to.isoformat() if charge.valid_to else None,
            "status": charge.status,
            "published_on": charge.published_on.isoformat() if charge.published_on else None,
            "read_on": charge.read_on.isoformat(),
            "source_title": charge.source_title,
            "source_url": charge.source_url,
            "terms": charge.terms,
            "published_unit": charge.published_unit,
            "published_value": float(charge.value),
            "carried_forward": self.carried_forward,
            "note": charge.note,
        }


def _day(text: Any) -> date | None:
    return None if text in (None, "") else date.fromisoformat(str(text))


def _charge(row: dict[str, Any]) -> PublishedCharge:
    kind, basis, status = row["kind"], row["basis"], row["status"]
    if kind not in KINDS or basis not in BASES or status not in STATUSES:
        raise PublishedTariffError(f"{row.get('charge_id')}: kind, basis or status unknown")
    if not str(row.get("source_url", "")).startswith("https://"):
        raise PublishedTariffError(f"{row['charge_id']}: an https source is required")
    return PublishedCharge(
        charge_id=row["charge_id"],
        kind=kind,
        basis=basis,
        value=Decimal(str(row["value"])),
        currency=row["currency"],
        published_unit=row["published_unit"],
        product=row.get("product") or "any",
        valid_from=_day(row.get("valid_from")),
        valid_to=_day(row.get("valid_to")),
        period_label=row.get("period_label") or "",
        status=status,
        published_on=_day(row.get("published_on")),
        read_on=date.fromisoformat(row["read_on"]),
        source_title=row["source_title"],
        source_url=row["source_url"],
        terms=row["terms"],
        note=row.get("note") or "",
        months=tuple(int(month) for month in row.get("months") or ()),
    )


def parse_published(payload: dict[str, Any]) -> tuple[PublishedTerminal, ...]:
    """Terminals from the reference payload.

    Raises:
        PublishedTariffError: unknown schema, kind, basis or status, or a non-https source.
    """

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PublishedTariffError("unknown schema_version")
    terminals = []
    for row in payload["terminals"]:
        entry = row.get("entry") or {}
        charges = tuple(_charge(item) for item in row.get("charges") or ())
        if row.get("permission_operator") and charges:
            raise PublishedTariffError(f"{row['terminal_id']}: a gated operator holds no figure")
        terminals.append(
            PublishedTerminal(
                terminal_id=row["terminal_id"],
                name=row["name"],
                operator=row["operator"],
                country=row["country"],
                hub=row["hub"],
                regime=row["regime"],
                entry_tso=entry.get("tso") or "",
                entry_point=entry.get("point") or "",
                charges=charges,
                not_published=row.get("not_published") or "",
                permission_operator=row.get("permission_operator"),
                aliases=tuple(str(alias).lower() for alias in row.get("aliases") or ()),
            )
        )
    return tuple(terminals)


@lru_cache(maxsize=1)
def published_terminals() -> tuple[PublishedTerminal, ...]:
    """Every terminal in the shipped reference file."""

    text = resources.files("eurogas_nexus.reference_data").joinpath(RESOURCE).read_text("utf-8")
    return parse_published(json.loads(text))


def published_terminal(terminal_id: str) -> PublishedTerminal | None:
    """One terminal by id, or None."""

    return next((t for t in published_terminals() if t.terminal_id == terminal_id), None)


def select(
    terminal: PublishedTerminal, kind: str, arrival: date, product: str = "spot"
) -> list[ChargeUse]:
    """The charges of ``kind`` that price a cargo arriving in ``arrival``'s month.

    A product-specific figure (``spot``/``term``) is taken for the asked product, else for the
    only product published; ``any`` figures always apply. Seasonal figures (``months``) apply in
    their months. Charges in force first; else the latest ended period, carried forward.
    """

    rows = [
        charge
        for charge in terminal.charges
        if charge.kind == kind and (not charge.months or arrival.month in charge.months)
    ]
    products = {charge.product for charge in rows} - {"any"}
    wanted = product if product in products else (sorted(products)[0] if products else None)
    rows = [charge for charge in rows if charge.product in {"any", wanted}]
    current = [charge for charge in rows if charge.in_force(arrival)]
    if current:
        return [ChargeUse(charge) for charge in current]
    ended = [charge for charge in rows if charge.valid_to is not None and charge.valid_to < arrival]
    if not ended:
        return []
    latest = max(charge.valid_to for charge in ended)
    return [
        ChargeUse(charge, carried_forward=True) for charge in ended if charge.valid_to == latest
    ]


def regas_total(uses: list[ChargeUse], q_del_mwh: Decimal) -> Decimal | None:
    """The regas charge for one cargo, in the charges' currency, or None with no figure."""

    if not uses:
        return None
    total = Decimal(0)
    for use in uses:
        charge = use.charge
        if charge.basis == "per_berthing":
            total += charge.value
        elif charge.basis == "per_mwh_unloaded":
            total += charge.value * q_del_mwh
        elif charge.basis == "eur_per_bcm_year":
            total += charge.value / MWH_PER_BCM * q_del_mwh
    return total


def entry_per_mwh(uses: list[ChargeUse]) -> Decimal | None:
    """Entry capacity and commodity per MWh sent out, in the charges' currency."""

    if not uses:
        return None
    total = Decimal(0)
    for use in uses:
        charge = use.charge
        if charge.basis in {"p_kwh_d", "p_kwh"}:
            total += charge.value * _TEN
        elif charge.basis == "eur_mwh_d_year":
            total += charge.value / _DAYS
    return total


def percent(uses: list[ChargeUse]) -> Decimal | None:
    """A percentage (gas in kind) from the first use, or None."""

    return uses[0].charge.value if uses else None


def weakest_status(uses: list[ChargeUse]) -> str:
    """INDICATIVE when any figure is indicative or carried forward, else FINAL."""

    if any(use.charge.status != "FINAL" or use.carried_forward for use in uses):
        return "INDICATIVE"
    return "FINAL"


__all__ = [
    "MWH_PER_BCM",
    "ChargeUse",
    "PublishedCharge",
    "PublishedTariffError",
    "PublishedTerminal",
    "entry_per_mwh",
    "parse_published",
    "percent",
    "published_terminal",
    "published_terminals",
    "regas_total",
    "select",
    "weakest_status",
]
