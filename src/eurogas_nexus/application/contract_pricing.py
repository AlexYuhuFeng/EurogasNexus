"""A contract's price for a delivery month, from the indices the store holds (CONTRACT_TYPES.md).

The formula is the contract's own (``domain/contracts/price_terms.py``); this module supplies the
index values, each with its class and source, by the live principle:

- a published index for a past or running window: the closes the caller is entitled to
  (``projections.daily_closes``), averaged over the averaging rule's window, per MWh in the
  index's currency; a simulated close makes the input simulated;
- a window not published yet (a future month): the forward curve's mark for the delivery month
  (the position ladder's curve), stated as an estimate of class ``indicative`` (or
  ``simulated`` on the demo desk), never as the index;
- Henry Hub, Brent and JKM from the observations that name them (``HH spot``, EIA, a vendor),
  in their native unit.

An index the store does not hold is named as missing; nothing is guessed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from eurogas_nexus.domain.contracts import kinds
from eurogas_nexus.domain.contracts.price_terms import IndexPoint, PriceIndex, evaluate

_TENOR = {"month_ahead": "month-ahead", "day_ahead": "day-ahead", "pricing_month": "month-ahead"}
_GLOBAL = {"HH": ("HH", "HENRY"), "BRENT": ("BRENT",), "JKM": ("JKM",)}


def _class_of(rows: list[dict[str, Any]]) -> str:
    if any(row.get("simulated") for row in rows):
        return "simulated"
    if rows and all(row.get("settlement") for row in rows):
        return "settlement"
    return "indicative"


class IndexLookup:
    """``lookup(index, first, last)`` over the caller's entitled closes and curve."""

    def __init__(self, session, caller, *, today: date | None = None) -> None:
        self.session = session
        self.caller = caller
        self.today = today or datetime.now(UTC).date()
        self._curve = None

    def __call__(self, index: PriceIndex, first: date, last: date) -> IndexPoint | None:
        code = index.index.upper()
        if code in _GLOBAL:
            return self._global(code, first, last)
        return self._hub(code, index, first, last)

    # ---- European hubs
    def _hub(self, code: str, index: PriceIndex, first: date, last: date) -> IndexPoint | None:
        from eurogas_nexus.application.projections.daily_closes import daily_rows

        tenor = _TENOR.get(index.product)
        if tenor is None:
            return None
        if first <= self.today:
            rows = [
                row
                for row in daily_rows(self.caller, first, min(last, self.today), tenors=(tenor,))
                if row["hub"] == code and row.get("hub_resolved", True) and row["tenor"] == tenor
            ]
            if rows:
                units = {row["unit_mwh"] for row in rows}
                if len(units) == 1:
                    value = sum(row["price_mwh"] for row in rows) / len(rows)
                    latest = max(rows, key=lambda row: row["day"])
                    return IndexPoint(
                        value=value,
                        unit=units.pop(),
                        input_class=_class_of(rows),
                        source_ref=f"{latest['source_system']}: {code} {tenor} closes",
                        as_of=latest["day"].isoformat(),
                        observations=len(rows),
                    )
        if last < self.today:
            return None  # a past window with no close: the index is not held
        return self._forward(code, index, last)

    def _forward(self, code: str, index: PriceIndex, last: date) -> IndexPoint | None:
        """The forward curve's mark for the delivery month: an estimate, labelled as one."""

        from eurogas_nexus.application.position_inputs import (
            CURVE_QUOTE_LOOKBACK_DAYS,
            curve_quotes,
        )
        from eurogas_nexus.core.config import demo_marks_allowed
        from eurogas_nexus.domain.market.forward_curve import build_forward_curve
        from eurogas_nexus.domain.ontology.markets import quote_currency

        # A month-before rule reads the window before delivery: the estimate is the delivery
        # month's forward price (the month after the window).
        before = index.averaging in {"month_before_delivery", "last_n_trading_days"}
        month = (last.replace(day=1) + timedelta(days=32)).replace(day=1) if before else last
        delivery = f"{month:%Y-%m}"
        if self._curve is None:
            self._curve = build_forward_curve(
                curve_quotes(
                    self.caller,
                    self.today - timedelta(days=CURVE_QUOTE_LOOKBACK_DAYS),
                    self.today,
                ),
                first_month=self.today.replace(day=1),
            )
        marks = self._curve.marks()
        value = marks.get((code, delivery))
        if value is None:
            return None
        currency = quote_currency(code) or "EUR"
        return IndexPoint(
            value=float(value),
            unit=f"{currency}/MWh",
            input_class="simulated" if demo_marks_allowed() else "indicative",
            source_ref=f"forward curve: {code} {delivery} (an estimate, not the index)",
            as_of=(self._curve.as_of.get(code) or self.today).isoformat(),
        )

    # ---- Henry Hub, Brent, JKM
    def _global(self, code: str, first: date, last: date) -> IndexPoint | None:
        from sqlalchemy import func, or_

        from eurogas_nexus.db.models import MarketObservationRecord

        names = _GLOBAL[code]
        query = self.session.query(MarketObservationRecord).filter(
            or_(*[func.upper(MarketObservationRecord.product).like(f"%{name}%") for name in names])
        )
        end = datetime.combine(min(last, self.today) + timedelta(days=1), datetime.min.time())
        start = datetime.combine(first, datetime.min.time())
        rows = (
            query.filter(MarketObservationRecord.observed_at_utc >= start)
            .filter(MarketObservationRecord.observed_at_utc < end)
            .all()
        )
        rows = [row for row in rows if (row.unit or "").upper().endswith(("MMBTU", "BBL"))]
        if not rows:
            return None
        unit = rows[0].unit if "/" in rows[0].unit else f"{rows[0].currency}/{rows[0].unit}"
        simulated = any(
            row.source_system.endswith("_Sim") or (row.metadata_json or {}).get("simulated")
            for row in rows
        )
        latest = max(rows, key=lambda row: row.observed_at_utc)
        return IndexPoint(
            value=sum(float(row.price) for row in rows) / len(rows),
            unit=unit,
            input_class="simulated" if simulated else "settlement",
            source_ref=f"{latest.source_system}: {latest.product}",
            as_of=latest.observed_at_utc.date().isoformat(),
            observations=len(rows),
        )


def delivery_month_bounds(month: str) -> tuple[date, date]:
    first = date(int(month[:4]), int(month[5:7]), 1)
    return first, (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def contract_price(session, caller, record, month: str, *, today: date | None = None) -> dict:
    """The price of one stored contract for one delivery month, with its inputs and words."""

    import json

    terms = kinds.terms_of(record.contract_kind, record.kind_terms)
    try:
        notes = json.loads(record.notes or "{}")
    except ValueError:
        notes = {}
    price_terms, note = kinds.price_terms_for(
        record.contract_kind,
        terms,
        contract_price=record.contract_price_gbp_mwh,
        currency=record.contract_price_currency,
        index_basis=notes.get("index_basis") if isinstance(notes, dict) else None,
    )
    first, last = delivery_month_bounds(month)
    out: dict[str, Any] = {
        "contract_id": record.contract_id,
        "month": month,
        "price_terms": (
            None if price_terms is None else price_terms.model_dump(mode="json", by_alias=True)
        ),
        "note": note,
    }
    if price_terms is None:
        out["result"] = None
        return out
    lookup = IndexLookup(session, caller, today=today)
    out["result"] = evaluate(price_terms, first, last, lookup).as_dict()
    return out
