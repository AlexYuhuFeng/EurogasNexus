"""The market scan: opportunities that need no existing position (lane "in the market").

A trader asks whether the product "detects arbitrage opportunities on the market", not only on
the book. The scan looks at the market as the snapshot holds it and lists what the firm could
do with capacity, a credit line and a mandate it may not hold; each item says what it would
need. Market items live in their own lane (``Lane.MARKET``), never in "must act", and carry no
book.

- **L (locational, market)**: for every ordered pair of scanned hubs with prices held, the
  day-ahead and the front month, priced through the one route pricer (``cheapest_route``)
  exactly as the book's L: sell at the bid, buy at the offer when quotes are held, else the
  closes (said on the row), less every transport leg. Only a complete priced route is listed:
  a pair with a missing tariff is not a market item.
- **P (prompt arbitrage)**: at one hub, within-day against day-ahead and day-ahead against the
  balance of the month: the dearer product's bid over the cheaper one's offer. A prompt edge
  under :data:`PROMPT_MIN_EDGE` is the prompt's normal shape, not an item.
- **T (seasonal, market)**: at one hub, the next full winter (October-March) over the summer
  before it, as month averages, less the stated storage cost (the firm's assumptions
  ``storage.capacity_fee`` + ``injection_fee`` + ``withdrawal_fee``; without them nothing is
  listed). Marked "needs storage capacity" where the firm holds none at the hub.

Volumes are a stated lot (:data:`LOT_MWH_PER_DAY` per gas day, :data:`STORAGE_LOT_MWH` for a
season): the value is what the edge is worth on that lot, not a position.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date
from eurogas_nexus.domain.opportunities.claims import grouped, signed
from eurogas_nexus.domain.opportunities.evaluator import EvaluationContext, register
from eurogas_nexus.domain.opportunities.locational import _Route, shipped_graph
from eurogas_nexus.domain.opportunities.model import (
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
from eurogas_nexus.domain.valuation.snapshot import SnapshotInput, SnapshotReader

EUR = "EUR"
UNIT = "EUR/MWh"
Q = Decimal("0.000001")
MONEY = Decimal("0.01")
#: Hubs the scan prices (the desk board's continental and UK hubs).
SCAN_HUBS = ("TTF", "THE", "PEG", "ZTP", "NBP", "PSV", "PVB", "CEGH")
#: The stated lot for a prompt or day item, MWh per gas day.
LOT_MWH_PER_DAY = Decimal(10000)
#: The stated lot for a seasonal item, MWh injected and withdrawn.
STORAGE_LOT_MWH = Decimal(1000000)
#: A prompt edge below this is the prompt's normal shape (EUR/MWh).
PROMPT_MIN_EDGE = Decimal("0.50")
STORAGE_COSTS = ("storage.capacity_fee", "storage.injection_fee", "storage.withdrawal_fee")


def day_ahead(today: date) -> DeliveryPeriod:
    """The day-ahead product the market quotes on gas day ``today`` (Monday's on a Friday or
    a weekend day, as ``resolve_product`` has it), as a delivery period."""

    from eurogas_nexus.domain.market.products import resolve_product

    period = resolve_product("DA", today)
    return DeliveryPeriod.gas_day(period.first_gas_day)


def balance_of_month(today: date) -> DeliveryPeriod | None:
    """The balance-of-month product quoted on ``today``; ``None`` on a month's last day."""

    from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product

    try:
        period = resolve_product("BOM", today)
    except ProductCodeError:
        return None
    return DeliveryPeriod(
        period.first_gas_day,
        period.last_gas_day + timedelta(days=1),
        f"BOM {period.first_gas_day.isoformat()}",
    )


def _basis(item: SnapshotInput) -> str:
    return "executable quotes" if item.detail.get("basis") == "quote" else "closes"


class MarketScanEvaluator:
    """Types L, P and T over the market, with no position: the market lane."""

    name = "market_scan"
    version = "1"
    type = OpportunityType.PROMPT_ARBITRAGE

    def __init__(self, graph_provider=shipped_graph) -> None:
        self.graph_provider = graph_provider

    def evaluate(self, snapshot: SnapshotReader, context: EvaluationContext) -> Iterable[Candidate]:
        """Market L, P and T candidates."""

        graph = self.graph_provider()
        # L needs a proven path between market areas; P and T are at one hub.
        graph_hubs = [hub for hub in SCAN_HUBS if graph.hub_for(hub) is not None]
        today = DeliveryPeriod.parse(gas_day_label(context.as_of_utc)).start
        yield from self._locational(snapshot, context, graph, graph_hubs, today)
        yield from self._prompt(snapshot, context, SCAN_HUBS, today)
        yield from self._seasonal(snapshot, context, SCAN_HUBS, today)

    # ------------------------------------------------------------------ L
    def _locational(self, s, ctx, graph, hubs, today):
        route = _Route(s, ctx, graph)
        month = today.month % 12 + 1
        year = today.year + (1 if month == 1 else 0)
        periods = (day_ahead(today), DeliveryPeriod.month(year, month))
        for period in periods:
            for buy in hubs:
                for sell in hubs:
                    if buy == sell or graph.hub_for(buy) == graph.hub_for(sell):
                        continue
                    candidate = route.price(
                        OpportunityType.LOCATIONAL,
                        buy,
                        sell,
                        period,
                        LOT_MWH_PER_DAY,
                        None,
                        side="new",
                    )
                    if candidate is None or candidate.blockers:
                        continue
                    if not all(item.held for item in candidate.inputs):
                        continue  # only a complete priced route is a market item
                    fields = dict(candidate.claim_fields)
                    fields["needs"] = (
                        f"transport capacity on {fields.get('costs', 'the route')}, a credit "
                        f"line at {buy} and {sell}, a mandate covering both"
                    )
                    yield replace(
                        candidate,
                        identity=("market", *candidate.identity),
                        book_ids=(),
                        claim_key="market.spread",
                        claim_fields=fields,
                        scope="market",
                        evaluator=self.name,
                    )

    # ------------------------------------------------------------------ P
    def _prompt(self, s, ctx, hubs, today):
        wd = DeliveryPeriod.gas_day(today)
        da = day_ahead(today)
        pairs = [("within-day", wd, "day-ahead", da)]
        bom = balance_of_month(today)
        if bom is not None:
            pairs.append(("day-ahead", da, "balance of month", bom))
        for hub in hubs:
            for name_a, period_a, name_b, period_b in pairs:
                yield from self._prompt_pair(s, ctx, hub, name_a, period_a, name_b, period_b)

    def _prompt_pair(self, s, ctx, hub, name_a, period_a, name_b, period_b):
        mids = {}
        for name, period in ((name_a, period_a), (name_b, period_b)):
            bid, ask = s.price(hub, period, "bid"), s.price(hub, period, "ask")
            if not (bid.held and ask.held) or (bid.currency or EUR) != EUR:
                return
            mids[name] = (period, bid, ask)
        # The dearer product is sold at its bid, the cheaper bought at its offer.
        (sell_name, (sell_period, sell, _)), (buy_name, (buy_period, _, buy)) = sorted(
            mids.items(), key=lambda kv: kv[1][1].value, reverse=True
        )
        if sell_name == buy_name:
            return
        edge = (sell.value - buy.value).quantize(Q)
        if edge < PROMPT_MIN_EDGE:
            return
        lot = LOT_MWH_PER_DAY
        value = (edge * lot).quantize(MONEY)
        basis = _basis(sell) if _basis(sell) == _basis(buy) else "a quote and a close"
        expires = gas_day_start_for_date(
            min(sell_period.start, buy_period.start) + timedelta(days=1)
        )
        if expires <= ctx.as_of_utc:
            expires = ctx.as_of_utc + timedelta(hours=1)
        legs = (
            Leg(
                LegKind.TERM,
                "prompt.sell",
                f"Sell {hub} {sell_name} at the bid ({sell.label or sell.source_family})",
                rate=Measure(sell.value, sell.unit),
                contribution=Measure(sell.value, UNIT),
                input_class=sell.input_class,
                source_family=sell.source_family,
                source_ref=sell.source_ref,
                as_of_utc=sell.as_of_utc,
                input_keys=(sell.key,),
            ),
            Leg(
                LegKind.TERM,
                "prompt.buy",
                f"Buy {hub} {buy_name} at the offer ({buy.label or buy.source_family})",
                rate=Measure(buy.value, buy.unit),
                contribution=Measure(-buy.value, UNIT),
                input_class=buy.input_class,
                source_family=buy.source_family,
                source_ref=buy.source_ref,
                as_of_utc=buy.as_of_utc,
                input_keys=(buy.key,),
            ),
            Leg(LegKind.RESULT, "prompt.edge", "Edge at one hub", subtotal=Measure(edge, UNIT)),
            Leg(
                LegKind.VOLUME,
                "prompt.lot",
                f"Stated lot {grouped(lot)} MWh",
                quantity=Measure(lot, "MWh"),
            ),
            Leg(LegKind.VALUE, "prompt.value", "Value on the lot", quantity=Measure(value, EUR)),
        )
        yield Candidate(
            type=OpportunityType.PROMPT_ARBITRAGE,
            identity=("market", hub, sell_name, buy_name),
            period=sell_period if sell_period.start <= buy_period.start else buy_period,
            book_ids=(),
            claim_key="prompt.spread",
            claim_fields={
                "hub": hub,
                "sell": sell_name,
                "buy": buy_name,
                "margin": f"{signed(edge, 3)} EUR/MWh",
                "volume": f"{grouped(lot)} MWh",
                "basis": basis,
                "value": f"EUR {grouped(value)}",
                "needs": f"a credit line at {hub} and a mandate for its prompt",
                "route_points": "",
            },
            headline=Measure(edge, UNIT),
            volume=Measure(lot, "MWh"),
            value=Measure(value, EUR),
            value_eur=Measure(value, EUR),
            margin_eur=Measure(edge, UNIT),
            legs=legs,
            falsifiers=(
                Falsifier(
                    "prompt.edge_closes",
                    f"{hub} {sell_name} less {buy_name} below {grouped(PROMPT_MIN_EDGE, 2)} "
                    "EUR/MWh (the prompt's normal shape).",
                ),
                Falsifier(
                    "prompt.not_executable",
                    f"No {buy_name} offer or {sell_name} bid of {grouped(lot)} MWh at {hub}"
                    + (
                        " (priced from closes, not quotes)."
                        if basis != "executable quotes"
                        else "."
                    ),
                ),
            ),
            sensitivity=(
                Sensitivity(
                    "edge",
                    "per_unit",
                    Measure((lot / 10).quantize(MONEY), EUR),
                    f"±0.10 EUR/MWh on the edge = ±EUR {grouped(lot / 10)}",
                ),
            ),
            checks=(
                Check(
                    CheckKind.CREDIT,
                    CheckResult.NOT_ASSESSED,
                    f"needs a credit line with a counterparty at {hub}",
                ),
                Check(
                    CheckKind.MANDATE,
                    CheckResult.NOT_ASSESSED,
                    f"needs a mandate covering the {hub} prompt",
                ),
            ),
            expires_at_utc=expires,
            inputs=(sell, buy),
            evaluator=self.name,
            evaluator_version=self.version,
            scope="market",
        )

    # ------------------------------------------------------------------ T
    def _seasonal(self, s, ctx, hubs, today):
        costs = [s.assumption(key) for key in STORAGE_COSTS]
        if not all(item.held for item in costs):
            return  # no stated storage cost: nothing is listed (never a zero cost)
        cost = sum((item.value for item in costs), Decimal(0)).quantize(Q)
        # The next full winter: October of the first year whose October is after this month.
        winter_year = today.year + (1 if today.month >= 4 else 0)
        summer = [DeliveryPeriod.month(winter_year, m) for m in range(4, 10)]
        winter = [DeliveryPeriod.month(winter_year, m) for m in (10, 11, 12)] + [
            DeliveryPeriod.month(winter_year + 1, m) for m in (1, 2, 3)
        ]
        holdings = {
            str(row.detail.get("hub") or "").upper() for row in s.collection("storage") if row.held
        }
        for hub in hubs:
            yield from self._seasonal_hub(s, ctx, hub, summer, winter, costs, cost, holdings)

    def _seasonal_hub(self, s, ctx, hub, summer, winter, costs, cost, holdings):
        # The season products as quoted (Sum-27 offer, Win-27 bid), else the month averages.
        year = summer[0].start.year % 100
        season_buy = s.price(hub, DeliveryPeriod.season("SUM", year), "ask")
        season_sell = s.price(hub, DeliveryPeriod.season("WIN", year), "bid")
        if season_buy.held and season_sell.held:
            buys, sells = [season_buy], [season_sell]
        else:
            buys = [s.price(hub, p, "ask") for p in summer]
            sells = [s.price(hub, p, "bid") for p in winter]
        if not all(item.held for item in buys + sells):
            return
        if any((item.currency or EUR) != EUR for item in buys + sells):
            return
        buy = (sum((i.value for i in buys), Decimal(0)) / len(buys)).quantize(Q)
        sell = (sum((i.value for i in sells), Decimal(0)) / len(sells)).quantize(Q)
        gross = (sell - buy).quantize(Q)
        net = (gross - cost).quantize(Q)
        if net <= 0:
            return
        lot = STORAGE_LOT_MWH
        value = (net * lot).quantize(MONEY)
        first, second = f"Sum-{summer[0].start:%y}", f"Win-{winter[0].start:%y}"
        held = hub.upper() in holdings
        basis = _basis(buys[0])
        legs = (
            Leg(
                LegKind.TERM,
                "seasonal.sell",
                f"Sell {hub} {second} at the bid"
                + (f", month average ({basis})" if len(sells) > 1 else f" ({basis})"),
                rate=Measure(sell, UNIT),
                contribution=Measure(sell, UNIT),
                input_class=sells[0].input_class,
                source_family=sells[0].source_family,
                input_keys=tuple(i.key for i in sells),
            ),
            Leg(
                LegKind.TERM,
                "seasonal.buy",
                f"Buy {hub} {first} at the offer"
                + (f", month average ({basis})" if len(buys) > 1 else f" ({basis})"),
                rate=Measure(buy, UNIT),
                contribution=Measure(-buy, UNIT),
                input_class=buys[0].input_class,
                source_family=buys[0].source_family,
                input_keys=tuple(i.key for i in buys),
            ),
            Leg(
                LegKind.SUBTOTAL,
                "seasonal.gross",
                "Winter over summer",
                subtotal=Measure(gross, UNIT),
            ),
            Leg(
                LegKind.TERM,
                "seasonal.cost",
                "Storage capacity, injection and withdrawal (the firm's stated costs)",
                rate=Measure(cost, UNIT),
                contribution=Measure(-cost, UNIT),
                input_class=costs[0].input_class,
                source_family=costs[0].source_family,
                input_keys=tuple(i.key for i in costs),
            ),
            Leg(LegKind.RESULT, "seasonal.net", "Net after storage", subtotal=Measure(net, UNIT)),
            Leg(
                LegKind.VOLUME,
                "seasonal.lot",
                f"Stated lot {grouped(lot)} MWh",
                quantity=Measure(lot, "MWh"),
            ),
            Leg(LegKind.VALUE, "seasonal.value", "Value on the lot", quantity=Measure(value, EUR)),
        )
        period = DeliveryPeriod(summer[0].start, winter[-1].end, f"{first}/{second}")
        yield Candidate(
            type=OpportunityType.TIME_SPREAD,
            identity=("market", hub, first, second),
            period=period,
            book_ids=(),
            claim_key="seasonal.market",
            claim_fields={
                "hub": hub,
                "first": first,
                "second": second,
                "where": "market",
                "margin": f"{signed(net, 3)} EUR/MWh",
                "cost": f"{grouped(cost, 2)} EUR/MWh",
                "volume": f"{grouped(lot)} MWh",
                "value": f"EUR {grouped(value)}",
                "needs": "storage capacity" + ("" if held else f" (none held at {hub})"),
                "route_points": "",
            },
            headline=Measure(net, UNIT),
            volume=Measure(lot, "MWh"),
            value=Measure(value, EUR),
            value_eur=Measure(value, EUR),
            margin_eur=Measure(net, UNIT),
            legs=legs,
            assumptions=tuple(_Route._assumption_use(item) for item in costs),
            falsifiers=(
                Falsifier(
                    "seasonal.spread_below_cost",
                    f"{hub} {second} over {first} below {grouped(cost, 3)} EUR/MWh.",
                ),
                Falsifier(
                    "seasonal.no_capacity",
                    f"No storage capacity for {grouped(lot)} MWh reachable from {hub}.",
                ),
            ),
            sensitivity=(
                Sensitivity(
                    "storage_cost",
                    "breakeven",
                    Measure(gross, UNIT),
                    f"Breakeven storage cost {grouped(gross, 3)} EUR/MWh",
                ),
            ),
            checks=(
                Check(
                    CheckKind.CAPACITY,
                    CheckResult.PASS if held else CheckResult.NOT_ASSESSED,
                    "storage held at the hub" if held else "needs storage capacity",
                ),
            ),
            expires_at_utc=gas_day_start_for_date(summer[0].start),
            inputs=(*buys, *sells, *costs),
            evaluator=self.name,
            evaluator_version=self.version,
            scope="market",
        )


MARKET_SCAN = register(MarketScanEvaluator())
