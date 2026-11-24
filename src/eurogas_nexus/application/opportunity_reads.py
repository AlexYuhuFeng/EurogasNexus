"""Book and feed rows the valuation snapshot serves as named collections (design J.1, J.2).

Each function returns plain rows; :class:`~eurogas_nexus.application.valuation_snapshot.
LiveSnapshotReader` turns every row into one recorded snapshot input, so an evaluator reads
the book only through its snapshot and a replay serves the same rows.

- ``positions``: net MWh per book, hub and month (contracts and filled trades, the position
  ladder's legs), for the current month and the next six;
- ``contracts``: active supply contracts with their hub, daily quantity and price in the hub's
  currency;
- ``mandates``: trader mandates (books, hubs, monthly net limit);
- ``held_capacity``: capacity the firm holds on a route (route candidates with booked legs);
- ``residuals``: tomorrow's balance per book and hub: the gas day's own lines
  (``application/gas_day.hub_daily_balance``, the figure Today and the daily balance show),
  each book's band from its own approved set, else the firm-wide set;
- ``outage_feed``: whether an outage feed is held at all (so "no outage on the path" can be
  told apart from "not assessed").
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

#: Months of positions read: the current month and the next six (design J.2 candidate set).
POSITION_MONTHS = 7


def _month_start(day: date, offset: int) -> date:
    month = day.month - 1 + offset
    return date(day.year + month // 12, month % 12 + 1, 1)


class BookReads:
    """The book as one caller sees it on one day, read once and shared by the collections."""

    def __init__(self, caller, today: date, *, as_of_utc: datetime | None = None) -> None:
        self.caller = caller
        self.today = today
        #: The evaluation instant (the gas day and its cut-offs are read at it).
        self.as_of_utc = as_of_utc or datetime.combine(today, time(12), tzinfo=UTC)
        self._inputs = None

    @property
    def inputs(self):
        """The position ladder's legs and contracts (``application/position_inputs``)."""

        if self._inputs is None:
            from eurogas_nexus.application.position_inputs import ladder_inputs

            end = _month_start(self.today, POSITION_MONTHS) - timedelta(days=1)
            self._inputs = ladder_inputs(self.caller, self.today, self.today, end)
        return self._inputs

    def positions(self) -> list[dict[str, Any]]:
        """Net MWh per (book, hub, month)."""

        totals: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
            lambda: {"physical": 0.0, "financial": 0.0}
        )
        for leg in self.inputs.legs:
            for offset in range(POSITION_MONTHS):
                first = _month_start(self.today, offset)
                end = _month_start(self.today, offset + 1)
                start = max(first, leg.first_gas_day, self.today)
                stop = min(end - timedelta(days=1), leg.last_gas_day)
                days = (stop - start).days + 1
                if days <= 0:
                    continue
                key = (leg.book_id or "", leg.hub, f"{first:%Y-%m}")
                totals[key][leg.kind] += leg.mwh_per_day * days
        return [
            {
                "book_id": book or None,
                "hub": hub,
                "month": month,
                "physical_mwh": round(values["physical"], 1),
                "financial_mwh": round(values["financial"], 1),
                "net_mwh": round(values["physical"] + values["financial"], 1),
            }
            for (book, hub, month), values in sorted(totals.items())
            if abs(values["physical"] + values["financial"]) > 1e-6
        ]

    def contracts(self) -> list[dict[str, Any]]:
        """Active supply contracts in the caller's books."""

        from eurogas_nexus.domain.ontology.markets import quote_currency

        records = {item.contract_id: item for item in self.inputs.contracts}
        rows = []
        for leg in self.inputs.legs:
            if leg.kind != "physical" or leg.reference not in records:
                continue
            record = records[leg.reference]
            rows.append(
                {
                    "contract_id": leg.reference,
                    "contract_name": record.contract_name,
                    "book_id": leg.book_id or None,
                    "hub": leg.hub,
                    "delivery_point": record.delivery_point_name,
                    "mwh_per_day": leg.mwh_per_day,
                    "price": leg.price,
                    "price_currency": quote_currency(leg.hub),
                    "first_gas_day": leg.first_gas_day.isoformat(),
                    "last_gas_day": leg.last_gas_day.isoformat(),
                    "allowed_exit_points": list(record.allowed_exit_points or []),
                    # Contract kinds: what kind of agreement, and its swing where it has one.
                    "contract_kind": record.contract_kind or "SUPPLY_GSA",
                    **_kind_inputs(record),
                }
            )
        return rows

    def residuals(self, session) -> list[dict[str, Any]]:
        """Tomorrow's residual per (book, hub): the gas day's own lines, book by book.

        The figure is the daily balance's (``application/gas_day.hub_daily_balance``): the
        physical lines net (contracts nominated where held, else their quantity, capped by an
        outage; LNG send-out; storage and imports less offtake, injection and exports) plus
        purchases less sales, every line in the books the caller may see. A residual within
        the book's band (its own approved set, else the firm-wide set, else 2 %) is balanced
        and not listed. The contracts' measured delivery is shown, not applied (QA-T-07).
        """

        from eurogas_nexus.application.gas_day import gas_day_view, hub_daily_balance
        from eurogas_nexus.db.models import ContractDeliveryRecord
        from eurogas_nexus.domain.market.gas_day import gas_day_label

        tomorrow = date.fromisoformat(gas_day_label(self.as_of_utc)) + timedelta(days=1)
        view = gas_day_view(
            session, self.caller, now=self.as_of_utc, inputs=self.inputs, days=[tomorrow],
            all_books=True,
        )
        rows = []
        for hub, balance in sorted(view.balances[tomorrow].items()):
            for book in sorted({line.book_id or "" for line in balance.lines}):
                (row,) = hub_daily_balance(session, view, hub, book_id=book)
                if row["state"] == "balanced":
                    continue
                contract_ids = list(dict.fromkeys(
                    line["ref"].split(":", 1)[1]
                    for line in row["lines"] if line["ref"].startswith("contract:")
                ))
                ratio = 1.0
                if contract_ids:
                    records = (
                        session.query(ContractDeliveryRecord)
                        .filter(ContractDeliveryRecord.contract_id.in_(contract_ids))
                        .filter(ContractDeliveryRecord.gas_day >= tomorrow - timedelta(days=31))
                        .filter(ContractDeliveryRecord.gas_day < tomorrow - timedelta(days=1))
                        .all()
                    )
                    nominated = sum(
                        r.nominated_mwh or 0.0 for r in records if r.allocated_mwh is not None
                    )
                    allocated = sum(
                        r.allocated_mwh or 0.0 for r in records if r.nominated_mwh is not None
                    )
                    if nominated > 0:
                        ratio = allocated / nominated
                rows.append(
                    {
                        "book_id": book or None,
                        "hub": hub,
                        "gas_day": tomorrow.isoformat(),
                        "residual_mwh": row["residual_mwh"],
                        "state": row["state"],
                        "supply_mwh": row["supply"],
                        "physical_in_mwh": row["physical_in_mwh"],
                        "physical_out_mwh": row["physical_out_mwh"],
                        "band_mwh": row["band"]["mwh"],
                        "definition": "gas_day",
                        "delivery_ratio": round(ratio, 4),
                        "delivery_ratio_applied": False,
                        "contracts": contract_ids,
                        "lines": len(row["lines"]),
                        "lines_simulated": row["simulated"],
                    }
                )
        return rows


def mandates(session) -> list[dict[str, Any]]:
    """Trader mandates (risk's approved limits)."""

    from eurogas_nexus.db.models import TraderMandateRecord

    return [
        {
            "mandate_id": row.mandate_id,
            "trader": row.trader,
            "book_ids": list(row.book_ids or []),
            "hubs": [hub.upper() for hub in row.hubs or []],
            "max_net_mwh_per_month": row.max_net_mwh_per_month,
            "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        }
        for row in session.query(TraderMandateRecord).order_by(TraderMandateRecord.mandate_id)
    ]


def held_capacity(session, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Capacity the firm holds on a route between two market areas.

    A route candidate whose legs state booked capacity is held capacity; it belongs to the
    book of the contract delivering at its start whose allowed exits include its target.
    """

    from eurogas_nexus.db.models import RouteCandidateRecord
    from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

    graph = shipped_market_area_graph()
    rows = []
    for route in (
        session.query(RouteCandidateRecord)
        .filter(RouteCandidateRecord.active.is_(True))
        .order_by(RouteCandidateRecord.route_id)
    ):
        start = graph.hub_for(route.start_point_name)
        target = graph.hub_for(route.target_point_name)
        if start is None or target is None or start == target:
            continue
        capacities = [
            float(leg["available_capacity_mwh_per_day"])
            for leg in route.route_legs or []
            if isinstance(leg.get("available_capacity_mwh_per_day"), int | float)
        ]
        if not capacities:
            continue
        from_hub, to_hub = graph.hub_names[start], graph.hub_names[target]
        owner = next(
            (
                item
                for item in contracts
                if item["hub"] == from_hub
                and to_hub in [str(point).upper() for point in item["allowed_exit_points"]]
            ),
            None,
        )
        rows.append(
            {
                "route_id": route.route_id,
                "route_name": route.route_name,
                "from_hub": from_hub,
                "to_hub": to_hub,
                "via_points": [
                    str(leg["point_key"]) for leg in route.route_legs or [] if leg.get("point_key")
                ],
                "capacity_mwh_per_day": min(capacities),
                "book_id": None if owner is None else owner["book_id"],
                "contract_id": None if owner is None else owner["contract_id"],
            }
        )
    return rows


def outage_feed(session, *, demo_desk: bool) -> dict[str, Any]:
    """How many outage messages are held, from which sources."""

    from sqlalchemy import func

    from eurogas_nexus.db.models import RemitUmmRecord

    counts = dict(
        session.query(RemitUmmRecord.source_system, func.count())
        .group_by(RemitUmmRecord.source_system)
        .all()
    )
    if not demo_desk:
        counts.pop("DEMO", None)
    return {"messages": int(sum(counts.values())), "sources": sorted(counts)}


def as_datetime(value: str | None) -> datetime | None:
    """An ISO instant or ``None``."""

    return None if not value else datetime.fromisoformat(value)


def storage(session) -> list[dict[str, Any]]:
    """Storage the firm holds (the storage facility masters it nominates against)."""

    from eurogas_nexus.db.models import StorageFacilityMasterRecord

    return [
        {
            "facility_id": row.facility_id,
            "name": row.name,
            "hub": str(row.market_hub).upper(),
            "working_gas_mwh": row.maximum_inventory_mwh - row.minimum_inventory_mwh,
            "max_injection_mwh_per_day": row.maximum_injection_mwh,
            "max_withdrawal_mwh_per_day": row.maximum_withdrawal_mwh,
            "injection_efficiency": row.injection_efficiency,
            "withdrawal_efficiency": row.withdrawal_efficiency,
            # The record's fee columns are named in GBP; their currency is stated, not assumed.
            "injection_fee": row.injection_cost_gbp_mwh,
            "withdrawal_fee": row.withdrawal_cost_gbp_mwh,
            "fee_currency": "GBP",
            "source_system": row.source_system,
        }
        for row in session.query(StorageFacilityMasterRecord)
        .filter(StorageFacilityMasterRecord.active.is_(True))
        .order_by(StorageFacilityMasterRecord.facility_id)
    ]


def resource_pool(session, principal, gas_day: date) -> list[dict[str, Any]]:
    """The composed resource pool (resources and sale options) for one gas day.

    The same composition ``/api/route-cost/resource-pool/options`` serves, narrowed by the
    caller's entitlement. Rows: one per resource (``row_kind`` = resource), one per sale
    option (``row_kind`` = option) and one header with the composition's blockers.
    """

    from eurogas_nexus.application.resource_pool import (
        compose_resource_pool_options,
        narrow_resource_pool_inputs,
        read_resource_pool_inputs,
    )

    inputs, _entitlement = narrow_resource_pool_inputs(
        principal, read_resource_pool_inputs(session)
    )
    composed = compose_resource_pool_options(**inputs, gas_day=gas_day)
    rows: list[dict[str, Any]] = [
        {
            "row_kind": "header",
            "id": "pool",
            "blockers": list(composed.get("blockers") or []),
            "warnings": list(composed.get("warnings") or [])[:20],
        }
    ]
    for item in composed.get("portfolio_resources") or []:
        rows.append({"row_kind": "resource", "id": str(item["resource_id"]), **item})
    for item in composed.get("sale_options") or []:
        rows.append({"row_kind": "option", "id": str(item["option_id"]), **item})
    return rows


def _kind_inputs(record) -> dict[str, Any]:
    """The flexibility and price basis a typed contract gives the evaluators."""

    from eurogas_nexus.domain.contracts import kinds

    terms = kinds.terms_of(record.contract_kind, record.kind_terms)
    out: dict[str, Any] = {"price_basis": kinds.price_basis(record.contract_kind, terms)["basis"]}
    if isinstance(terms, kinds.UpstreamTenderTerms):
        out["swing_min_mwh_per_day"] = terms.min_mwh()
        out["swing_max_mwh_per_day"] = terms.max_mwh()
        out["delivery_point"] = terms.delivery_point
    return out
