"""Type R: re-routing flexible volume through the resource pool (design basis 2, B.3).

The resource-pool optimiser (``domain/route_cost/resource_pool.py``, exact min-cost flow) is
run twice on the composed pool of one gas day: with every sale option, and with the local
disposals only (each resource sold where it is delivered). The claim is the optimiser's own
difference:

    delta = P&L per day (all options) - P&L per day (local disposals only)

so it equals the optimiser's delta margin by construction; the slices that differ are listed
on their own rows (resource, option, MWh/d, unit margin). Single-currency pools only (design
J.1): the optimiser's result fields carry one currency, so a pool mixing currencies is a named
"cannot evaluate" record. The scenario's default financing rate is the firm's
``financing.rate``; resources from saved contracts carry their own contract rate.

Worked example (fixture): one NBP resource of 10,000 MWh/d at 30.00 GBP/MWh, a local sale at
31.00 and a route to a second market at 33.50 less 1.20 route cost, capacity 6,000 MWh/d.
Local only: 10,000 x 1.00 = GBP 10,000/d; with the route: 6,000 x 2.30 + 4,000 x 1.00 =
GBP 17,800/d (before early-cash terms, which the optimiser adds identically on both sides);
the claim is the optimiser's difference, GBP 7,800/d with zero lag terms.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from decimal import Decimal

from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date
from eurogas_nexus.domain.opportunities.claims import grouped, signed
from eurogas_nexus.domain.opportunities.evaluator import EvaluationContext, register
from eurogas_nexus.domain.opportunities.model import (
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
from eurogas_nexus.domain.route_cost.resource_pool import (
    PortfolioOptimizationScenario,
    PortfolioResource,
    PortfolioSaleOption,
    optimize_resource_pool,
)
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.snapshot import SnapshotReader

MONEY = Decimal("0.01")
Q = Decimal("0.000001")
LOCAL = "LOCAL_MARKET_DISPOSITION"


def _model(model, detail):
    fields = model.model_fields
    return model.model_validate({k: v for k, v in detail.items() if k in fields})


def _d(value: float) -> Decimal:
    return Decimal(str(round(value, 6)))


class RerouteEvaluator:
    """Type R over the ``resource_pool`` collection."""

    name = "reroute"
    version = "1"
    type = OpportunityType.REROUTE

    def evaluate(self, snapshot: SnapshotReader, context: EvaluationContext) -> Iterable[Candidate]:
        """At most one candidate: the pool's re-routing gain for the next gas day."""

        rows = snapshot.collection("resource_pool")
        resources = [row for row in rows if row.detail.get("row_kind") == "resource"]
        options = [row for row in rows if row.detail.get("row_kind") == "option"]
        reroutes = [row for row in options if row.detail.get("route_topology_kind") != LOCAL]
        if not resources or not reroutes:
            return
        today = DeliveryPeriod.parse(gas_day_label(context.as_of_utc)).start
        period = DeliveryPeriod.gas_day(today + timedelta(days=1))
        expires = gas_day_start_for_date(period.start)
        if expires <= context.as_of_utc:
            return
        try:
            pool_resources = [_model(PortfolioResource, row.detail) for row in resources]
            pool_options = [_model(PortfolioSaleOption, row.detail) for row in options]
        except ValueError:
            return
        currencies = {r.contract_cost_currency.upper() for r in pool_resources} | {
            o.sale_price_currency.upper() for o in pool_options
        }
        inputs = tuple(resources + options)
        if len(currencies) != 1:
            subject = f"a pool in {', '.join(sorted(currencies))} (single-currency pools only)"
            yield Candidate(
                type=self.type,
                identity=("pool", "currency"),
                period=period,
                book_ids=(),
                claim_key="blocked.input_missing",
                claim_fields={"subject": subject},
                headline=Measure(Decimal(0), "EUR/d"),
                legs=(),
                falsifiers=(),
                blockers=(
                    Blocker(
                        "input_missing",
                        subject,
                        f"Cannot evaluate: re-routing for {subject}.",
                        "typed money on the optimiser result (later package)",
                    ),
                ),
                expires_at_utc=expires,
                inputs=inputs,
                evaluator=self.name,
                evaluator_version=self.version,
            )
            return
        (currency,) = currencies
        rate = snapshot.assumption("financing.rate")
        default_rate = float(rate.value) if rate.held else 0.0

        def run(sale_options):
            return optimize_resource_pool(
                PortfolioOptimizationScenario(
                    portfolio_id="opportunity-reroute",
                    resources=pool_resources,
                    sale_options=sale_options,
                    annual_financing_rate_pct=default_rate,
                )
            )

        full = run(pool_options)
        base = run([o for o in pool_options if o.route_topology_kind == LOCAL])
        with_all = _d(full.total_net_pnl_gbp_per_day)
        local_only = _d(base.total_net_pnl_gbp_per_day)
        delta = with_all - local_only
        if delta <= 0:
            return
        before = {(a.resource_id, a.option_id): a for a in base.allocations}
        changed = [
            a
            for a in full.allocations
            if (a.resource_id, a.option_id) not in before
            or abs(
                before[(a.resource_id, a.option_id)].allocated_quantity_mwh_per_day
                - a.allocated_quantity_mwh_per_day
            )
            > 1e-6
        ]
        routed = [
            a
            for a in changed
            if any(
                o.option_id == a.option_id and o.route_topology_kind != LOCAL for o in pool_options
            )
        ]
        moved = sum((_d(a.allocated_quantity_mwh_per_day) for a in routed), Decimal(0))
        if moved <= 0:
            return
        unit = f"{currency}/d"
        names = {o.option_id: o.label for o in pool_options}
        legs = [
            Leg(
                LegKind.TERM,
                "reroute.with_routes",
                f"Pool P&L per day with every sale option (min-cost flow, {full.status})",
                contribution=Measure(with_all, unit),
                input_class=None,
                input_keys=tuple(item.key for item in inputs),
            ),
            *[
                Leg(
                    LegKind.CONVERSION,
                    "reroute.slice",
                    f"{a.resource_id} -> {names.get(a.option_id, a.option_id)}: "
                    f"{grouped(_d(a.allocated_quantity_mwh_per_day))} MWh/d at "
                    f"{signed(_d(a.net_margin_gbp_mwh), 3)} {currency}/MWh",
                    quantity=Measure(_d(a.allocated_quantity_mwh_per_day), "MWh/d"),
                    rate=Measure(_d(a.net_margin_gbp_mwh), f"{currency}/MWh"),
                )
                for a in changed
            ],
            Leg(
                LegKind.TERM,
                "reroute.local_only",
                f"Pool P&L per day selling each resource locally ({base.status})",
                contribution=Measure(-local_only, unit),
                input_keys=tuple(item.key for item in resources),
            ),
            Leg(
                LegKind.RESULT,
                "reroute.delta",
                "Gain from re-routing per day",
                subtotal=Measure(delta, unit),
            ),
        ]
        value = (delta * 1).quantize(MONEY)
        legs += [
            Leg(LegKind.VOLUME, "reroute.days", "One gas day", quantity=Measure(Decimal(1), "d")),
            Leg(LegKind.VALUE, "reroute.value", "Value", quantity=Measure(value, currency)),
        ]
        margin = (delta / moved).quantize(Q)
        to_eur = None
        if currency == "EUR":
            to_eur = (margin, value)
        else:
            fx = snapshot.fx(currency, "EUR", period)
            if fx.held:
                inputs = (*inputs, fx)
                to_eur = ((margin * fx.value).quantize(Q), (value * fx.value).quantize(MONEY))
        capacity = [o for o in pool_options if o.option_id in {a.option_id for a in routed}]
        limits = [o.capacity_limit_mwh_per_day for o in capacity]
        checks = (
            Check(
                CheckKind.CAPACITY,
                CheckResult.PASS
                if all(limit is not None for limit in limits)
                else CheckResult.NOT_ASSESSED,
                "route capacity "
                + ", ".join(
                    "not held" if limit is None else f"{grouped(_d(limit))} MWh/d"
                    for limit in limits
                ),
            ),
            Check(
                CheckKind.CONTRACT,
                CheckResult.PASS,
                "every routed resource declares the sale mode the option needs",
            ),
            Check(
                CheckKind.MANDATE,
                CheckResult.NOT_ASSESSED,
                "mandate headroom of the routed sale is not assessed for the pool",
            ),
        )
        first = routed[0]
        source = {r.resource_id: r.location_point_name for r in pool_resources}
        target = {o.option_id: o.target_point_name for o in pool_options}
        route_points = _route_points(
            source.get(first.resource_id, ""), target.get(first.option_id, "")
        )
        yield Candidate(
            type=self.type,
            identity=tuple(sorted(f"{a.resource_id}->{a.option_id}" for a in routed)),
            period=period,
            book_ids=(),
            claim_key="reroute.pool",
            claim_fields={
                "gas_day": period.label,
                "moved": grouped(moved),
                "resource": first.resource_id,
                "option": names.get(first.option_id, first.option_id),
                "delta": f"{currency} {grouped(delta, 2)}",
                "margin": f"{signed(margin, 3)} {currency}/MWh",
                # The re-routed path for the map: ordered point ids, comma-separated ("" when
                # the two points are not on the pricing graph).
                "route_points": ",".join(route_points),
            },
            headline=Measure(delta, unit),
            volume=Measure(Decimal(1), "d"),
            value=Measure(value, currency),
            value_eur=None if to_eur is None else Measure(to_eur[1], "EUR"),
            margin_eur=None if to_eur is None else Measure(to_eur[0], "EUR/MWh"),
            legs=tuple(legs),
            falsifiers=(
                Falsifier(
                    "reroute.prices",
                    f"The routed markets' margin over local sale falls below "
                    f"{grouped(margin, 3)} {currency}/MWh.",
                ),
                Falsifier(
                    "reroute.capacity", "The route capacity for the gas day is not available."
                ),
            ),
            sensitivity=(
                Sensitivity(
                    "routed_margin",
                    "per_unit",
                    Measure(moved.quantize(MONEY), currency),
                    f"±1 {currency}/MWh on the routed margin = ±{currency} "
                    f"{grouped(moved)} per day",
                ),
            ),
            checks=checks,
            expires_at_utc=expires,
            inputs=inputs,
            evaluator=self.name,
            evaluator_version=self.version,
            extra={"full_status": full.status, "base_status": base.status},
        )


REROUTE = register(RerouteEvaluator())


def _route_points(from_point: str, to_point: str) -> list[str]:
    """Ordered point ids of the proven path between two points' market areas, or []."""

    from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

    graph = shipped_market_area_graph()
    start, target = graph.hub_for(from_point), graph.hub_for(to_point)
    if not start or not target or start == target:
        return []
    crossings = graph.route(start, target)
    if not crossings:
        return []
    return list(dict.fromkeys(point for crossing in crossings for point in crossing.points))
