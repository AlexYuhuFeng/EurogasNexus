"""Opportunity core (CP-08): golden cases, false-positive controls, lifecycle, ranking.

The golden cases carry their arithmetic in the docstring; each is reproducible by hand. The
synthetic spread evaluator below exists only to exercise the controls on a margin type the
way the type-L evaluator (a later package) will; its figures are design B.4's TTF -> THE
example.
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from eurogas_nexus.domain.opportunities.claims import (
    CLAIM_TEMPLATES,
    ClaimError,
    grouped,
    render_claim,
    template_fields,
    wording_violations,
)
from eurogas_nexus.domain.opportunities.controls import (
    ThresholdError,
    Thresholds,
    thresholds_from,
)
from eurogas_nexus.domain.opportunities.evaluator import (
    ContractBreach,
    EvaluationContext,
    registered,
    validate_candidate,
)
from eurogas_nexus.domain.opportunities.hedge_gap import HEDGE_GAP
from eurogas_nexus.domain.opportunities.lifecycle import (
    TransitionError,
    check_transition,
    expire_if_due,
    missed,
    seen,
)
from eurogas_nexus.domain.opportunities.model import (
    Candidate,
    Check,
    CheckKind,
    CheckResult,
    Falsifier,
    Lane,
    Leg,
    LegKind,
    Measure,
    OpportunityState,
    OpportunityType,
    ReconciliationError,
    reconcile,
)
from eurogas_nexus.domain.opportunities.ranking import RankInput, rank
from eurogas_nexus.domain.opportunities.testing import (
    assert_legs,
    assert_reconciles,
    book_row,
    fixture_snapshot,
    run,
)
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.domain.valuation.snapshot import (
    InputKind,
    SnapshotInput,
    price_key,
    tariff_key,
)

AS_OF = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)  # a Tuesday
JAN27 = DeliveryPeriod.month(2027, 1)
D = Decimal
ZERO = Decimal(0)


# ------------------------------------------------------------------ golden cases: type G


def test_golden_hedge_gap_below_band() -> None:
    """Design B.4, type G: "Norsk-2027", Jan-27.

    contract volume 300,000 MWh; linked cover 126,000 MWh -> 126,000 / 300,000 = 42 %;
    approved band 60-80 %. Band edge = 60 % x 300,000 = 180,000.0 MWh.
    Legs: +180,000.0 (band edge) - 126,000.0 (cover held) = 54,000.0 MWh below the band.
    Sensitivity: 1 percentage point = 3,000.0 MWh; breakeven cover 180,000.0 MWh.
    """

    row = book_row(
        "norsk-2027",
        "2027-01",
        contract_mwh="300000",
        hedged_mwh="126000",
        band_low_pct="60",
        band_high_pct="80",
        as_of=AS_OF,
        contract_name="Norsk-2027",
        approval_ref="RC-12",
        approved_by="risk committee",
        valid_until="2027-09-30",
    )
    ((candidate, assessment),) = run(HEDGE_GAP, fixture_snapshot([row], as_of=AS_OF), as_of=AS_OF)
    assert_legs(
        candidate, [("hedge_gap.band_edge", "180000.0"), ("hedge_gap.cover_held", "-126000.0")]
    )
    assert_reconciles(candidate)
    assert candidate.headline == Measure(D("54000.0"), "MWh")
    assert candidate.value is None  # no margin is claimed
    assert candidate.lane is Lane.MUST_ACT and candidate.quality is InputClass.SOURCED
    assert assessment.state is OpportunityState.ACTIONABLE
    assert assessment.claim_text == (
        "Norsk-2027 · Jan-27: cover 42 % against an approved band of 60–80 %; "
        "54,000 MWh below the band edge. Band approved by risk committee (ref RC-12)."
    )
    assert [s.value.value for s in candidate.sensitivity] == [D("3000.0"), D("180000.0")]
    assert candidate.deadline_utc == datetime(2027, 1, 1, 5, tzinfo=UTC)
    assert candidate.expires_at_utc == datetime(2027, 2, 1, 5, tzinfo=UTC)
    assert candidate.dependency_keys == ("contract:norsk-2027",)
    assert candidate.book_ids == ("book-1",)
    assert wording_violations(assessment.claim_text) == []


def test_golden_hedge_gap_above_band_and_inside_band() -> None:
    """Above: volume 200,000 MWh, cover 170,000 MWh (85 %), band 60-80 %.

    Band edge 80 % x 200,000 = 160,000.0; legs +170,000.0 (cover) - 160,000.0 (edge) =
    10,000.0 MWh above. Inside: cover 140,000 MWh (70 %) -> no candidate.
    """

    above = book_row(
        "c-above",
        "2027-02",
        contract_mwh="200000",
        hedged_mwh="170000",
        band_low_pct="60",
        band_high_pct="80",
        as_of=AS_OF,
    )
    inside = book_row(
        "c-inside",
        "2027-02",
        contract_mwh="200000",
        hedged_mwh="140000",
        band_low_pct="60",
        band_high_pct="80",
        as_of=AS_OF,
    )
    outcome = run(HEDGE_GAP, fixture_snapshot([above, inside], as_of=AS_OF), as_of=AS_OF)
    assert len(outcome) == 1
    candidate, _ = outcome[0]
    assert_legs(
        candidate, [("hedge_gap.cover_held", "170000.0"), ("hedge_gap.band_edge", "-160000.0")]
    )
    assert candidate.headline.value == D("10000.0")
    assert candidate.claim_key == "hedge_gap.above_band"


def test_golden_hedge_gap_on_a_sale_contract() -> None:
    """A sale: volume -310,000 MWh, buy hedges +93,000 MWh -> hedged -93,000 as reported.

    Cover = 93,000 (offsetting), 30 %; band at least 50 %: edge 155,000.0;
    gap 155,000.0 - 93,000.0 = 62,000.0 MWh below.
    """

    row = book_row(
        "sale-1",
        "2027-03",
        contract_mwh="-310000",
        hedged_mwh="-93000",
        band_low_pct="50",
        band_high_pct=None,
        as_of=AS_OF,
    )
    ((candidate, _),) = run(HEDGE_GAP, fixture_snapshot([row], as_of=AS_OF), as_of=AS_OF)
    assert candidate.headline.value == D("62000.0")
    assert candidate.claim_fields["band"] == "at least 50 %"


def test_a_demo_book_is_marked_simulated_and_capped() -> None:
    row = book_row(
        "demo-c",
        "2027-01",
        contract_mwh="100000",
        hedged_mwh="0",
        band_low_pct="60",
        band_high_pct="80",
        as_of=AS_OF,
        input_class=InputClass.SIMULATED,
    )
    snapshot = fixture_snapshot([row], as_of=AS_OF, demo_desk=True)
    ((candidate, assessment),) = run(HEDGE_GAP, snapshot, as_of=AS_OF)
    assert candidate.simulated and assessment.state is OpportunityState.INDICATIVE
    real = run(HEDGE_GAP, fixture_snapshot([row], as_of=AS_OF), as_of=AS_OF, demo_desk=False)
    assert real[0][1].state is None  # a real desk never produces it


# ------------------------------------------------------- a synthetic margin evaluator


SELL = price_key("THE", JAN27, "bid")
BUY = price_key("TTF", JAN27, "ask")
EXIT = tariff_key("ITP-00005", "EXIT", "MONTHLY", JAN27)
ENTRY = tariff_key("ITP-00005", "ENTRY", "MONTHLY", JAN27)


def _price(key: str, value: str, klass=InputClass.SOURCED, as_of=AS_OF) -> SnapshotInput:
    hub = key.split(":")[1]
    return SnapshotInput(
        key,
        InputKind.PRICE,
        klass,
        D(value),
        "EUR/MWh",
        "EUR",
        as_of,
        "ICE_ENDEX" if klass is InputClass.SOURCED else "operator-input",
        f"ref-{hub}",
        f"{hub} Jan-27",
    )


def _tariff(key: str, value: str) -> SnapshotInput:
    return SnapshotInput(
        key,
        InputKind.TARIFF,
        InputClass.SOURCED,
        D(value),
        "EUR/(kWh/h)/d",
        "EUR",
        AS_OF,
        "ENTSOG",
        f"t-{key}",
        "Oude Statenzijl",
        {"point_id": "ITP-00005"},
    )


class SpreadEvaluator:
    """Design B.4: sell THE 31.20, buy TTF 30.00, exit 0.0101 and entry 0.0132 EUR/(kWh/h)/d.

    Tariff per MWh at full load = rate / 24 x 1000, rounded to 3 dp: exit 0.421, entry 0.550.
    Net = 31.20 - 30.00 - 0.421 - 0.550 = 0.229 EUR/MWh; volume 10,000 MWh/d x 31 d =
    310,000 MWh; value = 0.229 x 310,000 = EUR 70,990. Route cost 0.971 EUR/MWh.
    """

    name = "harness_spread"
    version = "1"
    type = OpportunityType.LOCATIONAL

    def __init__(
        self, mwh_per_day: int = 10_000, checks=(), half_spread=None, fx_tol=None, internal=False
    ):
        self.mwh_per_day = mwh_per_day
        self.checks = checks
        self.half_spread = half_spread
        self.fx_tol = fx_tol
        self.internal = internal

    def evaluate(self, snapshot, context):
        sell = snapshot.price("THE", JAN27, "bid")
        buy = snapshot.price("TTF", JAN27, "ask")
        exit_ = snapshot.tariff("ITP-00005", "EXIT", "MONTHLY", JAN27)
        entry = snapshot.tariff("ITP-00005", "ENTRY", "MONTHLY", JAN27)
        inputs = (sell, buy, exit_, entry)
        volume = D(self.mwh_per_day * JAN27.days)
        held = all(item.held for item in inputs)
        unit = "EUR/MWh"

        def per_mwh(item):
            return (item.value / 24 * 1000).quantize(D("0.001")) if item.held else D(0)

        terms = [
            ("spread.sell", sell.value if sell.held else D(0)),
            ("spread.buy", -(buy.value if buy.held else D(0))),
            ("spread.exit", -per_mwh(exit_)),
            ("spread.entry", -per_mwh(entry)),
        ]
        net = sum((value for _k, value in terms), D(0))
        legs = [
            Leg(LegKind.TERM, key, key, contribution=Measure(value, unit)) for key, value in terms
        ]
        legs.append(Leg(LegKind.RESULT, "spread.net", "Net", subtotal=Measure(net, unit)))
        value = (net * volume).quantize(D("1"))
        legs += [
            Leg(LegKind.VOLUME, "spread.volume", "Volume", quantity=Measure(volume, "MWh")),
            Leg(LegKind.VALUE, "spread.value", "Value", quantity=Measure(value, "EUR")),
        ]
        yield Candidate(
            type=self.type,
            identity=("TTF", "THE", "ITP-00005"),
            period=JAN27,
            book_ids=("book-1",),
            claim_key="harness.spread",
            claim_fields={
                "sell_hub": "THE",
                "buy_hub": "TTF",
                "period": "Jan-27",
                "volume": f"{self.mwh_per_day:,} MWh/d",
                "margin": f"{net} EUR/MWh",
                "value": f"EUR {value:,}",
            },
            headline=Measure(net, unit),
            volume=Measure(volume, "MWh"),
            value=Measure(value, "EUR"),
            value_eur=Measure(value, "EUR") if held else None,
            margin_eur=Measure(net, unit) if held else None,
            route_cost_eur=Measure(per_mwh(exit_) + per_mwh(entry), unit),
            half_spread_eur=self.half_spread,
            fx_tolerance_eur=self.fx_tol,
            legs=tuple(legs),
            falsifiers=(Falsifier("spread.below_breakeven", "THE-TTF spread below 0.971"),),
            checks=self.checks,
            expires_at_utc=datetime(2027, 1, 1, 5, tzinfo=UTC),
            inputs=inputs,
            evaluator=self.name,
            evaluator_version=self.version,
            internal_inputs=self.internal,
        )


def _base(**overrides):
    inputs = {
        SELL: _price(SELL, "31.20"),
        BUY: _price(BUY, "30.00"),
        EXIT: _tariff(EXIT, "0.0101"),
        ENTRY: _tariff(ENTRY, "0.0132"),
    }
    inputs.update(overrides)
    return [item for item in inputs.values() if item is not None]


def _assess(evaluator=None, inputs=None, thresholds=None, demo=False, as_of=AS_OF):
    snapshot = fixture_snapshot(
        inputs if inputs is not None else _base(), as_of=as_of, demo_desk=demo
    )
    return run(evaluator or SpreadEvaluator(), snapshot, as_of=as_of, thresholds=thresholds)[0]


def test_golden_spread_is_actionable_when_every_input_is_sourced() -> None:
    candidate, assessment = _assess()
    assert_legs(
        candidate,
        [
            ("spread.sell", "31.20"),
            ("spread.buy", "-30.00"),
            ("spread.exit", "-0.421"),
            ("spread.entry", "-0.550"),
        ],
    )
    assert candidate.headline.value == D("0.229")
    assert candidate.value == Measure(D("70990"), "EUR")
    assert assessment.state is OpportunityState.ACTIONABLE, assessment.reasons


def test_control_minimum_margin_after_costs() -> None:
    _c, below = _assess(inputs=_base(**{SELL: _price(SELL, "31.05")}))  # net 0.079
    assert below.state is OpportunityState.WATCH and "margin_below_minimum" in below.reasons
    raised = thresholds_from({"min_margin": "0.25"})
    assert _assess(thresholds=raised)[1].state is OpportunityState.WATCH
    # Half bid-offer of both legs above the margin.
    wide = SpreadEvaluator(half_spread=Measure(D("0.30"), "EUR/MWh"))
    assert _assess(evaluator=wide)[1].state is OpportunityState.WATCH
    # 10 % of total route cost: 0.0971 < 0.229 passes; at 30 % (0.2913) it does not.
    assert _assess(thresholds=thresholds_from({"route_cost_share": "0.3"}))[1].state is (
        OpportunityState.WATCH
    )


def test_control_minimum_value() -> None:
    _c, small = _assess(evaluator=SpreadEvaluator(mwh_per_day=1_000))  # EUR 7,099
    assert small.state is OpportunityState.WATCH and "value_below_minimum" in small.reasons


def test_control_fx_tolerance_and_unassessed_check() -> None:
    tol = SpreadEvaluator(fx_tol=Measure(D("0.30"), "EUR/MWh"))
    assert "margin_within_fx_tolerance" in _assess(evaluator=tol)[1].reasons
    unassessed = SpreadEvaluator(checks=(Check(CheckKind.CAPACITY, CheckResult.NOT_ASSESSED, "-"),))
    assert _assess(evaluator=unassessed)[1].state is OpportunityState.WATCH


def test_control_stale_input_is_refused() -> None:
    old = AS_OF - timedelta(days=4)  # Friday before: 2 business days
    _c, stale = _assess(inputs=_base(**{SELL: _price(SELL, "31.20", as_of=old)}))
    assert stale.state is OpportunityState.BLOCKED and stale.blocker.code == "input_stale"
    friday_ok = AS_OF - timedelta(days=1)
    assert _assess(inputs=_base(**{SELL: _price(SELL, "31.20", as_of=friday_ok)}))[1].state is (
        OpportunityState.ACTIONABLE
    )


def test_control_firm_marks_settlements_and_assumptions_cap_at_indicative() -> None:
    marked = _base(**{SELL: _price(SELL, "31.20", InputClass.FIRM_MARK)})
    _c, capped = _assess(inputs=marked)
    assert capped.state is OpportunityState.INDICATIVE and "input_class_firm_mark" in capped.reasons
    accepted = thresholds_from({"marks_actionable": True})
    assert _assess(inputs=marked, thresholds=accepted)[1].state is OpportunityState.ACTIONABLE
    settled = _base(**{BUY: _price(BUY, "30.00", InputClass.INDICATIVE)})
    assert _assess(inputs=settled, thresholds=accepted)[1].state is OpportunityState.INDICATIVE


def test_control_simulated_never_mixes_with_real() -> None:
    demo_price = _base(**{SELL: _price(SELL, "31.20", InputClass.SIMULATED)})
    candidate, refused = _assess(inputs=demo_price, demo=False)
    assert refused.state is None and candidate.simulated
    _c, demo = _assess(inputs=demo_price, demo=True)
    assert demo.state is OpportunityState.INDICATIVE and "input_class_simulated" in demo.reasons


def test_control_incomplete_tariff_legs_name_the_missing_tariff() -> None:
    inputs = _base()
    inputs = [item for item in inputs if item.key != EXIT]
    candidate, blocked = _assess(inputs=inputs)
    assert blocked.state is OpportunityState.BLOCKED
    assert blocked.blocker.code == "tariff_not_held"
    assert blocked.claim_text == (
        "Cannot evaluate: tariff not held at ITP-00005 (exit, gas year 2026/27)."
    )
    assert "entsog-tariffs" in blocked.blocker.fix
    no_price = [item for item in _base() if item.key != BUY]
    assert _assess(inputs=no_price)[1].blocker.code == "price_missing"


def test_control_failed_check_and_insider_wall() -> None:
    failed = SpreadEvaluator(checks=(Check(CheckKind.OUTAGE, CheckResult.FAIL, "path cut"),))
    assert _assess(evaluator=failed)[1].state is OpportunityState.BLOCKED
    internal = SpreadEvaluator(internal=True)
    assert _assess(evaluator=internal)[1].state is None


def test_thresholds_are_bounded() -> None:
    assert Thresholds().min_value == Measure(D("10000"), "EUR")
    assert Thresholds().max_per_lane == 7 and Thresholds().persistence == 2
    for bad in (
        {"min_margin": -1},
        {"max_per_lane": 0},
        {"persistence": 1.5},
        {"nope": 1},
        {"marks_actionable": "yes"},
    ):
        with pytest.raises(ThresholdError):
            thresholds_from(bad)


# ------------------------------------------------------------- reconciliation property


def _random_candidate(rng: random.Random) -> Candidate:
    unit = rng.choice(["EUR/MWh", "MWh", "GBP/MWh"])
    terms = [
        D(rng.randint(-(10**7), 10**7)) / D(10 ** rng.randint(0, 4))
        for _ in range(rng.randint(1, 8))
    ]
    legs, running = [], D(0)
    for index, value in enumerate(terms):
        running += value
        legs.append(Leg(LegKind.TERM, f"t{index}", "t", contribution=Measure(value, unit)))
        if rng.random() < 0.3:
            legs.append(Leg(LegKind.SUBTOTAL, f"s{index}", "s", subtotal=Measure(running, unit)))
        if rng.random() < 0.2:
            legs.append(
                Leg(LegKind.CONVERSION, f"c{index}", "fx", fx=Measure(D("0.87"), "GBP/EUR"))
            )
    legs.append(Leg(LegKind.RESULT, "r", "r", subtotal=Measure(running, unit)))
    return Candidate(
        type=OpportunityType.LOCATIONAL,
        identity=("x",),
        period=JAN27,
        book_ids=(),
        claim_key="blocked.evaluator",
        claim_fields={"subject": "x"},
        headline=Measure(running, unit),
        legs=tuple(legs),
        falsifiers=(Falsifier("f", "f"),),
        expires_at_utc=AS_OF + timedelta(days=1),
        inputs=(_price(SELL, "1"),),
        evaluator="prop",
        evaluator_version="1",
    )


def test_reconciliation_property_over_generated_and_produced_objects() -> None:
    rng = random.Random(20261117)
    for _ in range(500):
        candidate = _random_candidate(rng)
        reconcile(candidate)
        broken = replace(
            candidate,
            headline=Measure(candidate.headline.value + D("0.001"), candidate.headline.unit),
        )
        with pytest.raises(ReconciliationError):
            reconcile(broken)
    # Every object the reference evaluator produces over random books reconciles too.
    rows = []
    for index in range(300):
        volume = rng.randint(1_000, 2_000_000) * rng.choice([1, -1])
        hedged = int(volume * rng.uniform(-0.2, 1.3))
        low = rng.choice([None, "40", "60", "75"])
        high = rng.choice([None, "80", "95"]) if low else "80"
        rows.append(
            book_row(
                f"c{index}",
                "2027-01",
                contract_mwh=str(volume),
                hedged_mwh=str(hedged),
                band_low_pct=low,
                band_high_pct=high,
                as_of=AS_OF,
            )
        )
    produced = run(HEDGE_GAP, fixture_snapshot(rows, as_of=AS_OF), as_of=AS_OF)
    assert produced
    for candidate, _ in produced:
        assert_reconciles(candidate)
        assert candidate.headline.value > 0


def test_the_contract_check_refuses_a_defective_candidate() -> None:
    candidate, _ = _assess()
    context = EvaluationContext(AS_OF, Thresholds(), False)
    validate_candidate(candidate, context)
    with pytest.raises(ContractBreach):
        validate_candidate(replace(candidate, falsifiers=()), context)
    with pytest.raises(ContractBreach):
        validate_candidate(replace(candidate, value=Measure(D("71000"), "EUR")), context)
    with pytest.raises(ContractBreach):
        validate_candidate(replace(candidate, expires_at_utc=AS_OF), context)
    assert HEDGE_GAP in registered()


# ------------------------------------------------------------------------ lifecycle


def test_persistence_and_hysteresis() -> None:
    t = Thresholds()
    first, changed = seen(None, OpportunityState.ACTIONABLE, D("100"), t)
    assert first.state is OpportunityState.NEW and not first.surfaced and changed
    second, _ = seen(first, OpportunityState.ACTIONABLE, D("100"), t)
    assert second.state is OpportunityState.ACTIONABLE and second.surfaced
    once = missed(second, t)
    assert once.state is OpportunityState.ACTIONABLE and once.consecutive_missed == 1
    back, _ = seen(once, OpportunityState.ACTIONABLE, D("100"), t)
    assert back.consecutive_missed == 0
    gone = missed(missed(back, t), t)
    assert gone.state is OpportunityState.EXPIRED and gone.ended_reason == "no_longer_found"
    never_shown = missed(first, t)
    assert never_shown.state is OpportunityState.EXPIRED
    single = thresholds_from({"persistence": 1})
    assert seen(None, OpportunityState.WATCH, None, single)[0].state is OpportunityState.WATCH


def test_material_change_makes_a_new_version() -> None:
    t = Thresholds()
    shown, _ = seen(
        seen(None, OpportunityState.ACTIONABLE, D("100"), t)[0],
        OpportunityState.ACTIONABLE,
        D("100"),
        t,
    )
    small, changed = seen(shown, OpportunityState.ACTIONABLE, D("110"), t)
    assert not changed and small.version == shown.version and small.value == D("100")
    big, changed = seen(shown, OpportunityState.ACTIONABLE, D("125"), t)
    assert changed and big.version == shown.version + 1
    state, changed = seen(shown, OpportunityState.WATCH, D("100"), t)
    assert changed and state.state is OpportunityState.WATCH


def test_expiry_and_conversion_are_final() -> None:
    t = Thresholds()
    shown, _ = seen(
        seen(None, OpportunityState.ACTIONABLE, D("1"), t)[0],
        OpportunityState.ACTIONABLE,
        D("1"),
        t,
    )
    expired = expire_if_due(shown, AS_OF, AS_OF)
    assert expired.state is OpportunityState.EXPIRED and expired.ended_reason == "validity_ended"
    assert expire_if_due(shown, AS_OF + timedelta(hours=1), AS_OF) is shown
    converted = replace(shown, state=OpportunityState.CONVERTED)
    assert seen(converted, OpportunityState.ACTIONABLE, D("9"), t)[0] is converted
    with pytest.raises(TransitionError):
        check_transition(OpportunityState.CONVERTED, OpportunityState.ACTIONABLE)
    with pytest.raises(TransitionError):
        check_transition(OpportunityState.EXPIRED, OpportunityState.ACTIONABLE)


# --------------------------------------------------------------------------- ranking


def _rank_input(
    oid,
    lane,
    value=None,
    quality=InputClass.SOURCED,
    simulated=False,
    seen_n=2,
    deadline=None,
    size=ZERO,
    expires=AS_OF + timedelta(days=9),
):
    return RankInput(
        oid,
        lane,
        quality,
        simulated,
        seen_n,
        expires,
        deadline,
        None if value is None else D(value),
        size,
        "MWh",
    )


def test_could_act_ranking_by_score_and_reason() -> None:
    rows = [
        _rank_input("a", Lane.COULD_ACT, "71000"),
        _rank_input("b", Lane.COULD_ACT, "100000", quality=InputClass.ASSUMPTION),  # 40,000
        _rank_input("c", Lane.COULD_ACT, "90000", quality=InputClass.INDICATIVE),  # 54,000
        _rank_input("d", Lane.COULD_ACT, "500000", simulated=True),
    ]
    ranked = rank(rows, AS_OF)
    assert [r.opportunity_id for r in ranked] == ["a", "c", "b", "d"]
    assert ranked[0].reason == "ranked 1st: EUR 71k, all inputs sourced, expires in 9 d"
    assert "weakest input: assumption" in ranked[2].reason
    assert "simulated inputs" in ranked[3].reason


def test_must_act_ranking_by_deadline_then_size() -> None:
    soon = AS_OF + timedelta(days=3)
    later = AS_OF + timedelta(days=30)
    rows = [
        _rank_input("late", Lane.MUST_ACT, deadline=later, size=D("90000")),
        _rank_input("small", Lane.MUST_ACT, deadline=soon, size=D("1000")),
        _rank_input("big", Lane.MUST_ACT, deadline=soon, size=D("54000")),
    ]
    ranked = rank(rows, AS_OF)
    assert [r.opportunity_id for r in ranked] == ["big", "small", "late"]
    assert ranked[0].reason.startswith("ranked 1st: due in 3 d, 54,000 MWh")
    with pytest.raises(ValueError):
        rank([rows[0], _rank_input("x", Lane.COULD_ACT, "1")], AS_OF)


# ---------------------------------------------------------------------------- claims


def test_every_claim_template_is_a_statement_not_advice() -> None:
    for key in CLAIM_TEMPLATES:
        text = render_claim(key, {name: "X" for name in template_fields(key)})
        assert wording_violations(text) == [], (key, text)
    assert wording_violations("You should buy now") == ["you should", "buy now"]
    assert grouped(D("-0.2")) == "0" and grouped(D("54000")) == "54,000"
    with pytest.raises(ClaimError):
        render_claim("hedge_gap.below_band", {"contract": "x"})
    with pytest.raises(ClaimError):
        render_claim("nope", {})
