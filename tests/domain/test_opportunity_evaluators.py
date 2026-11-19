"""Evaluators I (CP-09): golden cases for L, C, S and E, with their arithmetic.

Every case runs through the harness (contract check and false-positive controls, as the
service does), so the state asserted is the state the desk sees.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from eurogas_nexus.application.route_tariff_cost import cheapest_route
from eurogas_nexus.domain.opportunities.event_exposure import EventExposureEvaluator, source_name
from eurogas_nexus.domain.opportunities.locational import (
    HeldCapacityEvaluator,
    LocationalEvaluator,
)
from eurogas_nexus.domain.opportunities.model import LegKind, OpportunityState
from eurogas_nexus.domain.opportunities.sell_down import SellDownEvaluator
from eurogas_nexus.domain.opportunities.testing import (
    assert_legs,
    assert_reconciles,
    fixture_snapshot,
    run,
)
from eurogas_nexus.domain.route_cost.market_area_graph import MarketAreaGraph
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod, month_of
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.domain.valuation.snapshot import (
    InputKind,
    SnapshotInput,
    assumption_key,
    capacity_key,
    collection_key,
    outages_key,
    price_key,
    tariff_key,
)

AS_OF = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)
JAN27 = DeliveryPeriod.month(2027, 1)
TOMORROW = DeliveryPeriod.gas_day(AS_OF.date() + timedelta(days=1))
D = Decimal
SRC = InputClass.SOURCED


def _graph() -> MarketAreaGraph:
    """TTF and THE joined at Oude Statenzijl (one direct crossing)."""

    return MarketAreaGraph(
        hub_codes={"TTF": "VTP-NL", "THE": "VTP-DE"},
        hub_names={"VTP-NL": "TTF", "VTP-DE": "THE"},
        points={"ITP-00005": {"name": "Oude Statenzijl", "country": "NL"}},
        point_hubs={"ITP-00005": {"VTP-NL": ("NL-TSO",), "VTP-DE": ("DE-TSO",)}},
        operator_names={"NL-TSO": "GTS", "DE-TSO": "THE TSO"},
    )


def _in(key, kind, value, unit="", currency=None, klass=SRC, family="ICE_ENDEX", **detail):
    return SnapshotInput(
        key=key,
        kind=kind,
        input_class=klass,
        value=None if value is None else D(str(value)),
        unit=unit,
        currency=currency,
        as_of_utc=AS_OF,
        source_family=family,
        source_ref=f"ref:{key}",
        label=key,
        detail=detail,
    )


def _l_inputs(**overrides) -> list[SnapshotInput]:
    rows = {
        "pos": _in(
            "positions:book-1:TTF:2027-01",
            InputKind.BOOK,
            310000,
            "MWh",
            family="operator-input",
            book_id="book-1",
            hub="TTF",
            month="2027-01",
        ),
        "sell": _in(
            price_key("THE", JAN27, "bid"),
            InputKind.PRICE,
            "31.20",
            "EUR/MWh",
            "EUR",
            basis="quote",
        ),
        "buy": _in(
            price_key("TTF", JAN27, "ask"),
            InputKind.PRICE,
            "30.00",
            "EUR/MWh",
            "EUR",
            basis="quote",
        ),
        "exit": _in(
            tariff_key("ITP-00005", "EXIT", "MONTHLY", JAN27),
            InputKind.TARIFF,
            "0.0101",
            "EUR/(kWh/h)/d",
            "EUR",
            family="ENTSOG",
            tariff_status="FINAL",
        ),
        "entry": _in(
            tariff_key("ITP-00005", "ENTRY", "MONTHLY", JAN27),
            InputKind.TARIFF,
            "0.0132",
            "EUR/(kWh/h)/d",
            "EUR",
            family="ENTSOG",
            tariff_status="FINAL",
        ),
        "cap": _in(
            capacity_key("ITP-00005", "EXIT", JAN27),
            InputKind.CAPACITY,
            "3.5",
            "mcm/d",
            family="ENTSOG",
        ),
        "feed": _in("outage_feed:messages", InputKind.OUTAGE, 12, "messages", family="REMIT"),
        "mandate": _in(
            "mandates:M1",
            InputKind.BOOK,
            1000000,
            "MWh",
            family="operator-input",
            mandate_id="M1",
            book_ids=["book-1"],
            hubs=["TTF", "THE"],
            max_net_mwh_per_month=1000000,
        ),
    }
    rows.update(overrides)
    return [item for item in rows.values() if item is not None]


def _run_l(inputs, evaluator=None, demo=False):
    snapshot = fixture_snapshot(
        inputs,
        as_of=AS_OF,
        demo_desk=demo,
        collections={
            outages_key("TTF", JAN27): [],
            outages_key("THE", JAN27): [],
        },
    )
    return run(
        evaluator or LocationalEvaluator(_graph), snapshot, as_of=AS_OF, route_pricer=cheapest_route
    )


def test_golden_ttf_to_the_jan27() -> None:
    """Design B.4: TTF -> THE, Jan-27, 10,000 MWh/d (a long TTF position of 310,000 MWh).

    Sell THE bid 31.20, buy TTF offer 30.00: gross 1.20 EUR/MWh.
    Exit NL at Oude Statenzijl 0.0101 EUR/(kWh/h)/d / 24 x 1000 = 0.420833 (6 dp).
    Entry THE 0.0132 / 24 x 1000 = 0.550000. Net 1.20 - 0.420833 - 0.55 = 0.229167 EUR/MWh.
    Volume 10,000 MWh/d x 31 d = 310,000 MWh; value 0.229167 x 310,000 = EUR 71,041.77.
    Breakeven spread 0.970833. Load factor: breakeven 0.970833 / 1.20 = 80.9 %; at 80 % the
    transport is 0.970833 / 0.8 = 1.213541 and the net -0.013541 EUR/MWh.
    Checks: capacity 3.5 mcm/d (~38,500 MWh/d) pass; no outage on the path; mandate: the
    book's own long gas leaves TTF (310,000 - 310,000 = 0) and THE is unchanged (0): 0 % of
    the 1,000,000 MWh monthly limit, pass. All sourced: actionable.
    """

    ((candidate, assessment),) = _run_l(_l_inputs())
    assert_legs(
        candidate,
        [
            ("locational.sell", "31.20"),
            ("locational.buy", "-30.00"),
            ("locational.market_area_exit", "-0.420833"),
            ("locational.market_area_entry", "-0.550000"),
        ],
    )
    assert_reconciles(candidate)
    assert candidate.headline.value == D("0.229167")
    assert candidate.volume.value == D("310000.0")
    assert candidate.value.value == D("71041.77")
    assert assessment.state is OpportunityState.ACTIONABLE, assessment.reasons
    assert candidate.quality is InputClass.SOURCED
    texts = [f.text for f in candidate.falsifiers]
    assert "THE-TTF Jan-27 spread below 0.971 EUR/MWh." in texts
    assert any(
        text.startswith(
            "Load factor below 80.9 % (at 80 % the transport is 1.214 EUR/MWh and "
            "the net -0.014 EUR/MWh)"
        )
        for text in texts
    )
    assert [c.result.value for c in candidate.checks] == ["pass", "pass", "pass"]
    assert candidate.checks[2].figure == "0 % of the monthly mandate limit used after"
    assert assessment.claim_text == (
        "TTF → THE · Jan-27 · 10,000 MWh/d: +0.229 EUR/MWh after transport via Oude "
        "Statenzijl; EUR 71,042."
    )
    # The priced route travels with the record for the map: ordered point ids.
    assert candidate.claim_fields["route_points"] == "ITP-00005"


def test_l_is_priced_only_through_the_route_pricer() -> None:
    """One route pricer (application/route_tariff_cost.cheapest_route), injected: without it the
    evaluator prices nothing rather than carrying a second route implementation."""

    snapshot = fixture_snapshot(_l_inputs(), as_of=AS_OF)
    assert run(LocationalEvaluator(_graph), snapshot, as_of=AS_OF) == []
    calls = []

    def spy(*args, **kwargs):
        calls.append(args[:2])
        return cheapest_route(*args, **kwargs)

    assert run(LocationalEvaluator(_graph), snapshot, as_of=AS_OF, route_pricer=spy)
    assert ("TTF", "THE") in calls


def test_l_controls_on_the_golden_route() -> None:
    # The firm's 80 % load factor makes the route unprofitable: not an opportunity at all.
    load = _in(
        assumption_key("capacity.load_factor"),
        InputKind.ASSUMPTION,
        80,
        "%",
        klass=InputClass.ASSUMPTION,
        family="operator-input",
    )
    assert _run_l(_l_inputs(load=load)) == []
    # A missing entry tariff is a named record, not an opportunity.
    ((_c, blocked),) = _run_l(_l_inputs(entry=None))
    assert blocked.state is OpportunityState.BLOCKED
    assert blocked.claim_text == (
        "Cannot evaluate: tariff not held at ITP-00005 (entry, gas year 2026/27)."
    )
    # A firm's mark on one side caps it at indicative (decision L2).
    marked = _in(
        price_key("THE", JAN27, "bid"),
        InputKind.PRICE,
        "31.20",
        "EUR/MWh",
        "EUR",
        klass=InputClass.FIRM_MARK,
        family="operator-input",
        basis="firm_mark",
    )
    assert _run_l(_l_inputs(sell=marked))[0][1].state is OpportunityState.INDICATIVE
    # A THE outside the mandate's hubs fails the mandate check.
    narrow = _in(
        "mandates:M1",
        InputKind.BOOK,
        1000000,
        "MWh",
        family="operator-input",
        mandate_id="M1",
        book_ids=["book-1"],
        hubs=["TTF"],
        max_net_mwh_per_month=1000000,
    )
    assert _run_l(_l_inputs(mandate=narrow))[0][1].blocker.code == "check_failed"
    # No outage feed held: "not assessed" -> watch, never a pass.
    ((_c, watch),) = _run_l(_l_inputs(feed=None))
    assert watch.state is OpportunityState.WATCH and "check_not_assessed" in watch.reasons
    # An annual tariff for a month without the firm's multiplier is indicative.
    annual = {
        "exit": None,
        "entry": None,
        "exit_a": _in(
            tariff_key("ITP-00005", "EXIT", "ANNUAL", JAN27),
            InputKind.TARIFF,
            "0.0101",
            "EUR/(kWh/h)/d",
            "EUR",
            family="ENTSOG",
        ),
        "entry_a": _in(
            tariff_key("ITP-00005", "ENTRY", "ANNUAL", JAN27),
            InputKind.TARIFF,
            "0.0132",
            "EUR/(kWh/h)/d",
            "EUR",
            family="ENTSOG",
        ),
    }
    ((_c, indicative),) = _run_l(_l_inputs(**annual))
    assert indicative.state is OpportunityState.INDICATIVE


def test_golden_held_capacity_ttf_to_the() -> None:
    """Type C on the same route, capacity held 10,000 MWh/d: charges sunk.

    Net = 31.20 - 30.00 = 1.20 EUR/MWh (no variable charge held); 310,000 MWh; EUR 372,000.00.
    """

    held = _in(
        "held_capacity:r1",
        InputKind.BOOK,
        10000,
        "MWh/d",
        family="operator-input",
        route_id="r1",
        route_name="TTF-THE booked",
        from_hub="TTF",
        to_hub="THE",
        via_points=["ITP-00005"],
        capacity_mwh_per_day=10000,
        book_id="book-1",
    )
    inputs = [*_l_inputs(pos=None), held]
    ((candidate, assessment),) = [
        pair for pair in _run_l(inputs, HeldCapacityEvaluator(_graph)) if pair[0].period == JAN27
    ]
    assert_legs(candidate, [("locational.sell", "31.20"), ("locational.buy", "-30.00")])
    assert any(leg.label_key == "capacity.sunk" for leg in candidate.legs)
    assert candidate.value.value == D("372000.00")
    assert assessment.state is OpportunityState.ACTIONABLE, assessment.reasons


def _s_inputs(discount=True):
    rows = [
        _in(
            "residuals:book-1:NBP",
            InputKind.BOOK,
            3200,
            "MWh",
            family="operator-input",
            book_id="book-1",
            hub="NBP",
            delivery_ratio="0.97",
            supply_mwh="24000",
        ),
        _in(
            price_key("NBP", TOMORROW, "bid"),
            InputKind.PRICE,
            "27.81",
            "GBP/MWh",
            "GBP",
            basis="quote",
        ),
    ]
    if discount:
        rows.append(
            _in(
                assumption_key("balancing.long_discount"),
                InputKind.ASSUMPTION,
                "1.50",
                "GBP/MWh",
                "GBP",
                klass=InputClass.ASSUMPTION,
                family="operator-input",
                set_by="risk",
                set_at_utc="2026-11-01T00:00:00+00:00",
            )
        )
    return rows


def test_golden_sell_down_long_residual() -> None:
    """Long 3,200 MWh at NBP tomorrow; day-ahead bid 27.81 GBP/MWh; long discount 1.50.

    +27.81 (day-ahead) - 27.81 (cash-out at day-ahead) + 1.50 (discount) = 1.50 GBP/MWh;
    x 3,200 MWh = GBP 4,800.00. Must act, due at the start of the gas day; the discount is the
    firm's assumption, so it is indicative.
    """

    ((candidate, assessment),) = run(
        SellDownEvaluator(), fixture_snapshot(_s_inputs(), as_of=AS_OF), as_of=AS_OF
    )
    assert_reconciles(candidate)
    assert candidate.headline.value == D("1.50") and candidate.value.value == D("4800.00")
    assert candidate.value.unit == "GBP"
    assert candidate.deadline_utc == datetime(2026, 11, 18, 5, tzinfo=UTC)
    assert assessment.state is OpportunityState.INDICATIVE
    ((_c, blocked),) = run(
        SellDownEvaluator(), fixture_snapshot(_s_inputs(False), as_of=AS_OF), as_of=AS_OF
    )
    assert blocked.state is OpportunityState.BLOCKED and blocked.blocker.code == "input_missing"


def test_golden_event_exposure() -> None:
    """Haldor supply 24,000 MWh/d at NBP, contract 29.50 GBP/MWh; outage at "Haldor field":
    52 of 70 mcm/d out, ending 3 d from now.

    Share 52 / 70 = 0.742857 (6 dp); affected 24,000 x 0.742857 = 17,828.568 MWh/d;
    x 3 d = 53,485.7 MWh. Cover at the day-ahead offer 33.80: 33.80 - 29.50 = 4.30 GBP/MWh;
    4.30 x 53,485.7 = GBP 229,988.51.
    """

    outage = _in(
        "outage:m1",
        InputKind.OUTAGE,
        "563.2",
        "GWh/d",
        family="REMIT",
        message_id="m1",
        asset_name="Haldor field, Norwegian shelf",
        technical_capacity=70.0,
        unavailable_capacity=52.0,
        capacity_unit="mcm/d",
        event_start_utc=(AS_OF - timedelta(hours=3)).isoformat(),
        event_stop_utc=(AS_OF + timedelta(days=3)).isoformat(),
    )
    contract = _in(
        "contracts:haldor",
        InputKind.BOOK,
        24000,
        "MWh/d",
        family="operator-input",
        contract_id="haldor",
        contract_name="Haldor supply (Easington)",
        hub="NBP",
        price="29.50",
        price_currency="GBP",
        book_id="book-1",
    )
    cover = _in(
        price_key("NBP", TOMORROW, "ask"), InputKind.PRICE, "33.80", "GBP/MWh", "GBP", basis="quote"
    )
    snapshot = fixture_snapshot(
        [outage, contract, cover],
        as_of=AS_OF,
        collections={
            outages_key("NBP", month_of(AS_OF.date())): ["outage:m1"],
            collection_key("contracts"): ["contracts:haldor"],
        },
    )
    ((candidate, assessment),) = run(EventExposureEvaluator(), snapshot, as_of=AS_OF)
    assert_reconciles(candidate)
    assert candidate.volume.value == D("53485.7")
    assert candidate.headline.value == D("4.30") and candidate.value.value == D("229988.51")
    assert [leg.kind for leg in candidate.legs][:2] == [LegKind.CONVERSION, LegKind.CONVERSION]
    assert assessment.state is OpportunityState.ACTIONABLE
    assert assessment.claim_text.startswith(
        "Outage at Haldor field, Norwegian shelf: Haldor supply (Easington) supply "
        "-17,829 MWh/d for 3 d (53,486 MWh)"
    )
    assert source_name("Kestrel UK leg (TTF, sold at NBP)") == "Kestrel"
    assert source_name("Demo supply") is None
