"""LNG-4: substitute supply from across the portfolio for a delivery a disruption leaves short.

The owner (2026-11-25): a delayed cargo is not one cargo with the gas business disconnected
from it; when a customer would be short, the desk also looks at its upstream gas and at buying
at a hub and sending it to the customer. This module reads what the book and the market data
hold and hands the engine (``domain/lng/disruption.SubstituteSource``) one source per way the
gas can reach each obligation's point:

* **upstream**: a supply contract of the book (``upstream_resource_contracts``, not retired)
  with a delivery tolerance: its swing above the contracted quantity, priced by the contract's
  own price terms where they evaluate (``application/contract_pricing``), else its stated price,
  in EUR at the reader's FX choice, plus the transport from its delivery point;
* **hub**: gas bought at a hub the book prices, at the month price plus the short-notice
  premium, plus the transport from that hub to the obligation's point;
* **storage**: the firm holds no storage contract as a typed record yet (``contract_costs``
  says so too), so no storage source is read; the engine takes one when a holding exists, and
  costs it at the value of the gas in the month it would otherwise have been withdrawn.

Two functions are the integration points a later source-precedence resolver replaces:
:func:`_transport_cost` here (capacity the firm holds first, then the public tariff, through
``contract_costs.transport_leg_cost``) and ``lng_demurrage._fx_rate`` for every currency.
A source whose transport or price is not held is left out and named in the warnings: a cost
the data does not hold is never taken as zero.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from eurogas_nexus.application.lng_demurrage import FxBook, _fx_rate
from eurogas_nexus.domain.lng.disruption import Obligation, SubstituteSource


@dataclass(frozen=True)
class TransportCost:
    """The cost per MWh of moving gas from one point to another, as :func:`_transport_cost`
    answers it: in EUR (``None`` when not held), its basis, source and what was tried."""

    from_point: str
    to_point: str
    eur_mwh: float | None
    basis: str
    source: str
    tried: tuple[str, ...] = ()
    fx: dict[str, Any] | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_point,
            "to": self.to_point,
            "eur_mwh": self.eur_mwh,
            "basis": self.basis,
            "source": self.source,
            "tried": list(self.tried),
            "fx": self.fx,
            "note": self.note,
        }


def _transport_cost(
    session,
    from_point: str,
    to_point: str,
    gas_day: date,
    context: FxBook | None,
) -> TransportCost:
    """The one transport cost the LNG-4 substitute options use, per MWh in EUR.

    For now: capacity the firm holds on the leg (its charge is sunk, so using it costs nil),
    then the published tariffs along the cheapest proven route, else not held
    (``contract_costs.transport_leg_cost``), converted to EUR through ``_fx_rate``.
    Integration point: a contracted-then-public-tariff precedence resolver replaces this body;
    callers keep the same answer.
    """

    from eurogas_nexus.application.contract_costs import transport_leg_cost

    tried = ("capacity the firm holds on the leg", "public tariff on the cheapest proven route")
    if from_point.upper() == to_point.upper():
        return TransportCost(from_point, to_point, 0.0, "same_point", "no transport needed")
    try:
        answer = transport_leg_cost(
            session, None, from_point=from_point, to_point=to_point, gas_day=gas_day
        )
    except Exception as exc:  # noqa: BLE001 - a register that cannot be read is "not held"
        return TransportCost(
            from_point, to_point, None, "missing", "tariff register", tried, note=str(exc)
        )
    if answer.get("value") is None:
        return TransportCost(
            from_point,
            to_point,
            None,
            "missing",
            answer.get("source_ref") or "none",
            tried,
            note=answer.get("note"),
        )
    currency = answer.get("currency") or "EUR"
    fx = _fx_rate(session, currency, "EUR", gas_day, context)
    if fx.rate is None:
        return TransportCost(
            from_point,
            to_point,
            None,
            "missing",
            answer.get("source_ref") or "",
            tried,
            fx=fx.as_dict(),
            note=f"tariff in {currency} not converted: {fx.missing}",
        )
    basis = answer.get("basis") or "public_tariff"
    words = {
        "contract_sunk": "capacity the firm holds (sunk)",
        "public_tariff": "public tariff",
    }.get(basis, basis)
    return TransportCost(
        from_point,
        to_point,
        round(float(answer["value"]) * fx.rate, 6),
        basis,
        f"{words}: {answer.get('source_ref')}",
        tried,
        fx=None if currency == "EUR" else fx.as_dict(),
        note=answer.get("note"),
    )


def _gas_year(label: str | None) -> tuple[date, date] | None:
    found = re.search(r"(\d{4})", str(label or ""))
    if not found:
        return None
    year = int(found.group(1))
    return date(year, 10, 1), date(year + 1, 9, 30)


@dataclass
class Substitutes:
    sources: list[SubstituteSource] = field(default_factory=list)
    inputs: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _contracts(session, book_id: str):
    from eurogas_nexus.db.models import UpstreamResourceContractRecord

    return (
        session.query(UpstreamResourceContractRecord)
        .filter(
            UpstreamResourceContractRecord.book_id == book_id,
            UpstreamResourceContractRecord.retired_at_utc.is_(None),
        )
        .order_by(UpstreamResourceContractRecord.contract_id)
        .all()
    )


def _contract_price(session, record, month: str) -> tuple[float | None, str, str]:
    """The contract's price for ``month`` in its currency, and where it came from."""

    from eurogas_nexus.application.contract_pricing import contract_price

    currency = (record.contract_price_currency or "GBP").upper()
    try:
        priced = contract_price(session, None, record, month)
        result = priced.get("result") or {}
        if result.get("value") is not None:
            return (
                float(result["value"]),
                str(result.get("currency") or currency).upper(),
                f"upstream_resource_contract:{record.contract_id} price terms for {month}",
            )
    except Exception:  # noqa: BLE001 - fall back to the stated price, named so
        pass
    return (
        float(record.contract_price_gbp_mwh),
        currency,
        f"upstream_resource_contract:{record.contract_id} stated price",
    )


def load_substitutes(
    session,
    book_id: str,
    obligations: Iterable[Obligation],
    prices: Mapping[tuple[str, str], float],
    *,
    premium_eur_mwh: float,
    premium_source: str,
    fx: FxBook,
    today: date,
) -> Substitutes:
    """One source per way gas held or bought can reach each obligation's point."""

    from eurogas_nexus.application.identity_resolution import load_resolver

    out = Substitutes()
    items = list(obligations)
    if not items:
        return out
    resolver = load_resolver(session)
    hubs = sorted({hub for hub, _month in prices})
    contracts = _contracts(session, book_id)
    for item in items:
        target = item.hub.upper()
        first = max(item.start, today)
        if first > item.end:
            continue
        month = f"{first.year:04d}-{first.month:02d}"
        for hub in hubs:
            if (hub, month) not in prices:
                continue
            transport = _transport_cost(session, hub, target, first, fx)
            if transport.eur_mwh is None:
                out.warnings.append(
                    f"hub gas from {hub} to {item.counterparty} at {target} left out: no "
                    f"transport cost held ({transport.note or transport.source})"
                )
                continue
            source_id = f"hub:{hub}:{item.obligation_id}"
            out.sources.append(
                SubstituteSource(
                    source_id,
                    "hub",
                    f"{hub} gas" + ("" if hub == target else f" moved to {target}"),
                    target,
                    first,
                    item.end,
                    item.mwh_per_day,
                    price_hub=hub,
                    premium_eur_mwh=premium_eur_mwh,
                    transport_eur_mwh=transport.eur_mwh,
                    sources={
                        "gas": f"{hub} month price (the price book) + short notice: "
                        f"{premium_source}",
                        "transport": transport.source,
                        **({"fx": transport.fx["label"]} if transport.fx else {}),
                    },
                )
            )
            out.inputs.append({"input": f"substitute {source_id}", "source": transport.source})
        for record in contracts:
            swing = float(record.delivery_quantity_mwh_per_day or 0.0) * (
                float(record.delivery_tolerance_pct or 0.0) / 100
            )
            if swing <= 0:
                continue
            window = _gas_year(record.gas_year)
            start, end = first, item.end
            if window is not None:
                start, end = max(start, window[0]), min(end, window[1])
            if start > end:
                continue
            delivers = resolver.hub(record.delivery_point_name).hub or record.delivery_point_name
            transport = _transport_cost(session, str(delivers).upper(), target, start, fx)
            if transport.eur_mwh is None:
                out.warnings.append(
                    f"swing of {record.contract_name} to {item.counterparty} left out: no "
                    f"transport cost held from {delivers} to {target}"
                )
                continue
            price, currency, where = _contract_price(session, record, month)
            converted = _fx_rate(session, currency, "EUR", start, fx)
            if price is None or converted.rate is None:
                out.warnings.append(
                    f"swing of {record.contract_name} left out: price in {currency} not "
                    f"converted ({converted.missing})"
                )
                continue
            source_id = f"upstream:{record.contract_id}:{item.obligation_id}"
            out.sources.append(
                SubstituteSource(
                    source_id,
                    "upstream",
                    f"{record.contract_name} swing",
                    target,
                    start,
                    end,
                    swing,
                    price_eur_mwh=round(price * converted.rate, 6),
                    transport_eur_mwh=transport.eur_mwh,
                    sources={
                        "gas": where,
                        "transport": transport.source,
                        **({"fx": converted.text()} if currency != "EUR" else {}),
                    },
                    note=f"tolerance {record.delivery_tolerance_pct:g} % of "
                    f"{record.delivery_quantity_mwh_per_day:,.0f} MWh/d",
                )
            )
            out.inputs.append({"input": f"substitute {source_id}", "source": where})
    return out


__all__ = ["Substitutes", "TransportCost", "_transport_cost", "load_substitutes"]
