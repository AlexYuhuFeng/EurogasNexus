"""Research → Spreads: interpret a description into a StrategySpec, check it, evaluate it.

Three steps, each deterministic except the optional translation:

1. **Interpret** (``interpret``): text → StrategySpec. The model, when the deployment and the
   caller may use one, only translates (it is given the instruments the caller holds and the
   spec's shape, and must answer with JSON); the small parser of ``domain/research/
   strategy_text.py`` covers the common statement without a model. Pasted code is text: it is
   never run. Nothing the model writes is shown; the "understood as" chips are drawn from the
   spec.
2. **Check** (``check``): the spec against the caller's instrument catalogue, the units
   authority and the proven network; every gap is a question with choices (an unknown hub
   lists the hubs held; a tenor not held lists the tenors held; an unproven route offers to
   drop the cost), never a refusal.
3. **Evaluate** (``evaluate_curve`` / the spread lab for a history): every figure from the
   engine. A curve: the latest close of each leg per delivery month, converted to the display
   unit at the forward FX of that month (or spot when asked), the spread ``Σ weight × price``,
   less the route's published tariffs in the stated direction, converted the same way. Each
   row carries the input class of every input and the weakest of them; a simulated price
   keeps the row simulated.

研究 → 价差：把文字描述解释为 StrategySpec（模型仅翻译，可无模型运行），按已持有的合约、
单位与网络检查并以问题形式指出缺口，再由确定性引擎计算全部数字。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.application.instrument_catalogue import classify_tenor, source_class
from eurogas_nexus.application.market_normalisation import (
    NormalisationError,
    conversion,
    display_unit,
    parse_price_unit,
)
from eurogas_nexus.application.route_tariff_cost import cheapest_route, weakest
from eurogas_nexus.domain.market.fx_forward import Delivery, FxHoldings
from eurogas_nexus.domain.market.units import HUB_NATIVE_PRICE_UNIT
from eurogas_nexus.domain.research.strategy_spec import (
    Issue,
    StrategySpec,
    spec_from_dict,
)
from eurogas_nexus.domain.research.strategy_text import parse_description

ModelCall = Callable[[list[dict[str, str]]], str | None]

#: The forward curve is read up to this many delivery months ahead.
MAX_CURVE_MONTHS = 24
DISPLAY_UNITS = ("EUR/MWh", "p/th", "USD/MMBtu", "GBP/MWh")
_CODE_LIKE = re.compile(
    r"(\bdef\b|\breturn\b|\bimport\b|=>|;\s*$|\{|\}|==|\bfunction\b|\bselect\b)",
    re.IGNORECASE | re.MULTILINE,
)


# ------------------------------------------------------------------------- catalogue facts


@dataclass
class Holdings:
    """What the caller's store holds, read once per request."""

    rows: list[dict[str, Any]]
    fx: FxHoldings
    tariffs: list[dict[str, Any]]
    today: date
    catalogue: dict[str, Any] = field(default_factory=dict)
    #: TAR-2: the firm's pipeline bookings and its configured source order.
    bookings: list[Any] = field(default_factory=list)
    orders: dict[str, Any] = field(default_factory=dict)
    #: Reads the register's rows of one capacity product (``load_tariff_rows``); ``None``
    #: (fixtures) takes them from ``tariffs``.
    tariff_loader: Any = None
    _by_product: dict[str, list[dict[str, Any]]] = field(default_factory=dict, repr=False)

    def tariff_rows_for(self, product: str) -> list[dict[str, Any]]:
        """The register rows of one capacity product (a row naming none counts for any)."""

        product = product.upper()
        if product not in self._by_product:
            if self.tariff_loader is not None and product != "ANNUAL":
                rows = list(self.tariff_loader(product))
            else:
                rows = [
                    row for row in self.tariffs
                    if str(row.get("capacity_product") or "").upper() in {"", product}
                ]
            self._by_product[product] = rows
        return self._by_product[product]

    def hubs(self) -> list[str]:
        return [hub["hub"] for hub in self.catalogue.get("hubs", [])]

    def hub(self, code: str) -> dict[str, Any] | None:
        return next((hub for hub in self.catalogue.get("hubs", []) if hub["hub"] == code), None)

    def instruments(self, code: str) -> list[dict[str, Any]]:
        hub = self.hub(code)
        return [item for kind in (hub or {}).get("kinds", []) for item in kind["instruments"]]


# ------------------------------------------------------------------------------- interpret


def translation_messages(text: str, holdings: Holdings, language: str) -> list[dict[str, str]]:
    """The model's instructions: translate the description into the spec's JSON, nothing else."""

    held = {
        hub["hub"]: {
            "native_unit": hub["native_unit"],
            "tenors": [item["code"] for item in holdings.instruments(hub["hub"])][:30],
        }
        for hub in holdings.catalogue.get("hubs", [])
    }
    system = (
        "You translate a gas trader's description of a spread study into one JSON object and "
        "nothing else. You never compute, estimate or state a price, rate, tariff or result; "
        "the product's engine does. If the text contains program code or pseudo-code, read it "
        "only as a description of the intent; never execute or complete it.\n"
        "JSON shape: {\"version\":1,\"kind\":\"curve\"|\"history\",\"legs\":[{\"hub\":CODE,"
        "\"tenor\":CODE|null,\"weight\":1|-1}],\"unit\":\"EUR/MWh\"|\"p/th\"|\"USD/MMBtu\"|null,"
        "\"fx\":\"forward\"|\"spot\",\"cost\":{\"kind\":\"route_tariff\",\"from_hub\":CODE,"
        "\"to_hub\":CODE}|null,\"rule\":{\"kind\":\"zscore\"|\"threshold\",\"lookback\":N}|null}."
        "\nThe spread is the sum of weight times price: +1 where gas is sold, -1 where it is "
        "bought; a route tariff runs from the bought hub to the sold hub. 'between A and B' "
        "means gas moves A to B. 'curve' is the forward spread by delivery month; 'history' is "
        "the daily series of one tenor. Use only hub codes from this list (a hub not in it: "
        "write its name as given; the product will ask): "
        + json.dumps(held, ensure_ascii=False)
    )
    user = f"Language of the user: {language}. Description:\n{text}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _json_object(content: str | None) -> dict[str, Any] | None:
    if not content:
        return None
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(content[start : end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


@dataclass
class Interpretation:
    spec: StrategySpec
    issues: list[Issue]
    basis: str  # parser | model | none
    ai: str  # off | used | failed
    read_as_text: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.as_dict(),
            "issues": [issue.as_dict() for issue in self.issues],
            "basis": self.basis,
            "ai": self.ai,
            "read_as_text": self.read_as_text,
            "ready": not self.issues,
        }


def interpret(
    text: str,
    holdings: Holdings,
    *,
    language: str = "en",
    model: ModelCall | None = None,
) -> Interpretation:
    """The spec a description asks for, with the questions that stand before it can run."""

    clean = (text or "").strip()[:4000]
    held = set(holdings.hubs())
    parsed = parse_description(clean, held_hubs=held)
    raw: dict[str, Any] | None = None
    basis, ai = "none", "off"
    if model is not None:
        ai = "failed"
        candidate = _json_object(model(translation_messages(clean, holdings, language)))
        if candidate and len(candidate.get("legs") or []) >= 2:
            raw, basis, ai = candidate, "model", "used"
    if raw is None and parsed is not None:
        raw, basis = parsed, "parser"
    if raw is None:
        spec = StrategySpec("curve", ())
        issue = Issue(
            "instruments_unclear",
            "legs",
            "which two hubs? e.g. 'NBP vs TTF front month' or 'forward spread between TTF "
            "and NBP net of tariff'",
            choices=tuple(sorted(held))[:12],
        )
        return Interpretation(spec, [issue], basis, ai, bool(_CODE_LIKE.search(clean)))
    first_named = raw.get("_first_named")
    spec = spec_from_dict(raw)
    if spec.unit is None and spec.legs:
        anchor = first_named or spec.legs[0].hub
        native = HUB_NATIVE_PRICE_UNIT.get(anchor)
        if native:
            spec = _with(spec, unit=display_unit(parse_price_unit(native)))
    issues = list(spec.issues) + check(spec, holdings)
    return Interpretation(spec, issues, basis, ai, bool(_CODE_LIKE.search(clean)))


def _with(spec: StrategySpec, **changes: Any) -> StrategySpec:
    from dataclasses import replace

    return replace(spec, **changes)


# ----------------------------------------------------------------------------------- check


def check(spec: StrategySpec, holdings: Holdings) -> list[Issue]:
    """Questions that stand between the spec and a result, from what the store holds."""

    issues: list[Issue] = []
    held = holdings.hubs()
    for index, leg in enumerate(spec.legs):
        if leg.hub not in held:
            issues.append(Issue(
                "hub_not_held", f"legs[{index}].hub",
                f"{leg.hub} is not a hub with prices you can use; which hub is meant?",
                choices=tuple(held[:12]),
            ))
            continue
        items = holdings.instruments(leg.hub)
        if spec.kind == "curve":
            if not any(item["product_kind"] == "month" and not item["expired"] for item in items):
                issues.append(Issue(
                    "no_curve", f"legs[{index}].hub",
                    f"no forward curve by delivery month is held for {leg.hub}; study a "
                    "history instead?",
                    choices=("history",),
                ))
        else:
            codes = [item["code"] for item in items]
            if not leg.tenor or not _instrument(items, leg.tenor):
                issues.append(Issue(
                    "tenor_not_held", f"legs[{index}].tenor",
                    f"{leg.hub} {leg.tenor or ''}".strip() + ": which tenor? These are held:",
                    choices=tuple(codes[:12]),
                ))
            elif (found := _instrument(items, leg.tenor)) and found["observations"] < 30:
                issues.append(Issue(
                    "history_short", f"legs[{index}].tenor",
                    f"{leg.hub} {found['code']} has {found['observations']} days held; a "
                    "history needs 30",
                    choices=("curve",),
                ))
    if spec.unit:
        try:
            parsed = parse_price_unit(spec.unit)
            if parsed.unit.dimension.value != "energy":
                raise NormalisationError("unsupported_price_unit", spec.unit)
        except NormalisationError:
            issues.append(Issue("unit_unknown", "unit",
                                f"'{spec.unit}' is not a price unit; which one?",
                                choices=DISPLAY_UNITS))
    if spec.cost is not None:
        from eurogas_nexus.application.route_tariff_cost import MAX_ROUTE_HOPS
        from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

        graph = shipped_market_area_graph()
        start, target = graph.hub_for(spec.cost.from_hub), graph.hub_for(spec.cost.to_hub)
        # Any chain of market areas counts (NBP -> ZTP -> PEG), not only neighbours.
        if not start or not target or not graph.all_hub_paths(
            start, target, max_hops=MAX_ROUTE_HOPS
        ):
            issues.append(Issue(
                "route_unproven", "cost",
                f"no proven pipeline route from {spec.cost.from_hub} to {spec.cost.to_hub} is "
                "held; show the spread without a transport cost?",
                choices=("no_cost",),
            ))
    if spec.kind == "history" and spec.cost is not None and spec.fx == "spot":
        pass  # allowed: the cost lines use spot FX too
    return issues


def _instrument(items: Sequence[Mapping[str, Any]], code: str) -> Mapping[str, Any] | None:
    lower = code.strip().lower()
    for item in items:
        if item["code"].lower() == lower or item["tenor"].lower() == lower:
            return item
    return None


def stored_tenor(holdings: Holdings, hub: str, code: str) -> str | None:
    """The stored tenor key the spread lab reads for a hub and a product code."""

    found = _instrument(holdings.instruments(hub), code)
    return str(found["tenor"]) if found else None


# ----------------------------------------------------------------------------- evaluation


def _curve_points(rows: Sequence[Mapping[str, Any]], hub: str, today: date) -> dict[str, dict]:
    """The latest close per delivery month of a hub (a real source beats a simulated one)."""

    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("hub") != hub or not row.get("hub_resolved", True):
            continue
        shape = classify_tenor(str(row.get("tenor") or ""), today)
        if shape["product_kind"] != "month" or shape.get("expired"):
            continue
        if date.fromisoformat(shape["delivery"]["first_gas_day"]) <= today:
            continue  # delivery has begun: not a forward month
        klass = source_class(str(row["source_system"]), simulated=bool(row.get("simulated")),
                             settlement=bool(row.get("settlement")))
        key = shape["delivery"]["first_gas_day"]
        rank = (klass != "simulated", row["observed_at_utc"])
        held = best.get(key)
        if held is None or rank > held["_rank"]:
            best[key] = {**row, "_rank": rank, "_class": klass, "_label": shape["code"],
                         "_last": shape["delivery"]["last_gas_day"]}
    return best


def evaluate_curve(spec: StrategySpec, holdings: Holdings) -> dict[str, Any]:
    """The forward spread by delivery month, net of the route cost when the spec asks."""

    unit = spec.unit or display_unit(parse_price_unit(
        HUB_NATIVE_PRICE_UNIT.get(spec.legs[0].hub, "EUR/MWh")))
    curves = {leg.hub: _curve_points(holdings.rows, leg.hub, holdings.today)
              for leg in spec.legs}
    months = sorted(set.intersection(*(set(curve) for curve in curves.values())))[
        :MAX_CURVE_MONTHS]
    out_rows: list[dict[str, Any]] = []
    route_front: dict[str, Any] | None = None
    for first in months:
        sample = curves[spec.legs[0].hub][first]
        delivery = Delivery(date.fromisoformat(first), date.fromisoformat(sample["_last"]),
                            "month", sample["_label"])
        fx_delivery = None if spec.fx == "spot" else delivery
        legs_out: list[dict[str, Any]] = []
        refused: str | None = None
        gross = 0.0
        classes: list[str] = []
        for leg in spec.legs:
            point = curves[leg.hub][first]
            try:
                conv = conversion(point["unit"], unit, holdings=holdings.fx, as_of=point["day"],
                                  delivery=fx_delivery)
            except NormalisationError as exc:
                refused = str(exc)
                break
            value = point["price"] * conv.factor
            fx = conv.fx.as_dict() if conv.fx else None
            klass = weakest([point["_class"], *([conv.fx.input_class] if conv.fx else [])])
            classes.append(klass)
            native_value, native_unit = _native(leg.hub, point)
            legs_out.append({
                "hub": leg.hub,
                "weight": leg.weight,
                "native_value": native_value,
                "native_unit": native_unit,
                "value": value,
                "source_system": point["source_system"],
                "observed": point["day"].isoformat(),
                "input_class": klass,
                "price_class": point["_class"],
                "fx": fx,
            })
            gross += leg.weight * value
        row: dict[str, Any] = {
            "month": first,
            "label": delivery.label,
            "legs": legs_out,
            "gross": None if refused else gross,
            "cost": None,
            "net": None,
            "refused": refused,
        }
        if not refused and spec.cost is not None:
            choice = _route_choice(spec, spec.cost.from_hub, spec.cost.to_hub, delivery, holdings,
                                   unit, fx_delivery)
            route = choice.chosen
            cost_value = None
            cost_fx = None
            if route.total is not None and route.currency:
                try:
                    conv = conversion(f"{route.currency}/MWh", unit, holdings=holdings.fx,
                                      as_of=holdings.today, delivery=fx_delivery)
                    cost_value = route.total * conv.factor
                    cost_fx = conv.fx.as_dict() if conv.fx else None
                except NormalisationError as exc:
                    row["cost_refused"] = str(exc)
            row["cost"] = cost_value
            row["cost_class"] = route.input_class if cost_value is not None else "missing"
            row["cost_fx"] = cost_fx
            row["route_gas_years"] = route.gas_years
            delivery_year = _gas_year_label(delivery.first)
            # A tariff published for another gas year (an open-ended row carried forward) is
            # applied as an assumption, and said so.
            row["tariff_year_differs"] = any(
                "/" in year and year != delivery_year for year in route.gas_years
            )
            row["delivery_gas_year"] = delivery_year
            if row["tariff_year_differs"] and row["cost_class"] != "missing":
                row["cost_class"] = weakest([row["cost_class"], "assumption"])
            row["net"] = gross - cost_value if cost_value is not None else None
            classes.append(row["cost_class"])
            if route_front is None:
                every = choice if not spec.cost.through else _route_choice(
                    spec, spec.cost.from_hub, spec.cost.to_hub, delivery, holdings, unit,
                    fx_delivery, honour_through=False)
                route_front = _route_payload(choice, every, cost_value, unit, holdings,
                                             fx_delivery)
        elif not refused:
            row["net"] = gross
        row["input_class"] = "missing" if refused else weakest(classes)
        row["simulated"] = any(
            leg_out["input_class"] == "simulated" or leg_out["price_class"] == "simulated"
            for leg_out in legs_out
        ) or row.get("cost_class") == "simulated"
        out_rows.append(row)
    usable = [row for row in out_rows if row["net"] is not None or row["gross"] is not None]
    # Tariffs are published per gas year: with the cost asked for, the months a published
    # tariff covers are priced and the later ones are not. The result says where pricing stops
    # and takes its class from the priced months, not from the unpublished ones.
    coverage = None
    if spec.cost is not None:
        priced = [row for row in out_rows if row["net"] is not None]
        unpriced = [row for row in out_rows if row["net"] is None and row["gross"] is not None]
        if priced and unpriced:
            coverage = {
                "priced_to": priced[-1]["label"],
                "unpriced_from": unpriced[0]["label"],
                "months_priced": len(priced),
                "reason": "tariff not published",
            }
    fx_labels = sorted({
        leg["fx"]["label"] for row in out_rows for leg in row["legs"] if leg.get("fx")
    })
    return {
        "kind": "curve",
        "unit": unit,
        "fx_mode": spec.fx,
        "fx_labels": fx_labels,
        "rows": out_rows,
        "route": route_front,
        "months": len(out_rows),
        "input_class": (
            weakest(row["input_class"] for row in out_rows if row["net"] is not None)
            if coverage else
            weakest(row["input_class"] for row in out_rows) if out_rows else "missing"
        ),
        "coverage": coverage,
        "simulated": any(row["simulated"] for row in out_rows),
        "empty": None if usable else "no delivery month is held for every leg",
        "spread": " ".join(
            f"{'+' if leg.weight > 0 else '−'} {abs(leg.weight):g}×{leg.hub}" for leg in spec.legs
        ).lstrip("+ "),
    }


def _gas_year_label(day: date) -> str:
    start = day.year if day.month >= 10 else day.year - 1
    return f"{start}/{(start + 1) % 100:02d}"


def _native(hub: str, point: Mapping[str, Any]) -> tuple[float, str]:
    from eurogas_nexus.application.projections.daily_closes import in_native_unit

    value, unit = in_native_unit(hub, float(point["price"]), str(point["unit"]))
    return value, display_unit(parse_price_unit(unit)) if "/" in unit else unit


def _fx_factors(holdings: Holdings, currencies: set[str], into: str,
                delivery: Delivery | None) -> dict[str, float]:
    """Units of ``into`` per one unit of each currency, at the stated FX (forward or spot)."""

    from eurogas_nexus.domain.market.fx_forward import FxForwardError, conversion_rate

    out: dict[str, float] = {}
    for code in sorted(currencies - {into}):
        try:
            out[code] = conversion_rate(holdings.fx, code, into, as_of=holdings.today,
                                        delivery=delivery).rate
        except FxForwardError:
            continue
    return out


def _route_choice(spec: StrategySpec, start: str, end: str, delivery: Delivery,
                  holdings: Holdings, unit: str, fx_delivery: Delivery | None,
                  *, honour_through: bool = True):
    """The cheapest route (``route_tariff_cost.cheapest_route``), legs in another currency at
    the stated FX; the spec's ``through`` only for the direction the desk picked."""

    into = parse_price_unit(unit).currency
    currencies = {str(row.get("currency") or "").upper() for row in holdings.tariffs} - {""}
    picked = spec.cost is not None and (start, end) == (spec.cost.from_hub, spec.cost.to_hub)
    return cheapest_route(
        start, end, delivery, holdings.tariffs,
        through=spec.cost.through if honour_through and picked and spec.cost else None,
        fx=_fx_factors(holdings, currencies, into, fx_delivery),
        reporting_currency=into,
        bookings=holdings.bookings,
        orders=holdings.orders,
    )


def _route_payload(choice: Any, every: Any, cost_value: float | None, unit: str,
                   holdings: Holdings, fx_delivery: Delivery | None) -> dict[str, Any]:
    """The chosen route for the front month, the other complete routes with their extra cost
    against it in the display unit (cheapest first), and the routes that cannot be priced
    with their missing legs. ``every`` is the choice without the desk's pick."""

    def in_unit(route: Any) -> float | None:
        if route.total is None or not route.currency:
            return None
        try:
            return route.total * conversion(f"{route.currency}/MWh", unit, holdings=holdings.fx,
                                            as_of=holdings.today, delivery=fx_delivery).factor
        except NormalisationError:
            return None

    alternatives = []
    others = [route for route in (every.chosen, *every.alternatives)
              if route.complete and route.hubs != choice.chosen.hubs]
    for route in others:
        value = in_unit(route)
        alternatives.append({
            **route.as_dict(),
            "in_display_unit": value,
            "extra_cost": None if value is None or cost_value is None else value - cost_value,
        })
    payload = choice.as_dict()
    return {
        **payload["chosen"],
        "in_display_unit": cost_value,
        "alternatives": alternatives,
        "unavailable": every.as_dict()["unavailable"],
        "missing": payload["missing"],
        "picked": list(choice.chosen.hubs[1:-1]) if every is not choice else None,
    }


def route_lines(spec: StrategySpec, holdings: Holdings, unit: str) -> dict[str, Any] | None:
    """For a history: the route cost both ways for the front month, as horizontal lines (D.2).

    Outside the lines moving gas pays: above +cost(buy → sell) or below −cost(sell → buy).
    """

    if spec.cost is None:
        return None
    from eurogas_nexus.domain.market.fx_forward import delivery_from_period
    from eurogas_nexus.domain.market.products import resolve_product

    delivery = delivery_from_period(resolve_product("M+1", holdings.today))
    out: dict[str, Any] = {"delivery": delivery.as_dict(), "lines": []}
    for start, end, sign in ((spec.cost.from_hub, spec.cost.to_hub, 1),
                             (spec.cost.to_hub, spec.cost.from_hub, -1)):
        route = _route_choice(spec, start, end, delivery, holdings, unit,
                              None if spec.fx == "spot" else delivery).chosen
        value = None
        if route.total is not None and route.currency:
            try:
                conv = conversion(f"{route.currency}/MWh", unit, holdings=holdings.fx,
                                  as_of=holdings.today,
                                  delivery=None if spec.fx == "spot" else delivery)
                value = sign * route.total * conv.factor
            except NormalisationError:
                value = None
        out["lines"].append({**route.as_dict(), "value": value})
    return out


def load_holdings(who: Any, *, today: date | None = None) -> Holdings:
    """Prices, FX, tariffs and the catalogue the caller may use."""

    from eurogas_nexus.application.instrument_catalogue import build_catalogue
    from eurogas_nexus.application.market_normalisation import load_holdings as load_fx
    from eurogas_nexus.application.projections.daily_closes import daily_rows
    from eurogas_nexus.application.route_tariff_cost import load_route_capacity, load_tariff_rows

    today = today or datetime.now(UTC).date()
    rows = daily_rows(who)
    bookings, orders = load_route_capacity()
    return Holdings(rows, load_fx(who), load_tariff_rows(), today,
                    build_catalogue(rows, today=today), bookings, orders,
                    tariff_loader=lambda product: load_tariff_rows(product=product))
