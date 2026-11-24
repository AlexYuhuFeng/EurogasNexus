"""Type S: tomorrow's open residual at a hub, against the cash-out it would otherwise meet.

The daily balance (``application/gas_day.hub_daily_balance``: the gas day's own lines, the
figure Today and Book > Delivery show) leaves a residual per book for the next gas day. Left
open, the TSO cashes it out: long below the day-ahead price by the desk's long discount, short
above it by the desk's short premium (``balancing.long_discount``,
``balancing.short_premium``; no public cash-out price is held). Each book is evaluated with
its own approved assumption set, else the firm-wide set, as the gas day's cost of doing
nothing is (a book's rate in another currency than the hub's is another hub's, and is not
used). Per MWh:

    long:  value = P_DA(bid) - (P_DA - long_discount)  = long_discount
    short: value = (P_DA + short_premium) - P_DA(ask)  = short_premium

so the claim is the cash-out cost the open residual carries; volume = |residual|. It is an
obligation of the gas day, listed in the must-act lane, due when the gas day starts. Without
the desk's premium or discount it cannot be evaluated, and says so.

Worked example: long residual 3,200 MWh at NBP tomorrow, day-ahead bid 81.50 p/th =
27.81 GBP/MWh (unit authority), long discount 1.50 GBP/MWh: +27.81 - 27.81 + 1.50 = 1.50
GBP/MWh x 3,200 MWh = GBP 4,800.00.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal

from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date
from eurogas_nexus.domain.ontology.markets import quote_currency
from eurogas_nexus.domain.opportunities.claims import grouped
from eurogas_nexus.domain.opportunities.evaluator import EvaluationContext, register
from eurogas_nexus.domain.opportunities.model import (
    AssumptionUse,
    Candidate,
    Falsifier,
    Leg,
    LegKind,
    Measure,
    OpportunityType,
    Sensitivity,
)
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.snapshot import SnapshotInput, SnapshotReader

MONEY = Decimal("0.01")
Q = Decimal("0.000001")


def _leg(key, label, item: SnapshotInput | None, contribution: Decimal, unit: str) -> Leg:
    return Leg(
        kind=LegKind.TERM,
        label_key=key,
        label=label,
        rate=None if item is None else Measure(item.value, item.unit),
        contribution=Measure(contribution, unit),
        input_class=None if item is None else item.input_class,
        source_family=None if item is None else item.source_family,
        source_ref="" if item is None else item.source_ref,
        as_of_utc=None if item is None else item.as_of_utc,
        input_keys=() if item is None else (item.key,),
    )


class SellDownEvaluator:
    """Type S over the ``residuals`` collection."""

    name = "sell_down"
    #: 2: the residual is the gas day's own lines and the penalty the book's own set (P-11).
    version = "2"
    type = OpportunityType.SELL_DOWN

    def evaluate(self, snapshot: SnapshotReader, context: EvaluationContext) -> Iterable[Candidate]:
        """One candidate per (book, hub) with an open residual tomorrow."""

        today = DeliveryPeriod.parse(gas_day_label(context.as_of_utc)).start
        period = DeliveryPeriod.gas_day(today + timedelta(days=1))
        due = gas_day_start_for_date(period.start)
        if due <= context.as_of_utc:
            return
        for residual in snapshot.collection("residuals"):
            amount = residual.value or Decimal(0)
            if amount == 0:
                continue
            long = amount > 0
            hub = str(residual.detail.get("hub"))
            book_id = residual.detail.get("book_id") or None
            price = snapshot.price(hub, period, "bid" if long else "ask")
            key = "balancing.long_discount" if long else "balancing.short_premium"
            penalty = snapshot.assumption(key, book_id)
            foreign = penalty.currency not in (None, quote_currency(hub))
            if penalty.detail.get("book_id") and foreign:
                # A book's cash-out rate in another currency is another hub's (the gas day's
                # rule): the firm-wide set answers, or nothing does.
                penalty = snapshot.assumption(key)
            whose = "book's" if penalty.detail.get("book_id") else "firm's"
            inputs = (residual, price, penalty)
            unit = price.unit or "EUR/MWh"
            currency = unit.split("/")[0]
            p = price.value if price.held else Decimal(0)
            d = penalty.value if penalty.held else Decimal(0)
            conversion: list[Leg] = []
            if penalty.held and price.held and penalty.currency and penalty.currency != currency:
                fx = snapshot.fx(penalty.currency, currency, period)
                inputs = (*inputs, fx)
                if fx.held:
                    d = (d * fx.value).quantize(Q)
                    conversion.append(
                        Leg(
                            kind=LegKind.CONVERSION,
                            label_key="sell_down.fx",
                            label=f"{penalty.currency} to {currency}: {fx.label}",
                            fx=Measure(fx.value, fx.unit),
                            input_class=fx.input_class,
                            source_family=fx.source_family,
                            source_ref=fx.source_ref,
                            input_keys=(fx.key,),
                        )
                    )
            if long:
                terms = [
                    _leg(
                        "sell_down.da_bid", f"Day-ahead bid {hub} ({price.label})", price, p, unit
                    ),
                    _leg(
                        "sell_down.cash_out",
                        "Cash-out long at the day-ahead price",
                        price,
                        -p,
                        unit,
                    ),
                    _leg(
                        "sell_down.long_discount",
                        f"less the desk's long discount ({whose} assumption)",
                        penalty,
                        d,
                        unit,
                    ),
                ]
            else:
                terms = [
                    _leg(
                        "sell_down.cash_out",
                        "Cash-out short at the day-ahead price",
                        price,
                        p,
                        unit,
                    ),
                    _leg(
                        "sell_down.short_premium",
                        f"plus the desk's short premium ({whose} assumption)",
                        penalty,
                        d,
                        unit,
                    ),
                    _leg(
                        "sell_down.da_ask",
                        f"Day-ahead offer {hub} ({price.label})",
                        price,
                        -p,
                        unit,
                    ),
                ]
            net = sum((leg.contribution.value for leg in terms), Decimal(0))
            volume = abs(amount)
            supply = Decimal(str(residual.detail.get("supply_mwh") or 0))
            value = (net * volume).quantize(MONEY)
            legs = (
                *conversion,
                *terms,
                Leg(
                    LegKind.RESULT,
                    "sell_down.net",
                    "Cash-out cost per MWh left open",
                    subtotal=Measure(net, unit),
                ),
                Leg(
                    LegKind.VOLUME,
                    "sell_down.volume",
                    f"{'Long' if long else 'Short'} residual of the gas day's lines",
                    quantity=Measure(volume, "MWh"),
                ),
                Leg(
                    LegKind.VALUE,
                    "sell_down.value",
                    "Cash-out cost",
                    quantity=Measure(value, currency),
                ),
            )
            assumption = AssumptionUse.of(penalty) if penalty.held else None
            yield Candidate(
                type=self.type,
                identity=(hub, "long" if long else "short"),
                period=period,
                book_ids=tuple(item for item in (residual.detail.get("book_id"),) if item),
                claim_key="sell_down.residual",
                claim_fields={
                    "hub": hub,
                    "gas_day": period.label,
                    "side": "long" if long else "short",
                    "volume": grouped(volume),
                    "penalty": f"{grouped(d, 2)} {unit}",
                    "relation": "below" if long else "above",
                    "value": f"{currency} {grouped(value, 2)}",
                },
                headline=Measure(net, unit),
                volume=Measure(volume, "MWh"),
                value=Measure(value, currency),
                legs=legs,
                assumptions=() if assumption is None else (assumption,),
                falsifiers=(
                    Falsifier(
                        "sell_down.delivery",
                        f"Tomorrow's physical lines differ from {grouped(supply)} MWh net.",
                    ),
                    Falsifier(
                        "sell_down.trades",
                        f"Trades for {period.label} at {hub} close the residual.",
                    ),
                ),
                sensitivity=(
                    Sensitivity(
                        "penalty",
                        "per_unit",
                        Measure((volume / 10).quantize(MONEY), currency),
                        f"±0.10 {unit} of cash-out penalty = ±{currency} {grouped(volume / 10, 2)}",
                    ),
                ),
                expires_at_utc=due,
                deadline_utc=due,
                inputs=inputs,
                evaluator=self.name,
                evaluator_version=self.version,
            )


SELL_DOWN = register(SellDownEvaluator())
