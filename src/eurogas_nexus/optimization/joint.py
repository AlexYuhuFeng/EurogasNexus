"""Time-expanded physical resource/network/storage decisions in native MWh/GBP.

Storage carries conserved energy between periods. Multiplicative losses are
outside this circulation model and explicitly rejected, not approximated away.
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eurogas_nexus.domain.economics.financing import simple_interest
from eurogas_nexus.optimization.circulation import Arc, solve_circulation


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


class Supply(StrictModel):
    supply_id: str = Field(min_length=1, max_length=80)
    node: str = Field(min_length=1, max_length=80)
    day: date
    maximum_mwh: float = Field(ge=0, le=1e9)
    minimum_mwh: float = Field(default=0, ge=0)
    cost_gbp_mwh: float
    annual_financing_rate_pct: float = Field(ge=0, le=100)
    funding_days: int = Field(ge=0, le=3660)
    day_count: Literal["ACT/365F", "ACT/360"]


class Sale(StrictModel):
    sale_id: str = Field(min_length=1, max_length=80)
    node: str = Field(min_length=1, max_length=80)
    day: date
    maximum_mwh: float = Field(ge=0, le=1e9)
    minimum_mwh: float = Field(default=0, ge=0)
    value_gbp_mwh: float


class Transport(StrictModel):
    edge_id: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)
    capacity_by_day: dict[date, float]
    tariff_gbp_mwh: float = Field(ge=0)
    access_confirmed: bool


class Store(StrictModel):
    storage_id: str = Field(min_length=1, max_length=80)
    node: str = Field(min_length=1, max_length=80)
    initial_mwh: float = Field(ge=0, le=1e9)
    minimum_mwh: float = Field(ge=0)
    maximum_mwh: float = Field(ge=0, le=1e9)
    injection_limit_mwh: float = Field(ge=0)
    withdrawal_limit_mwh: float = Field(ge=0)
    injection_cost_gbp_mwh: float = Field(ge=0)
    withdrawal_cost_gbp_mwh: float = Field(ge=0)
    terminal_minimum_mwh: float = Field(ge=0)
    terminal_maximum_mwh: float = Field(ge=0)
    terminal_value_gbp_mwh: float
    initial_value_gbp_mwh: float
    injection_efficiency: Literal[1.0] = 1.0
    withdrawal_efficiency: Literal[1.0] = 1.0


class JointRequest(StrictModel):
    analyze_bottlenecks: bool = False
    days: tuple[date, ...] = Field(min_length=1, max_length=31)
    supplies: tuple[Supply, ...] = Field(max_length=128)
    sales: tuple[Sale, ...] = Field(max_length=128)
    transports: tuple[Transport, ...] = Field(default=(), max_length=32)
    stores: tuple[Store, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def valid_constraints(self):
        if any(b - a != timedelta(days=1) for a, b in zip(self.days, self.days[1:], strict=False)):
            raise ValueError("joint horizon must contain consecutive ordered days")
        for items, field in (
            (self.supplies, "supply_id"),
            (self.sales, "sale_id"),
            (self.transports, "edge_id"),
            (self.stores, "storage_id"),
        ):
            if len({getattr(x, field) for x in items}) != len(items):
                raise ValueError(f"duplicate {field}")
        for row in (*self.supplies, *self.sales):
            if row.day not in self.days or row.minimum_mwh > row.maximum_mwh:
                raise ValueError("quantity bound or delivery day invalid")
        for edge in self.transports:
            if set(edge.capacity_by_day) != set(self.days):
                raise ValueError("transport capacity must be explicit for every day")
            if any(not 0 <= v <= 1e9 for v in edge.capacity_by_day.values()):
                raise ValueError("invalid transport capacity")
        for store in self.stores:
            if not store.minimum_mwh <= store.initial_mwh <= store.maximum_mwh:
                raise ValueError("initial inventory outside bounds")
            if (
                not store.minimum_mwh
                <= store.terminal_minimum_mwh
                <= store.terminal_maximum_mwh
                <= store.maximum_mwh
            ):
                raise ValueError("terminal inventory outside bounds")
        return self


def optimize_joint(payload: JointRequest, checkpoint: Callable[[], None] = lambda: None) -> dict:
    arcs = []
    funding_costs = {}
    hub = lambda day, node: f"hub:{day}:{node}"  # noqa: E731
    for supply in payload.supplies:
        financing = simple_interest(
            max(supply.cost_gbp_mwh, 0),
            supply.annual_financing_rate_pct,
            supply.funding_days,
            supply.day_count,
        )
        funding_costs[supply.supply_id] = financing
        arcs.append(
            Arc(
                f"supply:{supply.supply_id}",
                "source",
                hub(supply.day, supply.node),
                supply.minimum_mwh,
                supply.maximum_mwh,
                supply.cost_gbp_mwh + financing,
            )
        )
    for sale in payload.sales:
        arcs.append(
            Arc(
                f"sale:{sale.sale_id}",
                hub(sale.day, sale.node),
                "sink",
                sale.minimum_mwh,
                sale.maximum_mwh,
                -sale.value_gbp_mwh,
            )
        )
    for edge in payload.transports:
        for day in payload.days:
            arcs.append(
                Arc(
                    f"edge:{edge.edge_id}:{day}",
                    hub(day, edge.source),
                    hub(day, edge.target),
                    0,
                    edge.capacity_by_day[day] if edge.access_confirmed else 0,
                    edge.tariff_gbp_mwh,
                )
            )
    for store in payload.stores:
        state = lambda i, storage_id=store.storage_id: f"store:{storage_id}:{i}"  # noqa: E731
        arcs.append(
            Arc(
                f"initial:{store.storage_id}",
                "source",
                state(0),
                store.initial_mwh,
                store.initial_mwh,
                0,
            )
        )
        for i, day in enumerate(payload.days):
            before = f"before:{store.storage_id}:{i}"
            arcs.append(
                Arc(
                    f"available:{store.storage_id}:{day}", state(i), before, 0, store.maximum_mwh, 0
                )
            )
            arcs.append(
                Arc(
                    f"inject:{store.storage_id}:{day}",
                    hub(day, store.node),
                    before,
                    0,
                    store.injection_limit_mwh,
                    store.injection_cost_gbp_mwh,
                )
            )
            arcs.append(
                Arc(
                    f"withdraw:{store.storage_id}:{day}",
                    before,
                    hub(day, store.node),
                    0,
                    store.withdrawal_limit_mwh,
                    store.withdrawal_cost_gbp_mwh,
                )
            )
            arcs.append(
                Arc(
                    f"inventory:{store.storage_id}:{day}",
                    before,
                    state(i + 1),
                    store.minimum_mwh,
                    store.maximum_mwh,
                    0,
                )
            )
        arcs.append(
            Arc(
                f"terminal:{store.storage_id}",
                state(len(payload.days)),
                "sink",
                store.terminal_minimum_mwh,
                store.terminal_maximum_mwh,
                -store.terminal_value_gbp_mwh,
            )
        )
    total = sum(s.maximum_mwh for s in payload.supplies) + sum(
        s.initial_mwh for s in payload.stores
    )
    arcs.append(Arc("return", "sink", "source", 0, total, 0))
    result = solve_circulation(arcs, checkpoint)
    if result["status"] == "optimal":
        result["net_value_gbp"] = -result["cost"] - sum(
            s.initial_mwh * s.initial_value_gbp_mwh for s in payload.stores
        )
        flow = result["flows"]
        trace = [
            {
                "supply_id": s.supply_id,
                "quantity_mwh": flow[f"supply:{s.supply_id}"],
                "procurement_gbp": flow[f"supply:{s.supply_id}"] * s.cost_gbp_mwh,
                "financing_gbp": flow[f"supply:{s.supply_id}"] * funding_costs[s.supply_id],
                "annual_rate_pct": s.annual_financing_rate_pct,
                "funding_days": s.funding_days,
                "day_count": s.day_count,
            }
            for s in payload.supplies
        ]
        result["contract_economics"] = trace
        result["economic_attribution"] = {
            "sales_revenue_gbp": sum(
                flow[f"sale:{s.sale_id}"] * s.value_gbp_mwh for s in payload.sales
            ),
            "procurement_cost_gbp": sum(r["procurement_gbp"] for r in trace),
            "financing_cost_gbp": sum(r["financing_gbp"] for r in trace),
            "transport_cost_gbp": sum(
                flow[f"edge:{e.edge_id}:{day}"] * e.tariff_gbp_mwh
                for e in payload.transports
                for day in payload.days
            ),
            "injection_cost_gbp": sum(
                flow[f"inject:{s.storage_id}:{day}"] * s.injection_cost_gbp_mwh
                for s in payload.stores
                for day in payload.days
            ),
            "withdrawal_cost_gbp": sum(
                flow[f"withdraw:{s.storage_id}:{day}"] * s.withdrawal_cost_gbp_mwh
                for s in payload.stores
                for day in payload.days
            ),
            "terminal_value_gbp": sum(
                flow[f"terminal:{s.storage_id}"] * s.terminal_value_gbp_mwh for s in payload.stores
            ),
            "opening_inventory_value_gbp": sum(
                s.initial_mwh * s.initial_value_gbp_mwh for s in payload.stores
            ),
        }
        result["binding_capacity"] = [
            a.arc_id
            for a in arcs
            if a.arc_id.startswith("edge:")
            and a.upper > 0
            and abs(result["flows"][a.arc_id] - a.upper) < 1e-7
        ]
    result["model"] = "multi-day-energy-conserving-network/1"
    result["assumptions"] = [
        "GBP/MWh prices; MWh quantities; unit storage efficiencies",
        "terminal value and contract-specific financing explicitly supplied",
    ]
    if payload.analyze_bottlenecks and result["status"] == "optimal":
        sensitivity = []
        for reference in result["binding_capacity"][:8]:
            checkpoint()
            selected = next(a for a in arcs if a.arc_id == reference)
            changed = [
                Arc(
                    a.arc_id,
                    a.source,
                    a.target,
                    a.lower,
                    a.upper + 1 if a.arc_id == reference else a.upper,
                    a.cost,
                )
                for a in arcs
            ]
            alternative = solve_circulation(changed, checkpoint)
            sensitivity.append(
                {
                    "edge_period": selected.arc_id,
                    "extra_capacity_mwh": 1.0,
                    "incremental_value_gbp": result["cost"] - alternative["cost"],
                }
            )
        result["capacity_sensitivity"] = sensitivity
        result["capacity_sensitivity_complete"] = len(result["binding_capacity"]) <= 8
    return result
