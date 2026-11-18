"""Types L (locational spread) and C (capacity already held) over the proven network.

**L**: buy at hub A, sell at hub B for the same delivery period along a proven path
(``MarketAreaGraph``: no pricing between market areas without a crossing). Per MWh, in EUR:

    net = P_B(bid) x fx_B - P_A(ask) x fx_A - sum(tariff_leg x product multiplier / load factor)
          - fuel % x P_A

- every crossing contributes its market-area exit, any pipeline charge and the market-area
  entry, each from the published tariff in force for the period (a missing one is named:
  "tariff not held at <point>", never zero);
- tariffs are capacity charges: the published per-MWh figure assumes the capacity flows every
  hour (100 % load factor, ``ingestion/entsog_tariffs.per_mwh_at_full_load``). The firm's
  load factor, when its assumption set holds one, divides it; the falsifiers always state
  the load factor at which the net reaches zero and the net at 80 %;
- a month or day priced from an annual tariff applies the firm's short-term multiplier when
  held (an assumption); without it the annual tariff is used and the leg is indicative;
- a hub quoted in another currency converts at the snapshot's FX for the delivery period
  (forward by interest parity for a forward month), on its own conversion row.

Candidates are bounded by the book (design J.2): for every month M+1..M+6 in which a book is
long at a hub, each market area within two crossings is a place to sell; where it is short,
each one is a place to buy. Day-ahead (the intraday L): tomorrow's long residual at a hub,
executable quote sides only. A pair is produced when both prices are held and the spread is
positive: a complete one whose net is not positive is not an opportunity; one with a missing
tariff is a named "cannot evaluate" record.

**C**: the same arithmetic for capacity the firm already holds on a route: its capacity
charges are sunk, so only variable charges count (none are held: the rows say so), and the
volume is the held capacity.

Worked example (design B.4, TTF -> THE, Jan-27, 10,000 MWh/d): 31.20 - 30.00 = 1.20 gross;
exit NL at Oude Statenzijl 0.0101 EUR/(kWh/h)/d x 1000/24 = 0.420833 (6 dp); entry THE 0.0132 x
1000/24 = 0.55; net 0.229167 EUR/MWh; 310,000 MWh; EUR 71,041.77. At 80 % load the transport
is 0.970833 / 0.8 = 1.213541 and the net -0.013541; breakeven load factor 80.9 %.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import timedelta
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date
from eurogas_nexus.domain.opportunities.claims import grouped, period_label, signed
from eurogas_nexus.domain.opportunities.evaluator import EvaluationContext, register
from eurogas_nexus.domain.opportunities.model import (
    AssumptionUse,
    Blocker,
    Candidate,
    Check,
    CheckKind,
    CheckResult,
    Falsifier,
    Leg,
    LegKind,
    Measure,
    OpportunityType,
    Sensitivity,
)
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.domain.valuation.snapshot import InputKind, SnapshotInput, SnapshotReader

EUR = "EUR"
UNIT = "EUR/MWh"
Q = Decimal("0.000001")
MONEY = Decimal("0.01")
HUNDRED = Decimal(100)
#: Desk GCV for capacity stated by volume (domain/market/units.DESK_ASSUMED_GCV_KWH_PER_M3).
MWH_PER_MCM = Decimal("11000")
FORWARD_MONTHS = 6
MAX_CROSSINGS = 2
PRODUCT_FOR_KIND = {"day": "DAILY", "month": "MONTHLY", "quarter": "QUARTERLY"}


def _dec(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def shipped_graph():
    """The pricing graph of the shipped reference bundle (static reference data)."""

    from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

    return shipped_market_area_graph()


def forward_months(as_of_day) -> list[DeliveryPeriod]:
    """Months M+1 .. M+6 after the evaluation day."""

    out = []
    month, year = as_of_day.month, as_of_day.year
    for _ in range(FORWARD_MONTHS):
        month += 1
        if month > 12:
            month, year = 1, year + 1
        out.append(DeliveryPeriod.month(year, month))
    return out


def tariff_per_mwh(item: SnapshotInput) -> tuple[Decimal | None, str]:
    """A capacity tariff as currency per MWh at full load, and how it was converted."""

    unit = (item.unit or "").replace(" ", "")
    value = item.value
    if value is None:
        return None, ""
    if unit.endswith("/MWh"):
        return value, f"{item.detail.get('published') or value} published, per MWh at full load"
    if unit.endswith("/(kWh/h)/d"):
        return value * 1000 / 24, f"{value} {item.unit} / 24 x 1000"
    if unit.startswith("p/") and unit.endswith("/(kWh/h)/h"):
        return value * 1000 / 100, f"{value} {item.unit} x 24 / 24 x 1000 / 100"
    return None, f"unit {item.unit} not convertible"


class _Route:
    """Prices one (A -> B, period) through the snapshot; ``None`` when not an opportunity."""

    def __init__(self, snapshot: SnapshotReader, context: EvaluationContext, graph) -> None:
        self.s = snapshot
        self.ctx = context
        self.graph = graph

    def _eur(self, price: SnapshotInput, period: DeliveryPeriod):
        currency = price.currency or EUR
        if currency == EUR:
            return price.value, None
        fx = self.s.fx(currency, EUR, period)
        if not fx.held:
            return None, fx
        return price.value * fx.value, fx

    def price(
        self,
        kind: OpportunityType,
        buy_hub: str,
        sell_hub: str,
        period: DeliveryPeriod,
        mwh_per_day: Decimal,
        book_id: str | None,
        *,
        position: SnapshotInput | None = None,
        via: tuple[str, ...] = (),
        held_capacity: SnapshotInput | None = None,
        executable_only: bool = False,
        side: str = "new",
    ) -> Candidate | None:
        start, target = self.graph.hub_for(buy_hub), self.graph.hub_for(sell_hub)
        if start is None or target is None or start == target:
            return None
        crossings = self.graph.route(start, target, via_points=via, max_hops=MAX_CROSSINGS)
        if crossings is None:
            return None  # unproven path: never priced directly (route_adjacency rule)
        sell = self.s.price(sell_hub, period, "bid")
        buy = self.s.price(buy_hub, period, "ask")
        if not (sell.held and buy.held):
            return None
        if executable_only and not (
            sell.detail.get("basis") == "quote" and buy.detail.get("basis") == "quote"
        ):
            return None
        sell_eur, sell_fx = self._eur(sell, period)
        buy_eur, buy_fx = self._eur(buy, period)
        inputs: list[SnapshotInput] = [sell, buy]
        legs: list[Leg] = []
        blockers: list[Blocker] = []
        for fx in (sell_fx, buy_fx):
            if fx is not None:
                inputs.append(fx)
        if sell_eur is None or buy_eur is None:
            missing = sell_fx if sell_eur is None else buy_fx
            return self._blocked(kind, buy_hub, sell_hub, period, book_id, missing)
        sell_eur, buy_eur = sell_eur.quantize(Q), buy_eur.quantize(Q)
        gross = sell_eur - buy_eur
        if gross <= 0:
            return None

        def price_leg(item, hub, side, contribution, fx):
            return Leg(
                kind=LegKind.TERM,
                label_key=f"locational.{side}",
                label=f"{'Sell' if side == 'sell' else 'Buy'} {hub} {period_label(period.label)}"
                f" {'bid' if side == 'sell' else 'offer'} ({item.label or item.source_family})",
                rate=Measure(item.value, item.unit),
                fx=None if fx is None else Measure(fx.value, fx.unit),
                contribution=Measure(contribution, UNIT),
                input_class=item.input_class,
                source_family=item.source_family,
                source_ref=item.source_ref,
                as_of_utc=item.as_of_utc,
                input_keys=(item.key,) + (() if fx is None else (fx.key,)),
            )

        legs.append(price_leg(sell, sell_hub, "sell", sell_eur, sell_fx))
        if sell_fx is not None:
            legs.append(self._fx_row(sell_fx, sell.currency))
        legs.append(price_leg(buy, buy_hub, "buy", -buy_eur, buy_fx))
        if buy_fx is not None:
            legs.append(self._fx_row(buy_fx, buy.currency))
        legs.append(
            Leg(LegKind.SUBTOTAL, "locational.gross", "Gross spread", subtotal=Measure(gross, UNIT))
        )
        running = gross

        load = self.s.assumption("capacity.load_factor")
        load_pct = load.value if load.held else HUNDRED
        assumptions: list[AssumptionUse] = []
        if load.held:
            inputs.append(load)
            assumptions.append(self._assumption_use(load))
        sunk = kind is OpportunityType.UNUSED_CAPACITY
        transport = Decimal(0)
        points: list[str] = []
        for crossing in crossings:
            for spec in self.graph.legs(crossing):
                points.append(spec.point_name)
                if sunk:
                    legs.append(
                        Leg(
                            kind=LegKind.CONVERSION,
                            label_key="capacity.sunk",
                            label=f"{spec.role.replace('_', ' ')} at {spec.point_name} "
                            f"({spec.tso}): capacity held, its charge is sunk",
                            note="variable (commodity) charges: none held for this point",
                        )
                    )
                    continue
                item, multiplier, extra = self._tariff(spec, period)
                inputs.extend(extra)
                if item is None or not item.held:
                    missing = item if item is not None else None
                    if missing is not None:
                        inputs.append(missing)
                    continue
                per_mwh, how = tariff_per_mwh(item)
                if per_mwh is None:
                    blockers.append(
                        Blocker("input_missing", spec.point_name, f"Cannot evaluate: {how}.")
                    )
                    continue
                if item.currency and item.currency != EUR:
                    fx = self.s.fx(item.currency, EUR, period)
                    inputs.append(fx)
                    if not fx.held:
                        continue
                    per_mwh *= fx.value
                inputs.append(item)
                cost = (per_mwh * multiplier.value / (load_pct / HUNDRED)).quantize(Q)
                transport += cost
                running -= cost
                legs.append(
                    Leg(
                        kind=LegKind.TERM,
                        label_key=f"locational.{spec.role}",
                        label=f"{spec.role.replace('_', ' ').capitalize()} at {spec.point_name} "
                        f"({spec.tso}), {item.detail.get('tariff_status', '').lower()} "
                        f"{item.key.split(':')[3].lower()} tariff: {how}"
                        + (f", x{multiplier.value} short-term" if multiplier.value != 1 else "")
                        + (
                            " (annual product for a shorter period: the short-term multiplier"
                            " is not held, so this leg is indicative)"
                            if any(x.key.endswith("#short-term") for x in extra)
                            else ""
                        )
                        + (f", at {load_pct} % load" if load_pct != HUNDRED else ", full load"),
                        rate=Measure(per_mwh.quantize(Q), UNIT),
                        contribution=Measure(-cost, UNIT),
                        input_class=(
                            InputClass.INDICATIVE
                            if any(x.key.endswith("#short-term") for x in extra)
                            and item.input_class is InputClass.SOURCED
                            else item.input_class
                        ),
                        source_family=item.source_family,
                        source_ref=item.source_ref,
                        as_of_utc=item.as_of_utc,
                        input_keys=(item.key,),
                    )
                )
        fuel = self.s.assumption("transport.fuel_shrinkage")
        if fuel.held and not sunk:
            inputs.append(fuel)
            assumptions.append(self._assumption_use(fuel))
            fuel_cost = (fuel.value / HUNDRED * buy_eur).quantize(Q)
            running -= fuel_cost
            transport += fuel_cost
            legs.append(
                Leg(
                    kind=LegKind.TERM,
                    label_key="locational.fuel",
                    label=f"Fuel and shrinkage {fuel.value} % of the purchase (firm's assumption)",
                    rate=Measure(fuel.value, "%"),
                    contribution=Measure(-fuel_cost, UNIT),
                    input_class=fuel.input_class,
                    source_family=fuel.source_family,
                    source_ref=fuel.source_ref,
                    input_keys=(fuel.key,),
                )
            )
        net = running
        complete = all(item.held for item in inputs) and not blockers
        if complete and net <= 0:
            return None
        if position is not None:
            inputs.append(position)
        checks, volume_per_day = self._checks(
            crossings, buy_hub, sell_hub, period, mwh_per_day, book_id, held_capacity, side
        )
        volume = (volume_per_day * period.days).quantize(Decimal("0.1"))
        legs.append(
            Leg(
                LegKind.RESULT, "locational.net", "Net after transport", subtotal=Measure(net, UNIT)
            )
        )
        value = (net * volume).quantize(MONEY)
        legs.append(
            Leg(
                LegKind.VOLUME,
                "locational.volume",
                f"Volume {grouped(volume_per_day)} MWh/d x {period.days} d",
                quantity=Measure(volume, "MWh"),
            )
        )
        legs.append(Leg(LegKind.VALUE, "locational.value", "Value", quantity=Measure(value, EUR)))
        half_spread = self._half_spread(sell, buy, sell_hub, buy_hub, period, sell_fx, buy_fx)
        fx_tolerance = sum(
            (
                (_dec(fx.detail.get("tolerance")) or Decimal(0)) * price.value
                for fx, price in ((sell_fx, sell), (buy_fx, buy))
                if fx is not None and fx.held
            ),
            Decimal(0),
        )
        via_text = " / ".join(dict.fromkeys(points)) or "direct"
        breakeven = transport
        falsifiers = [
            Falsifier(
                "locational.spread_below_breakeven",
                f"{sell_hub}-{buy_hub} {period_label(period.label)} spread below "
                f"{grouped(breakeven, 3)} EUR/MWh.",
            ),
            Falsifier(
                "locational.no_capacity",
                f"No firm capacity offered at {via_text} for {period_label(period.label)}.",
            ),
        ]
        sensitivity = [
            Sensitivity(
                "spread",
                "breakeven",
                Measure(breakeven.quantize(Q), UNIT),
                f"Breakeven spread {grouped(breakeven, 3)} EUR/MWh",
            ),
            Sensitivity(
                "spread",
                "per_unit",
                Measure((volume / 10).quantize(MONEY), EUR),
                f"±0.10 EUR/MWh on the spread = ±EUR {grouped(volume / 10)}",
            ),
        ]
        tariff_total = transport - (
            (fuel.value / HUNDRED * buy_eur).quantize(Q) if fuel.held and not sunk else 0
        )
        if not sunk and tariff_total > 0:
            full_load = tariff_total * load_pct / HUNDRED
            be_load = (
                (full_load / (gross - (transport - tariff_total)) * HUNDRED)
                if gross > (transport - tariff_total)
                else None
            )
            at80 = (full_load / Decimal("0.8")).quantize(Q)
            net80 = gross - (transport - tariff_total) - at80
            falsifiers.append(
                Falsifier(
                    "locational.load_factor",
                    "Load factor below "
                    + (f"{grouped(be_load, 1)} %" if be_load is not None else "any level")
                    + f" (at 80 % the transport is {grouped(at80, 3)} EUR/MWh and the net "
                    f"{signed(net80, 3)} EUR/MWh).",
                )
            )
            sensitivity.append(
                Sensitivity(
                    "load_factor",
                    "range_low",
                    Measure(net80, UNIT),
                    f"Net at 80 % load factor: {signed(net80, 3)} EUR/MWh",
                )
            )
        # Valid until delivery starts (the booking and trading deadline for the period).
        expires = gas_day_start_for_date(period.start)
        if expires <= self.ctx.as_of_utc:
            return None
        claim_type = "capacity" if sunk else "locational"
        return Candidate(
            type=kind,
            identity=(buy_hub, sell_hub, *dict.fromkeys(points)),
            period=period,
            book_ids=tuple(item for item in (book_id,) if item),
            claim_key=f"{claim_type}.spread",
            claim_fields={
                "buy_hub": buy_hub,
                "sell_hub": sell_hub,
                "period": period_label(period.label),
                "volume": f"{grouped(volume_per_day)} MWh/d",
                "margin": f"{signed(net, 3)} EUR/MWh",
                "costs": "held capacity (charges sunk)" if sunk else f"transport via {via_text}",
                "value": f"EUR {grouped(value)}",
            },
            headline=Measure(net, UNIT),
            volume=Measure(volume, "MWh"),
            value=Measure(value, EUR),
            value_eur=Measure(value, EUR),
            margin_eur=Measure(net, UNIT),
            route_cost_eur=Measure(transport, UNIT),
            half_spread_eur=half_spread,
            fx_tolerance_eur=Measure(fx_tolerance.quantize(Q), UNIT) if fx_tolerance else None,
            legs=tuple(legs),
            assumptions=tuple(assumptions),
            falsifiers=tuple(falsifiers),
            sensitivity=tuple(sensitivity),
            checks=tuple(checks),
            blockers=tuple(blockers),
            expires_at_utc=expires,
            inputs=tuple(dict((item.key, item) for item in inputs).values()),
            evaluator="held_capacity" if sunk else "locational",
            evaluator_version="1",
            extra={"points": points, "crossings": [c.via for c in crossings]},
        )

    # ---- parts
    def _blocked(self, kind, buy_hub, sell_hub, period, book_id, missing: SnapshotInput):
        subject = f"{missing.label or missing.key} for {period_label(period.label)}"
        expires = gas_day_start_for_date(period.start)
        if expires <= self.ctx.as_of_utc:
            return None
        return Candidate(
            type=kind,
            identity=(buy_hub, sell_hub, "fx"),
            period=period,
            book_ids=tuple(item for item in (book_id,) if item),
            claim_key="blocked.input_missing",
            claim_fields={"subject": subject},
            headline=Measure(Decimal(0), UNIT),
            legs=(),
            falsifiers=(),
            blockers=(
                Blocker(
                    "input_missing",
                    subject,
                    f"Cannot evaluate: {subject} not held.",
                    "load the ECB reference rates and the overnight benchmark fixings",
                ),
            ),
            expires_at_utc=expires,
            inputs=(missing,),
            evaluator="held_capacity" if kind is OpportunityType.UNUSED_CAPACITY else "locational",
            evaluator_version="1",
        )

    def _fx_row(self, fx: SnapshotInput, currency: str | None) -> Leg:
        return Leg(
            kind=LegKind.CONVERSION,
            label_key="locational.fx",
            label=f"{currency} to EUR: {fx.label}",
            fx=Measure(fx.value, fx.unit),
            input_class=fx.input_class,
            source_family=fx.source_family,
            source_ref=fx.source_ref,
            as_of_utc=fx.as_of_utc,
            input_keys=(fx.key,),
        )

    @staticmethod
    def _assumption_use(item: SnapshotInput) -> AssumptionUse:
        return AssumptionUse(
            key=item.key.split(":", 1)[1],
            value=Measure(item.value, item.unit),
            origin="firm_set",
            set_by=str(item.detail.get("set_by") or ""),
            set_at_utc=str(item.detail.get("set_at_utc") or ""),
            input_key=item.key,
            range_low=_dec(item.detail.get("range_low")),
            range_high=_dec(item.detail.get("range_high")),
        )

    def _tariff(self, spec, period: DeliveryPeriod):
        """The tariff for the period's product, else the annual one with the multiplier."""

        product = PRODUCT_FOR_KIND.get(period.kind, "ANNUAL")
        first = self.s.tariff(spec.point_key, spec.direction, product, period)
        one = Measure(Decimal(1), "x")
        if first.held or product == "ANNUAL":
            return first, one, []
        annual = self.s.tariff(spec.point_key, spec.direction, "ANNUAL", period)
        if not annual.held:
            return annual, one, []
        multiplier = self.s.assumption("capacity.short_term_multiplier")
        if multiplier.held:
            return annual, Measure(multiplier.value, "x"), [multiplier]
        marker = SnapshotInput(
            key=f"{annual.key}#short-term",
            kind=InputKind.TARIFF,
            input_class=InputClass.INDICATIVE,
            value=Decimal(1),
            unit="x",
            as_of_utc=annual.as_of_utc,
            source_family=annual.source_family,
            source_ref=annual.source_ref,
            label=f"annual tariff at {spec.point_name} applied to a {period.kind}: the "
            "short-term multiplier is not held",
        )
        return annual, one, [marker]

    def _half_spread(self, sell, buy, sell_hub, buy_hub, period, sell_fx, buy_fx):
        if not (sell.detail.get("basis") == "quote" and buy.detail.get("basis") == "quote"):
            return None
        sell_ask = self.s.price(sell_hub, period, "ask")
        buy_bid = self.s.price(buy_hub, period, "bid")
        if not (sell_ask.held and buy_bid.held):
            return None
        rate_s = sell_fx.value if sell_fx is not None else Decimal(1)
        rate_b = buy_fx.value if buy_fx is not None else Decimal(1)
        half = ((sell_ask.value - sell.value) * rate_s + (buy.value - buy_bid.value) * rate_b) / 2
        return Measure(half.quantize(Q), UNIT)

    def _checks(self, crossings, buy_hub, sell_hub, period, mwh_per_day, book_id, held, side):
        checks: list[Check] = []
        volume = mwh_per_day
        first_point = crossings[0].points[0]
        if held is not None:
            capacity = held.value or Decimal(0)
            volume = min(volume, capacity)
            checks.append(
                Check(
                    CheckKind.CAPACITY,
                    CheckResult.PASS,
                    f"capacity held {grouped(capacity)} MWh/d on {held.detail.get('route_name')}",
                    held.source_ref,
                )
            )
        else:
            cap = self.s.capacity(first_point, "EXIT", period)
            if cap.held and cap.value is not None:
                mwh = cap.value * MWH_PER_MCM
                if mwh <= 0:
                    checks.append(
                        Check(
                            CheckKind.CAPACITY,
                            CheckResult.FAIL,
                            f"no firm capacity at {first_point}",
                            cap.source_ref,
                        )
                    )
                else:
                    volume = min(volume, mwh)
                    checks.append(
                        Check(
                            CheckKind.CAPACITY,
                            CheckResult.PASS,
                            f"firm technical capacity {grouped(cap.value, 2)} mcm/d "
                            f"(~{grouped(mwh)} MWh/d at 11 kWh/m3) at {first_point}",
                            cap.source_ref,
                        )
                    )
            else:
                checks.append(
                    Check(
                        CheckKind.CAPACITY,
                        CheckResult.NOT_ASSESSED,
                        f"capacity at {first_point} not held",
                    )
                )
        checks.append(self._outage_check(crossings, buy_hub, sell_hub, period))
        checks.append(self._mandate_check(buy_hub, sell_hub, period, volume, book_id, side))
        return checks, volume

    def _outage_check(self, crossings, buy_hub, sell_hub, period) -> Check:
        feed = self.s.collection("outage_feed")
        if not feed or not feed[0].held:
            return Check(CheckKind.OUTAGE, CheckResult.NOT_ASSESSED, "no outage feed held")
        names = {
            str(self.graph.points.get(point, {}).get("name") or point).casefold()
            for crossing in crossings
            for point in crossing.points
        }
        hits = []
        for hub in (buy_hub, sell_hub):
            for outage in self.s.outages(hub, period):
                asset = str(outage.detail.get("asset_name") or outage.label).casefold()
                if any(name and (name in asset or asset in name) for name in names):
                    hits.append(outage)
        if hits:
            return Check(
                CheckKind.OUTAGE,
                CheckResult.FAIL,
                "; ".join(f"{item.label}: {item.value} {item.unit} out" for item in hits),
                ",".join(item.source_ref for item in hits),
            )
        return Check(
            CheckKind.OUTAGE, CheckResult.PASS, "no published outage on the path for the period"
        )

    def _mandate_check(self, buy_hub, sell_hub, period, volume_per_day, book_id, side) -> Check:
        """Mandate headroom after the move.

        ``side`` is what the move does to the book: ``source`` (the book's long gas at the buy
        hub goes to the sell hub: the buy hub's net falls), ``sink`` (gas bought at the buy hub
        covers the book's short at the sell hub: the sell hub's net rises), or ``new`` (a
        purchase and a sale added to the book).
        """

        if not book_id:
            return Check(CheckKind.MANDATE, CheckResult.NOT_ASSESSED, "no book: no mandate")
        mandates = [
            item
            for item in self.s.collection("mandates")
            if book_id in (item.detail.get("book_ids") or [])
        ]
        if not mandates:
            return Check(
                CheckKind.MANDATE, CheckResult.NOT_ASSESSED, f"no mandate held for book {book_id}"
            )
        positions = {
            (item.detail.get("hub"), item.detail.get("month")): item.value or Decimal(0)
            for item in self.s.collection("positions")
            if item.detail.get("book_id") == book_id
        }
        month = period.start.strftime("%Y-%m")
        volume = volume_per_day * period.days
        worst = Decimal(0)
        for mandate in mandates:
            hubs = [str(hub).upper() for hub in mandate.detail.get("hubs") or []]
            # Only a hub where the move places a trade must be in the mandate: moving the
            # book's own gas out of its source hub is not a trade there.
            traded = {"source": (sell_hub,), "sink": (buy_hub,)}.get(side, (buy_hub, sell_hub))
            outside = [hub for hub in traded if hubs and hub not in hubs]
            if outside:
                return Check(
                    CheckKind.MANDATE,
                    CheckResult.FAIL,
                    f"{', '.join(outside)} outside mandate {mandate.detail.get('mandate_id')}",
                    mandate.source_ref,
                )
            limit = _dec(mandate.detail.get("max_net_mwh_per_month"))
            if not limit:
                continue
            at_buy = positions.get((buy_hub, month), Decimal(0))
            at_sell = positions.get((sell_hub, month), Decimal(0))
            after_buy = {"source": at_buy - volume, "sink": at_buy}.get(side, at_buy + volume)
            after_sell = {"sink": at_sell + volume, "source": at_sell}.get(side, at_sell - volume)
            worst = max(worst, abs(after_buy) / limit, abs(after_sell) / limit)
        result = CheckResult.PASS if worst <= 1 else CheckResult.FAIL
        return Check(
            CheckKind.MANDATE,
            result,
            f"{grouped(worst * 100)} % of the monthly mandate limit used after",
            ",".join(item.source_ref for item in mandates),
        )


class LocationalEvaluator:
    """Type L: forward months from the book's positions; day-ahead from tomorrow's residuals."""

    name = "locational"
    version = "1"
    type = OpportunityType.LOCATIONAL

    def __init__(self, graph_provider: Callable[[], Any] = shipped_graph) -> None:
        self.graph_provider = graph_provider

    def _targets(self, graph, hub: str) -> list[str]:
        key = graph.hub_for(hub)
        if key is None:
            return []
        out = set()
        frontier = {key}
        for _ in range(MAX_CROSSINGS):
            frontier = {n for k in frontier for n in graph.neighbours(k)} - {key}
            out |= frontier
        return sorted(graph.hub_names[k] for k in out if k in graph.hub_names)

    def evaluate(self, snapshot: SnapshotReader, context: EvaluationContext) -> Iterable[Candidate]:
        """Forward and day-ahead candidates bounded by the book."""

        graph = self.graph_provider()
        route = _Route(snapshot, context, graph)
        months = {p.label: p for p in forward_months(context.as_of_utc.date())}
        for position in snapshot.collection("positions"):
            period = months.get(str(position.detail.get("month")))
            net = position.value
            hub = str(position.detail.get("hub"))
            if period is None or not net:
                continue
            per_day = abs(net) / period.days
            for other in self._targets(graph, hub):
                buy, sell = (hub, other) if net > 0 else (other, hub)
                candidate = route.price(
                    self.type,
                    buy,
                    sell,
                    period,
                    per_day,
                    position.detail.get("book_id"),
                    position=position,
                    side="source" if net > 0 else "sink",
                )
                if candidate is not None:
                    yield candidate
        tomorrow = DeliveryPeriod.gas_day(
            DeliveryPeriod.parse(gas_day_label(context.as_of_utc)).start + timedelta(days=1)
        )
        for residual in snapshot.collection("residuals"):
            value = residual.value or Decimal(0)
            if value <= 0:
                continue
            hub = str(residual.detail.get("hub"))
            for other in self._targets(graph, hub):
                candidate = route.price(
                    self.type,
                    hub,
                    other,
                    tomorrow,
                    value,
                    residual.detail.get("book_id"),
                    position=residual,
                    executable_only=True,
                    side="source",
                )
                if candidate is not None:
                    yield candidate


class HeldCapacityEvaluator:
    """Type C: capacity the firm holds on a route, priced with its charges sunk."""

    name = "held_capacity"
    version = "1"
    type = OpportunityType.UNUSED_CAPACITY

    def __init__(self, graph_provider: Callable[[], Any] = shipped_graph) -> None:
        self.graph_provider = graph_provider

    def evaluate(self, snapshot: SnapshotReader, context: EvaluationContext) -> Iterable[Candidate]:
        """One candidate per held route and forward month."""

        route = _Route(snapshot, context, self.graph_provider())
        for held in snapshot.collection("held_capacity"):
            for period in forward_months(context.as_of_utc.date()):
                candidate = route.price(
                    self.type,
                    str(held.detail.get("from_hub")),
                    str(held.detail.get("to_hub")),
                    period,
                    held.value or Decimal(0),
                    held.detail.get("book_id"),
                    position=held,
                    via=tuple(held.detail.get("via_points") or ()),
                    held_capacity=held,
                    side="source",
                )
                if candidate is not None:
                    yield candidate


LOCATIONAL = register(LocationalEvaluator())
HELD_CAPACITY = register(HeldCapacityEvaluator())
