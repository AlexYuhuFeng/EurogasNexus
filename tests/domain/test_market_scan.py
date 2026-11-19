"""The market scan (lane "in the market, not on your book"): P at one hub, its threshold,
its lane and what it says the firm would need."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

from eurogas_nexus.domain.opportunities.market_scan import PROMPT_MIN_EDGE, MarketScanEvaluator
from eurogas_nexus.domain.opportunities.model import Lane, OpportunityType
from eurogas_nexus.domain.opportunities.testing import assert_reconciles, fixture_snapshot, run
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.domain.valuation.snapshot import InputKind, SnapshotInput, price_key

AS_OF = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)
TODAY = date(2026, 11, 27)


def _price(hub, period, side, value):
    return SnapshotInput(
        key=price_key(hub, period, side),
        kind=InputKind.PRICE,
        input_class=InputClass.SIMULATED,
        value=D(value),
        unit="EUR/MWh",
        currency="EUR",
        as_of_utc=AS_OF - timedelta(minutes=5),
        source_family="DEMO",
        source_ref="demo",
        label=f"{hub} {period.label}",
        detail={"basis": "settlement"},
    )


def _scan(wd_gap: str):
    wd, da = DeliveryPeriod.gas_day(TODAY), DeliveryPeriod.gas_day(TODAY + timedelta(days=1))
    inputs = [
        _price("TTF", wd, "bid", D("40.00") + D(wd_gap)),
        _price("TTF", wd, "ask", D("40.00") + D(wd_gap)),
        _price("TTF", da, "bid", "40.00"),
        _price("TTF", da, "ask", "40.00"),
    ]
    snapshot = fixture_snapshot(inputs, as_of=AS_OF, demo_desk=True)
    return [c for c, _a in run(MarketScanEvaluator(), snapshot, as_of=AS_OF)]


def test_prompt_spread_at_one_hub_is_a_market_item() -> None:
    (candidate,) = [c for c in _scan("1.50") if c.type is OpportunityType.PROMPT_ARBITRAGE]
    assert_reconciles(candidate)
    assert candidate.lane is Lane.MARKET and candidate.book_ids == ()
    assert candidate.headline.value == D("1.5") and candidate.value.value == D("15000.00")
    assert (
        candidate.claim_fields["sell"] == "within-day"
        and candidate.claim_fields["basis"] == "closes"
    )
    assert "credit line" in candidate.claim_fields["needs"]


def test_a_prompt_edge_within_the_normal_shape_is_not_an_item() -> None:
    assert D("0.25") < PROMPT_MIN_EDGE
    assert not [c for c in _scan("0.25") if c.type is OpportunityType.PROMPT_ARBITRAGE]
